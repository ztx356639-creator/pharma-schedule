#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
共享数据结构和工具：部门定义、依赖关系、时间推导、风险检测、资源池排程。
"""
from __future__ import annotations
import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ============================================================
# 部门定义
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
        "blocks": ["sales"],
    },
    "sales": {
        "name": "销售发货",
        "icon": "🚚",
        "typical_duration_days": 3,
        "typical_tasks": [
            {"name": "放行审核", "duration": "1天"},
            {"name": "发货准备", "duration": "1天"},
            {"name": "物流安排", "duration": "1天"},
            {"name": "客户签收确认", "duration": "1-3天"},
        ],
        "depends_on": ["qc_finished"],
        "blocks": [],
    },
}

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

@dataclass
class Personnel:
    """人员信息。"""
    name: str
    department: str
    level: str = ""
    skills: str = ""
    note: str = ""

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

def is_workday(d: dt.date) -> bool:
    if d.weekday() >= 5:
        return False
    if d.isoformat() in HOLIDAYS_2026:
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

def reverse_schedule(deadline: dt.date, dept_durations: dict) -> dict:
    order = ["procurement", "qc_incoming", "workshop", "qc_finished", "sales"]
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
# 资源池模型（参考 Smart-QC / Binocs）
# ============================================================
@dataclass
class ResourceSlot:
    """资源的一个时间段占用。"""
    resource_name: str
    resource_type: str   # "person" | "instrument" | "room"
    date: dt.date
    period: str          # "上午" | "下午" | "全天"
    task_name: str = ""
    task_department: str = ""
    locked: bool = False  # 已确认不可改

class ResourcePool:
    """
    资源池：统一管理人员、仪器、房间的时间槽。
    核心逻辑：每个资源在每个工作日有 2 个时间槽（上午/下午），
    排班 = 把任务塞进资源的时间槽，自动避免冲突。
    """
    def __init__(self, start: dt.date, end: dt.date):
        self.start = start
        self.end = end
        self.work_days = []
        cur = start
        while cur <= end:
            if is_workday(cur):
                self.work_days.append(cur)
            cur += dt.timedelta(days=1)
        
        # 资源注册表
        self.personnel: dict[str, dict] = {}      # name -> {department, level, skills, note}
        self.instruments: dict[str, dict] = {}     # name -> {model, location, cal_due, status, shared, qty}
        self.rooms: dict[str, dict] = {}           # name -> {type, capacity, location}
        
        # 时间槽占用表: {(resource_name, date, period) -> ResourceSlot}
        self.slots: dict[tuple, ResourceSlot] = {}
    
    def register_person(self, name: str, department: str, level: str = "", skills: str = "", note: str = ""):
        """注册人员到资源池。"""
        self.personnel[name] = {"department": department, "level": level, "skills": skills, "note": note}
    
    def register_instrument(self, name: str, model: str = "", location: str = "", cal_due: str = "",
                            status: str = "正常", shared: bool = False, qty: int = 1):
        """注册仪器到资源池。"""
        self.instruments[name] = {
            "model": model, "location": location, "cal_due": cal_due,
            "status": status, "shared": shared, "qty": qty,
        }
    
    def register_room(self, name: str, room_type: str = "", capacity: int = 1, location: str = ""):
        """注册房间到资源池。"""
        self.rooms[name] = {"type": room_type, "capacity": capacity, "location": location}
    
    def is_available(self, resource_name: str, date: dt.date, period: str) -> bool:
        """检查资源在指定时间槽是否可用。"""
        key = (resource_name, date, period)
        if key in self.slots:
            return False
        
        # 仪器校准检查
        if resource_name in self.instruments:
            inst = self.instruments[resource_name]
            if inst["cal_due"]:
                try:
                    cal = dt.date.fromisoformat(inst["cal_due"])
                    if cal < date:
                        return False  # 校准已过期
                except ValueError:
                    pass
            if inst["status"] != "正常":
                return False  # 仪器状态异常
        
        return True
    
    def book(self, resource_name: str, resource_type: str, date: dt.date,
             period: str, task_name: str = "", task_department: str = "",
             locked: bool = False) -> bool:
        """预定资源时间槽。成功返回 True，冲突返回 False。"""
        if not self.is_available(resource_name, date, period):
            return False
        key = (resource_name, date, period)
        self.slots[key] = ResourceSlot(
            resource_name=resource_name,
            resource_type=resource_type,
            date=date,
            period=period,
            task_name=task_name,
            task_department=task_department,
            locked=locked,
        )
        return True
    
    def release(self, resource_name: str, date: dt.date, period: str):
        """释放资源时间槽。"""
        key = (resource_name, date, period)
        if key in self.slots and not self.slots[key].locked:
            del self.slots[key]
    
    def get_resource_schedule(self, resource_name: str) -> list[ResourceSlot]:
        """获取某个资源的全部排班。"""
        result = []
        for day in self.work_days:
            for period in ["上午", "下午"]:
                key = (resource_name, day, period)
                if key in self.slots:
                    result.append(self.slots[key])
        return result
    
    def get_day_schedule(self, date: dt.date) -> dict[str, list[ResourceSlot]]:
        """获取某一天所有资源的排班情况。"""
        result = {"person": [], "instrument": [], "room": []}
        for key, slot in self.slots.items():
            if slot.date == date:
                result[slot.resource_type].append(slot)
        return result
    
    def get_available_periods(self, resource_name: str, date: dt.date) -> list[str]:
        """获取资源在某天的可用时段。"""
        available = []
        for period in ["上午", "下午"]:
            if self.is_available(resource_name, date, period):
                available.append(period)
        return available
    
    def get_person_workload(self, person_name: str) -> dict:
        """统计人员工作量。"""
        booked = 0
        total = len(self.work_days) * 2  # 每天2个时段
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
        """统计仪器使用率。"""
        inst = self.instruments.get(inst_name, {})
        booked = 0
        total = len(self.work_days) * 2
        users = set()
        for key, slot in self.slots.items():
            if slot.resource_name == inst_name and slot.resource_type == "instrument":
                booked += 1
                users.add(slot.task_department)
        # 校准过期天数
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
# 自动排程引擎
# ============================================================
class SchedulingEngine:
    """
    约束驱动排程引擎。
    硬约束：资源可用性、校准有效期、依赖关系
    软约束：人员偏好、缓冲时间、优先级
    """
    def __init__(self, pool: ResourcePool):
        self.pool = pool
        self.assigned_tasks: list[dict] = []
        self.unassigned_tasks: list[dict] = []
        self.conflicts: list[str] = []
    
    def assign_task(self, task_name: str, department: str, assignee: str,
                    instruments: list[str] = None, duration_hours: float = 4,
                    priority: str = "普通", depends_on: str = "",
                    earliest_start: dt.date = None) -> bool:
        """
        分配一个任务到资源池。
        
        逻辑：
        1. 找 assignee 的可用时间槽
        2. 如果需要仪器，同时找仪器的可用时间槽
        3. 取交集
        4. 从 earliest_start 开始往后找
        """
        instruments = instruments or []
        start_date = earliest_start or self.pool.start
        
        # 计算需要几个时间槽（每个时段=4小时）
        slots_needed = max(1, int((duration_hours + 3) // 4))
        
        # 找候选时间段
        for day_idx, day in enumerate(self.pool.work_days):
            if day < start_date:
                continue
            
            for period in ["上午", "下午"]:
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
                
                # 找到可用槽，预定
                self.pool.book(assignee, "person", day, period,
                              task_name=task_name, task_department=department)
                for inst_name in instruments:
                    self.pool.book(inst_name, "instrument", day, period,
                                  task_name=task_name, task_department=department)
                
                self.assigned_tasks.append({
                    "task": task_name,
                    "department": department,
                    "assignee": assignee,
                    "instruments": instruments,
                    "date": day.isoformat(),
                    "period": period,
                    "priority": priority,
                })
                return True
        
        # 无法分配
        self.unassigned_tasks.append({
            "task": task_name,
            "department": department,
            "assignee": assignee,
            "instruments": instruments,
            "reason": "无可用资源时间槽",
        })
        self.conflicts.append(f"⚠️ {task_name} 无法分配给 {assignee}（资源冲突）")
        return False
    
    def auto_schedule(self, tasks: list[dict]) -> dict:
        """
        批量自动排程。
        
        tasks 格式：
        [
            {
                "name": "含量测定",
                "department": "qc_finished",
                "assignee": "张三",
                "instruments": ["HPLC-1"],
                "duration_hours": 3,
                "priority": "高",
                "depends_on": "",
                "earliest_start": "2026-07-10"
            },
            ...
        ]
        
        排序策略：
        1. 优先级 高 > 普通 > 低
        2. 有依赖的排后面
        3. 仪器需求多的优先（资源竞争大）
        """
        # 按优先级排序
        priority_order = {"高": 0, "普通": 1, "低": 2}
        sorted_tasks = sorted(tasks, key=lambda t: (
            0 if t.get("depends_on") else 1,  # 无依赖的先排
            priority_order.get(t.get("priority", "普通"), 1),
            -len(t.get("instruments", [])),  # 仪器需求多的先排
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
                "date": task["date"],
                "period": task["period"],
                "department": task["department"],
            })
        # 按日期+时段排序
        gantt.sort(key=lambda x: (x["date"], 0 if x["period"] == "上午" else 1))
        return gantt

# ============================================================
# 风险检测
# ============================================================
def detect_instrument_conflicts(instruments: list, tasks: list) -> list:
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
                    "type": "仪器冲突",
                    "instrument": inst_name,
                    "date": date,
                    "tasks": names,
                    "message": f"⚠️ {inst_name} 在 {date} 被多人使用: {', '.join(names)}",
                })
    return conflicts

def detect_calibration_risks(instruments: list, end_date: dt.date) -> list:
    risks = []
    for inst in instruments:
        if inst.cal_due:
            try:
                cal = dt.date.fromisoformat(inst.cal_due)
                if cal < end_date:
                    risks.append({
                        "type": "校准过期",
                        "instrument": inst.name,
                        "cal_due": inst.cal_due,
                        "message": f"🔴 {inst.name} 校准 {inst.cal_due} 在排班期内过期！",
                    })
                elif (cal - end_date).days < 30:
                    risks.append({
                        "type": "校准临近",
                        "instrument": inst.name,
                        "cal_due": inst.cal_due,
                        "message": f"⚠️ {inst.name} 校准临近（{inst.cal_due}），建议确认",
                    })
            except ValueError:
                pass
    return risks

def detect_personnel_conflicts(personnel: list, tasks: list) -> list:
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
                "type": "人员跨部门冲突",
                "person": person,
                "date": date,
                "message": f"⚠️ {person} 在 {date} 跨部门工作: {', '.join(dept_names)}",
            })
    return conflicts

def detect_schedule_risks(schedule: dict) -> list:
    risks = []
    for dept_id, times in schedule.items():
        dept_name = DEPARTMENTS.get(dept_id, {}).get("name", dept_id)
        buffer = workdays_between(times["end"], times["start"]) - times["duration_workdays"]
        if buffer < 0:
            risks.append({
                "type": "赶工",
                "department": dept_name,
                "message": f"🔴 {dept_name} 排班时间不足！需要 {times['duration_workdays']} 工作日，但只有 {workdays_between(times['start'], times['end'])} 天",
            })
        elif buffer < 2:
            risks.append({
                "type": "缓冲不足",
                "department": dept_name,
                "message": f"⚠️ {dept_name} 缓冲仅 {buffer} 天，风险较高",
            })
    return risks
