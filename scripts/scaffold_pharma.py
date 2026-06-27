#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
药厂多部门排班脚手架。
从交货截止日反向推导各部门时间，生成完整排班目录。
支持资源池模型：自动分配人员+仪器时间槽，避免冲突。
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.common import (
    DEPARTMENTS, WEEKDAY_CN, ProjectInfo, TaskItem, Personnel, Instrument,
    ResourcePool, SchedulingEngine,
    is_workday, add_workdays, subtract_workdays, workdays_between,
    reverse_schedule, detect_instrument_conflicts, detect_calibration_risks,
    detect_personnel_conflicts, detect_schedule_risks,
)

# ============================================================
# 资源池排程
# ============================================================

def run_resource_pool_schedule(proj, schedule, personnel_raw, instruments_raw, test_items):
    """
    用资源池模型自动排程。
    返回 (pool, engine_result, gantt_data)。
    """
    start = dt.date.fromisoformat(proj.start_date)
    end = dt.date.fromisoformat(proj.deadline)
    
    # 创建资源池
    pool = ResourcePool(start, end)
    
    # 注册人员
    for p in personnel_raw:
        pool.register_person(
            name=p["name"],
            department=p.get("department", ""),
            level=p.get("level", ""),
            skills=p.get("skills", ""),
            note=p.get("note", ""),
        )
    
    # 注册仪器
    for i in instruments_raw:
        pool.register_instrument(
            name=i["name"],
            model=i.get("model", ""),
            location=i.get("location", ""),
            cal_due=i.get("cal_due", ""),
            status=i.get("status", "正常"),
            shared=i.get("shared", False),
            qty=i.get("qty", 1),
        )
    
    # 构建任务列表
    tasks = []
    for t in test_items:
        # 计算 earliest_start：基于部门排班起始日
        dept_id = t.get("department", "")
        dept_schedule = schedule.get(dept_id, {})
        earliest = dept_schedule.get("start", start)
        if isinstance(earliest, dt.date):
            earliest_str = earliest.isoformat()
        else:
            earliest_str = str(earliest)
        
        # 解析仪器列表
        inst_str = t.get("instruments", t.get("instrument", ""))
        inst_list = [x.strip() for x in inst_str.split(",") if x.strip() and x.strip() != "-"]
        
        # 解析耗时
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
            "name": t.get("name", ""),
            "department": dept_id,
            "assignee": t.get("assignee", ""),
            "instruments": inst_list,
            "duration_hours": dur_hours,
            "priority": t.get("priority", "普通"),
            "depends_on": t.get("depends_on", ""),
            "earliest_start": earliest_str,
        })
    
    # 自动排程
    engine = SchedulingEngine(pool)
    result = engine.auto_schedule(tasks)
    gantt = engine.generate_gantt_data()
    
    return pool, result, gantt

# ============================================================
# 模板生成
# ============================================================

def gen_readme(proj, schedule, risks, pool_result=None):
    lines = [
        f"# {proj.project_name} — 多部门排班总览\n",
        f"> 生成日期: {dt.date.today().isoformat()}\n",
        "## 项目信息\n",
        "| 字段 | 内容 |",
        "|------|------|",
        f"| 药品名称 | {proj.drug_name} |",
        f"| 批号 | {proj.batch_no} |",
        f"| 批量 | {proj.batch_size} |",
        f"| 项目类型 | {proj.batch_type} |",
        f"| 质量标准 | {proj.standard} |",
        f"| 项目启动 | {proj.start_date} |",
        f"| 交货截止 | {proj.deadline} |",
        f"| 特殊要求 | {proj.special or '无'} |",
        f"| 参与部门 | {', '.join(DEPARTMENTS.get(d,{}).get('name',d) for d in proj.departments)} |",
        "",
        "## 项目时间线（反向推导）\n",
        "| 阶段 | 部门 | 开始 | 截止 | 工作日 | 前置 | 缓冲 | 状态 |",
        "|------|------|------|------|--------|------|------|------|",
    ]
    for dept_id in ["procurement", "qc_incoming", "workshop", "qc_finished", "sales"]:
        if dept_id not in proj.departments:
            continue
        dept = DEPARTMENTS.get(dept_id, {})
        s = schedule.get(dept_id, {})
        start = s.get("start", "—")
        end = s.get("end", "—")
        dur = s.get("duration_workdays", "—")
        deps = dept.get("depends_on", [])
        dep_names = [DEPARTMENTS.get(d, {}).get("name", d) for d in deps] if deps else ["—"]
        total_days = workdays_between(s["start"], s["end"]) if "start" in s and "end" in s else 0
        buffer = total_days - dur if isinstance(dur, int) else 0
        buffer_str = f"{buffer}天" if buffer >= 0 else f"🔴 {buffer}天"
        lines.append(
            f"| {dept.get('name', dept_id)} | {dept.get('icon','')} "
            f"| {start.isoformat() if isinstance(start, dt.date) else start} "
            f"| {end.isoformat() if isinstance(end, dt.date) else end} "
            f"| {dur} | {', '.join(dep_names)} | {buffer_str} | ⬜ |"
        )
    lines.extend(["", "## 关键路径\n", "```"])
    lines.append(" → ".join(
        DEPARTMENTS.get(d, {}).get("name", d)
        for d in ["procurement", "qc_incoming", "workshop", "qc_finished", "sales"]
        if d in proj.departments
    ))
    lines.append("```\n")
    
    # 资源池摘要
    if pool_result:
        lines.extend(["## 资源池排程结果\n"])
        lines.append(f"- ✅ 已分配任务: {pool_result['assigned']} 项")
        lines.append(f"- ❌ 未分配任务: {pool_result['unassigned']} 项")
        if pool_result.get("conflicts"):
            lines.append(f"- ⚠️ 冲突: {len(pool_result['conflicts'])} 个")
        lines.append("")
    
    if risks:
        lines.extend(["## ⚠️ 风险预警\n"])
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
        "- [仪器总排期.md](仪器总排期.md) — 跨部门仪器排期汇总",
        "- [人员总排期.md](人员总排期.md) — 跨部门人员排期汇总",
        "- [进度追踪.md](进度追踪.md) — 全流程进度",
        "- [风险看板.md](风险看板.md) — 跨部门风险汇总",
        "", "---", "*由 pharma-schedule skill 自动生成*",
    ])
    return "\n".join(lines)


def gen_dependency_map(proj):
    lines = [
        f"# {proj.project_name} — 依赖关系\n",
        "## 流程依赖图\n", "```",
        "采购下单 ──→ 原料到货 ──→ QC来料检验 ──→ 车间生产 ──→ QC成品检验 ──→ 放行 ──→ 销售发货",
        "    │                                          │                              │",
        "    └── 包材采购 ─────────────────────────────┘                              │",
        "    └── 试剂/耗材 ──→ QC用                                                │",
        "                                        客户签收 ←──────────────────────────┘",
        "```\n", "## 依赖明细\n",
        "| 上游 | 交付物 | 下游 | 接收条件 |",
        "|------|--------|------|----------|",
    ]
    deps = [
        ("采购部", "原辅料到货", "QC来料", "到货验收单+供应商检验报告"),
        ("采购部", "包材到货", "车间", "到货验收单"),
        ("QC来料", "原料放行报告", "车间", "检验合格+放行"),
        ("车间", "成品完工+请验单", "QC成品", "生产记录完整+取样"),
        ("QC成品", "成品检验报告+放行", "销售", "全项合格+QA放行签字"),
        ("销售", "客户签收", "全项目", "签收单+回款"),
    ]
    for u, d, ds, c in deps:
        lines.append(f"| {u} | {d} | {ds} | {c} |")
    lines.extend(["", "## 关键约束\n",
        "1. **原料未放行，车间不得投料** — GMP 强制要求",
        "2. **成品未放行，销售不得发货** — GMP 强制要求",
        "3. **微生物检验有培养周期** — 来料 5天，成品 5天",
        "4. **无菌检验培养 14天** — 如果涉及无菌品种",
        "5. **仪器共享** — QC 和车间可能共用天平、pH 计等",
    ])
    return "\n".join(lines)


def gen_dept_schedule(proj, dept_id, schedule, personnel, instruments, test_items, pool=None):
    dept = DEPARTMENTS.get(dept_id, {})
    s = schedule.get(dept_id, {})
    start = s.get("start")
    end = s.get("end")
    dept_personnel = [p for p in personnel if p.get("department") == dept_id]
    dept_instruments = [i for i in instruments if i.get("location") == dept_id or i.get("shared")]
    dept_tasks = [t for t in test_items if t.get("department") == dept_id]
    
    lines = [
        f"# {proj.project_name} — {dept.get('name', dept_id)}排班\n",
        f"> 部门: {dept.get('icon','')} {dept.get('name', dept_id)}",
        f"> 排班周期: {start.isoformat() if isinstance(start, dt.date) else start} ~ {end.isoformat() if isinstance(end, dt.date) else end}",
        f"> 前置依赖: {', '.join(DEPARTMENTS.get(d,{}).get('name',d) for d in dept.get('depends_on',[])) or '无'}\n",
    ]
    
    # 任务清单（如果有资源池数据，显示实际分配结果）
    lines.extend([
        "## 检验/工作任务清单\n",
        "| 序号 | 任务 | 负责人 | 仪器 | 耗时 | 优先级 | 分配日期 | 分配时段 | 状态 |",
        "|------|------|--------|------|------|--------|----------|----------|------|",
    ])
    if dept_tasks:
        for i, t in enumerate(dept_tasks, 1):
            assignee = t.get("assignee", "待填")
            inst = t.get("instruments", t.get("instrument", "-"))
            # 从资源池查找分配结果
            alloc_date, alloc_period = "待排", "—"
            if pool:
                for key, slot in pool.slots.items():
                    if slot.task_name == t.get("name", "") and slot.resource_type == "person":
                        alloc_date = slot.date.strftime("%m-%d")
                        alloc_period = slot.period
                        break
            lines.append(
                f"| {i} | {t.get('name','-')} | {assignee} | {inst} | {t.get('duration','-')} | {t.get('priority','普通')} | {alloc_date} | {alloc_period} | ⬜ |"
            )
    else:
        for i, t in enumerate(dept.get("typical_tasks", []), 1):
            lines.append(f"| {i} | {t['name']} | 待填 | — | {t['duration']} | 普通 | 待排 | — | ⬜ |")
    
    # 人员排班表
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
                        # 从资源池获取实际排班
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
    """生成资源池总览。"""
    lines = [
        f"# {proj.project_name} — 资源池总览\n",
        "> 资源池模型：人员、仪器、房间统一管理，自动避免时间冲突\n",
        f"> 排程结果: ✅ {engine_result['assigned']} 项已分配 | ❌ {engine_result['unassigned']} 项未分配\n",
    ]
    
    # 人员资源池
    lines.extend(["## 👥 人员资源池\n", "| 姓名 | 部门 | 级别 | 总时段 | 已用 | 使用率 | 任务数 |", "|------|------|------|--------|------|--------|--------|"])
    for name in pool.personnel:
        wl = pool.get_person_workload(name)
        dept = pool.personnel[name].get("department", "")
        dept_name = DEPARTMENTS.get(dept, {}).get("name", dept)
        level = pool.personnel[name].get("level", "-")
        lines.append(f"| {name} | {dept_name} | {level} | {wl['total_slots']} | {wl['booked_slots']} | {wl['utilization']} | {wl['task_count']} |")
    
    # 仪器资源池
    lines.extend(["\n## 🔬 仪器资源池\n", "| 仪器 | 型号 | 位置 | 校准到期 | 总时段 | 可用 | 已用 | 使用率 | 使用部门 |", "|------|------|------|----------|--------|------|------|--------|----------|"])
    for name in pool.instruments:
        iu = pool.get_instrument_utilization(name)
        inst = pool.instruments[name]
        dept_name = DEPARTMENTS.get(inst.get("location", ""), {}).get("name", inst.get("location", "-"))
        cal = inst.get("cal_due", "-")
        shared_tag = " 🔗" if inst.get("shared") else ""
        lines.append(f"| {name}{shared_tag} | {inst.get('model','-')} | {dept_name} | {cal} | {iu['total_slots']} | {iu['available_slots']} | {iu['booked_slots']} | {iu['utilization']} | {', '.join(iu['departments']) or '-'} |")
    
    # 冲突
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
    """生成甘特图排程表。"""
    lines = [
        f"# {proj.project_name} — 甘特图排程\n",
        "> 自动排程结果，按日期排列\n",
        "| 日期 | 星期 | 时段 | 任务 | 负责人 | 仪器 | 部门 |",
        "|------|------|------|------|--------|------|------|",
    ]
    for item in gantt_data:
        try:
            d = dt.date.fromisoformat(item["date"])
            wd = WEEKDAY_CN[d.weekday()]
        except:
            wd = "-"
        dept_name = DEPARTMENTS.get(item["department"], {}).get("name", item["department"])
        lines.append(f"| {item['date']} | {wd} | {item['period']} | {item['task']} | {item['resource']} | {item['instruments']} | {dept_name} |")
    if not gantt_data:
        lines.append("| （无排程数据） | | | | | | |")
    return "\n".join(lines)


def gen_instrument_overview(proj, instruments, schedule, pool=None):
    lines = [
        f"# {proj.project_name} — 仪器总排期\n",
        "> 跨部门仪器使用汇总\n",
    ]
    for inst in instruments:
        name = inst.get("name", "") if isinstance(inst, dict) else getattr(inst, "name", "")
        model = inst.get("model", "-") if isinstance(inst, dict) else getattr(inst, "model", "-")
        shared = inst.get("shared", False) if isinstance(inst, dict) else getattr(inst, "shared", False)
        shared_tag = " 🔗共享" if shared else ""
        lines.extend([
            f"\n## {name}（{model}）{shared_tag}\n",
            "| 日期 | 星期 | 上午 | 下午 | 使用人 | 部门 | 任务 |",
            "|------|------|------|------|--------|------|------|",
        ])
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


def gen_progress(proj, schedule):
    lines = [
        f"# {proj.project_name} — 进度追踪\n",
        f"> 更新日期: {dt.date.today().isoformat()}\n",
        "## 全流程进度\n",
        "| 阶段 | 部门 | 计划开始 | 计划截止 | 实际完成 | 状态 | 备注 |",
        "|------|------|----------|----------|----------|------|------|",
    ]
    for dept_id in ["procurement", "qc_incoming", "workshop", "qc_finished", "sales"]:
        if dept_id not in proj.departments:
            continue
        dept = DEPARTMENTS.get(dept_id, {})
        s = schedule.get(dept_id, {})
        ss = s.get("start", "—")
        se = s.get("end", "—")
        lines.append(f"| {dept.get('name', dept_id)} | {dept.get('icon','')} | {ss.isoformat() if isinstance(ss, dt.date) else ss} | {se.isoformat() if isinstance(se, dt.date) else se} | — | ⬜ | |")
    lines.extend(["", "## 状态说明\n", "- ⬜ 未开始", "- 🔄 进行中", "- ✅ 已完成", "- ❌ 异常/暂停", "- ⏳ 等待上游", "- 🔴 延期"])
    return "\n".join(lines)


def gen_risk_board(proj, all_risks):
    lines = [f"# {proj.project_name} — 风险看板\n", f"> 生成日期: {dt.date.today().isoformat()}\n"]
    if not all_risks:
        lines.append("✅ 暂无风险\n")
    else:
        by_type = {}
        for r in all_risks:
            by_type.setdefault(r.get("type", "其他"), []).append(r)
        for risk_type, risks in by_type.items():
            lines.extend([f"## {risk_type}\n"])
            for r in risks:
                lines.append(f"- {r['message']}")
            lines.append("")
    lines.extend(["## 排班通用注意事项\n",
        "- 微生物限度需提前5天安排（培养周期）",
        "- 无菌检查需提前14天安排（培养周期）",
        "- 仪器方法切换需预留30min平衡/冲洗时间",
        "- 建议每个部门留10-20%缓冲时间",
        "- GMP要求：原料未放行不得投料，成品未放行不得发货",
        "- 节假日不排班（已自动排除）",
    ])
    return "\n".join(lines)


# ============================================================
# 主流程
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="药厂多部门排班脚手架")
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
    parser.add_argument("--departments", default="procurement,qc_incoming,workshop,qc_finished,sales")
    parser.add_argument("--dept-durations", default="{}")
    parser.add_argument("--personnel-json", default="[]")
    parser.add_argument("--instruments-json", default="[]")
    parser.add_argument("--test-items-json", default="[]")
    parser.add_argument("--auto-schedule", action="store_true", help="启用资源池自动排程")
    
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
    except json.JSONDecodeError as e:
        print(f"❌ JSON 解析错误: {e}", file=sys.stderr)
        sys.exit(1)
    
    instruments = [Instrument(
        name=i["name"], model=i.get("model",""), location=i.get("location",""),
        qty=i.get("qty",1), cal_due=i.get("cal_due",""), status=i.get("status","正常"),
        shared=i.get("shared",False),
    ) for i in instruments_raw]
    
    proj = ProjectInfo(
        project_name=args.project_name, drug_name=args.drug_name,
        batch_no=args.batch_no, batch_type=args.batch_type, batch_size=args.batch_size,
        standard=args.standard, start_date=args.start_date, deadline=args.deadline,
        special=args.special, departments=departments,
    )
    schedule = reverse_schedule(deadline, dept_durations)
    
    # 资源池排程
    pool = None
    engine_result = None
    gantt_data = []
    if args.auto_schedule and test_items:
        pool, engine_result, gantt_data = run_resource_pool_schedule(
            proj, schedule, personnel_raw, instruments_raw, test_items,
        )
    
    # 风险检测
    all_risks = []
    all_risks.extend(detect_schedule_risks(schedule))
    all_risks.extend(detect_calibration_risks(instruments, deadline))
    
    # 创建目录
    dept_dir = target / "部门排班"
    dept_dir.mkdir(exist_ok=True)
    
    # 生成文件
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
    
    # 资源池文件
    if pool and engine_result:
        (target / "资源池总览.md").write_text(gen_resource_pool_overview(proj, pool, engine_result), encoding="utf-8")
        (target / "甘特图排程.md").write_text(gen_gantt(proj, gantt_data), encoding="utf-8")
    else:
        (target / "资源池总览.md").write_text(f"# {proj.project_name} — 资源池总览\n\n（未启用自动排程，使用 --auto-schedule 开启）\n", encoding="utf-8")
        (target / "甘特图排程.md").write_text(f"# {proj.project_name} — 甘特图排程\n\n（未启用自动排程）\n", encoding="utf-8")
    
    (target / "仪器总排期.md").write_text(gen_instrument_overview(proj, instruments_raw, schedule, pool), encoding="utf-8")
    (target / "人员总排期.md").write_text(f"# {args.project_name} — 人员总排期\n\n（排班后自动汇总）\n", encoding="utf-8")
    (target / "进度追踪.md").write_text(gen_progress(proj, schedule), encoding="utf-8")
    (target / "风险看板.md").write_text(gen_risk_board(proj, all_risks), encoding="utf-8")
    
    # 输出摘要
    print(f"\n✅ 药厂多部门排班已创建: {target}")
    print(f"   项目: {args.project_name} | 部门: {len(departments)} 个")
    print(f"   排班周期: {args.start_date} → {args.deadline} ({workdays_between(start, deadline)} 工作日)")
    if pool and engine_result:
        print(f"\n   🏊 资源池排程:")
        print(f"      人员: {len(pool.personnel)} 人 | 仪器: {len(pool.instruments)} 台")
        print(f"      ✅ 已分配: {engine_result['assigned']} | ❌ 未分配: {engine_result['unassigned']}")
    print(f"\n   时间线:")
    for dept_id in departments:
        dept = DEPARTMENTS.get(dept_id, {})
        s = schedule.get(dept_id, {})
        print(f"   {dept.get('icon','')} {dept.get('name',dept_id)}: {s.get('start','?')} ~ {s.get('end','?')} ({s.get('duration_workdays','?')}工作日)")
    if all_risks:
        print(f"\n   ⚠️ 风险:")
        for r in all_risks:
            print(f"   {r['message']}")
    print(f"\n   文件:")
    for f in sorted(target.rglob("*.md")):
        print(f"   - {f.relative_to(target)}")


if __name__ == "__main__":
    main()
