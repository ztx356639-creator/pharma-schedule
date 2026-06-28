#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
药厂排班数据收集工具 v1。
用途：在排班实际执行后，收集每项任务的实际完成时间、实际负责人、
实际耗时、OOS信息、偏差信息等。

功能：
- 从模板生成数据收集表（CSV/Markdown）
- 解析收集表（CSV → 字典）
- 对比计划 vs 实际（自动算偏差）
- 追加到历史数据库（JSONL）
- 生成回顾分析报告
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Optional

# ============================================================
# 数据收集表模板
# ============================================================

COLLECTION_TEMPLATE_CSV = """任务名称,部门,计划日期,计划时段,计划负责人,计划仪器,计划耗时,实际开始,实际结束,实际负责人,实际耗时,实际仪器,完成状态,OOS,偏差说明,备注
{rows}
"""

COLLECTION_TEMPLATE_MD = """# {project_name} — 实际执行数据收集表

> 项目: {project_name} | 批号: {batch_no} | 截止: {deadline}
> 收集人: _________ | 收集日期: _________
> 排班生成时间: {generated_at}

## 填写说明

1. **实际开始/结束**：填实际执行的日期，格式 YYYY-MM-DD
2. **实际负责人**：可能与计划负责人不同（如临时换人）
3. **实际耗时**：填实际用的时间（如 3h、1.5天）
4. **完成状态**：✅ 已完成 / ❌ 未完成 / 🔄 进行中 / ⏸ 暂停
5. **OOS**：是/否（Out Of Specification，超标）
6. **偏差说明**：实际与计划不符的原因

---

## 任务执行记录

| 序号 | 任务 | 部门 | 计划日期 | 计划时段 | 计划负责人 | 计划仪器 | 计划耗时 | 实际开始 | 实际结束 | 实际负责人 | 实际耗时 | 实际仪器 | 完成状态 | OOS | 偏差说明 | 备注 |
|------|------|------|----------|----------|------------|----------|----------|----------|----------|------------|----------|----------|------|------|----------|------|
{rows}
"""

# ============================================================
# 数据收集模板生成
# ============================================================

def generate_collection_template(project_name: str, batch_no: str, deadline: str,
                                  tasks: list, output_path: str):
    """根据排班计划生成数据收集表。"""
    rows_md = ""
    rows_csv = []
    for i, t in enumerate(tasks, 1):
        # Markdown
        rows_md += f"| {i} | {t.get('name','-')} | {t.get('department','-')} | {t.get('start_date','')} | {t.get('start_period','')} | {t.get('assignee','')} | {t.get('instruments','')} | {t.get('duration_hours','')}h | | | | | | | | |\n"
        # CSV
        rows_csv.append([
            t.get('name', ''), t.get('department', ''),
            t.get('start_date', ''), t.get('start_period', ''),
            t.get('assignee', ''), t.get('instruments', ''),
            f"{t.get('duration_hours', '')}h",
            '', '', '', '', '', '', '', '', ''
        ])

    out = Path(output_path)
    if out.suffix.lower() == '.csv':
        with open(out, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['任务名称','部门','计划日期','计划时段','计划负责人','计划仪器','计划耗时','实际开始','实际结束','实际负责人','实际耗时','实际仪器','完成状态','OOS','偏差说明','备注'])
            for r in rows_csv:
                writer.writerow(r)
    else:
        content = COLLECTION_TEMPLATE_MD.format(
            project_name=project_name, batch_no=batch_no, deadline=deadline,
            generated_at=dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
            rows=rows_md,
        )
        out.write_text(content, encoding='utf-8')

    return str(out)

# ============================================================
# 数据解析
# ============================================================

def parse_csv(filepath: str) -> list[dict]:
    """解析收集后的 CSV 文件。"""
    records = []
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # 跳过完全空的行
            if not any(row.values()):
                continue
            records.append({
                "task": row.get("任务名称", "").strip(),
                "department": row.get("部门", "").strip(),
                "plan_date": row.get("计划日期", "").strip(),
                "plan_period": row.get("计划时段", "").strip(),
                "plan_assignee": row.get("计划负责人", "").strip(),
                "plan_instrument": row.get("计划仪器", "").strip(),
                "plan_duration": row.get("计划耗时", "").strip(),
                "actual_start": row.get("实际开始", "").strip(),
                "actual_end": row.get("实际结束", "").strip(),
                "actual_assignee": row.get("实际负责人", "").strip(),
                "actual_duration": row.get("实际耗时", "").strip(),
                "actual_instrument": row.get("实际仪器", "").strip(),
                "status": row.get("完成状态", "").strip(),
                "oos": row.get("OOS", "").strip(),
                "deviation": row.get("偏差说明", "").strip(),
                "note": row.get("备注", "").strip(),
            })
    return records

# ============================================================
# 偏差分析
# ============================================================

def parse_duration_to_hours(s: str) -> Optional[float]:
    """解析时长字符串为小时数。"""
    if not s:
        return None
    s = str(s).strip()
    try:
        if "天" in s:
            return float(s.replace("天", "").strip()) * 8
        elif "h" in s or "H" in s:
            return float(s.replace("h", "").replace("H", "").strip())
        else:
            return float(s)
    except ValueError:
        return None

def analyze_deviation(records: list) -> dict:
    """对比计划 vs 实际，生成偏差分析。"""
    total = len(records)
    completed = sum(1 for r in records if r["status"] in ["✅", "已完成", "是"])
    incomplete = total - completed
    oos_count = sum(1 for r in records if r["oos"] in ["是", "Y", "y", "yes"])

    # 日期偏差
    date_deviations = []
    time_deviations = []
    assignee_changes = []
    instrument_changes = []

    for r in records:
        # 日期偏差
        if r["plan_date"] and r["actual_start"]:
            try:
                plan = dt.date.fromisoformat(r["plan_date"])
                actual = dt.date.fromisoformat(r["actual_start"])
                diff = (actual - plan).days
                if diff != 0:
                    date_deviations.append({
                        "task": r["task"],
                        "plan": r["plan_date"],
                        "actual": r["actual_start"],
                        "delay_days": diff,
                    })
            except ValueError:
                pass

        # 耗时偏差
        plan_h = parse_duration_to_hours(r["plan_duration"])
        actual_h = parse_duration_to_hours(r["actual_duration"])
        if plan_h and actual_h:
            diff = actual_h - plan_h
            if abs(diff) > 0.5:
                time_deviations.append({
                    "task": r["task"],
                    "plan_hours": plan_h,
                    "actual_hours": actual_h,
                    "delta": diff,
                })

        # 人员变更
        if r["plan_assignee"] and r["actual_assignee"] and r["plan_assignee"] != r["actual_assignee"]:
            assignee_changes.append({
                "task": r["task"],
                "plan": r["plan_assignee"],
                "actual": r["actual_assignee"],
            })

        # 仪器变更
        if r["plan_instrument"] and r["actual_instrument"] and r["plan_instrument"] != r["actual_instrument"]:
            instrument_changes.append({
                "task": r["task"],
                "plan": r["plan_instrument"],
                "actual": r["actual_instrument"],
            })

    # 按时率
    on_time_rate = (completed - len([d for d in date_deviations if d["delay_days"] > 0])) / total if total > 0 else 0

    return {
        "summary": {
            "total_tasks": total,
            "completed": completed,
            "incomplete": incomplete,
            "oos_count": oos_count,
            "on_time_rate": f"{on_time_rate:.0%}",
            "avg_delay_days": sum(d["delay_days"] for d in date_deviations) / len(date_deviations) if date_deviations else 0,
        },
        "date_deviations": date_deviations,
        "time_deviations": time_deviations,
        "assignee_changes": assignee_changes,
        "instrument_changes": instrument_changes,
    }

# ============================================================
# 报告生成
# ============================================================

def generate_report(project_name: str, batch_no: str, records: list, analysis: dict) -> str:
    lines = [
        f"# {project_name} — 执行回顾报告\n",
        f"> 批号: {batch_no} | 报告日期: {dt.date.today().isoformat()}\n",
        "## 总体情况\n",
        "| 指标 | 数值 |",
        "|------|------|",
        f"| 总任务数 | {analysis['summary']['total_tasks']} |",
        f"| 已完成 | {analysis['summary']['completed']} |",
        f"| 未完成 | {analysis['summary']['incomplete']} |",
        f"| 完成率 | {analysis['summary']['completed']/analysis['summary']['total_tasks']*100:.0f}% |" if analysis['summary']['total_tasks'] else "| 完成率 | - |",
        f"| 按时完成率 | {analysis['summary']['on_time_rate']} |",
        f"| OOS 次数 | {analysis['summary']['oos_count']} |",
        f"| 平均延迟天数 | {analysis['summary']['avg_delay_days']:.1f} |" if analysis['summary']['avg_delay_days'] else "| 平均延迟天数 | 0 |",
        "",
    ]

    # 日期偏差
    if analysis['date_deviations']:
        lines.extend(["## 📅 日期偏差\n", "| 任务 | 计划 | 实际 | 延迟(天) |", "|------|------|------|----------|"])
        for d in analysis['date_deviations']:
            lines.append(f"| {d['task']} | {d['plan']} | {d['actual']} | {d['delay_days']:+d} |")
        lines.append("")

    # 耗时偏差
    if analysis['time_deviations']:
        lines.extend(["## ⏱️ 耗时偏差（>0.5h）\n", "| 任务 | 计划(h) | 实际(h) | 偏差(h) |", "|------|---------|---------|---------|"])
        for t in analysis['time_deviations']:
            lines.append(f"| {t['task']} | {t['plan_hours']:.1f} | {t['actual_hours']:.1f} | {t['delta']:+.1f} |")
        lines.append("")

    # 人员变更
    if analysis['assignee_changes']:
        lines.extend(["## 👥 人员变更\n", "| 任务 | 计划 | 实际 |", "|------|------|------|"])
        for c in analysis['assignee_changes']:
            lines.append(f"| {c['task']} | {c['plan']} | {c['actual']} |")
        lines.append("")

    # 仪器变更
    if analysis['instrument_changes']:
        lines.extend(["## 🔬 仪器变更\n", "| 任务 | 计划 | 实际 |", "|------|------|------|"])
        for c in analysis['instrument_changes']:
            lines.append(f"| {c['task']} | {c['plan']} | {c['actual']} |")
        lines.append("")

    # OOS 列表
    oos_records = [r for r in records if r["oos"] in ["是", "Y", "y", "yes"]]
    if oos_records:
        lines.extend(["## ⚠️ OOS（超标）记录\n", "| 任务 | 负责人 | 偏差说明 | 备注 |", "|------|--------|----------|------|"])
        for r in oos_records:
            lines.append(f"| {r['task']} | {r['actual_assignee'] or r['plan_assignee']} | {r['deviation']} | {r['note']} |")
        lines.append("")

    # 改进建议
    lines.extend(["## 💡 改进建议\n"])
    if analysis['date_deviations']:
        avg = sum(d['delay_days'] for d in analysis['date_deviations']) / len(analysis['date_deviations'])
        if avg > 0:
            lines.append(f"- 平均延迟 {avg:.1f} 天，下次预留更多缓冲")
    if analysis['summary']['oos_count'] > 0:
        lines.append(f"- 本次出现 {analysis['summary']['oos_count']} 次 OOS，建议加强方法验证和人员培训")
    if analysis['assignee_changes']:
        lines.append("- 人员变更较多，建议减少关键任务的人员变动")
    if not any([analysis['date_deviations'], analysis['summary']['oos_count'], analysis['assignee_changes']]):
        lines.append("- ✅ 执行顺利，无明显偏差")
    lines.append("")

    # 详细记录
    lines.extend(["## 详细执行记录\n", "| 任务 | 计划 | 实际 | 状态 | OOS | 偏差 |", "|------|------|------|------|-----|------|"])
    for r in records:
        lines.append(f"| {r['task']} | {r['plan_date']} {r['plan_period']} {r['plan_assignee']} | {r['actual_start']} {r['actual_assignee']} | {r['status']} | {r['oos']} | {r['deviation']} |")

    return "\n".join(lines)

# ============================================================
# 历史数据库（JSONL 追加）
# ============================================================

def append_history(history_file: str, project_name: str, batch_no: str,
                   records: list, analysis: dict):
    """追加到历史数据库。"""
    entry = {
        "timestamp": dt.datetime.now().isoformat(),
        "project": project_name,
        "batch_no": batch_no,
        "summary": analysis['summary'],
        "oos_count": analysis['summary']['oos_count'],
        "delay_count": len(analysis['date_deviations']),
        "assignee_changes": len(analysis['assignee_changes']),
        "records": records,
    }
    with open(history_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

# ============================================================
# 主流程
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="药厂排班数据收集与分析")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # 1. 生成模板
    p_gen = sub.add_parser("template", help="生成数据收集模板")
    p_gen.add_argument("--project-name", required=True)
    p_gen.add_argument("--batch-no", default="")
    p_gen.add_argument("--deadline", required=True)
    p_gen.add_argument("--tasks-json", required=True, help="排班结果JSON")
    p_gen.add_argument("--output", "-o", required=True, help="输出文件路径")

    # 2. 分析数据
    p_analyze = sub.add_parser("analyze", help="分析收集的数据")
    p_analyze.add_argument("--input", "-i", required=True, help="收集的CSV文件")
    p_analyze.add_argument("--project-name", default="")
    p_analyze.add_argument("--batch-no", default="")
    p_analyze.add_argument("--report", "-r", help="报告输出路径")
    p_analyze.add_argument("--history", help="历史数据库JSONL路径")

    args = parser.parse_args()

    if args.cmd == "template":
        tasks = json.loads(args.tasks_json)
        out = generate_collection_template(args.project_name, args.batch_no,
                                           args.deadline, tasks, args.output)
        print(f"✅ 数据收集模板已生成: {out}")

    elif args.cmd == "analyze":
        records = parse_csv(args.input)
        if not records:
            print("❌ CSV文件中没有有效数据")
            sys.exit(1)
        analysis = analyze_deviation(records)
        report = generate_report(args.project_name or "项目", args.batch_no or "", records, analysis)
        if args.report:
            Path(args.report).write_text(report, encoding='utf-8')
            print(f"✅ 报告已生成: {args.report}")
        if args.history:
            append_history(args.history, args.project_name or "项目",
                          args.batch_no or "", records, analysis)
            print(f"✅ 已追加到历史数据库: {args.history}")
        # 控制台输出汇总
        print(f"\n📊 汇总:")
        print(f"   总任务: {analysis['summary']['total_tasks']}")
        print(f"   完成: {analysis['summary']['completed']}")
        print(f"   OOS: {analysis['summary']['oos_count']}")
        print(f"   按时率: {analysis['summary']['on_time_rate']}")
        print(f"   日期偏差: {len(analysis['date_deviations'])}")
        print(f"   人员变更: {len(analysis['assignee_changes'])}")
        if not args.report:
            print("\n" + report)


if __name__ == "__main__":
    main()