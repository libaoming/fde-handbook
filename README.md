# FDE 手册

**AI 交付的现场手册**——把 agent 送上生产之后，怎么确认它真的在干活。

写给正在做 AI 交付的工程师与 PM。规程与检查表为主体，公开事故复盘与标注过的合成示例做证据。
体裁是手册，不是回忆录：你应该能「遇到某个症状翻到某一节」，而不是从头读到尾。

> 🚧 **写作中。** 本仓库目前公开的是目录与写作纪律，正文陆续发布。

---

## 这本手册解决什么

一次 AI 应用交付里，真正让人栽跟头的很少是「模型不行」，而是**「我以为我做完了」和「实际发生了什么」之间的那条缝**：

- 服务显示 `active`，接活的却是上一版的进程；
- 磁盘上的配置是对的，运行时生效的是旧的；
- 本机自测全绿，用户那条路根本不通；
- 提示词写了「必须」，模型把它当成了建议；
- 你的 AI 助手报了 `EXIT: 0`，而它根本没执行过那条命令。

手册把这些形态拆成可执行的检查，每条检查都给判据——**什么算通过、什么算没通过**。

## 两个入口

| 入口 | 你的问题 | 去哪 |
|---|---|---|
| 主线 | 我在交付的哪一步，该做什么 | 第 2 部，按交付生命周期 |
| 速查 | 我遇到了这个症状，去哪查 | 附录 A，按故障域索引，每条指向正文小节 |

每个检查项有稳定编号（`VER-02.3`），评审、工单、速查表都能引用一个不会漂移的号。

---

## 目录

### 第 0 部 · 怎么用这本手册
两个入口、编号体系、案例档位说明。

### 第 1 部 · 这份工作
| 节 | 内容 |
|---|---|
| ROL-01 | FDE 是什么，不是什么 |
| ROL-02 | 与相邻角色的边界：售前 / 解决方案架构师 / 交付经理 / 客户 IT |
| ROL-03 | 交付物清单：一次交付到底要产出哪些东西 |
| ROL-04 | 全景图：六个阶段与阶段之间的关口 |

### 第 2 部 · 交付生命周期
每个阶段固定结构：**进入条件 → 规程节 → 退出条件 → 本阶段交付物**。

| 阶段 | 代码 | 核心问题 |
|---|---|---|
| 承接 | `ENG` | 这活能不能接？红线在哪？成功标准怎么定义？ |
| 勘察 | `SUR` | 现场环境、约束、依赖，以及不在工程域里的阻塞项 |
| 搭建 | `BLD` | 最小可用链路；换链路时的能力丢失清单 |
| 上线 | `DEP` | 部署、切换、灰度、回滚预案 |
| **签收** | `VER` | **本手册的重心**：什么算做完了，证据链怎么留 |
| 移交 | `HND` | 运维、监控、责任交接、知识转移 |

### 第 3 部 · 贯穿全程的验证纪律
| 节 | 内容 |
|---|---|
| DIS-01 | 证据分级：什么算证据，什么只是信号 |
| DIS-02 | 三道焊缝：回读（靠自觉）→ 判定标量（靠设计）→ 闸门（靠系统） |
| DIS-03 | **用 AI agent 做交付时的额外风险面**——助手会谎报完成、伪造凭证、诿过环境 |
| DIS-04 | 事故台账：失败怎么进流程才算被吸取 |

### 第 4 部 · 团队与规模化
把个人纪律变成团队制度；评审机制；新人上手路径。

### 附录（都是能直接拷走的东西）
| 附录 | 内容 |
|---|---|
| A | **故障速查**——按症状索引，五段式条目（怎么确认是它 → 怎么修 → 怎么确认好了 → 怎么撤销） |
| B | **检查表汇编**——全部检查项抽出成册，可打印逐条打分 |
| C | **模板库**——交付计划、验收清单、移交文档、事故台账 |
| D | **案例集**——公开事故复盘索引 + 合成示例 |
| E | 术语表 |
| F | 引用口径、案例档位说明与证据账本 |

---

## 写作纪律

这本手册对自己的要求，和它要求读者对交付的要求是同一条：**声明之前先拿到证据。**

**引文必须核实。** 每一条外部引用都在写作当轮实际访问过原始页面、确认字句实存，
并标注不可外推边界。这条纪律有来历——本项目早期出过一次事故：
给一个不存在的说法挂了一个真实的文档链接做背书。那次自伤是这条规矩的疤。

**案例分三档，读者必须一眼知道是哪一档。**

| 档 | 说明 |
|---|---|
| 公开事故复盘 | 附原始 postmortem 链接与日期，读者可自行查证 |
| 合成示例 | 为讲清某个检查项构造的教学场景，**显式标注**，且不含任何伪造的时间戳、PID、哈希或日志原文 |
| 一手案例 | 附证据账本与证据等级 |

区别不在于案例谁写的，在于**读者知不知道它是构造的**。标注为合成是专业惯例；
冒充成亲历，这本手册就一文不值。

**保守缺省。** 每张判定表都配一条兜底：拿不准时按更坏的情况处理。
某项检查因为工具不可用、权限不足或日志缺失而**无法验证**时，一律按未通过处理。

---

## 一个必须说明的事情

手册第 2 部的**六阶段划分是自建框架，不是行业标准**。

Palantir 公开材料给出了 FDE 的角色定义——软件工程师是「one capability, many customers」，
前线部署工程师是「one customer, many capabilities」
（[出处](https://blog.palantir.com/dev-versus-delta-demystifying-engineering-roles-at-palantir-ad44c2a6e87)）——
但**没有给出阶段化的交付生命周期**。本手册的六阶段是为了让内容可检索而自建的组织方式，
用它之前请先确认它符合你的实际交付形态。

结构范式参考了 Google SRE Workbook、PagerDuty Incident Response、
AWS Well-Architected Framework、GitLab Handbook 与 GitLab 生产 runbook 的公开做法。

---

## Status

| 部分 | 状态 |
|---|---|
| 架构与写作纪律 | 已定 |
| `VER-02` 切换验证 | 首个成稿规程节 |
| 附录 A（故障速查） | 首条条目成稿 |
| 其余 | 写作中 |

---

## About

by [@libaoming](https://github.com/libaoming)

Issues 与建议欢迎。如果你在自己的交付里撞到过手册没覆盖的失败形态，尤其欢迎提出来。

---

<details>
<summary><b>English</b></summary>

### FDE Handbook

A field handbook for shipping AI agents to production — focused on one question:
**after you deploy, how do you know the thing actually doing the work is the thing you deployed?**

Written for engineers and PMs doing AI delivery. Procedures and checklists are the body;
public postmortems and clearly-labelled synthetic scenarios are the evidence.
It is a handbook, not a memoir — you should be able to look something up, not read it cover to cover.

**Two entry points**: the main line follows the delivery lifecycle (*where am I in the process?*);
Appendix A indexes by failure domain (*I'm seeing this symptom, where do I look?*).
Every check carries a stable ID (`VER-02.3`) so reviews and tickets can reference something that won't drift.

**Discipline**: every external citation is verified against the original page at the time of writing,
with its limits of extrapolation stated. Cases come in three tiers — public postmortems,
labelled synthetic examples, and first-hand accounts with an evidence ledger — and readers are
always told which tier they are reading. Synthetic examples never carry fabricated timestamps,
PIDs, hashes, or log output.

**Note**: the six-phase lifecycle in Part 2 is a construct of this handbook, not an industry standard.
Palantir's public material defines the role but publishes no phased delivery lifecycle.

🚧 Work in progress — the outline and writing discipline are public; chapters follow.

</details>
