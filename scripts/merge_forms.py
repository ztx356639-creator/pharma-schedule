#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
部门表单汇总 → 排班参数。

读取各部门的 Markdown 表单，提取结构化数据，
生成 scaffold_pharma.py / visualize.py 所需的参数。

用法：
    python3 merge_forms.py --forms-dir forms --project-name "XX" --start-date 2026-07-01 --deadline 2026-08-15 --output merged.json
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path


def parse_markdown_table(text: str) -> list[dict]:
    """解析 Markdown 表格 → list[dict]。"""
    lines = [l.strip() for l in text.split("\n") if l.strip().startswith("|")]
    if len(lines) < 2:
        return []
    headers = [h.strip() for h in lines[0].strip("|").split("|")]
    rows = []
    for line in lines[2:]:  # 跳过表头和分隔行
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) == len(headers):
            rows.append(dict(zip(headers, cells)))
    return rows


def extract_sections(text: str) -> dict:
    """按 ## 二级标题切分。如果有 ### 三级标题切分，并合并到父级。"""
    sections = {}
    current = None
    buf = []
    for line in text.split("\n"):
        ls = line.strip()
        # 先识别 ###，再识别 ##（避免 ## 匹配到 ###）
        if ls.startswith("### "):
            buf.append("\n## " + ls[4:].strip())
            continue
        m2 = re.match(r"^##\s+(.+)", ls)
        if m2:
            if current:
                sections[current] = "\n".join(buf).strip()
            current = m2.group(1).strip()
            buf = []
        else:
            buf.append(line)
    if current:
        sections[current] = "\n".join(buf).strip()
    return sections


# ============================================================
# 部门解析
# ============================================================

def parse_procurement(text: str) -> dict:
    """解析采购部表单。"""
    sections = extract_sections(text)
    info = {}
    for k, v in sections.items():
        if "基本信息" in k:
            for line in v.split("\n"):
                m = re.match(r"^\|\s*(.+?)\s*\|\s*(.+?)\s*\|", line)
                if m and m.group(1) != "字段":
                    key, val = m.group(1).strip(), m.group(2).strip()
                    if val and val not in ("", "（如 ...）"):
                        info[key] = val
        elif "采购人员" in k:
            info["采购人员"] = parse_markdown_table(v)
        elif "原辅料" in k:
            info["原辅料"] = parse_markdown_table(v)
        elif "包材" in k:
            info["包材"] = parse_markdown_table(v)
        elif "检验试剂" in k or "标准品" in k or "采购" in k:
            # 含子节"### 标准品/对照品"、"### 色谱柱"、"### 化学试剂"
            subsections = extract_subsections(v)
            for sub_k, sub_v in subsections.items():
                if "标准品" in sub_k or "对照品" in sub_k:
                    info["标准品"] = parse_markdown_table(sub_v)
                elif "色谱柱" in sub_k:
                    info["色谱柱"] = parse_markdown_table(sub_v)
                elif "化学试剂" in sub_k:
                    info["化学试剂"] = parse_markdown_table(sub_v)
                elif "培养基" in sub_k:
                    info["培养基"] = parse_markdown_table(sub_v)
                elif "耗材" in sub_k:
                    info["耗材"] = parse_markdown_table(sub_v)
    return info


def _filter_reagent_table(rows: list, name_col: str = "名称") -> list:
    """过滤试剂表格，去掉表头噪音行。"""
    out = []
    for r in rows:
        name = r.get(name_col, "").strip()
        if not name or name in ("名称", "------") or "货期" in name:
            continue
        out.append(r)
    return out


def extract_subsections(text: str) -> dict:
    """从带 ## 子节标记的文本中提取子节。"""
    subsections = {}
    current = None
    buf = []
    for line in text.split("\n"):
        m2 = re.match(r"^##\s+(.+)", line.strip())
        if m2:
            if current:
                subsections[current] = "\n".join(buf).strip()
            current = m2.group(1).strip()
            buf = []
        else:
            buf.append(line)
    if current:
        subsections[current] = "\n".join(buf).strip()
    return subsections


def parse_qc(text: str, dept: str) -> dict:
    """解析 QC 表单（来料或成品）。"""
    sections = extract_sections(text)
    info = {"部门": dept, "检验项目": [], "人员": [], "仪器": [], "技能矩阵": []}

    person_section = "QC 来料人员" if dept == "qc_incoming" else "QC 成品人员"
    inst_section = "三、检验仪器" if dept == "qc_incoming" else "三、检验仪器"

    for k, v in sections.items():
        # 人员表
        if (k == person_section or k == "二、QC 成品人员" or k == "二、QC 来料人员"):
            tables = []
            for block in v.split("\n\n"):
                if "能力矩阵" in block:
                    continue
                tables.extend(parse_markdown_table(block))
            info["人员"] = tables
        elif "能力矩阵" in k:
            info["技能矩阵"] = parse_markdown_table(v)
        elif k == inst_section:
            info["仪器"] = parse_markdown_table(v)
        else:
            # 扫描子节（## 标题）找到检验项目
            subsections = extract_subsections(v)
            for sub_k, sub_v in subsections.items():
                if any(kw in sub_k for kw in ["化学鉴别", "性状", "鉴别", "含量", "杂质", "检查", "微生物", "无菌"]):
                    for r in parse_markdown_table(sub_v):
                        if r.get("检验项目"):
                            info["检验项目"].append(r)
    return info


def parse_workshop(text: str) -> dict:
    """解析车间表单。"""
    sections = extract_sections(text)
    info = {"人员": [], "工序": [], "设备": []}
    for k, v in sections.items():
        if "车间生产人员" in k:
            tables = []
            for block in v.split("\n\n"):
                if "能力矩阵" in block:
                    continue
                tables.extend(parse_markdown_table(block))
            info["人员"] = tables
        elif k == "二、本次车间生产人员":
            tables = []
            for block in v.split("\n\n"):
                if "能力矩阵" in block:
                    continue
                tables.extend(parse_markdown_table(block))
            info["人员"] = tables
        elif k == "四、生产设备清单" or "设备清单" in k:
            info["设备"] = parse_markdown_table(v)
        else:
            # 处理"三、生产工序安排"含 ### 准备阶段/### 核心生产 子节
            subsections = extract_subsections(v)
            for sub_v in subsections.values():
                tables = parse_markdown_table(sub_v)
                for t in tables:
                    if t.get("工序"):
                        info["工序"].append(t)
    return info


def parse_qa(text: str) -> dict:
    """解析 QA 表单。"""
    sections = extract_sections(text)
    info = {"审核分工": [], "QA人员": []}
    for k, v in sections.items():
        if "二、QA 人员" in k or k == "二、QA 人员":
            info["QA人员"] = parse_markdown_table(v)
        elif "三、审核分工" in k or k == "三、审核分工安排":
            info["审核分工"] = parse_markdown_table(v)
    return info


def parse_sales(text: str) -> dict:
    """解析销售表单。"""
    sections = extract_sections(text)
    info = {"订单信息": {}, "运输要求": {}, "销售人员": []}
    for k, v in sections.items():
        if "一、订单" in k:
            for line in v.split("\n"):
                m = re.match(r"^\|\s*(.+?)\s*\|\s*(.+?)\s*\|", line)
                if m and m.group(1) != "字段":
                    key, val = m.group(1).strip(), m.group(2).strip()
                    if val:
                        info["订单信息"][key] = val
        elif "三、运输" in k:
            for line in v.split("\n"):
                m = re.match(r"^\|\s*(.+?)\s*\|\s*(.+?)\s*\|", line)
                if m and m.group(1) != "字段":
                    key, val = m.group(1).strip(), m.group(2).strip()
                    if val:
                        info["运输要求"][key] = val
        elif "五、销售人员" in k or k == "五、销售人员":
            info["销售人员"] = parse_markdown_table(v)
    return info


# ============================================================
# 转换为 scaffold 参数
# ============================================================

def convert_to_scaffold_params(merged: dict) -> dict:
    """合并后的数据 → scaffold_pharma.py 需要的 JSON。"""
    out = {
        "personnel": [],
        "instruments": [],
        "reagents": [],
        "test_items": [],
        "project_meta": {},
    }

    # 人员：合并各部门人员
    dept_id_map = {
        "采购部": "procurement",
        "采购人员": "procurement",
        "QC来料检验": "qc_incoming",
        "QC成品检验": "qc_finished",
        "车间生产": "workshop",
        "QA放行": "qa_release",
        "销售发货": "sales",
    }
    for dept_name, persons in merged.get("by_dept_persons", {}).items():
        dept_id = dept_id_map.get(dept_name, dept_name)
        for p in persons:
            name = p.get("姓名", "").strip()
            if not name:
                continue
            out["personnel"].append({
                "name": name,
                "department": dept_id,
                "level": p.get("级别", ""),
                "skills": p.get("擅长", p.get("技能", "")),
                "note": p.get("备注", ""),
            })

    # 仪器：合并各部门
    for inst_list in merged.get("by_dept_instruments", {}).values():
        for inst in inst_list:
            name = inst.get("仪器", inst.get("设备", "")).strip()
            if not name or "—" in name:
                continue
            out["instruments"].append({
                "name": name,
                "model": inst.get("型号", ""),
                "location": inst.get("位置", inst.get("所在部门", "")),
                "cal_due": inst.get("校准到期", inst.get("下次校准", "")),
                "status": inst.get("状态", "正常"),
            })

    # 试剂/标准品/耗材
    reagent_data = merged.get("reagents", {})
    for std in _filter_reagent_table(reagent_data.get("标准品", [])):
        out["reagents"].append({
            "name": std.get("名称", ""), "category": "对照品",
            "expiry": std.get("当前效期", std.get("效期", "")),
        })
    for col in _filter_reagent_table(reagent_data.get("色谱柱", [])):
        out["reagents"].append({
            "name": col.get("名称", ""), "category": "色谱柱",
            "lead_time_days": col.get("货期", ""),
        })
    for chem in _filter_reagent_table(reagent_data.get("化学试剂", [])):
        out["reagents"].append({
            "name": chem.get("名称", ""), "category": "试剂",
        })
    for med in _filter_reagent_table(reagent_data.get("培养基", [])):
        out["reagents"].append({
            "name": med.get("名称", ""), "category": "培养基",
            "expiry": med.get("效期", ""),
        })
    for con in _filter_reagent_table(reagent_data.get("耗材", [])):
        out["reagents"].append({
            "name": con.get("名称", ""), "category": "耗材",
        })

    # 任务：合并各部门
    for dept_name, tasks in merged.get("by_dept_tasks", {}).items():
        dept_id = dept_id_map.get(dept_name, dept_name)
        for t in tasks:
            name = t.get("检验项目", t.get("工序", t.get("任务", ""))).strip()
            if not name:
                continue
            assignee = t.get("负责人", t.get("操作员", "")).strip()
            inst = t.get("仪器", t.get("设备", "")).strip()
            dur = t.get("耗时", t.get("预计耗时", "")).strip()
            priority = t.get("优先级", "普通").strip()
            out["test_items"].append({
                "name": name,
                "department": dept_id,
                "assignee": assignee,
                "instruments": inst,
                "duration": dur,
                "priority": priority,
            })

    return out


# ============================================================
# 主流程
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="汇总部门表单 → 排班参数")
    parser.add_argument("--forms-dir", required=True, help="表单目录（forms/）")
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--deadline", required=True)
    parser.add_argument("--output", "-o", default="merged.json")
    args = parser.parse_args()

    forms_dir = Path(args.forms_dir)
    if not forms_dir.exists():
        print(f"❌ 表单目录不存在: {forms_dir}")
        sys.exit(1)

    # 加载各部门的表单
    form_data = {}
    dept_map = {
        "procurement": "采购部信息收集表.md",
        "qc_incoming": "QC来料检验信息收集表.md",
        "workshop": "车间生产信息收集表.md",
        "qc_finished": "QC成品检验信息收集表.md",
        "qa_release": "QA放行信息收集表.md",
        "sales": "销售发货信息收集表.md",
    }
    for dept, filename in dept_map.items():
        path = forms_dir / dept / filename
        if path.exists():
            form_data[dept] = path.read_text(encoding="utf-8")
            print(f"✅ 加载 {dept}: {filename}")
        else:
            print(f"⚠️ 缺失 {dept}: {filename}")

    # 解析
    merged = {
        "by_dept_persons": {},
        "by_dept_instruments": {},
        "by_dept_tasks": {},
        "reagents": {},
    }
    if "procurement" in form_data:
        info = parse_procurement(form_data["procurement"])
        merged["by_dept_persons"]["采购部"] = info.get("采购人员", [])
        merged["reagents"]["标准品"] = info.get("标准品", [])
        merged["reagents"]["色谱柱"] = info.get("色谱柱", [])
        merged["reagents"]["化学试剂"] = info.get("化学试剂", [])
        merged["reagents"]["培养基"] = info.get("培养基", [])
        merged["reagents"]["耗材"] = info.get("耗材", [])

    if "qc_incoming" in form_data:
        info = parse_qc(form_data["qc_incoming"], "qc_incoming")
        merged["by_dept_persons"]["QC来料检验"] = info.get("人员", [])
        merged["by_dept_instruments"]["qc_incoming"] = info.get("仪器", [])
        merged["by_dept_tasks"]["QC来料检验"] = info.get("检验项目", [])

    if "qc_finished" in form_data:
        info = parse_qc(form_data["qc_finished"], "qc_finished")
        merged["by_dept_persons"]["QC成品检验"] = info.get("人员", [])
        merged["by_dept_instruments"]["qc_finished"] = info.get("仪器", [])
        merged["by_dept_tasks"]["QC成品检验"] = info.get("检验项目", [])

    if "workshop" in form_data:
        info = parse_workshop(form_data["workshop"])
        merged["by_dept_persons"]["车间生产"] = info.get("人员", [])
        merged["by_dept_instruments"]["workshop"] = info.get("设备", [])
        merged["by_dept_tasks"]["车间生产"] = info.get("工序", [])

    if "qa_release" in form_data:
        info = parse_qa(form_data["qa_release"])
        merged["by_dept_persons"]["QA放行"] = info.get("QA人员", [])
        merged["by_dept_tasks"]["QA放行"] = info.get("审核分工", [])

    if "sales" in form_data:
        info = parse_sales(form_data["sales"])
        merged["by_dept_persons"]["销售发货"] = info.get("销售人员", [])

    # 转换为 scaffold 参数
    params = convert_to_scaffold_params(merged)
    params["project_meta"] = {
        "project_name": args.project_name,
        "start_date": args.start_date,
        "deadline": args.deadline,
    }

    # 写入
    Path(args.output).write_text(json.dumps(params, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ 汇总完成: {args.output}")
    print(f"   人员: {len(params['personnel'])} 人")
    print(f"   仪器: {len(params['instruments'])} 台")
    print(f"   试剂: {len(params['reagents'])} 种")
    print(f"   任务: {len(params['test_items'])} 项")
    print(f"\n   下一步:")
    print(f"   1. 检视 {args.output}")
    print(f"   2. 手动补充缺失项（如人员/仪器）")
    print(f"   3. 运行排班脚本")


if __name__ == "__main__":
    main()