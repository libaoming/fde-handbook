# ROL-01 · 角色定义：FDE 是什么、不是什么

**目的**　用五个固定字段说清 FDE（Forward Deployed Engineer，前置部署工程师——被派到
客户现场完成交付的工程师）这个角色，让你能做两件事：向客户、同事或新人一句话讲清
你是干什么的；判断一件活**该不该按 FDE 交付的方式走**（该走的进 ROL-04 的生命周期，
不该走的趁早说清楚）。

**前置条件**
- 无。本节是全书入口，不依赖其他节。

> **字段结构的出处**：本节的五字段（是什么 / 为什么需要 / 职责 / 谁在做 / 怎么成为）
> 抄自 PagerDuty 事故响应手册的角色页模板——其每个角色固定用
> "What is it? / Why have one? / What are the responsibilities? / Who are they? /
> How can I become one?" 五问描述（https://response.pagerduty.com/before/different_roles/ ）。
> 角色定义前置在流程之前，也是抄它的。

---

## 规程

![Dev 是一个能力服务许多客户；FDE 是一家客户身上横跨许多能力，成功以客户目标度量](../figures/rol01-dev-delta.svg)

### ROL-01.1　是什么

**FDE 是把既有产品能力部署成客户结果、并以客户目标的达成来度量成功的工程师。**

这个定义里有三个承重件，少一个都不是这个角色：

| 承重件 | 含义 | 少了它变成什么 |
|---|---|---|
| **既有能力** | 主体是部署与适配已存在的产品/平台，不是从零造新产品 | 从零造 → 外包定制开发 |
| **客户结果** | 交付物是在客户环境里跑起来并被使用的系统 | 只出方案不出系统 → 咨询 |
| **以客户目标度量** | 成功标准是客户的业务判据，不是「功能上线了」 | 以上线度量 → 实施外包 |

公开系统描述这个角色、并让它广为人知的样本是 Palantir。其官方博客对两类工程师的切分：
Dev（软件工程师）"develop and engineer our software platforms"，
Delta（Forward Deployed Software Engineer）"deploy our software platforms to customers"；
一句话对比是 **"one capability, many customers"（Dev）对
"one customer, many capabilities"（Delta）**。

### ROL-01.2　为什么需要这个角色

**产品能力和客户结果之间隔着现场**：客户的数据、权限、网络、审批流、既有系统、
和真正要用它的人。产品团队按「一个能力服务很多客户」优化，没有人对
「这一家客户的结果」负责——FDE 补的是这个空位。

Palantir 对这个空位的表述：Delta 的工作是 "technology-driven value creation"，
且 "measure success in terms of impact on the customer's goal"——
**度量单位是客户目标的达成，不是功能的交付。** 本手册全部验证纪律（第 3 部）
都建立在这一句上：既然成功以客户结果度量，「做完了」就必须能在客户那一侧被观察到。

### ROL-01.3　职责

Palantir 原文描述 FDSE 的活动词是：与客户 "scoping the future of a project"、
"monitoring, debugging, deploying, or configuring our software"、
"reviewing pull requests"，并且 "often contribute code back to the core product"。

本手册把这些活动整理为六阶段（映射关系见 ROL-04；**六阶段是本手册自建框架，
Palantir 原文没有阶段划分**）：

| 活动 | 阶段 |
|---|---|
| 界定范围、定成功标准、判断能不能接 | ENG 承接 |
| 摸清客户环境、约束、依赖 | SUR 勘察 |
| 部署、配置、搭链路 | BLD 搭建 |
| 上线、切换、灰度 | DEP 上线 |
| 监控、调试、拿到「确实做完了」的证据 | VER 签收 |
| 移交运维、知识转移 | HND 移交 |
| 把现场发现贡献回产品 | 贯穿（不属于单一阶段） |

**最后一行是这个角色的双向性**：你不只是产品的输出端，也是它的传感器——
现场暴露的缺陷与需求回流到产品，是 FDE 与实施外包的又一条分界。

### ROL-01.4　谁在做

- **Palantir**：公开系统描述此角色、最广为人知的样本（内部称 Delta / FDSE）。
- **AI 交付领域**：随 AI 系统进客户现场，同名或近似岗位在扩散。
  ⚠️ 本手册**未逐家核实**各公司 JD（Palantir 官方 JD 页对抓取返回 403，无法引用），
  不在此罗列公司名单。你的岗位叫不叫 FDE 不重要——**工作满足 ROL-01.1 三个承重件，
  本手册就适用于你。**

### ROL-01.5　怎么成为（从相邻角色迁移时补什么）

本手册不是求职指南，只给一条实用信息：从哪个角色来，第一课就是什么。

| 你从哪来 | 最先要补的认知 |
|---|---|
| 产品/平台工程师 | 现场没有你习惯的一切：权限要谈、环境不可控、可观测性经常是零。你的验证习惯需要整体降级重建（第 3 部） |
| 咨询顾问 | 交付物从「建议」变成「运行系统」——建议无法被验收，系统可以，也必须（VER） |
| 售前/解决方案架构师 | 演示的成功与交付的成功是两个东西；合同签了，你的计时才开始 |

---

## 常见误判

**「FDE 就是驻场咨询」**
不是。Palantir 对这条分界的原话："we are actually deploying existing software products
to achieve the customer's outcomes"——交付物是**部署起来的运行系统**，不是建议书。
咨询的产出无法被机械验收，FDE 的产出必须能（VER-05、DIS-02）。

**「FDE 就是售后支持 / 实施外包」**
实施外包以「装完上线」为终点，且信息单向流出。FDE 以客户目标达成为终点（ROL-01.2），
且信息双向流动——"often contribute code back to the core product"（ROL-01.3）。
把 FDE 当实施外包用，丢的是「现场作为产品传感器」的那一半价值。

**「FDE 是产品工程师的弱化版」**
方向反了。Dev 是「一个能力打磨到极致」，FDE 是 "one customer, many capabilities"——
在一家客户身上横跨全栈能力,且在**没有脚手架**（没有 CI、没有可观测性、没有同事 review）
的环境下工作。脚手架越少，对验证纪律的要求越高，这正是第 3 部存在的理由。

---

## 判定标准

一件活该不该按 FDE 交付（即本手册的生命周期）来走，问两个问题：

```checklist
[ ] 成功是否以「客户目标的达成」度量？（而不是「功能上线」「工时交付」）
[ ] 工作主体是否是「部署/适配既有能力」？（而不是从零开发，也不是只出建议）
```

两问与 ROL-01.1 三承重件的对应：第一问检验「以客户目标度量」；第二问的主句检验
「既有能力」，括号里的「不是只出建议」检验「客户结果」——交付物必须是运行系统。

**两问皆是** → 按 FDE 交付走，从 ROL-04 的 ENG 关口进入。
**任一为否** → 是别的工作形态（定制开发/咨询/支持），本手册的规程只可参考、不可照搬——
尤其是 VER 部的签收判据，它假定了「客户结果可观察」这个前提。

---

## 案例证据

> ### 引证 · 第三方声明｜Palantir "Dev versus Delta"
>
> 本节全部英文引句出自 Palantir 官方博客
> "Dev versus Delta: Demystifying Engineering Roles at Palantir"：
> https://blog.palantir.com/dev-versus-delta-demystifying-engineering-roles-at-palantir-ad44c2a6e87
> （2026-08-06 逐句核实实存）。
>
> **不可外推边界**：这是单一公司对自家岗位的自述，且博客带招聘目的；
> 「FDE 都应如此」不能从它推出。文章**没有**给出阶段化的交付生命周期——
> 本手册的六阶段是自建框架，出处与声明见 ROL-04。

---

## 相关小节

- **ROL-02 相邻角色边界**——本节说「你是谁」，那节说「你旁边的人各拥有什么」
- **ROL-03 交付物清单**——「以客户目标度量成功」落到纸面上是哪几样东西
- **ROL-04 全景图**——六阶段框架与进入口
- **DIS-01 证据分级**——「客户结果可被观察到」的方法论起点
- **附录 A · FX-ORG-04（待写）**——症状「什么都找你，角色被当成驻场咨询/售后」的速查入口
