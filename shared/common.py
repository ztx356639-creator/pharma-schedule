#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
共享数据结构和工具：部门定义、依赖关系、时间推导、风险检测、资源池排程。
v2: 修复多时段排程、依赖约束，新增10类风险检测。
"""
from __future__ import annotations
import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ============================================================
# 部门定义（新增 QA 部门）
# ============================================================
DEPARTMENTS = {
    "procurement": {
        "name": "采购部",
        "icon": "📦",
        "typical_duration_days": 7,
        "typical_tasks": [
            {"name": "物料需求确认", "duration": "0.5天"},
            {"name": "原辅料询价下单", "duration": "1天"},
            {"name": "原辅料到货验收", "duration": "0.5天"},
            {"name": "包材确认下单", "duration": "1天"},
            {"name": "包材到货验收", "duration": "0.5天"},
            {"name": "标准品/对照品采购", "duration": "1天"},
            {"name": "色谱柱采购", "duration": "0.5天"},
            {"name": "HPLC流动相试剂采购", "duration": "0.5天"},
            {"name": "微生物培养基采购", "duration": "0.5天"},
            {"name": "化学试剂采购", "duration": "0.5天"},
            {"name": "检验耗材采购（进样瓶/滤膜/吸头等）", "duration": "0.5天"},
            {"name": "试剂耗材到货验收+入库", "duration": "0.5天"},
        ],
        "depends_on": [],
        "blocks": ["qc_incoming"],
    },
    "qc_incoming": {
        "name": "QC来料检验",
        "icon": "🔬",
        "typical_duration_days": 3,
        "typical_tasks": [
            {"name": "取样", "duration": "0.5天"},
            {"name": "理化检验", "duration": "1-2天"},
            {"name": "微生物检验", "duration": "5天(培养)"},
            {"name": "出具检验报告", "duration": "0.5天"},
        ],
        "depends_on": ["procurement"],
        "blocks": ["workshop"],
    },
    "workshop": {
        "name": "车间生产",
        "icon": "🏭",
        "typical_duration_days": 5,
        "typical_tasks": [
            {"name": "称量配料", "duration": "0.5天"},
            {"name": "制粒/混合", "duration": "1天"},
            {"name": "压片/灌装", "duration": "1天"},
            {"name": "包衣/封装", "duration": "1天"},
            {"name": "内包装", "duration": "0.5天"},
            {"name": "外包装", "duration": "1天"},
        ],
        "depends_on": ["qc_incoming"],
        "blocks": ["qc_finished"],
    },
    "qc_finished": {
        "name": "QC成品检验",
        "icon": "🧪",
        "typical_duration_days": 5,
        "typical_tasks": [
            {"name": "取样", "duration": "0.5天"},
            {"name": "理化全项检验", "duration": "2-3天"},
            {"name": "微生物限度检验", "duration": "5天(培养)"},
            {"name": "稳定性考察(如需)", "duration": "长期"},
            {"name": "出具检验报告", "duration": "0.5天"},
        ],
        "depends_on": ["workshop"],
        "blocks": ["qa_release"],
    },
    "qa_release": {
        "name": "QA放行",
        "icon": "✅",
        "typical_duration_days": 2,
        "typical_tasks": [
            {"name": "放行资料审核", "duration": "0.5天"},
            {"name": "批记录审核", "duration": "0.5天"},
            {"name": "偏差/变更审核", "duration": "0.5天"},
            {"name": "QA放行签字", "duration": "0.5天"},
        ],
        "depends_on": ["qc_finished"],
        "blocks": ["sales"],
    },
    "sales": {
        "name": "销售发货",
        "icon": "🚚",
        "typical_duration_days": 2,
        "typical_tasks": [
            {"name": "发货准备", "duration": "0.5天"},
            {"name": "物流安排", "duration": "0.5天"},
            {"name": "出库发货", "duration": "0.5天"},
            {"name": "客户签收确认", "duration": "1-3天"},
        ],
        "depends_on": ["qa_release"],
        "blocks": [],
    },
}

# 默认流程顺序（含 QA）
DEFAULT_ORDER = ["procurement", "qc_incoming", "workshop", "qc_finished", "qa_release", "sales"]

# ============================================================
# 数据结构
# ============================================================
@dataclass
class ProjectInfo:
    """项目基础信息。"""
    project_name: str = ""
    drug_name: str = ""
    batch_no: str = ""
    batch_type: str = "常规生产"
    batch_size: str = ""
    standard: str = ""
    start_date: str = ""
    deadline: str = ""
    special: str = ""
    departments: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "project_name": self.project_name,
            "drug_name": self.drug_name,
            "batch_no": self.batch_no,
            "batch_type": self.batch_type,
            "batch_size": self.batch_size,
            "standard": self.standard,
            "start_date": self.start_date,
            "deadline": self.deadline,
            "special": self.special,
            "departments": self.departments,
        }

@dataclass
class TaskItem:
    """单个排班任务。"""
    name: str
    department: str
    assignee: str = ""
    instrument: str = ""
    start: str = ""
    end: str = ""
    duration: str = ""
    priority: str = "普通"
    depends_on: list = field(default_factory=list)
    status: str = "⬜"
    note: str = ""
    required_skills: str = ""  # 新增：所需技能

@dataclass
class Personnel:
    """人员信息。"""
    name: str
    department: str
    level: str = ""
    skills: str = ""
    note: str = ""
    available_from: str = ""   # 新增：可用开始日
    available_until: str = ""  # 新增：可用结束日（请假/培训）

@dataclass
class Instrument:
    """仪器信息。"""
    name: str
    model: str = ""
    location: str = ""
    qty: int = 1
    cal_due: str = ""
    status: str = "正常"
    shared: bool = False
    switch_buffer_min: int = 30  # 新增：方法切换缓冲时间(分钟)

@dataclass
class Reagent:
    """试剂/标准品信息。"""
    name: str
    category: str = ""       # "标准品" | "对照品" | "试剂" | "培养基" | "耗材"
    purity: str = ""
    expiry: str = ""         # 效期 YYYY-MM-DD
    quantity: str = ""        # 库存量
    min_quantity: str = ""    # 最低需要量
    supplier: str = ""
    lead_time_days: int = 0  # 采购周期

# ============================================================
# 时间推导
# ============================================================
WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

HOLIDAYS_2026 = [
    "2026-01-01", "2026-01-02",
    "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20",
    "2026-02-21", "2026-02-22", "2026-02-23",
    "2026-04-05", "2026-04-06", "2026-04-07",
    "2026-05-01", "2026-05-02", "2026-05-03", "2026-05-04",
    "2026-05-31", "2026-06-01", "2026-06-02",
    "2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04",
    "2026-10-05", "2026-10-06", "2026-10-07",
]
HOLIDAYS_2027 = [
    "2027-01-01",
    "2027-02-06", "2027-02-07", "2027-02-08", "2027-02-09",
    "2027-02-10", "2027-02-11", "2027-02-12",
    "2027-04-05",
    "2027-05-01", "2027-05-02", "2027-05-03",
    "2027-06-19", "2027-06-20", "2027-06-21",
    "2027-10-01", "2027-10-02", "2027-10-03", "2027-10-04",
    "2027-10-05", "2027-10-06", "2027-10-07",
]
ALL_HOLIDAYS = set(HOLIDAYS_2026 + HOLIDAYS_2027)

def is_workday(d: dt.date) -> bool:
    if d.weekday() >= 5:
        return False
    if d.isoformat() in ALL_HOLIDAYS:
        return False
    return True

def add_workdays(start: dt.date, days: int) -> dt.date:
    current = start
    added = 0
    while added < days:
        current += dt.timedelta(days=1)
        if is_workday(current):
            added += 1
    return current

def subtract_workdays(end: dt.date, days: int) -> dt.date:
    current = end
    subtracted = 0
    while subtracted < days:
        current -= dt.timedelta(days=1)
        if is_workday(current):
            subtracted += 1
    return current

def workdays_between(a: dt.date, b: dt.date) -> int:
    if a > b:
        a, b = b, a
    count = 0
    cur = a
    while cur <= b:
        if is_workday(cur):
            count += 1
        cur += dt.timedelta(days=1)
    return count

def reverse_schedule(deadline: dt.date, dept_durations: dict,
                     departments: list = None) -> dict:
    order = departments or DEFAULT_ORDER
    schedule = {}
    current_end = deadline
    for dept_id in reversed(order):
        duration = dept_durations.get(dept_id, DEPARTMENTS.get(dept_id, {}).get("typical_duration_days", 3))
        start = subtract_workdays(current_end, duration)
        schedule[dept_id] = {
            "start": start,
            "end": current_end,
            "duration_workdays": duration,
        }
        current_end = start
    return schedule

# ============================================================
# 资源池模型 v2
# ============================================================
@dataclass
class ResourceSlot:
    """资源的一个时间段占用。"""
    resource_name: str
    resource_type: str
    date: dt.date
    period: str
    task_name: str = ""
    task_department: str = ""
    locked: bool = False
    task_id: str = ""  # 新增：关联任务ID，用于多时段任务追踪

class ResourcePool:
    """资源池 v2：支持人员可用性、方法切换缓冲。"""
    def __init__(self, start: dt.date, end: dt.date):
        self.start = start
        self.end = end
        self.work_days = []
        cur = start
        while cur <= end:
            if is_workday(cur):
                self.work_days.append(cur)
            cur += dt.timedelta(days=1)
        
        self.personnel: dict[str, dict] = {}
        self.instruments: dict[str, dict] = {}
        self.rooms: dict[str, dict] = {}
        self.reagents: dict[str, dict] = {}  # 新增
        self.slots: dict[tuple, ResourceSlot] = {}
    
    def register_person(self, name: str, department: str, level: str = "",
                        skills: str = "", note: str = "",
                        available_from: str = "", available_until: str = ""):
        self.personnel[name] = {
            "department": department, "level": level, "skills": skills,
            "note": note, "available_from": available_from,
            "available_until": available_until,
        }
    
    def register_instrument(self, name: str, model: str = "", location: str = "",
                            cal_due: str = "", status: str = "正常",
                            shared: bool = False, qty: int = 1,
                            switch_buffer_min: int = 30):
        self.instruments[name] = {
            "model": model, "location": location, "cal_due": cal_due,
            "status": status, "shared": shared, "qty": qty,
            "switch_buffer_min": switch_buffer_min,
        }
    
    def register_room(self, name: str, room_type: str = "", capacity: int = 1,
                      location: str = ""):
        self.rooms[name] = {"type": room_type, "capacity": capacity, "location": location}
    
    def register_reagent(self, name: str, category: str = "", expiry: str = "",
                         quantity: str = "", min_quantity: str = "",
                         supplier: str = "", lead_time_days: int = 0):
        """注册试剂/标准品到资源池。"""
        self.reagents[name] = {
            "category": category, "expiry": expiry, "quantity": quantity,
            "min_quantity": min_quantity, "supplier": supplier,
            "lead_time_days": lead_time_days,
        }
    
    def is_available(self, resource_name: str, date: dt.date, period: str) -> bool:
        key = (resource_name, date, period)
        if key in self.slots:
            return False
        
        # 人员可用性检查（请假/培训）
        if resource_name in self.personnel:
            p = self.personnel[resource_name]
            if p.get("available_from"):
                try:
                    avail_from = dt.date.fromisoformat(p["available_from"])
                    if date < avail_from:
                        return False
                except ValueError:
                    pass
            if p.get("available_until"):
                try:
                    avail_until = dt.date.fromisoformat(p["available_until"])
                    if date > avail_until:
                        return False
                except ValueError:
                    pass
        
        # 仪器校准+状态检查
        if resource_name in self.instruments:
            inst = self.instruments[resource_name]
            if inst["cal_due"]:
                try:
                    cal = dt.date.fromisoformat(inst["cal_due"])
                    if cal < date:
                        return False
                except ValueError:
                    pass
            if inst["status"] != "正常":
                return False
        
        return True
    
    def book(self, resource_name: str, resource_type: str, date: dt.date,
             period: str, task_name: str = "", task_department: str = "",
             locked: bool = False, task_id: str = "") -> bool:
        if not self.is_available(resource_name, date, period):
            return False
        key = (resource_name, date, period)
        self.slots[key] = ResourceSlot(
            resource_name=resource_name, resource_type=resource_type,
            date=date, period=period, task_name=task_name,
            task_department=task_department, locked=locked, task_id=task_id,
        )
        return True
    
    def release(self, resource_name: str, date: dt.date, period: str):
        key = (resource_name, date, period)
        if key in self.slots and not self.slots[key].locked:
            del self.slots[key]
    
    def get_resource_schedule(self, resource_name: str) -> list[ResourceSlot]:
        result = []
        for day in self.work_days:
            for period in ["上午", "下午"]:
                key = (resource_name, day, period)
                if key in self.slots:
                    result.append(self.slots[key])
        return result
    
    def get_day_schedule(self, date: dt.date) -> dict[str, list[ResourceSlot]]:
        result = {"person": [], "instrument": [], "room": []}
        for key, slot in self.slots.items():
            if slot.date == date:
                result[slot.resource_type].append(slot)
        return result
    
    def get_available_periods(self, resource_name: str, date: dt.date) -> list[str]:
        available = []
        for period in ["上午", "下午"]:
            if self.is_available(resource_name, date, period):
                available.append(period)
        return available
    
    def get_person_workload(self, person_name: str) -> dict:
        booked = 0
        total = len(self.work_days) * 2
        tasks = set()
        for key, slot in self.slots.items():
            if slot.resource_name == person_name and slot.resource_type == "person":
                booked += 1
                if slot.task_name:
                    tasks.add(slot.task_name)
        return {
            "person": person_name,
            "total_slots": total,
            "booked_slots": booked,
            "utilization": f"{booked/total*100:.0f}%" if total > 0 else "0%",
            "task_count": len(tasks),
            "tasks": list(tasks),
        }
    
    def get_instrument_utilization(self, inst_name: str) -> dict:
        inst = self.instruments.get(inst_name, {})
        booked = 0
        total = len(self.work_days) * 2
        users = set()
        for key, slot in self.slots.items():
            if slot.resource_name == inst_name and slot.resource_type == "instrument":
                booked += 1
                users.add(slot.task_department)
        cal_blocked = 0
        if inst.get("cal_due"):
            try:
                cal = dt.date.fromisoformat(inst["cal_due"])
                for day in self.work_days:
                    if cal < day:
                        cal_blocked += 2
            except ValueError:
                pass
        return {
            "instrument": inst_name,
            "total_slots": total,
            "available_slots": total - cal_blocked,
            "booked_slots": booked,
            "utilization": f"{booked/(total-cal_blocked)*100:.0f}%" if (total-cal_blocked) > 0 else "N/A",
            "departments": list(users),
        }

# ============================================================
# 排程引擎 v2：支持多时段任务 + 依赖约束
# ============================================================
class SchedulingEngine:
    """排程引擎 v2。"""
    def __init__(self, pool: ResourcePool):
        self.pool = pool
        self.assigned_tasks: list[dict] = []
        self.unassigned_tasks: list[dict] = []
        self.conflicts: list[str] = []
        # 任务完成时间表: task_name -> (last_date, last_period)
        self.task_completion: dict[str, tuple[dt.date, str]] = {}
    
    def assign_task(self, task_name: str, department: str, assignee: str,
                    instruments: list[str] = None, duration_hours: float = 4,
                    priority: str = "普通", depends_on: str = "",
                    earliest_start: dt.date = None,
                    required_skills: str = "") -> bool:
        """
        分配任务到资源池。支持多时段任务。
        """
        instruments = instruments or []
        start_date = earliest_start or self.pool.start
        
        # 依赖约束：如果 depends_on 指定了前置任务，等前置完成后再开始
        if depends_on and depends_on in self.task_completion:
            dep_date, dep_period = self.task_completion[depends_on]
            # 前置任务完成后，下一个时段开始
            if dep_period == "上午":
                start_date = max(start_date, dep_date)
            else:
                start_date = max(start_date, add_workdays(dep_date, 1))
        
        # 计算需要几个时段
        slots_needed = max(1, int((duration_hours + 3) // 4))
        
        # 找连续可用的时间段
        booked_slots = []
        for day in self.pool.work_days:
            if day < start_date:
                continue
            for period in ["上午", "下午"]:
                if len(booked_slots) >= slots_needed:
                    break
                
                # 检查人员可用
                if not self.pool.is_available(assignee, day, period):
                    continue
                
                # 检查仪器可用
                inst_available = True
                for inst_name in instruments:
                    if not self.pool.is_available(inst_name, day, period):
                        inst_available = False
                        break
                if not inst_available:
                    continue
                
                # 预定
                task_id = f"{task_name}_{assignee}_{len(self.assigned_tasks)}"
                self.pool.book(assignee, "person", day, period,
                              task_name=task_name, task_department=department,
                              task_id=task_id)
                for inst_name in instruments:
                    self.pool.book(inst_name, "instrument", day, period,
                                  task_name=task_name, task_department=department,
                                  task_id=task_id)
                booked_slots.append((day, period))
            
            if len(booked_slots) >= slots_needed:
                break
        
        if len(booked_slots) >= slots_needed:
            last_date, last_period = booked_slots[-1]
            self.assigned_tasks.append({
                "task": task_name, "department": department,
                "assignee": assignee, "instruments": instruments,
                "start_date": booked_slots[0][0].isoformat(),
                "start_period": booked_slots[0][1],
                "end_date": last_date.isoformat(),
                "end_period": last_period,
                "slots_used": len(booked_slots),
                "priority": priority,
                "required_skills": required_skills,
            })
            self.task_completion[task_name] = (last_date, last_period)
            return True
        
        # 无法分配
        self.unassigned_tasks.append({
            "task": task_name, "department": department,
            "assignee": assignee, "instruments": instruments,
            "reason": f"需要{slots_needed}个时段，资源不足",
        })
        self.conflicts.append(f"⚠️ {task_name} 无法分配给 {assignee}（需要{slots_needed}个时段，资源不足）")
        return False
    
    def auto_schedule(self, tasks: list[dict]) -> dict:
        """批量自动排程。"""
        priority_order = {"高": 0, "普通": 1, "低": 2}
        sorted_tasks = sorted(tasks, key=lambda t: (
            0 if t.get("depends_on") else 1,
            priority_order.get(t.get("priority", "普通"), 1),
            -len(t.get("instruments", [])),
        ))
        
        for task in sorted_tasks:
            earliest = None
            if task.get("earliest_start"):
                earliest = dt.date.fromisoformat(task["earliest_start"])
            
            self.assign_task(
                task_name=task["name"],
                department=task.get("department", ""),
                assignee=task.get("assignee", ""),
                instruments=task.get("instruments", []),
                duration_hours=task.get("duration_hours", 4),
                priority=task.get("priority", "普通"),
                depends_on=task.get("depends_on", ""),
                earliest_start=earliest,
                required_skills=task.get("required_skills", ""),
            )
        
        return {
            "assigned": len(self.assigned_tasks),
            "unassigned": len(self.unassigned_tasks),
            "conflicts": self.conflicts,
            "tasks": self.assigned_tasks,
            "unassigned_tasks": self.unassigned_tasks,
        }
    
    def generate_gantt_data(self) -> list[dict]:
        """生成甘特图数据。"""
        gantt = []
        for task in self.assigned_tasks:
            gantt.append({
                "task": task["task"],
                "resource": task["assignee"],
                "instruments": ", ".join(task["instruments"]) if task["instruments"] else "—",
                "start_date": task["start_date"],
                "start_period": task["start_period"],
                "end_date": task["end_date"],
                "end_period": task["end_period"],
                "slots": task.get("slots_used", 1),
                "department": task["department"],
            })
        gantt.sort(key=lambda x: (x["start_date"], 0 if x["start_period"] == "上午" else 1))
        return gantt

# ============================================================
# 风险检测 v2：10 类风险
# ============================================================

def detect_schedule_risks(schedule: dict) -> list:
    """检测排班时间风险。"""
    risks = []
    for dept_id, times in schedule.items():
        dept_name = DEPARTMENTS.get(dept_id, {}).get("name", dept_id)
        total = workdays_between(times["start"], times["end"])
        dur = times["duration_workdays"]
        buffer = total - dur
        if buffer < 0:
            risks.append({
                "type": "赶工", "level": "高",
                "department": dept_name,
                "message": f"🔴 {dept_name} 排班时间不足！需要 {dur} 工作日，但只有 {total} 天",
            })
        elif buffer < 2:
            risks.append({
                "type": "缓冲不足", "level": "中",
                "department": dept_name,
                "message": f"⚠️ {dept_name} 缓冲仅 {buffer} 天，风险较高",
            })
    return risks


def detect_instrument_conflicts(instruments: list, tasks: list) -> list:
    """检测仪器时间冲突。"""
    conflicts = []
    by_instrument = {}
    for t in tasks:
        if t.instrument:
            by_instrument.setdefault(t.instrument, []).append(t)
    for inst_name, inst_tasks in by_instrument.items():
        by_date = {}
        for t in inst_tasks:
            if t.start:
                by_date.setdefault(t.start, []).append(t)
        for date, date_tasks in by_date.items():
            if len(date_tasks) > 1:
                names = [f"{t.name}({t.assignee})" for t in date_tasks]
                conflicts.append({
                    "type": "仪器冲突", "level": "高",
                    "instrument": inst_name, "date": date,
                    "message": f"🔴 {inst_name} 在 {date} 被多人使用: {', '.join(names)}",
                })
    return conflicts


def detect_calibration_risks(instruments: list, end_date: dt.date) -> list:
    """检测仪器校准风险。"""
    risks = []
    for inst in instruments:
        if inst.cal_due:
            try:
                cal = dt.date.fromisoformat(inst.cal_due)
                if cal < end_date:
                    risks.append({
                        "type": "校准过期", "level": "高",
                        "instrument": inst.name,
                        "message": f"🔴 {inst.name} 校准 {inst.cal_due} 在排班期内过期！",
                    })
                elif (cal - end_date).days < 30:
                    risks.append({
                        "type": "校准临近", "level": "中",
                        "instrument": inst.name,
                        "message": f"⚠️ {inst.name} 校准临近（{inst.cal_due}），建议确认",
                    })
            except ValueError:
                pass
    return risks


def detect_personnel_conflicts(personnel: list, tasks: list) -> list:
    """检测人员同一天跨部门冲突。"""
    conflicts = []
    by_person = {}
    for t in tasks:
        if t.assignee and t.start:
            key = (t.assignee, t.start)
            by_person.setdefault(key, []).append(t)
    for (person, date), p_tasks in by_person.items():
        depts = set(t.department for t in p_tasks)
        if len(depts) > 1:
            dept_names = [DEPARTMENTS.get(d, {}).get("name", d) for d in depts]
            conflicts.append({
                "type": "人员跨部门冲突", "level": "中",
                "person": person, "date": date,
                "message": f"⚠️ {person} 在 {date} 跨部门工作: {', '.join(dept_names)}",
            })
    return conflicts


def detect_reagent_expiry_risks(reagents: list, end_date: dt.date) -> list:
    """[新增] 检测试剂/标准品效期风险。"""
    risks = []
    for r in reagents:
        if r.expiry:
            try:
                exp = dt.date.fromisoformat(r.expiry)
                if exp < end_date:
                    risks.append({
                        "type": "试剂效期过期", "level": "高",
                        "reagent": r.name, "category": r.category,
                        "message": f"🔴 {r.name}（{r.category}）效期 {r.expiry} 在排班期内过期，需更换！",
                    })
                elif (exp - end_date).days < 30:
                    risks.append({
                        "type": "试剂效期临近", "level": "中",
                        "reagent": r.name, "category": r.category,
                        "message": f"⚠️ {r.name}（{r.category}）效期临近（{r.expiry}），建议提前更换",
                    })
            except ValueError:
                pass
    return risks


def detect_skill_mismatch_risks(personnel: list, tasks: list) -> list:
    """[新增] 检测人员能力不匹配风险。"""
    risks = []
    skill_map = {}
    for p in personnel:
        skill_map[p.name] = set(s.strip() for s in p.skills.split("、") if s.strip())
    
    for t in tasks:
        if t.required_skills and t.assignee:
            required = set(s.strip() for s in t.required_skills.split("、") if s.strip())
            person_skills = skill_map.get(t.assignee, set())
            missing = required - person_skills
            if missing and person_skills:  # 有技能信息但不匹配
                risks.append({
                    "type": "技能不匹配", "level": "中",
                    "task": t.name, "person": t.assignee,
                    "message": f"⚠️ {t.assignee} 缺少 {t.name} 所需技能: {', '.join(missing)}",
                })
    return risks


def detect_single_point_of_failure(personnel: list, tasks: list) -> list:
    """[新增] 检测单点故障风险（某项关键技能只有1人）。"""
    risks = []
    # 统计每项技能的人数
    skill_count = {}
    for p in personnel:
        for s in p.skills.split("、"):
            s = s.strip()
            if s:
                skill_count[s] = skill_count.get(s, 0) + 1
    
    # 检查关键任务
    critical_tasks = [t for t in tasks if t.priority == "高"]
    for t in critical_tasks:
        if t.required_skills:
            for s in t.required_skills.split("、"):
                s = s.strip()
                if s and skill_count.get(s, 0) <= 1:
                    risks.append({
                        "type": "单点故障", "level": "高",
                        "skill": s, "task": t.name,
                        "message": f"🔴 关键技能「{s}」只有1人掌握（{t.name}），人员生病/离职将导致停线",
                    })
    return risks


def detect_microbiology_deadline_risk(tasks: list, deadline: dt.date) -> list:
    """[新增] 检测微生物培养周期与截止日冲突。"""
    risks = []
    for t in tasks:
        if "微生物" in t.name or "无菌" in t.name:
            # 微生物培养5天，无菌14天
            incubation = 14 if "无菌" in t.name else 5
            if t.end:
                try:
                    end = dt.date.fromisoformat(t.end)
                    if add_workdays(end, incubation) > deadline:
                        risks.append({
                            "type": "培养周期冲突", "level": "高",
                            "task": t.name,
                            "message": f"🔴 {t.name} 培养周期{incubation}天，完成日+培养后超过交货截止日！",
                        })
                except ValueError:
                    pass
    return risks


def detect_instrument_bottleneck(pool: ResourcePool, threshold: float = 0.7) -> list:
    """[新增] 检测仪器瓶颈（使用率过高）。"""
    risks = []
    for name in pool.instruments:
        iu = pool.get_instrument_utilization(name)
        total = iu["total_slots"] - iu.get("available_slots", iu["total_slots"]) + iu["total_slots"]
        avail = iu.get("available_slots", iu["total_slots"])
        if avail > 0:
            util_rate = iu["booked_slots"] / avail
            if util_rate > threshold:
                risks.append({
                    "type": "仪器瓶颈", "level": "中",
                    "instrument": name,
                    "message": f"⚠️ {name} 使用率 {util_rate:.0%}，接近饱和，建议增加备用仪器或错峰使用",
                })
    return risks


def detect_oos_buffer_risk(tasks: list, deadline: dt.date) -> list:
    """[新增] 检测是否为OOS调查预留了缓冲时间。"""
    risks = []
    # 检查QC成品检验是否有缓冲
    qc_tasks = [t for t in tasks if t.department == "qc_finished"]
    if qc_tasks:
        end_dates = [t.end for t in qc_tasks if t.end]
        if not end_dates:
            return risks
        latest_end = max(end_dates)
        try:
            latest = dt.date.fromisoformat(latest_end)
            buffer_days = workdays_between(latest, deadline)
            if buffer_days < 3:  # 至少需要3天做OOS调查
                risks.append({
                    "type": "OOS缓冲不足", "level": "中",
                    "message": f"⚠️ QC成品检验完成到交货仅{buffer_days}天缓冲，若出现OOS（超标）结果，调查时间不足",
                })
        except ValueError:
            pass
    return risks


def detect_all_risks(proj, schedule: dict, personnel: list, instruments: list,
                     tasks: list, reagents: list = None,
                     pool: ResourcePool = None) -> list:
    """汇总所有风险检测。"""
    deadline = dt.date.fromisoformat(proj.deadline)
    all_risks = []
    all_risks.extend(detect_schedule_risks(schedule))
    all_risks.extend(detect_calibration_risks(
        [Instrument(**i) if isinstance(i, dict) else i for i in instruments], deadline))
    all_risks.extend(detect_reagent_expiry_risks(
        [Reagent(**r) if isinstance(r, dict) else r for r in (reagents or [])], deadline))
    
    # 构建 TaskItem 列表用于检测
    task_items = []
    for t in tasks:
        task_items.append(TaskItem(
            name=t.get("name", ""), department=t.get("department", ""),
            assignee=t.get("assignee", ""), priority=t.get("priority", "普通"),
            required_skills=t.get("required_skills", ""),
            end=t.get("end_date", t.get("end", "")),
        ))
    
    personnel_items = []
    for p in personnel:
        personnel_items.append(Personnel(
            name=p.get("name", ""), department=p.get("department", ""),
            skills=p.get("skills", ""),
        ))
    
    all_risks.extend(detect_skill_mismatch_risks(personnel_items, task_items))
    all_risks.extend(detect_single_point_of_failure(personnel_items, task_items))
    all_risks.extend(detect_microbiology_deadline_risk(task_items, deadline))
    
    if pool:
        all_risks.extend(detect_instrument_bottleneck(pool))
    all_risks.extend(detect_oos_buffer_risk(task_items, deadline))
    
    # 去重（按 message）
    seen = set()
    unique_risks = []
    for r in all_risks:
        if r["message"] not in seen:
            seen.add(r["message"])
            unique_risks.append(r)
    
    # 按 level 排序：高 > 中 > 低
    level_order = {"高": 0, "中": 1, "低": 2}
    unique_risks.sort(key=lambda r: level_order.get(r.get("level", "低"), 2))
    
    return unique_risks
