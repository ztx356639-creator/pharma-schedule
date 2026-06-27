#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
药厂多部门排班脚手架 v2。
支持：QA独立部门、多时段任务、依赖约束、10类风险检测。
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.common import (
    DEPARTMENTS, DEFAULT_ORDER, WEEKDAY_CN, ProjectInfo, TaskItem, Personnel,
    Instrument, Reagent, ResourcePool, SchedulingEngine,
    is_workday, add_workdays, subtract_workdays, workdays_between,
    reverse_schedule, detect_all_risks,
)

# ============================================================
# 资源池排程
# ============================================================

def run_resource_pool_schedule(proj, schedule, personnel_raw, instruments_raw,
                               test_items, reagents_raw=None):
    start = dt.date.fromisoformat(proj.start_date)
    end = dt.date.fromisoformat(proj.deadline)
    pool = ResourcePool(start, end)
    
    for p in personnel_raw:
        pool.register_person(
            name=p["name"], department=p.get("department", ""),
            level=p.get("level", ""), skills=p.get("skills", ""),
            note=p.get("note", ""), available_from=p.get("available_from", ""),
            available_until=p.get("available_until", ""),
        )
    
    for i in instruments_raw:
        pool.register_instrument(
            name=i["name"], model=i.get("model", ""), location=i.get("location", ""),
            cal_due=i.get("cal_due", ""), status=i.get("status", "正常"),
            shared=i.get("shared", False), qty=i.get("qty", 1),
            switch_buffer_min=i.get("switch_buffer_min", 30),
        )
    
    for r in (reagents_raw or []):
        pool.register_reagent(
            name=r["name"], category=r.get("category", ""),
            expiry=r.get("expiry", ""), quantity=r.get("quantity", ""),
            min_quantity=r.get("min_quantity", ""),
        )
    
    tasks = []
    for t in test_items:
        dept_id = t.get("department", "")
        dept_schedule = schedule.get(dept_id, {})
        earliest = dept_schedule.get("start", start)
        if isinstance(earliest, dt.date):
            earliest_str = earliest.isoformat()
        else:
            earliest_str = str(earliest)
        
        inst_str = t.get("instruments", t.get("instrument", ""))
        inst_list = [x.strip() for x in inst_str.split(",") if x.strip() and x.strip() != "-"]
        
        dur_str = t.get("duration", "4h")
        try:
            if "天" in dur_str:
                dur_hours = float(dur_str.replace("天", "").strip()) * 8
            elif "h" in dur_str:
                dur_hours = float(dur_str.replace("h", "").strip())
            else:
                dur_hours = 4
        except ValueError:
            dur_hours = 4
        
        tasks.append({
            "name": t.get("name", ""), "department": dept_id,
            "assignee": t.get("assignee", ""), "instruments": inst_list,
            "duration_hours": dur_hours, "priority": t.get("priority", "普通"),
            "depends_on": t.get("depends_on", ""), "earliest_start": earliest_str,
            "required_skills": t.get("required_skills", ""),
        })
    
    engine = SchedulingEngine(pool)
    result = engine.auto_schedule(tasks)
    gantt = engine.generate_gantt_data()
    
    # 风险检测
    all_risks = detect_all_risks(proj, schedule, personnel_raw, instruments_raw,
                                 test_items, reagents_raw or [], pool)
    
    return pool, result, gantt, all_risks

# ============================================================
# 模板生成
# ============================================================

def gen_readme(proj, schedule, risks, pool_result=None):
    lines = [
        f"# {proj.project_name} — 多部门排班总览\n",
        f"> 生成日期: {dt.date.today().isoformat()}\n",
        "## 项目信息\n",
        "| 字段 | 内容 |", "|------|------|",
        f"| 药品名称 | {proj.drug_name} |",
        f"| 批号 | {proj.batch_no} |",
        f"| 批量 | {proj.batch_size} |",
        f"| 项目类型 | {proj.batch_type} |",
        f"| 质量标准 | {proj.standard} |",
        f"| 项目启动 | {proj.start_date} |",
        f"| 交货截止 | {proj.deadline} |",
        f"| 特殊要求 | {proj.special or '无'} |",
        f"| 参与部门 | {', '.join(DEPARTMENTS.get(d,{}).get('name',d) for d in proj.departments)} |",
        "", "## 项目时间线（反向推导）\n",
        "| 阶段 | 部门 | 开始 | 截止 | 工作日 | 前置 | 缓冲 | 状态 |",
        "|------|------|------|------|--------|------|------|------|",
    ]
    for dept_id in proj.departments:
        dept = DEPARTMENTS.get(dept_id, {})
        s = schedule.get(dept_id, {})
        if not s:
            continue
        start_val, end_val, dur = s.get("start", "—"), s.get("end", "—"), s.get("duration_workdays", "—")
        deps = dept.get("depends_on", [])
        dep_names = [DEPARTMENTS.get(d, {}).get("name", d) for d in deps] if deps else ["—"]
        total = workdays_between(s["start"], s["end"]) if "start" in s and "end" in s else 0
        buffer = total - dur if isinstance(dur, int) else 0
        buffer_str = f"{buffer}天" if buffer >= 0 else f"🔴 {buffer}天"
        lines.append(
            f"| {dept.get('name', dept_id)} | {dept.get('icon','')} "
            f"| {start_val.isoformat() if isinstance(start_val, dt.date) else start_val} "
            f"| {end_val.isoformat() if isinstance(end_val, dt.date) else end_val} "
            f"| {dur} | {', '.join(dep_names)} | {buffer_str} | ⬜ |"
        )
    lines.extend(["", "## 关键路径\n", "```"])
    lines.append(" → ".join(DEPARTMENTS.get(d, {}).get("name", d) for d in proj.departments if d in proj.departments))
    lines.append("```\n")
    
    if pool_result:
        lines.extend(["## 资源池排程结果\n"])
        lines.append(f"- ✅ 已分配任务: {pool_result['assigned']} 项")
        lines.append(f"- ❌ 未分配任务: {pool_result['unassigned']} 项")
        if pool_result.get("conflicts"):
            lines.append(f"- ⚠️ 冲突: {len(pool_result['conflicts'])} 个")
        lines.append("")
    
    if risks:
        high = [r for r in risks if r.get("level") == "高"]
        med = [r for r in risks if r.get("level") == "中"]
        lines.extend([f"## ⚠️ 风险预警（{len(high)}项高 / {len(med)}项中）\n"])
        for r in risks:
            lines.append(f"- {r['message']}")
        lines.append("")
    
    lines.extend([
        "## 文件导航\n",
        "- [项目信息.md](项目信息.md) — 基础信息",
        "- [依赖关系.md](依赖关系.md) — 部门间依赖+关键路径",
        "- [关键时间节点.md](关键时间节点.md) — 各部门起止时间详情",
    ])
    for dept_id in proj.departments:
        dept = DEPARTMENTS.get(dept_id, {})
        lines.append(f"- [部门排班/{dept.get('name', dept_id)}排班.md](部门排班/{dept.get('name', dept_id)}排班.md)")
    lines.extend([
        "- [资源池总览.md](资源池总览.md) — 人员+仪器资源池视图",
        "- [甘特图排程.md](甘特图排程.md) — 自动排程结果",
        "- [风险看板.md](风险看板.md) — 10类风险汇总",
        "", "---", "*pharma-schedule v2 自动生成*",
    ])
    return "\n".join(lines)


def gen_dependency_map(proj):
    lines = [
        f"# {proj.project_name} — 依赖关系\n",
        "## 流程依赖图\n", "```",
        "采购下单 → 原料到货 → QC来料检验 → 车间生产 → QC成品检验 → QA放行 → 销售发货",
        "    │                                            │                      │",
        "    └── 包材采购 ───────────────────────────────┘                      │",
        "    └── 试剂/标准品/耗材 → QC用                                       │",
        "                                            客户签收 ←────────────────┘",
        "```\n", "## 依赖明细\n",
        "| 上游 | 交付物 | 下游 | 接收条件 |",
        "|------|--------|------|----------|",
    ]
    deps = [
        ("采购部", "原辅料到货", "QC来料", "到货验收单+供应商COA"),
        ("采购部", "包材到货", "车间", "到货验收单"),
        ("采购部", "试剂/标准品到货", "QC来料/QC成品", "入库验收单"),
        ("QC来料", "原料放行报告", "车间", "检验合格+放行"),
        ("车间", "成品完工+请验单", "QC成品", "生产记录完整+取样"),
        ("QC成品", "成品检验报告", "QA放行", "全项合格"),
        ("QA放行", "放行签字", "销售", "QA放行签字+批记录"),
        ("销售", "客户签收", "全项目", "签收单+回款"),
    ]
    for u, d, ds, c in deps:
        lines.append(f"| {u} | {d} | {ds} | {c} |")
    lines.extend(["", "## 关键约束\n",
        "1. **原料未放行，车间不得投料** — GMP 强制",
        "2. **成品未放行，销售不得发货** — GMP 强制",
        "3. **QA独立于生产和销售** — GMP 要求质量部门独立",
        "4. **微生物培养5天/无菌14天** — 刚性周期，不可压缩",
        "5. **仪器共享需错峰** — 同一仪器同一时段只能1人用",
        "6. **HPLC方法切换需30min** — 平衡/冲洗时间",
        "7. **OOS调查预留3天** — 检验超标需调查",
    ])
    return "\n".join(lines)


def gen_dept_schedule(proj, dept_id, schedule, personnel, instruments, test_items, pool=None):
    dept = DEPARTMENTS.get(dept_id, {})
    s = schedule.get(dept_id, {})
    if not s:
        return f"# {proj.project_name} — {dept.get('name', dept_id)}排班\n\n（未参与本次排班）\n"
    start, end = s.get("start"), s.get("end")
    dept_personnel = [p for p in personnel if p.get("department") == dept_id]
    dept_instruments = [i for i in instruments if i.get("location") == dept_id or i.get("shared")]
    dept_tasks = [t for t in test_items if t.get("department") == dept_id]
    
    lines = [
        f"# {proj.project_name} — {dept.get('name', dept_id)}排班\n",
        f"> 部门: {dept.get('icon','')} {dept.get('name', dept_id)}",
        f"> 排班周期: {start.isoformat() if isinstance(start, dt.date) else start} ~ {end.isoformat() if isinstance(end, dt.date) else end}",
        f"> 前置依赖: {', '.join(DEPARTMENTS.get(d,{}).get('name',d) for d in dept.get('depends_on',[])) or '无'}\n",
    ]
    lines.extend([
        "## 任务清单\n",
        "| 序号 | 任务 | 负责人 | 仪器 | 耗时 | 优先级 | 分配日期 | 时段 | 状态 |",
        "|------|------|--------|------|------|--------|----------|------|------|",
    ])
    if dept_tasks:
        for i, t in enumerate(dept_tasks, 1):
            inst = t.get("instruments", t.get("instrument", "-"))
            alloc_date, alloc_period = "待排", "—"
            if pool:
                for key, slot in pool.slots.items():
                    if slot.task_name == t.get("name", "") and slot.resource_type == "person":
                        alloc_date = slot.date.strftime("%m-%d")
                        alloc_period = slot.period
                        break
            lines.append(f"| {i} | {t.get('name','-')} | {t.get('assignee','待填')} | {inst} | {t.get('duration','-')} | {t.get('priority','普通')} | {alloc_date} | {alloc_period} | ⬜ |")
    else:
        for i, t in enumerate(dept.get("typical_tasks", []), 1):
            lines.append(f"| {i} | {t['name']} | 待填 | — | {t['duration']} | 普通 | 待排 | — | ⬜ |")
    
    if dept_personnel:
        lines.extend(["\n## 人员排班\n"])
        for p in dept_personnel:
            lines.append(f"\n### {p['name']}（{p.get('level', '-')}）\n")
            lines.append(f"> 擅长: {p.get('skills', '-')} | 备注: {p.get('note', '-')}\n")
            lines.append("| 日期 | 星期 | 上午(8:00-12:00) | 下午(13:00-17:00) | 使用仪器 | 状态 |")
            lines.append("|------|------|-----------------|------------------|----------|------|")
            if isinstance(start, dt.date) and isinstance(end, dt.date):
                cur = start
                while cur <= end:
                    if is_workday(cur):
                        wd = WEEKDAY_CN[cur.weekday()]
                        am_task, pm_task, am_inst = "空闲", "空闲", "—"
                        if pool:
                            am_key = (p["name"], cur, "上午")
                            pm_key = (p["name"], cur, "下午")
                            if am_key in pool.slots:
                                am_task = pool.slots[am_key].task_name or "已排"
                                am_inst = ", ".join(
                                    s.resource_name for s in pool.slots.values()
                                    if s.date == cur and s.period == "上午"
                                    and s.resource_type == "instrument"
                                    and s.task_name == am_task
                                ) or "—"
                            if pm_key in pool.slots:
                                pm_task = pool.slots[pm_key].task_name or "已排"
                        lines.append(f"| {cur.strftime('%m-%d')} | {wd} | {am_task} | {pm_task} | {am_inst} | ⬜ |")
                    cur += dt.timedelta(days=1)
    else:
        lines.extend(["\n## 人员排班\n", "（待补充人员信息）\n"])
    return "\n".join(lines)


def gen_resource_pool_overview(proj, pool, engine_result):
    lines = [
        f"# {proj.project_name} — 资源池总览\n",
        "> 资源池模型：人员、仪器、房间统一管理，自动避免时间冲突\n",
        f"> 排程结果: ✅ {engine_result['assigned']} 项已分配 | ❌ {engine_result['unassigned']} 项未分配\n",
    ]
    lines.extend(["## 👥 人员资源池\n", "| 姓名 | 部门 | 级别 | 总时段 | 已用 | 使用率 | 任务数 |", "|------|------|------|--------|------|--------|--------|"])
    for name in pool.personnel:
        wl = pool.get_person_workload(name)
        dept = pool.personnel[name].get("department", "")
        dept_name = DEPARTMENTS.get(dept, {}).get("name", dept)
        level = pool.personnel[name].get("level", "-")
        lines.append(f"| {name} | {dept_name} | {level} | {wl['total_slots']} | {wl['booked_slots']} | {wl['utilization']} | {wl['task_count']} |")
    lines.extend(["\n## 🔬 仪器资源池\n", "| 仪器 | 型号 | 位置 | 校准到期 | 总时段 | 可用 | 已用 | 使用率 | 使用部门 |", "|------|------|------|----------|--------|------|------|--------|----------|"])
    for name in pool.instruments:
        iu = pool.get_instrument_utilization(name)
        inst = pool.instruments[name]
        dept_name = DEPARTMENTS.get(inst.get("location", ""), {}).get("name", inst.get("location", "-"))
        cal = inst.get("cal_due", "-")
        shared_tag = " 🔗" if inst.get("shared") else ""
        lines.append(f"| {name}{shared_tag} | {inst.get('model','-')} | {dept_name} | {cal} | {iu['total_slots']} | {iu['available_slots']} | {iu['booked_slots']} | {iu['utilization']} | {', '.join(iu['departments']) or '-'} |")
    if pool.reagents:
        lines.extend(["\n## 🧪 试剂/标准品资源\n", "| 名称 | 类别 | 效期 | 状态 |", "|------|------|------|------|"])
        for name, r in pool.reagents.items():
            status = "✅ 正常"
            if r.get("expiry"):
                try:
                    exp = dt.date.fromisoformat(r["expiry"])
                    if exp < pool.end:
                        status = "🔴 过期"
                    elif (exp - pool.end).days < 30:
                        status = "⚠️ 临近"
                except ValueError:
                    pass
            lines.append(f"| {name} | {r.get('category','-')} | {r.get('expiry','-')} | {status} |")
    if engine_result.get("conflicts"):
        lines.extend(["\n## ⚠️ 排程冲突\n"])
        for c in engine_result["conflicts"]:
            lines.append(f"- {c}")
    if engine_result.get("unassigned_tasks"):
        lines.extend(["\n## ❌ 未分配任务\n", "| 任务 | 部门 | 负责人 | 原因 |", "|------|------|--------|------|"])
        for t in engine_result["unassigned_tasks"]:
            lines.append(f"| {t['task']} | {DEPARTMENTS.get(t['department'],{}).get('name',t['department'])} | {t['assignee']} | {t['reason']} |")
    return "\n".join(lines)


def gen_gantt(proj, gantt_data):
    lines = [
        f"# {proj.project_name} — 甘特图排程\n",
        "> 自动排程结果，按日期排列\n",
        "| 日期 | 星期 | 时段 | 任务 | 负责人 | 仪器 | 部门 | 耗时 |",
        "|------|------|------|------|--------|------|------|------|",
    ]
    for item in gantt_data:
        try:
            d = dt.date.fromisoformat(item["start_date"])
            wd = WEEKDAY_CN[d.weekday()]
        except:
            wd = "-"
        dept_name = DEPARTMENTS.get(item["department"], {}).get("name", item["department"])
        slots = item.get("slots", 1)
        dur_str = f"{slots}时段" if slots > 1 else "1时段"
        lines.append(f"| {item['start_date']} | {wd} | {item['start_period']} | {item['task']} | {item['resource']} | {item['instruments']} | {dept_name} | {dur_str} |")
    if not gantt_data:
        lines.append("| （无排程数据） | | | | | | | |")
    return "\n".join(lines)


def gen_risk_board(proj, all_risks):
    lines = [f"# {proj.project_name} — 风险看板\n", f"> 生成日期: {dt.date.today().isoformat()}\n"]
    if not all_risks:
        lines.append("✅ 暂无风险\n")
    else:
        high = [r for r in all_risks if r.get("level") == "高"]
        med = [r for r in all_risks if r.get("level") == "中"]
        lines.append(f"**总计: {len(all_risks)} 项风险（🔴 高 {len(high)} / ⚠️ 中 {len(med)}）**\n")
        by_type = {}
        for r in all_risks:
            by_type.setdefault(r.get("type", "其他"), []).append(r)
        for risk_type, risks in by_type.items():
            lines.extend([f"## {risk_type}\n"])
            for r in risks:
                lines.append(f"- {r['message']}")
            lines.append("")
    lines.extend([
        "## 风险等级说明\n",
        "- 🔴 **高**：直接影响交货或GMP合规，必须立即处理",
        "- ⚠️ **中**：可能导致延误或质量问题，建议提前处理",
        "", "## 应急方案（按风险类型）\n",
        "### 🔴 仪器校准过期\n",
        "**预防**：提前30天申请校准，避开排班期\n",
        "**应急**：\n",
        "1. 启用备用仪器（如果可用）\n",
        "2. 借用兄弟部门仪器\n",
        "3. 委托第三方计量单位加急校准（2-3天）\n",
        "4. 重新排期该仪器任务，等校准完成后再做\n",
        "5. 如已过校准日期做了检验，该数据需重新验证有效性\n",
        "", "### 🔴 试剂/标准品效期过期\n",
        "**预防**：入库前核对效期，按效期先进先出，库存预警30天\n",
        "**应急**：\n",
        "1. 联系供应商紧急采购（标准品7-14天）\n",
        "2. 联系兄弟单位借用同批号对照品\n",
        "3. 使用工作对照品（需做系统适用性验证）\n",
        "4. 推迟该检验项目，重新评估排期\n",
        "5. 若对照品无法替换，启用方法学验证或外检\n",
        "", "### 🔴 单点故障（关键技能只有1人）\n",
        "**预防**：制定岗位备份计划，关键技能至少2人掌握\n",
        "**应急**：\n",
        "1. 该人员请假/离职时，立即启动备份人员（需提前培训）\n",
        "2. 紧急调用外部资源（兼职专家、退休返聘）\n",
        "3. 外包给有资质的第三方实验室\n",
        "4. 该关键任务推迟，重新评估交货期\n",
        "", "### 🔴 缓冲不足/赶工\n",
        "**预防**：预留10-20%缓冲，反向推导时间要充分\n",
        "**应急**：\n",
        "1. 提前启动日期，压缩上游环节\n",
        "2. 与客户沟通延迟交货（提前通知，避免GMP投诉）\n",
        "3. 增加临时人员/外包\n",
        "4. 并行能并行的任务（如鉴别+含量HPLC合并进样）\n",
        "5. 推迟交货日（最差方案）\n",
        "", "### 🔴 微生物培养周期撞截止日\n",
        "**预防**：项目启动即计算培养结束日，反推接种日期\n",
        "**应急**：\n",
        "1. 紧急改用快速检测方法（如需验证适用性）\n",
        "2. 加急外检（找有能力的第三方）\n",
        "3. 与客户沟通分批放行（先做理化全项，微生物后补）\n",
        "4. 推迟交货日\n",
        "", "### ⚠️ 试剂效期临近\n",
        "**预防**：库存预警30天，提前采购新批号并做对照\n",
        "**应急**：\n",
        "1. 紧急采购新批号对照品\n",
        "2. 做新旧批号对照验证（ICH Q2）\n",
        "3. 调整使用计划，临近效期的优先用掉\n",
        "", "### ⚠️ 仪器瓶颈（使用率过高）\n",
        "**预防**：仪器数量按峰值需求配置\n",
        "**应急**：\n",
        "1. 错峰使用（早班/午休/晚班加班）\n",
        "2. 委托外检\n",
        "3. 临时租赁仪器\n",
        "4. 优先级排序，非紧急任务让路\n",
        "", "### ⚠️ OOS（超标）缓冲不足\n",
        "**预防**：成品检验完成到交货日预留≥3天\n",
        "**应急**：\n",
        "1. OOS发生后立即启动调查（24h内）\n",
        "2. 同步开展偏差调查、原因分析、纠正预防\n",
        "3. 复检时优先用同批号对照品/新购对照品\n",
        "4. 若确认失败，启动产品召回评估（QA决策）\n",
        "5. 与客户沟通延迟交货\n",
        "", "### ⚠️ 技能不匹配\n",
        "**预防**：任务分配前先核对人员技能矩阵\n",
        "**应急**：\n",
        "1. 安排熟练人员现场带教（需符合GMP资质要求）\n",
        "2. 改派其他具备技能的人员\n",
        "3. 紧急培训（需评估培训充分性）\n",
        "4. 推迟该任务到合适人员可执行时\n",
        "", "### ⚠️ 人员冲突（跨部门/请假）\n",
        "**应急**：\n",
        "1. 改派同部门备份人员\n",
        "2. 调整任务到非冲突日期\n",
        "3. 与员工沟通调整请假时间（紧急情况）\n",
        "", "### ⚠️ 节假日冲突\n",
        "**预防**：排班前核对法定节假日清单\n",
        "**应急**：\n",
        "1. 调整排班避开节假日\n",
        "2. 节假日安排值班人员（需支付加班费）\n",
        "", "## 应急联系人模板\n",
        "建议每个项目存档以下应急联系人：\n",
        "- 项目负责人：\n",
        "- QA经理：\n",
        "- QC主管：\n",
        "- 车间主任：\n",
        "- 采购主管：\n",
        "- 仪器校准单位：\n",
        "- 标准品供应商：\n",
        "- 第三方检测实验室：\n",
        "", "## 排班通用注意事项\n",
        "- 微生物限度需提前5天安排（培养周期）",
        "- 无菌检查需提前14天安排（培养周期）",
        "- HPLC方法切换需预留30min平衡/冲洗时间",
        "- 建议每个部门留10-20%缓冲时间",
        "- GMP要求：原料未放行不得投料，成品未放行不得发货",
        "- QA必须独立于生产和销售",
        "- 检验超标（OOS）需预留调查时间",
        "- 节假日不排班（已自动排除）",
    ])
    return "\n".join(lines)


def gen_progress(proj, schedule):
    lines = [
        f"# {proj.project_name} — 进度追踪\n",
        f"> 更新日期: {dt.date.today().isoformat()}\n",
        "## 全流程进度\n",
        "| 阶段 | 部门 | 计划开始 | 计划截止 | 实际完成 | 状态 | 备注 |",
        "|------|------|----------|----------|----------|------|------|",
    ]
    for dept_id in proj.departments:
        dept = DEPARTMENTS.get(dept_id, {})
        s = schedule.get(dept_id, {})
        if not s:
            continue
        ss, se = s.get("start", "—"), s.get("end", "—")
        lines.append(f"| {dept.get('name', dept_id)} | {dept.get('icon','')} | {ss.isoformat() if isinstance(ss, dt.date) else ss} | {se.isoformat() if isinstance(se, dt.date) else se} | — | ⬜ | |")
    lines.extend(["", "## 状态说明\n", "- ⬜ 未开始", "- 🔄 进行中", "- ✅ 已完成", "- ❌ 异常/暂停", "- ⏳ 等待上游", "- 🔴 延期"])
    return "\n".join(lines)


def gen_instrument_overview(proj, instruments, schedule, pool=None):
    lines = [f"# {proj.project_name} — 仪器总排期\n", "> 跨部门仪器使用汇总\n"]
    for inst in instruments:
        name = inst.get("name", "") if isinstance(inst, dict) else getattr(inst, "name", "")
        model = inst.get("model", "-") if isinstance(inst, dict) else getattr(inst, "model", "-")
        shared = inst.get("shared", False) if isinstance(inst, dict) else getattr(inst, "shared", False)
        shared_tag = " 🔗共享" if shared else ""
        lines.extend([f"\n## {name}（{model}）{shared_tag}\n",
            "| 日期 | 星期 | 上午 | 下午 | 使用人 | 部门 | 任务 |",
            "|------|------|------|------|--------|------|------|"])
        if pool:
            for day in pool.work_days:
                wd = WEEKDAY_CN[day.weekday()]
                am = pool.slots.get((name, day, "上午"))
                pm = pool.slots.get((name, day, "下午"))
                am_str = am.task_name if am else "空闲"
                pm_str = pm.task_name if pm else "空闲"
                am_user = am.task_department if am else "-"
                lines.append(f"| {day.strftime('%m-%d')} | {wd} | {am_str} | {pm_str} | — | {am_user} | — |")
        else:
            lines.append("| （排班后自动填充） | | | | | | |")
    return "\n".join(lines)


# ============================================================
# 主流程
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="药厂多部门排班脚手架 v2")
    parser.add_argument("target_dir")
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--drug-name", default="")
    parser.add_argument("--batch-no", default="")
    parser.add_argument("--batch-type", default="常规生产")
    parser.add_argument("--batch-size", default="")
    parser.add_argument("--standard", default="")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--deadline", required=True)
    parser.add_argument("--special", default="")
    parser.add_argument("--departments", default=",".join(DEFAULT_ORDER))
    parser.add_argument("--dept-durations", default="{}")
    parser.add_argument("--personnel-json", default="[]")
    parser.add_argument("--instruments-json", default="[]")
    parser.add_argument("--test-items-json", default="[]")
    parser.add_argument("--reagents-json", default="[]", help="试剂/标准品 JSON")
    parser.add_argument("--auto-schedule", action="store_true")
    
    args = parser.parse_args()
    target = Path(args.target_dir)
    if target.exists() and any(target.iterdir()):
        print(f"❌ 目标目录 {target} 非空，拒绝覆盖。", file=sys.stderr)
        sys.exit(1)
    target.mkdir(parents=True, exist_ok=True)
    
    departments = [d.strip() for d in args.departments.split(",")]
    start = dt.date.fromisoformat(args.start_date)
    deadline = dt.date.fromisoformat(args.deadline)
    try:
        dept_durations = json.loads(args.dept_durations)
        personnel_raw = json.loads(args.personnel_json)
        instruments_raw = json.loads(args.instruments_json)
        test_items = json.loads(args.test_items_json)
        reagents_raw = json.loads(args.reagents_json)
    except json.JSONDecodeError as e:
        print(f"❌ JSON 解析错误: {e}", file=sys.stderr)
        sys.exit(1)
    
    proj = ProjectInfo(
        project_name=args.project_name, drug_name=args.drug_name,
        batch_no=args.batch_no, batch_type=args.batch_type, batch_size=args.batch_size,
        standard=args.standard, start_date=args.start_date, deadline=args.deadline,
        special=args.special, departments=departments,
    )
    schedule = reverse_schedule(deadline, dept_durations, departments)
    
    pool, engine_result, gantt_data, all_risks = None, None, [], []
    if args.auto_schedule and test_items:
        pool, engine_result, gantt_data, all_risks = run_resource_pool_schedule(
            proj, schedule, personnel_raw, instruments_raw, test_items, reagents_raw,
        )
    
    dept_dir = target / "部门排班"
    dept_dir.mkdir(exist_ok=True)
    
    (target / "README.md").write_text(gen_readme(proj, schedule, all_risks, engine_result), encoding="utf-8")
    (target / "项目信息.md").write_text(
        f"# {args.project_name} — 项目信息\n\n| 字段 | 内容 |\n|------|------|\n"
        f"| 药品名称 | {args.drug_name} |\n| 批号 | {args.batch_no} |\n| 批量 | {args.batch_size} |\n"
        f"| 项目类型 | {args.batch_type} |\n| 质量标准 | {args.standard} |\n"
        f"| 项目启动 | {args.start_date} |\n| 交货截止 | {args.deadline} |\n"
        f"| 总工期 | {workdays_between(start, deadline)} 工作日 |\n| 特殊要求 | {args.special or '无'} |\n",
        encoding="utf-8"
    )
    (target / "依赖关系.md").write_text(gen_dependency_map(proj), encoding="utf-8")
    (target / "关键时间节点.md").write_text(
        f"# {args.project_name} — 关键时间节点\n\n" + "\n".join(
            f"## {DEPARTMENTS.get(d,{}).get('name',d)}\n\n"
            f"- 开始: {schedule.get(d,{}).get('start','—')}\n- 截止: {schedule.get(d,{}).get('end','—')}\n"
            f"- 工作日: {schedule.get(d,{}).get('duration_workdays','—')}\n"
            f"- 前置: {', '.join(DEPARTMENTS.get(dd,{}).get('name',dd) for dd in DEPARTMENTS.get(d,{}).get('depends_on',[])) or '无'}\n"
            for d in departments
        ), encoding="utf-8"
    )
    
    for dept_id in departments:
        dept = DEPARTMENTS.get(dept_id, {})
        (dept_dir / f"{dept.get('name', dept_id)}排班.md").write_text(
            gen_dept_schedule(proj, dept_id, schedule, personnel_raw, instruments_raw, test_items, pool),
            encoding="utf-8"
        )
    
    if pool and engine_result:
        (target / "资源池总览.md").write_text(gen_resource_pool_overview(proj, pool, engine_result), encoding="utf-8")
        (target / "甘特图排程.md").write_text(gen_gantt(proj, gantt_data), encoding="utf-8")
    else:
        (target / "资源池总览.md").write_text(f"# {proj.project_name} — 资源池总览\n\n（使用 --auto-schedule 开启）\n", encoding="utf-8")
        (target / "甘特图排程.md").write_text(f"# {proj.project_name} — 甘特图排程\n\n（使用 --auto-schedule 开启）\n", encoding="utf-8")
    
    (target / "仪器总排期.md").write_text(gen_instrument_overview(proj, instruments_raw, schedule, pool), encoding="utf-8")
    (target / "人员总排期.md").write_text(f"# {args.project_name} — 人员总排期\n\n（排班后自动汇总）\n", encoding="utf-8")
    (target / "进度追踪.md").write_text(gen_progress(proj, schedule), encoding="utf-8")
    (target / "风险看板.md").write_text(gen_risk_board(proj, all_risks), encoding="utf-8")
    
    high_risks = len([r for r in all_risks if r.get("level") == "高"])
    med_risks = len([r for r in all_risks if r.get("level") == "中"])
    print(f"\n✅ 排班已创建: {target}")
    print(f"   项目: {args.project_name} | 部门: {len(departments)} 个")
    print(f"   周期: {args.start_date} → {args.deadline} ({workdays_between(start, deadline)} 工作日)")
    if pool and engine_result:
        print(f"\n   🏊 资源池: {len(pool.personnel)}人 + {len(pool.instruments)}台仪器 + {len(pool.reagents)}种试剂")
        print(f"   ✅ 已分配: {engine_result['assigned']} | ❌ 未分配: {engine_result['unassigned']}")
    if all_risks:
        print(f"\n   ⚠️ 风险: {len(all_risks)} 项（🔴高{high_risks} / ⚠️中{med_risks}）")
    print(f"\n   文件:")
    for f in sorted(target.rglob("*.md")):
        print(f"   - {f.relative_to(target)}")


if __name__ == "__main__":
    main()
