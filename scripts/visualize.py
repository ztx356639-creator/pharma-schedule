#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
药厂排班可视化 HTML 生成器 v2。
支持：部门/人员/仪器筛选、风险高亮、打印优化、导出 CSV。
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.common import (
    DEPARTMENTS, DEFAULT_ORDER, WEEKDAY_CN, ProjectInfo,
    ResourcePool, SchedulingEngine,
    is_workday, workdays_between, reverse_schedule, detect_all_risks,
)


HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{title} — 可视化排班</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
        background: #0d1117; color: #e6edf3; padding: 20px; line-height: 1.5; }}
header {{ display: flex; justify-content: space-between; align-items: center;
          margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid #21262d; }}
h1 {{ font-size: 22px; }}
h2 {{ font-size: 16px; color: #58a6ff; margin: 20px 0 10px; padding-bottom: 6px;
     border-bottom: 1px solid #21262d; }}
.subtitle {{ color: #8b949e; font-size: 13px; }}
.toolbar {{ display: flex; gap: 8px; }}
.btn {{ background: #21262d; color: #e6edf3; border: 1px solid #30363d;
        padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 13px; }}
.btn:hover {{ background: #30363d; }}
.btn.primary {{ background: #238636; border-color: #2ea043; }}
.summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 10px; margin-bottom: 20px; }}
.card {{ background: #161b22; border: 1px solid #21262d; border-radius: 8px;
         padding: 14px; text-align: center; }}
.card-num {{ font-size: 24px; font-weight: 700; color: #58a6ff; }}
.card-label {{ font-size: 12px; color: #8b949e; margin-top: 4px; }}
.card.danger .card-num {{ color: #f85149; }}
.card.warning .card-num {{ color: #d29922; }}
.card.success .card-num {{ color: #3fb950; }}
.tabs {{ display: flex; gap: 4px; margin-bottom: 16px; border-bottom: 1px solid #21262d; }}
.tab {{ padding: 8px 16px; cursor: pointer; color: #8b949e; border-bottom: 2px solid transparent;
        font-size: 14px; }}
.tab.active {{ color: #58a6ff; border-bottom-color: #58a6ff; }}
.tab-content {{ display: none; }}
.tab-content.active {{ display: block; }}
.filter {{ display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; align-items: center; }}
.filter label {{ font-size: 13px; color: #8b949e; }}
.filter select, .filter input {{ background: #0d1117; color: #e6edf3;
                                   border: 1px solid #30363d; padding: 4px 8px;
                                   border-radius: 4px; font-size: 13px; }}
.gantt-scroll {{ overflow-x: auto; max-width: 100%; }}
table {{ border-collapse: collapse; font-size: 12px; min-width: 100%; }}
th, td {{ border: 1px solid #21262d; padding: 4px 6px; text-align: center;
          white-space: nowrap; }}
th {{ background: #161b22; color: #8b949e; font-weight: 500; position: sticky; top: 0; z-index: 3; }}
th.row-header {{ position: sticky; left: 0; z-index: 4; background: #161b22; min-width: 100px; text-align: left; }}
td.row-header {{ position: sticky; left: 0; z-index: 1; background: #0d1117; min-width: 100px;
                 text-align: left; padding-left: 8px; }}
td.cell {{ min-width: 50px; padding: 2px; position: relative; }}
.weekend {{ background: #161b22; }}
.today {{ box-shadow: inset 0 0 0 2px #58a6ff; }}
.bar {{ display: inline-block; width: 100%; height: 18px; border-radius: 3px;
        line-height: 18px; font-size: 10px; color: #fff; white-space: nowrap;
        overflow: hidden; text-overflow: ellipsis; cursor: pointer; }}
.bar:hover {{ opacity: 0.85; transform: scaleY(1.2); z-index: 5; }}
.bar.proc {{ background: #238636; }}
.bar.qc-in {{ background: #1f6feb; }}
.bar.work {{ background: #d29922; }}
.bar.qc-out {{ background: #8957e5; }}
.bar.qa {{ background: #a371f7; }}
.bar.sale {{ background: #f78166; }}
.legend {{ display: flex; gap: 14px; margin-bottom: 10px; flex-wrap: wrap;
           font-size: 12px; }}
.legend-item {{ display: flex; align-items: center; gap: 5px; }}
.legend-color {{ width: 14px; height: 12px; border-radius: 2px; }}
.risk-card {{ background: #161b22; border: 1px solid #21262d; border-radius: 6px;
              padding: 10px 14px; margin-bottom: 8px; border-left: 3px solid; }}
.risk-card.high {{ border-left-color: #f85149; }}
.risk-card.medium {{ border-left-color: #d29922; }}
.risk-card.low {{ border-left-color: #58a6ff; }}
.risk-title {{ font-size: 13px; font-weight: 600; margin-bottom: 4px; }}
.risk-msg {{ font-size: 12px; color: #c9d1d9; }}
.risk-contingency {{ margin-top: 8px; padding-top: 8px; border-top: 1px dashed #30363d;
                    font-size: 12px; color: #8b949e; }}
.risk-contingency strong {{ color: #d29922; }}
.stat-table {{ font-size: 12px; }}
.stat-table th {{ background: #161b22; }}
.stat-bar {{ display: inline-block; height: 14px; background: #238636; vertical-align: middle;
              margin-right: 4px; border-radius: 2px; }}
.stat-bar.medium {{ background: #d29922; }}
.stat-bar.high {{ background: #1f6feb; }}
.stat-bar.full {{ background: #f85149; }}
.modal {{ display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0;
          background: rgba(0,0,0,0.7); z-index: 100; padding: 40px; overflow: auto; }}
.modal.show {{ display: flex; align-items: center; justify-content: center; }}
.modal-content {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px;
                  padding: 20px; max-width: 600px; width: 100%; }}
.modal-close {{ float: right; cursor: pointer; color: #8b949e; font-size: 18px; }}
@media print {{ body {{ background: #fff; color: #000; }} .btn, .toolbar {{ display: none; }}
                .tab-content {{ display: block !important; }} th {{ background: #f0f0f0; color: #000; }}
                .bar {{ color: #fff !important; }} }}
</style>
</head>
<body>

<header>
  <div>
    <h1>📋 {title} — 可视化排班</h1>
    <p class="subtitle">生成日期: {today} | 资源池 + 10类风险检测 + 应急方案</p>
  </div>
  <div class="toolbar">
    <button class="btn" onclick="window.print()">🖨️ 打印</button>
    <button class="btn primary" onclick="exportCSV()">📥 导出CSV</button>
    <button class="btn" onclick="toggleFullscreen()">⛶ 全屏</button>
  </div>
</header>

<!-- 概览卡片 -->
<div class="summary">
  <div class="card"><div class="card-num">{dept_count}</div><div class="card-label">参与部门</div></div>
  <div class="card"><div class="card-num">{person_count}</div><div class="card-label">人员</div></div>
  <div class="card"><div class="card-num">{instr_count}</div><div class="card-label">仪器</div></div>
  <div class="card success"><div class="card-num">{assigned}</div><div class="card-label">已分配任务</div></div>
  <div class="card {unassigned_class}"><div class="card-num">{unassigned}</div><div class="card-label">未分配</div></div>
  <div class="card"><div class="card-num">{work_days}</div><div class="card-label">工作日</div></div>
  <div class="card {high_class}"><div class="card-num">{high_risks}</div><div class="card-label">🔴 高风险</div></div>
  <div class="card {med_class}"><div class="card-num">{med_risks}</div><div class="card-label">⚠️ 中风险</div></div>
</div>

<!-- Tab 切换 -->
<div class="tabs">
  <div class="tab active" data-tab="gantt">📊 甘特图</div>
  <div class="tab" data-tab="person">👥 人员排班</div>
  <div class="tab" data-tab="instr">🔬 仪器排期</div>
  <div class="tab" data-tab="risk">⚠️ 风险看板</div>
  <div class="tab" data-tab="resource">🏊 资源池</div>
</div>

<!-- Tab 1: 甘特图 -->
<div class="tab-content active" id="tab-gantt">
<h2>📊 项目甘特图（按人员 × 日期）</h2>
<div class="filter">
  <label>部门筛选:</label>
  <select id="dept-filter" onchange="filterGantt()">
    <option value="all">全部</option>
    {dept_options}
  </select>
  <label>优先级:</label>
  <select id="pri-filter" onchange="filterGantt()">
    <option value="all">全部</option>
    <option value="高">高</option>
    <option value="普通">普通</option>
    <option value="低">低</option>
  </select>
</div>
<div class="legend">
  <div class="legend-item"><div class="legend-color" style="background:#238636"></div>采购</div>
  <div class="legend-item"><div class="legend-color" style="background:#1f6feb"></div>QC来料</div>
  <div class="legend-item"><div class="legend-color" style="background:#d29922"></div>车间</div>
  <div class="legend-item"><div class="legend-color" style="background:#8957e5"></div>QC成品</div>
  <div class="legend-item"><div class="legend-color" style="background:#a371f7"></div>QA放行</div>
  <div class="legend-item"><div class="legend-color" style="background:#f78166"></div>销售发货</div>
</div>
<div class="gantt-scroll">
<table id="gantt-table">
<thead><tr>
  <th class="row-header">部门 / 人员</th>
  {date_headers}
</tr></thead>
<tbody>
  {gantt_rows}
</tbody>
</table>
</div>
</div>

<!-- Tab 2: 人员排班 -->
<div class="tab-content" id="tab-person">
<h2>👥 人员详细排班</h2>
<div class="gantt-scroll">
<table class="stat-table">
<thead><tr>
  <th class="row-header">人员</th>
  <th class="row-header">部门</th>
  <th>已用时段</th>
  <th>使用率</th>
  <th>任务数</th>
</tr></thead>
<tbody>
  {person_rows}
</tbody>
</table>
</div>
</div>

<!-- Tab 3: 仪器排期 -->
<div class="tab-content" id="tab-instr">
<h2>🔬 仪器使用情况</h2>
<div class="gantt-scroll">
<table class="stat-table">
<thead><tr>
  <th class="row-header">仪器</th>
  <th>型号</th>
  <th>位置</th>
  <th>校准到期</th>
  <th>使用率</th>
  <th>使用部门</th>
</tr></thead>
<tbody>
  {instr_rows}
</tbody>
</table>
</div>
</div>

<!-- Tab 4: 风险看板 -->
<div class="tab-content" id="tab-risk">
<h2>⚠️ 风险检测结果（共 {total_risks} 项）</h2>
{risks_html}
</div>

<!-- Tab 5: 资源池 -->
<div class="tab-content" id="tab-resource">
<h2>🏊 资源池使用统计</h2>
{resource_html}
</div>

<!-- 详情弹窗 -->
<div class="modal" id="detail-modal">
  <div class="modal-content">
    <span class="modal-close" onclick="closeModal()">✕</span>
    <h3 id="modal-title"></h3>
    <p id="modal-body" style="margin-top:10px;white-space:pre-wrap"></p>
  </div>
</div>

<script>
const ASSIGNED = {assigned_json};
const RISKS = {risks_json};

// Tab 切换
document.querySelectorAll('.tab').forEach(tab => {{
  tab.addEventListener('click', () => {{
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById('tab-' + tab.dataset.tab).classList.add('active');
  }});
}});

// 甘特图筛选
function filterGantt() {{
  const dept = document.getElementById('dept-filter').value;
  const pri = document.getElementById('pri-filter').value;
  document.querySelectorAll('#gantt-table tbody tr').forEach(row => {{
    const rowDept = row.dataset.dept || '';
    const rowPri = row.dataset.priority || '';
    const show = (dept === 'all' || rowDept === dept) && (pri === 'all' || rowPri === pri);
    row.style.display = show ? '' : 'none';
  }});
}}

// 任务详情
function showDetail(taskName) {{
  const t = ASSIGNED.find(x => x.task === taskName);
  if (!t) return;
  document.getElementById('modal-title').textContent = t.task;
  document.getElementById('modal-body').textContent =
    `部门: ${{t.department}}\\n负责人: ${{t.assignee}}\\n仪器: ${{t.instruments || '—'}}\\n日期: ${{t.start_date}} ${{t.start_period}}\\n优先级: ${{t.priority}}\\n占用: ${{t.slots || 1}} 个时段`;
  document.getElementById('detail-modal').classList.add('show');
}}
function closeModal() {{
  document.getElementById('detail-modal').classList.remove('show');
}}
document.getElementById('detail-modal').addEventListener('click', e => {{
  if (e.target.id === 'detail-modal') closeModal();
}});

// 导出 CSV
function exportCSV() {{
  let csv = "任务,部门,负责人,仪器,开始日期,时段,优先级,占用时段\\n";
  ASSIGNED.forEach(t => {{
    csv += `"${{t.task}}","${{t.department}}","${{t.assignee}}","${{t.instruments || ''}}","${{t.start_date}}","${{t.start_period}}","${{t.priority}}","${{t.slots || 1}}"\\n`;
  }});
  const blob = new Blob([csv], {{type: 'text/csv;charset=utf-8'}});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = '排班明细-' + new Date().toISOString().slice(0, 10) + '.csv';
  a.click();
  URL.revokeObjectURL(url);
}}

// 全屏切换
function toggleFullscreen() {{
  if (!document.fullscreenElement) document.documentElement.requestFullscreen();
  else document.exitFullscreen();
}}
</script>

</body>
</html>'''


DEPT_CLASS = {
    "procurement": "proc",
    "qc_incoming": "qc-in",
    "workshop": "work",
    "qc_finished": "qc-out",
    "qa_release": "qa",
    "sales": "sale",
}


def render_html(proj, schedule, pool, engine_result, gantt_data, all_risks):
    """生成完整 HTML。"""
    today = dt.date.today().isoformat()
    dept_count = len(proj.departments)
    person_count = len(pool.personnel) if pool else 0
    instr_count = len(pool.instruments) if pool else 0
    assigned = engine_result["assigned"]
    unassigned = engine_result["unassigned"]
    work_days = workdays_between(dt.date.fromisoformat(proj.start_date),
                                 dt.date.fromisoformat(proj.deadline))
    high_risks = len([r for r in all_risks if r.get("level") == "高"])
    med_risks = len([r for r in all_risks if r.get("level") == "中"])

    # 部门筛选选项
    dept_options = "\n".join(
        f'<option value="{d}">{DEPARTMENTS.get(d,{}).get("name",d)}</option>'
        for d in proj.departments
    )

    # 日期列
    start = dt.date.fromisoformat(proj.start_date)
    end = dt.date.fromisoformat(proj.deadline)
    date_headers = ""
    work_day_list = []
    cur = start
    today_obj = dt.date.today()
    while cur <= end:
        wd = WEEKDAY_CN[cur.weekday()]
        weekend_cls = "" if is_workday(cur) else "weekend"
        today_cls = " today" if cur == today_obj else ""
        date_headers += f'<th class="{weekend_cls}{today_cls}">{cur.strftime("%m-%d")}<br><span style="font-size:9px">{wd}</span></th>\n'
        if is_workday(cur):
            work_day_list.append(cur)
        cur += dt.timedelta(days=1)

    # 甘特图行（按部门+人员分组）
    gantt_rows = ""
    if gantt_data:
        # 按人员分组
        person_data = {}
        for item in gantt_data:
            person = item["resource"]
            dept = item["department"]
            if person not in person_data:
                person_data[person] = {"dept": dept, "slots": set()}
            person_data[person]["slots"].add((item["start_date"], item["start_period"]))

        # 按部门顺序输出
        for dept_id in proj.departments:
            dept_name = DEPARTMENTS.get(dept_id, {}).get("name", dept_id)
            dept_persons = [p for p in person_data if person_data[p]["dept"] == dept_id]
            for person in dept_persons:
                gantt_rows += f'<tr data-dept="{dept_id}" data-priority="高">\n'
                gantt_rows += f'<td class="row-header">{dept_name} / {person}</td>\n'
                # 找到该人员的所有任务（合并跨日时段的连续任务）
                person_tasks = [t for t in gantt_data if t["resource"] == person]
                task_ranges = {}
                for t in person_tasks:
                    key = t["task"]
                    if key not in task_ranges:
                        task_ranges[key] = {
                            "start_date": t["start_date"],
                            "start_period": t["start_period"],
                            "end_date": t["start_date"],
                            "end_period": t["start_period"],
                            "department": t["department"],
                            "instruments": t["instruments"],
                        }
                    else:
                        # 扩展
                        ex = task_ranges[key]
                        if t["start_date"] > ex["end_date"]:
                            ex["end_date"] = t["start_date"]
                            ex["end_period"] = t["start_period"]
                        elif t["start_date"] == ex["end_date"] and t["start_period"] == "下午":
                            ex["end_period"] = "下午"

                booked_ranges = []
                for tname, info in task_ranges.items():
                    cur_d = dt.date.fromisoformat(info["start_date"])
                    end_d = dt.date.fromisoformat(info["end_date"])
                    while cur_d <= end_d:
                        if is_workday(cur_d):
                            for p in ["上午", "下午"]:
                                if cur_d == end_d and p == "下午" and info["end_period"] != "下午":
                                    continue
                                if cur_d.strftime("%Y-%m-%d") == info["start_date"] and p == "上午" and info["start_period"] != "上午":
                                    continue
                                booked_ranges.append((cur_d.isoformat(), p, tname, info))
                        cur_d += dt.timedelta(days=1)

                for day in work_day_list:
                    ds = day.isoformat()
                    am_match = next((r for r in booked_ranges if r[0] == ds and r[1] == "上午"), None)
                    pm_match = next((r for r in booked_ranges if r[0] == ds and r[1] == "下午"), None)
                    am_html = ""
                    pm_html = ""
                    if am_match:
                        d, p, tname, info = am_match
                        cls = DEPT_CLASS.get(info["department"], "")
                        am_html = f'<div class="bar {cls}" onclick="showDetail(\'{tname}\')" title="{tname}|{info["instruments"]}">{tname[:6]}</div>'
                    if pm_match:
                        d, p, tname, info = pm_match
                        cls = DEPT_CLASS.get(info["department"], "")
                        pm_html = f'<div class="bar {cls}" onclick="showDetail(\'{tname}\')" title="{tname}|{info["instruments"]}">{tname[:6]}</div>'
                    gantt_rows += f'<td class="cell">{am_html}<br>{pm_html}</td>\n'
                gantt_rows += '</tr>\n'

    # 人员统计
    person_rows = ""
    if pool:
        for name in pool.personnel:
            wl = pool.get_person_workload(name)
            dept = pool.personnel[name].get("department", "")
            dept_name = DEPARTMENTS.get(dept, {}).get("name", dept)
            booked = wl["booked_slots"]
            total = wl["total_slots"]
            pct = booked / total if total > 0 else 0
            bar_cls = "full" if pct > 0.9 else "high" if pct > 0.6 else "medium" if pct > 0.3 else ""
            bar_w = max(int(pct * 80), 2)
            person_rows += f'<tr><td class="row-header">{name}</td><td class="row-header">{dept_name}</td><td>{booked}/{total}</td><td><div class="stat-bar {bar_cls}" style="width:{bar_w}px"></div>{wl["utilization"]}</td><td>{wl["task_count"]}</td></tr>\n'

    # 仪器统计
    instr_rows = ""
    if pool:
        for name in pool.instruments:
            iu = pool.get_instrument_utilization(name)
            inst = pool.instruments[name]
            dept_name = DEPARTMENTS.get(inst.get("location", ""), {}).get("name", inst.get("location", "-"))
            cal = inst.get("cal_due", "-")
            shared_tag = " 🔗" if inst.get("shared") else ""
            booked = iu["booked_slots"]
            avail = iu["available_slots"]
            pct = booked / avail if avail > 0 else 0
            bar_cls = "full" if pct > 0.9 else "high" if pct > 0.6 else "medium" if pct > 0.3 else ""
            bar_w = max(int(pct * 80), 2)
            # 校准过期预警
            cal_warning = ""
            if cal and cal != "-":
                try:
                    cal_d = dt.date.fromisoformat(cal)
                    if cal_d < end:
                        cal_warning = " 🔴过期"
                    elif (cal_d - end).days < 30:
                        cal_warning = " ⚠️临近"
                except ValueError:
                    pass
            instr_rows += f'<tr><td class="row-header">{name}{shared_tag}</td><td>{inst.get("model","-")}</td><td>{dept_name}</td><td>{cal}{cal_warning}</td><td><div class="stat-bar {bar_cls}" style="width:{bar_w}px"></div>{iu["utilization"]}</td><td>{", ".join(iu["departments"]) or "-"}</td></tr>\n'

    # 风险详情
    risks_html = ""
    if all_risks:
        contingency_map = {
            "校准过期": "启用备用仪器 / 借仪器 / 委托第三方加急校准",
            "校准临近": "提前30天申请校准，避开排班期",
            "试剂效期过期": "紧急采购 / 借用 / 工作对照品 / 外检",
            "试剂效期临近": "紧急采购新批号，做新旧批号对照验证",
            "单点故障": "启动备份人员 / 外包第三方 / 推迟任务",
            "缓冲不足": "提前启动 / 通知客户延迟 / 并行合并任务",
            "赶工": "压缩上游环节 / 增加临时人员 / 推迟交货",
            "仪器冲突": "错峰使用 / 重新排期",
            "人员跨部门冲突": "改派备份人员 / 调整任务日期",
            "技能不匹配": "安排带教 / 改派 / 紧急培训",
            "培养周期冲突": "紧急外检 / 改快速方法 / 分批放行 / 推迟交货",
            "仪器瓶颈": "错峰使用 / 外检 / 租赁 / 优先级排序",
            "OOS缓冲不足": "24h内启动调查 / 偏差分析 / 召回评估",
        }
        for r in all_risks:
            level = r.get("level", "")
            level_cls = {"高": "high", "中": "medium", "低": "low"}.get(level, "")
            contingency = contingency_map.get(r.get("type", ""), "见风险看板详细方案")
            risks_html += f'''<div class="risk-card {level_cls}">
<div class="risk-title">{level} | {r.get("type","")}</div>
<div class="risk-msg">{r["message"]}</div>
<div class="risk-contingency"><strong>应急方案：</strong>{contingency}</div>
</div>
'''
    else:
        risks_html = '<div class="risk-card low"><div class="risk-title">✅ 暂无风险</div></div>'

    # 资源池摘要
    resource_html = ""
    if pool:
        resource_html += f'<p style="color:#8b949e">人员 {len(pool.personnel)} 人 · 仪器 {len(pool.instruments)} 台 · 试剂 {len(pool.reagents)} 种</p>'
        if pool.reagents:
            resource_html += '<h3>🧪 试剂/标准品</h3><table class="stat-table"><thead><tr><th class="row-header">名称</th><th>类别</th><th>效期</th><th>状态</th></tr></thead><tbody>'
            for name, r in pool.reagents.items():
                status = "✅ 正常"
                if r.get("expiry"):
                    try:
                        exp = dt.date.fromisoformat(r["expiry"])
                        if exp < end:
                            status = "🔴 过期"
                        elif (exp - end).days < 30:
                            status = "⚠️ 临近"
                    except ValueError:
                        pass
                resource_html += f'<tr><td class="row-header">{name}</td><td>{r.get("category","-")}</td><td>{r.get("expiry","-")}</td><td>{status}</td></tr>'
            resource_html += '</tbody></table>'

    unassigned_class = "danger" if unassigned > 0 else "success"
    high_class = "danger" if high_risks > 0 else "success"
    med_class = "warning" if med_risks > 0 else "success"

    return HTML_TEMPLATE.format(
        title=proj.project_name, today=today,
        dept_count=dept_count, person_count=person_count, instr_count=instr_count,
        assigned=assigned, unassigned=unassigned, work_days=work_days,
        high_risks=high_risks, med_risks=med_risks,
        unassigned_class=unassigned_class, high_class=high_class, med_class=med_class,
        dept_options=dept_options,
        date_headers=date_headers, gantt_rows=gantt_rows,
        person_rows=person_rows, instr_rows=instr_rows,
        risks_html=risks_html, resource_html=resource_html,
        total_risks=len(all_risks),
        assigned_json=json.dumps(engine_result["tasks"], ensure_ascii=False),
        risks_json=json.dumps([{"type": r.get("type"), "level": r.get("level"), "message": r["message"]} for r in all_risks], ensure_ascii=False),
    )


def main():
    parser = argparse.ArgumentParser(description="生成可视化排班HTML")
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--drug-name", default="")
    parser.add_argument("--batch-no", default="")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--deadline", required=True)
    parser.add_argument("--departments", default=",".join(DEFAULT_ORDER))
    parser.add_argument("--dept-durations", default="{}")
    parser.add_argument("--personnel-json", default="[]")
    parser.add_argument("--instruments-json", default="[]")
    parser.add_argument("--test-items-json", default="[]")
    parser.add_argument("--reagents-json", default="[]")
    parser.add_argument("--output", "-o", default="排班可视化.html")
    args = parser.parse_args()

    start = dt.date.fromisoformat(args.start_date)
    deadline = dt.date.fromisoformat(args.deadline)
    departments = [d.strip() for d in args.departments.split(",")]
    dept_durations = json.loads(args.dept_durations)
    personnel = json.loads(args.personnel_json)
    instruments = json.loads(args.instruments_json)
    test_items = json.loads(args.test_items_json)
    reagents = json.loads(args.reagents_json)

    proj = ProjectInfo(
        project_name=args.project_name, drug_name=args.drug_name,
        batch_no=args.batch_no, start_date=args.start_date,
        deadline=args.deadline, departments=departments,
    )
    schedule = reverse_schedule(deadline, dept_durations, departments)

    # 运行排程
    pool = ResourcePool(start, deadline)
    for p in personnel:
        pool.register_person(**{k: v for k, v in p.items() if k in ["name","department","level","skills","note","available_from","available_until"]})
    for i in instruments:
        pool.register_instrument(**{k: v for k, v in i.items() if k in ["name","model","location","cal_due","status","shared","qty","switch_buffer_min"]})
    for r in reagents:
        pool.register_reagent(**{k: v for k, v in r.items() if k in ["name","category","expiry","quantity","min_quantity","supplier"]})

    tasks = []
    for t in test_items:
        dept_id = t.get("department", "")
        ds = schedule.get(dept_id, {})
        earliest = ds.get("start", start)
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
            "depends_on": t.get("depends_on", ""),
            "earliest_start": earliest.isoformat() if isinstance(earliest, dt.date) else str(earliest),
            "required_skills": t.get("required_skills", ""),
        })

    engine = SchedulingEngine(pool)
    result = engine.auto_schedule(tasks)
    gantt = engine.generate_gantt_data()
    risks = detect_all_risks(proj, schedule, personnel, instruments, test_items, reagents, pool)

    html = render_html(proj, schedule, pool, result, gantt, risks)
    Path(args.output).write_text(html, encoding="utf-8")
    print(f"✅ 可视化HTML已生成: {args.output}")
    print(f"   任务: {result['assigned']} 分配 / {result['unassigned']} 未分配")
    print(f"   风险: {len(risks)} 项（🔴{len([r for r in risks if r.get('level')=='高'])} / ⚠️{len([r for r in risks if r.get('level')=='中'])}）")


if __name__ == "__main__":
    main()