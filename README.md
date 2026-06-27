# 药厂排班系统

## 文件夹结构

```
药厂排班系统/
├── README.md                    ← 本文件
├── 药厂排班-信息采集表.md        ← ⭐ 填这个，填完发给我排班
├── SKILL.md                     ← 技能定义（触发规则+资源池说明）
├── scripts/
│   └── scaffold_pharma.py       ← 排班生成脚本
├── shared/
│   ├── common.py                ← 核心引擎：ResourcePool + SchedulingEngine
│   ├── qc_tasks.md              ← QC 检验任务参考清单
│   ├── workshop_tasks.md        ← 车间生产任务参考清单
│   ├── procurement_tasks.md     ← 采购任务参考清单
│   └── sales_tasks.md           ← 销售发货任务参考清单
└── references/
    ├── industry-tools.md        ← 行业工具调研（Smart-QC/Binocs/LabWare等）
    └── qc-domain-knowledge.md   ← QC 领域知识
```

## 使用方式

1. 填写 `药厂排班-信息采集表.md`
2. 发给 Hermes，自动生成排班

## 排班输出

每次排班会生成一个独立文件夹，包含：
- 项目总览 + 依赖关系图
- 各部门排班表（人员×仪器×时间）
- 资源池总览（人员使用率+仪器使用率）
- 甘特图排程
- 风险看板
