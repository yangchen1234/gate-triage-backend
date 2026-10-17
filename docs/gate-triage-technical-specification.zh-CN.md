# Gate Triage 技术设计与全栈开发规范

版本：1.1　编写日期：2026 年 10 月 17 日　适用地区：洛杉矶港　文档语言：中文　产品界面：英文。

实时决策、SSE 推送、服务端模拟数据台、RAG 边界和本地数据库资源要求详见 [实时决策补充规范](realtime-decision-contract.zh-CN.md)。本次独立分支开发同时遵循两份规范；实现完成情况以测试记录为准。

第 1.1 节记录开发前的团队基线，不能作为本分支的最新实现状态。独立应用的启动方法见 [英文运行说明](../README-workbench.md)，实际验证与限制见 [验收记录](workbench-verification.md)。

本规范面向负责完整产品开发的工程师或 Codex Work，覆盖产品边界、行业依据、数据合同、后端、前端、约束调度、事件仿真、真实事件参考、部署与验收。目标是交付一个可独立启动、可实际操作、可复现评估的应用。优先指标是有效完成量、等待和中断恢复，费用是辅助指标。

**核心设计决定：Terminal49 是唯一真实外部业务数据提供方。真实数据模式用于提柜准备与异常协调；现场资源调度和吞吐量实验在明确标记的运营仿真中运行。** 称重、温度、设备和道路参数不能被伪装成 Terminal49 返回的数据。三种模式共享业务模型，但存储、权限、时钟、结果标签相互隔离。

本文件是待实现产品的规范，不是已经通过现场验证的码头操作手册。文中的“必须”规定本产品的实现和验收要求；只有明确引用适用法规的条目才是在说明外部义务。真实部署前，码头人员需要确认当地 SOP、权限和资源参数。

## 1 阅读与开发顺序

产品负责人先阅读第 2 至 5 节及真实案例；后端开发先实现数据来源与状态模型，再实现任务和仿真；前端以 API 合同和页面规范开发；测试人员用约束不变量、场景断言和公平对照实验验收。

文档后半部分包含详细调度与仿真规范、页面与端到端验收。若补充章节中的示例名字不同，以第 6 节的数据枚举、第 10 节的 API 合同和第 15 节的场景标识为准。实现时应生成 OpenAPI 和 JSON Schema，将例子转成可验证 fixture。

### 1.1 现有仓库与完成状态

现有代码基线为 [gate-triage-backend](https://github.com/yangchen1234/gate-triage-backend)。文档包包含开发规范和合成参考数据，不包含已经实现的新版产品；交付给新的开发环境时先取得该代码基线或对应团队快照。

| 项目 | 当前事实 | 本次开发要求 |
|---|---|---|
| 后端 | FastAPI；现有 `/containers`、`/scenario`、`/stats`、`/health` | 保留现有合同和回归测试，在 `/api/v1` 增加新产品 API |
| 数据 | Ryan 提供 100 个合成货柜与规则打分 | 保留原始文件；转换为新 fixture 时记录转换与缺失字段，不称为 Terminal49 实际数据 |
| 费用统计 | 简化的一日排队费用模型 | 不作为吞吐量证据；新实验采用离散事件仿真 |
| 初步规则草稿 | `gate_triage/planner_engine.py` 未接入、未测试 | 仅作为设计参考；不把其中固定自重、温度阈值、日容量当行业参数 |
| 前端 | 团队另有前端 | 本规范开发独立产品前端，后续再核对与团队前端的合并方式 |
| 真实接入 | 本次未验证团队 Terminal49 账号权限、字段覆盖或真实数据 | 做启动能力探测；缺少密钥时仍可完整运行离线演示 |

### 1.2 成品定义

交付必须同时包含：可运行前后端、数据库迁移、Terminal49 适配器、可重放 fixture、三类历史事件启发的应急场景、约束优化器、三种策略的仿真比较、来源与决策时间线、自动化测试、部署配置及英文 README。

只展示静态页面、随机变化的指标、单一分数排序、没有真实求解的优化按钮，均不算完成。没有账号密钥不阻止离线成品交付，但真实接入状态必须显示 `not_configured`，不能显示接入成功。

## 2 问题与操作范围

### 2.1 目标用户

主要用户是一个码头当班负责闸口相关异常协调和作业安排的运营人员。其工作是识别当前阻碍、联系责任角色、安排授权范围内的任务，并把有限资源用于能够推进的业务。洛杉矶港是背景范围，具体码头是工作空间；不假设一个人能指挥全港。

端到端流程为：接收来源记录 → 保存证据 → 识别独立问题 → 检查每个动作的条件 → 生成并行任务 → 排程或协调 → 人员接手 → 新证据进入 → 重新评估 → 记录结果与交班。

### 2.2 两类能力

**真实 Terminal49 模式**应提供四类工作队列：当前报告可提、存在扣留需协调、信息不一致或待更新、等待后续运输里程碑。系统可以提示谁需要处理什么，并记录本应用内部的接手和复核过程。

**运营仿真模式**在上述数据结构之外增加明确的车道、设备、任务耗时、司机到达、温度、独立称重和局部关闭事件。只有该模式能够评估资源排程、模拟卡车周转和模拟吞吐量。

外部真实执行接口不在本版本范围：不控制设备，不代替海关撤销扣留，不自动付款，不向船公司或司机发送消息，不在码头系统创建预约。可生成供用户审阅的联系草稿及计划导出。

### 2.3 对比赛题目的逐项回答

| 题目要求 | 产品交付 | 数据前提 |
|---|---|---|
| 一个柜子出现多种说法 | 同时保留重量疑点、温度报警和扣留；多个任务不相互覆盖 | 实物重量和温度仅在模拟或明确现场报告中出现 |
| Slow inspect reroute release | 为具体动作显示允许、受阻或未知及依据 | `release` 在界面改为 `Reported ready for pickup` 或模拟交接，避免把建议写成授权 |
| 哪个来源可信 | 判断来源适用问题、时间、字段含义和是否为独立证据 | 不用固定 95% 可信度覆盖其他来源 |
| 哪个柜不能等 | 显示应优先响应的问题及期限，同时展示当前可执行交接 | 关键货物等级、温度范围和响应目标必须有来源或模拟政策 |
| 半数车道不可用 | 有作用范围的资源更新与滚动排程 | 模拟输入，不声称 Terminal49 提供实时车道信息 |
| 日常与危机都有效 | 正常安排、异常协调、中断重排、分阶段恢复使用同一模型 | 数据与策略可追溯，事件可以重放 |

参与者材料将 Ports & Logistics 的可行性描述为能被 shipper、port 或 trucker 近期采用，影响可体现为减少延误、成本或排放，dual-use 要求日常物流顺畅且中断时仍工作。材料中的 `mock data data` 原文存在重复，不能据此推断任何额外赞助商接口承诺。实际提交要求以团队拿到的最新主办方材料为准。

## 3 成熟方案与本项目的设计差异

### 3.1 可以直接学习的成熟做法

| 现有产品或规范 | 可核实的能力 | 本项目吸收的做法 | 本项目进一步实现的重点 |
|---|---|---|---|
| Terminal49 | 风险货柜、LFD、holds、fees、availability、来源与运输事件 | 统一追踪、变化驱动、保留多来源和未知状态 | 将证据关联到并行任务、条件与任务进展 |
| 洛杉矶港 Port Optimizer | 货物流动、停留、卡车周转及预约等运营可见性 | 用环节指标定位瓶颈，明确参与方和工作范围 | 局部事件影响、待办闭环及可复现实验 |
| Kaleris N4 等 TOS | 堆场规划、资源优化、内部车辆实时调度与控制室 | 任务先后关系、资源能力、作业时间表 | 以题目中的多重异常为中心组织证据与约束解释 |
| APM TERMPoint | 预约相关状态和多项 availability reasons | 预约、可提状态、费用与区域问题分开表达 | 一项问题解决后只更新相关条件 |
| DCSA Track & Trace | 统一描述和交换运输与设备事件 | 事件时间、地点、来源和对象的一致表达 | 在本地模型中加入决策、任务和仿真身份 |

依据：[Terminal49 风险列表](https://help.terminal49.com/articles/1980719496-containers-at-risk)、[港方运营平台](https://portoflosangeles.org/business/operations)、[Kaleris N4](https://kaleris.com/solutions/terminal-operating-system/container-terminals/)、[APM TERMPoint 公开接口](https://developer.apmterminals.com/sites/default/files/2025-01/TAS%20API%20Document%20v20240205_0.pdf)、[DCSA](https://dcsa.org/standards/track-and-trace)。

### 3.2 可辩护的原创性

项目的组合设计是：**将多来源异常转换为带证据、责任分工和许可条件的并行行动；把核实信息的工作也纳入资源安排；在局部中断时比较满足相同限制的候选计划，并通过事件回放解释效率与公平取舍。**

原创性验收要求实际实现上述连接关系。统一数据、风险标红、AI 聊天、一般排程或 what-if 本身已经存在，不能单独宣称行业首创。该研究范围也不足以证明不存在具有类似能力的商业产品。

## 4 数据来源与运行模式

### 4.1 来源类型

| `origin_kind` | 内容 | 可否出现在真实模式 |
|---|---|---|
| `terminal49_live` | 团队账号实际返回的数据与已验证 webhook | 是 |
| `terminal49_fixture` | 按官方结构生成或经过脱敏处理的离线样例 | 否，只在重放或模拟工作空间 |
| `operator_report` | 人员输入的现场报告；记录角色、时间和附件引用 | 本版本默认关闭真实现场输入；未来启用需配置权限 |
| `simulation_operational` | 车道、设备、温度、称重、司机到达、事故与恢复 | 否，只在模拟工作空间 |
| `derived` | 由证据与规则计算的结论 | 可以，必须携带输入证据引用与规则版本 |

历史公告属于离线参考资料，不能自动变成当下运行状态。港方、消防局、运营商网页用于编写案例，不作为第二个运行时业务数据接口。LLM 服务是计算服务，不是新的事实提供方。

### 4.2 三种工作空间

| `mode` | 时钟与数据 | 可用功能 | 必须显示的标识 |
|---|---|---|---|
| `LIVE_T49` | 当前 UTC 时间；真实 Terminal49 | 追踪、准备状态、协调任务、交班与观测指标 | `Live Terminal49`、账号跟踪范围、最近检查时间 |
| `REPLAY_T49` | 可暂停的重放时间；Terminal49 结构的 fixture | 事件回放、规则与接口演示 | `Synthetic replay` 或 `Sanitized historical replay` |
| `SIMULATION` | 虚拟时钟；fixture 加独立运营模型 | 全部协调、资源排程、事故演练和比较实验 | `Simulation`、模型版本、参数与种子 |

模式在创建工作空间时确定，之后不可原地切换。切换模式创建新工作空间，防止模拟数据污染真实记录。真实密钥绝不发送到浏览器，也不用于模拟场景的写回。

### 4.3 Terminal49 字段合同

下表是截至编写日期官方文档支持的字段类别；真实账号返回情况仍需启动探测和逐字段验证。[Container API](https://terminal49.com/docs/api-docs/api-reference/containers/get-a-container)、[Field availability](https://terminal49.com/docs/coverage/fields)。

| 数据 | 字段或关系 | 在本产品中的含义与限制 |
|---|---|---|
| 身份 | 资源 `id`、`number`、shipment 关系 | 用资源 ID 加旅程关系识别记录，不能仅按可能重复使用的箱号合并历史旅程 |
| 可提状态 | `availability_known`、`available_for_pickup` | 必须保留未知；只表达当前供应方报告，不授予本应用放行权限 |
| 扣留 | `holds_at_pod_terminal` | 保留多项；区分 `hold`、`pending` 和未识别值 |
| 费用 | `fees_at_pod_terminal` | 保留金额、币种和类别；不从金额推算合同日费率 |
| 最后免费日 | `pickup_lfd`、`import_deadlines.*` | 同时保留合并值和各来源；来源冲突生成待核实事项 |
| 预约 | `pickup_appointment_at` | 只代表已取得的预约信息；空值不等于确定没有预约 |
| 里程碑 | `pod_discharged_at`、`pod_full_out_at` 等 | 用于本账号跟踪货柜的事件和停留观测，不能代表全港库存 |
| 所属码头 | `pod_terminal`、`pickup_facility` | 过滤洛杉矶港并定位码头；未知关系进入待确认队列 |
| 场内位置 | `location_at_pod_terminal` | 可为场区文本；不转换为精确堆叠位置或可行驶道路 |
| 设备类型 | `equipment_type`、`equipment_length`、`equipment_height` | `reefer` 表示冷藏设备，不证明当前温度、货物类型或医疗用途 |
| 重量 | `weight_in_lbs` | 船公司相关字段，可缺失；不作为独立地磅测量或实测 VGM |
| 数据检查 | `terminal_checked_at`、tracking 时间 | 用于采集状态；不等同于某个重量、温度或业务状态实际发生时间 |
| 船期 | shipment ETA、ATA 和相关 transport events | ETA 是估计；不等于提柜时间、装船截关或作业许可 |

**不具备公开字段保证的内容**：实时冷藏温度和设定温度、插电状态、独立地磅实测、当前空重申报与实物对照、可用车道、堆场设备和班组、道路关闭、安全恢复许可。获得个别自定义字段也不改变来源：用户写入 Terminal49 的自定义数据不能因此被标成 Terminal49 独立测量。

重量有特别的数据解释风险：官方船公司覆盖说明指出，部分来源可能返回一票货的平均重量。适配器需保留该来源说明，避免逐柜实测的误解。[船公司数据解释](https://terminal49.com/docs/coverage/ocean-carriers)

### 4.4 空值与状态规则

| 输入 | 必须输出 | 禁止推断 |
|---|---|---|
| `availability_known=false` | `UNKNOWN` | 无扣留所以可提 |
| 可提 `true`、无 active hold、证据有效 | `REPORTED_AVAILABLE` | 所有现场条件齐备或系统授权放行 |
| 可提 `true`、仍有 active hold | `CONFLICT`，保留扣留，安排重新读取或协调 | 选择相信其中一项并自动放行 |
| 可提 `false`、holds 为有效空数组 | `REPORTED_UNAVAILABLE`，原因未报告 | 一定是海关扣留 |
| 已明确返回 `holds=[]` | 无已报告 active holds | 把它当缺失数据错误，或扩大为所有机构已确认放行 |
| holds 字段缺失或 `null` | 扣留信息未知 | 自动替换为空数组 |
| `pickup_appointment_at=null` | 未取得预约信息 | 司机确定没有预约 |
| `pod_full_out_at=null` | 尚未收到 full-out 时间 | 柜子确定仍在该场区 |
| 已知 active hold 后数据中断 | 保留最后已知 hold，加当前状态待更新 | 数据不可信所以撤销扣留 |
| `pending` hold | 待发生的警示，单独列出；按应用政策要求派遣前复核 | 等同于已发生 active hold，或完全忽略 |
| 未识别的 hold 名称或状态 | 保存原值、标记需核实 | 丢弃未知项以得到可提结论 |

待更新时长阈值是应用的提示政策，不是 Terminal49 的服务时效保证。新证据是否能推翻旧证据必须看同一旅程、字段、来源、业务时间和完整性；最新收到的消息不一定描述最新业务状态。

### 4.5 LFD 与费用

官方合并 `pickup_lfd` 按 line → terminal → rail 的固定优先级选择，不是最早日期。系统保存全部日期，另定义 `attention_deadline` 为提醒政策选出的日期，并显示政策和来源。提醒采用更早日期不能被描述成更改合同免费期。[LFD 说明](https://terminal49.com/docs/api-docs/webhooks/use-cases/lfd-alerts)

费用使用 Decimal，保留币种。存在明细及 `total` 时不重复相加；只有 total 时展示该合计；多个合计或合计与明细不符时保留各项并提示核实。不跨币种求和。金额为零、缺失金额和已确认无费用是不同状态。真实模式不根据 `free_days_left` 合成每日账单。[Holds and fees](https://terminal49.com/docs/api-docs/in-depth-guides/holds-and-fees)

### 4.6 账号与覆盖预检

服务端读取当前凭据能力、少量本账号资源及目标码头覆盖，输出能力矩阵：`supported`、`permission_denied`、`not_configured`、`not_observed`、`unknown`。区分账号读取权限、字段是否支持以及某柜暂时未返回值。

公开文档目前对免费账户 GET 读取有限制，试用窗口和 active-container 数量也有限；开发不能假设普通免费 key 能读取 100 个柜。权限和价格可能变化，因此启动时检查真实响应，UI 显示实际能力。没有读取权限时使用独立演示模式，不购买或升级账号。[API 权限](https://terminal49.com/docs/api-docs/useful-info/entitlements)

## 5 工作流程与决策边界

### 5.1 行业要求与应用策略

| 类型 | 示例 | 实现方式 |
|---|---|---|
| 适用的安全要求 | 确认空重、重量信息、起吊能力 | 规则引用依据与适用作业；不把 VGM 规则套到全部进口闸口 |
| 外部权限 | active customs hold、道路封控、特定移位许可 | 与商业目标分开；只有相应新证据更新其状态 |
| 码头程序 | 预约、交接检查、场区与操作权限 | 每码头配置，未取得内容时显示未验证 |
| 合同与服务承诺 | 交付时间、约定的服务窗口 | 可比较违约风险；调整需留记录，不假设全部都可任意协商 |
| 应用建议政策 | 提示阈值、任务升级时限、排程冻结窗口 | 配置化、版本化，标明是产品选择 |
| 模拟假设 | 设备数量、耗时分布、温度演练阈值 | 仅在仿真中生效，参数面板可查看 |

OSHA 对适用装卸作业的空重和重量有要求；IMO 指南第 11、12 节分别说明车载称重与空柜确认。用经核实的柜号、单位、车辆扣重、箱体自重和合格测量判断差异，不设置“所有空柜 8 吨以上必然装货”的行业结论。[OSHA 1918.85](https://www.osha.gov/laws-regs/regulations/standardnumber/1918/1918.85)、[IMO MSC.1/Circ.1475](https://wwwcdn.imo.org/localresources/en/OurWork/Safety/Documents/MSC.1%20Circ.1475.pdf)

### 5.2 自动化与人员职责

自动化可以：校验结构与时间、识别报告不一致、计算派生状态、生成版本化待办、在已知约束中求解模拟安排、准备解释和交班摘要。

运营人员可以：认领任务、记录已联系或等待回复、选择有权限采用的模拟计划、记录现场报告。认领或点击完成不能产生海关放行、道路开放或货物质量合格的事实。

真实外部系统仍负责相应许可与现场执行。本产品不提供通用 `override_hold` 功能。授权保税移运与交付收货人的提离是不同动作；若未来支持前者，需要独立动作类型、许可依据与验收，不能把“有 hold”解释成任何现场处理均禁止。

### 5.3 多问题并行

每个柜有独立 `issues[]`、`constraints[]`、`actions[]`、`tasks[]`。重量问题不能遮盖温度报警；海关扣留不应阻止生成冷藏状况核查任务，但实际移位仍检查自身条件。警示事实、操作限制和工作待办各有自己的生命周期。

任务默认链路：`open → acknowledged → in_progress → waiting_external → resolved`。允许从 waiting 回到 in_progress，允许问题撤销后 cancelled。任务被重新触发时增加 episode，不重复刷出大量同一报警；已完成记录留在时间线。

`resolved` 必须说明完成了什么：联系已完成不等于 hold 已解除，维护已完成不等于货物质量已获批准。由规则判定问题是否解除；人工记录任务结果只更新它负责的事项。

### 5.4 陌生事件与大模型

陌生事件先进入通用流程：接收报告 → 标记来源与未知 → 确认作用范围 → 建立待核实任务 → 根据已证实变化重排。来源描述不足时不能自动创造道路、设备或许可变化。

LLM 可以基于已有证据提出候选解释、列出需要确认的问题、把非结构化描述整理为待审阅草稿、说明候选方案取舍。输出分为 `established_facts`、`hypotheses`、`questions`、`draft_actions`，每条事实带证据引用。

LLM 不直接修改证据、许可、资源容量、优先政策或求解结果。原始码头描述为不可信输入，不用其文本执行动作。结构化校验拒绝未知证据引用和越界动作；模型失败时保留结构化规则解释。模型对未来恢复时刻的猜测只可进入单独的模拟敏感性分析。

## 6 领域模型与数据存储

### 6.1 架构与技术选择

采用模块化单体：React 与 TypeScript 前端；FastAPI 与 Pydantic 后端；PostgreSQL 为完整产品存储；本地离线演示允许 SQLite；SQLAlchemy 与 Alembic 负责持久化和迁移；OR-Tools CP-SAT 负责仿真排程。Node 和 Python 依赖均锁定在仓库中，并在 CI 与 Docker 中使用同一锁文件。

后台任务由持久化 job 表和独立 worker 进程运行。第一版不需要消息集群。数据库事务、幂等记录和 job lease 保证失败可恢复；worker 重启能够重新领取到期任务。生产和仿真实例隔离，所有查询带工作空间边界。

数据链路为：Terminal49 HTTP 与 webhook → 原始 inbox → 验证与标准化 → 证据存储 → 当前状态投影 → 问题与任务 → 模拟排程或真实协调 → 前端与审计。仿真引擎从独立 fixture 和运营事件进入同一内部事件模型。

### 6.2 目录约定

```text
apps/web/                 React TypeScript 页面与组件
gate_triage/api_v1/        版本化 HTTP 合同与鉴权
gate_triage/connectors/    Terminal49 客户端与 webhook 验证
gate_triage/domain/        类型 时间 证据 状态 规则
gate_triage/workflows/     问题 待办 决策版本
gate_triage/planning/      约束模型 候选计划 独立验证
gate_triage/simulation/    虚拟时钟 事件队列 策略比较
gate_triage/persistence/   表模型 仓库与事务
gate_triage/llm/           可选结构化解释适配器
fixtures/t49/             合成供应方响应和 webhook
scenarios/                版本化场景与参数
tests/                    单元 合同 集成与性质测试
e2e/                      浏览器验收
docs/                     本规范 方法说明 运行手册
```

### 6.3 表与关键约束

| 表 | 核心字段 | 约束与用途 |
|---|---|---|
| workspaces | id mode organization_id revision created_at | 模式不可变；所有子表按 workspace 隔离 |
| users / memberships | id organization_id role password_hash disabled_at | 单租户试点账号与角色；公开合成演示使用独立访客会话 |
| sessions | id_hash user_id workspace_scope expires_at revoked_at | 服务器会话；浏览器只持有随机会话 cookie |
| provider_credentials | encrypted_reference capabilities last_probe_at | 不返回明文密钥，不与仿真共享 |
| provider_inbox | provider account event_id body_hash raw_body received_at status | `(account,event_id)` 去重；同 ID 不同正文隔离审查 |
| container_journeys | id provider_id number shipment_id terminal_id | 旅程身份；箱号不是唯一历史键 |
| evidence | id subject field value origin_kind source effective_at received_at precision raw_ref | 追加保存；不覆盖原始证据 |
| container_projections | journey_id projection_json revision evidence_ids | 可从证据与规则版本重建 |
| issues | id journey_id kind episode status evidence_ids | 同一活跃 episode 唯一 |
| tasks | id issue_id kind owner_role status due_at resource_requirements revision | 并行待办，任务状态与问题状态独立 |
| task_events | id task_id actor action evidence_refs occurred_at | 认领、转派和完成的历史 |
| policies | id version content approval_status | 硬条件与服务策略分开版本化 |
| incidents | id scope status reported_at effective_at reference_kind | 道路、闸口、区域、时间分别表达 |
| resources | id simulation_id kind capabilities calendar | 仅在运营模型中有资源容量 |
| simulation_runs | id scenario_version seed clock status parent_id | 独立虚拟世界，可重建 |
| replay_runs | id workspace_id fixture_hash cursor snapshot_revision status | 只读来源重放，定位历史时点后可重建投影 |
| simulation_events | run_id sequence observed_at effective_at payload | 可见时间与物理发生时间分开 |
| plans | id workspace_id input_revision policy_version status metrics_json | 每个结果绑定输入与求解状态 |
| plan_operations | plan_id task_id resource_id start_at end_at conditional | 时间区间与前置条件 |
| audit_events | id actor action target before_hash after_hash provenance | 原因、证据及变更可追查 |
| jobs | id kind payload status lease_until attempts error_code | 接入、求解、仿真、解释的持久化任务 |

对 raw_body 和原始来源保留可配置期限；审计不声称具有防篡改认证。个人联系方式不进入公开演示 fixture。数据库唯一键防重复，并发更新用 revision 乐观锁。

### 6.4 统一证据对象

以下是本应用的内部对象，不是 Terminal49 的原始响应格式。

```json
{
  "evidence_id": "ev-demo-001",
  "subject_id": "journey-demo-001",
  "field": "availability",
  "value": {"known": true, "available": false},
  "origin_kind": "terminal49_fixture",
  "source": {"provider": "terminal49", "upstream": "terminal", "terminal_id": "terminal-demo-la"},
  "effective_at": "2026-10-17T16:00:00Z",
  "received_at": "2026-10-17T16:03:00Z",
  "time_precision": "second",
  "quality": "reported",
  "raw_ref": "inbox-demo-001",
  "scenario_id": "normal_operations"
}
```

时间为带时区 ISO 8601，数据库存 UTC，界面按 America/Los_Angeles 展示。date-only 保留 `time_precision=date`，不得用补上的午夜计算分钟级性能。没有业务时间则保存 null，不用接收时间冒充。

### 6.5 派生结论

```json
{
  "decision_id": "decision-demo-001",
  "subject_id": "journey-demo-001",
  "input_revision": 7,
  "rule_version": "readiness-1.0",
  "pickup_state": "REPORTED_UNAVAILABLE",
  "urgency_band": "high",
  "evidence_ids": ["ev-demo-001"],
  "reason_codes": ["ACTIVE_CUSTOMS_HOLD", "LFD_APPROACHING"],
  "actions": [
    {"kind": "coordinate_customs", "feasibility": "allowed", "owner_role": "customs_broker"},
    {"kind": "outgate_delivery", "feasibility": "blocked", "blocker_codes": ["ACTIVE_CUSTOMS_HOLD"]}
  ]
}
```

`allowed` 仅指该动作在本应用当前模型中的条件允许；真实模式动作范围为协调，现场出闸仍标为供应方报告和额外条件待确认。每个 action 单独检查，不让一个通用状态控制所有动作。

## 7 标准化规则与状态更新

### 7.1 规则目录

| 规则标识 | 触发与结果 | 依据类别 |
|---|---|---|
| R01 | 活跃 hold 存在时，交付出闸建议受阻；生成对应协调任务 | 供应方结构化状态及适用外部权限 |
| R02 | availability 与 active hold 不一致时进入 conflict 并重新核实 | 数据一致性策略 |
| R03 | 未知、未识别或过时的数据保留未知，已知 hold 不因过时消失 | 应用保守状态策略 |
| R04 | LFD 来源不同生成日期差异任务，保留原值与提醒策略 | 供应方日期语义与应用政策 |
| R05 | 缺少实际温度时不生成升温结论 | 数据来源边界 |
| R06 | 重量比较先检查单位、口径、箱体身份与测量来源 | 适用称重安全要求与应用校验 |
| R07 | 关闭范围只阻止使用该范围的动作，不影响无关任务 | 模拟地图与事件作用域 |
| R08 | 操作人员认领、已联系和已维护不产生外部放行 | 权限模型 |
| R09 | 恢复事件仅撤销对应 incident 带来的限制 | 状态与审计一致性 |
| R10 | 尚未发生、不可见或只是假设的许可，不计入可执行计划 | 仿真信息边界 |
| R11 | active/pending/unknown hold 保持不同语义 | 官方字段语义 |
| R12 | 同一设备时间区间、容量与前置关系经独立验证后才能提交计划 | 排程可行性要求 |

规则目录用机器可读配置或确定性函数实现，输出规则标识、证据引用和解释。规则可以包含条件判断；技术深度来自联合排程、不确定情景和闭环验证，而不是隐藏或否认这些边界判断。

### 7.2 任务角色与结果

角色包括 planner、terminal_operations、carrier_contact、customs_broker、reefer_technician、equipment_maintenance、supervisor。角色是责任类别，不是已验证的某码头组织架构或员工人数。

任务类型至少包括 `verify_availability`、`coordinate_hold`、`reconcile_lfd`、`verify_weight_basis`、`reweigh_request`、`reefer_condition_check`、`confirm_resource_status`、`prepare_pickup`、`review_unknown_incident`。现场类任务仅在有对应现场报告或模拟事实时生成。

状态变化写入 task_events；关闭任务需要结果代码与证据引用。更新当前状态投影后，再决定该 issue 是否解决。若仍有其他 blocker，界面保持该 blocker；不因一个任务结束将整个柜子变绿。

### 7.3 紧急程度

`critical/high/normal` 是响应等级，不是出闸许可。等级由可配置的事实触发和服务策略产生，解释需列出最主要原因。真实模式不能从设备类型猜测“医院疫苗”；模拟 fixture 可以明确设置 `cargo_criticality`，同时标记来源。

没有经过货物规范验证的温度范围、持续时长和货损模型时，只能提示条件异常核查，不能倒计时预测报废。普通任务采用等待累积或最大等待目标避免长期得不到服务。

## 8 多方利益与优化策略

### 8.1 各方目标进入模型的方式

| 参与方 | 利益诉求 | 可获取或可配置的输入 | 保护方式 |
|---|---|---|---|
| 码头运营方 | 完成量、堆场通畅、设备利用 | 资源与作业模型仅来自模拟或已确认现场配置 | 最大化有效交接，报告忙碌、空闲与不可用原因 |
| 船公司与船舶运营方 | 截关、装船窗口、相关计划稳定 | Terminal49 船期不等于截关；截关和任务关联只能由配置或明确报告提供 | 把已确认窗口作为服务约束，不假称已优化船舶离港 |
| 货主与收货方 | 按期交付、货物状况、避免长期被插队 | 合同和重要性不由设备类型推断；演示中显式配置 | 最大合格等待、期限违约和业务组差异 |
| 卡车公司与司机 | 预约履约、总等待、减少空跑 | 实际到达与车队资源不在已核实 T49 核心合同内；只在仿真提供 | 外部与内部等待分开，长尾等待可见 |
| 作业人员 | 合法、安全且稳定的任务 | 班次、资质、设备能力在运营模型配置 | 已启动任务与冻结窗口，单人和多人任务容量 |
| 海关及其他有权机构 | 检查与许可条件得到执行 | T49 结构化报告及独立许可类别 | 作为不可被收益抵消的条件 |
| 应急管理方 | 封控范围、应急调派、恢复次序 | 真实模式无事故接口；演练中用带来源的本地事件 | 限制作用域、恢复确认、任务与指挥角色分开 |

### 8.2 决策层次

模型先满足不可突破的权限、物理和资源约束。其后按已批准的关键服务政策、有效交接完成量、最大合格等待、群体等待差异及计划稳定性分层优化。费用只用于辅助对照或运营效果相同的末级选择。

重要服务目标未必总能满足，必须报告不足及未服务任务，不能通过不选某项任务获得“零违约”。合同中的硬截止与可协商目标由 policy 明确区分，算法不能擅自把合同义务全部软化。

### 8.3 候选方案与公平性

默认提供不超过三种候选：`Throughput`、`Balanced waiting`、`Stable recovery`。它们共用同一安全与关键服务底线；只在公开的次级目标或允许的完成量让步范围上有差异。用户能看到哪组业务多等、最长等多久、减少几次重排、完成量有何变化。

采用 epsilon 约束时，先保留一个最好已知可行完成数，再限定允许的让步量，优化等待和稳定性。若没有证明最优，只能称“当前候选中的最好可行值”。候选不被其他已找到方案支配时可标为 `Non-dominated among generated candidates`，不能称已计算完整 Pareto 前沿。

公平性不按船公司规模或谁愿意付更多钱随意加权。可配置策略至少包括等待老化、最大合格等待目标、已确认服务窗口和关键任务响应时限。对照报告同时保留因权限受阻的时间、合格队列等待和总等待，避免把困难货柜从分母删掉。

### 8.4 增益主张

排序能改变服务次序，但只有资源竞争、耗时差异、依赖、可避免的切换或阻碍解决影响实际执行时，才可能改变完成量。模型必须包含这些机制并检验，不预设优化一定有效。所有任务耗时相同且通道固定的负对照应显示相同理论完成量。

## 9 Terminal49 接入与事件可靠性

### 9.1 服务端适配器

只由后端调用 Terminal49。使用官方 Token 认证；API key 存服务器环境变量或密钥引用。读取前检查当前账号能力；按账号共享请求预算，缓存适当的列表和详情，使用 webhook 更新加补偿读取。终端字段覆盖与账号能力分别报告。

初始同步流程：读取允许范围的 tracking 与 containers → 取得关联 shipment/terminal → 过滤 POD 为 Los Angeles 的旅程 → 按响应分页链接读取 → 保存原始响应及摘要 → 生成证据与投影。未知 POD 进入待确认，不能仅因附近坐标就并入洛杉矶；Long Beach 不在本工作空间范围。

客户端超时、429、5xx 用有限指数退避及抖动；遵守 Retry-After，设置全局请求预算。401/403 区分凭据错误与功能未获授权，禁止无限重试。按需刷新只有账号实际具备权限时显示，不能把本地重算按钮包装成刷新港口现场数据。

### 9.2 Webhook

按官方指南读取原始请求字节，用 webhook secret 校验 `X-T49-Webhook-Signature` 的 HMAC SHA-256，常量时间比较。先验签再信任 JSON。请求体大小、解析时间与请求速率有服务端上限；日志不输出 secret。[官方 webhook 设置](https://terminal49.com/docs/api-docs/in-depth-guides/webhooks)

业务处理顺序：验签 → 验证 envelope → 按账号与 notification `data.id` 去重 → 数据库持久接受 → 返回 202 → worker 标准化 → 更新投影、任务和 revision。返回成功前必须可靠落盘。重复投递正常返回成功，但不重复转换任务或累计指标。

失联恢复不能假设提供方会重播所有漏掉的历史通知。重读受影响资源以恢复当前状态；历史精度不足时标记不可恢复区间，不把补读时间反填为业务发生时间。原始通知和已接受的本地记录支持本应用自己的重放。

### 9.3 事件映射

| Terminal49 事件类别 | 本应用内部变化 | 要求 |
|---|---|---|
| `container.updated` | 货柜属性和 holds/fees/availability 重新评估 | changeset 的前后值与完整快照交叉检查 |
| `container.pickup_lfd.changed` 及来源日期变化 | 更新日期证据与提醒政策 | 保留每个来源，不仅保存合并值 |
| `container.pickup_appointment.changed` | 已取得预约时间变化 | 不代表本应用创建预约 |
| `container.transport.available` | 提柜准备状态候选变化 | 仍读取 active holds 等条件 |
| `container.transport.vessel_discharged` | 卸船里程碑 | 保留发生、接收与时间精度 |
| `container.transport.full_out` | 已报告重柜出场 | 同旅程去重；实际完成事件不能由点击按钮产生 |
| tracking success/failure | 接入工作状态 | 与码头运营故障分开 |

正式订阅名称以锁定的官方事件目录和真实样例验证。不存在的专用 hold changed 名称不能被自行发明为提供方事件。[事件目录](https://terminal49.com/docs/api-docs/webhooks/event-catalog)

### 9.4 乱序与重算

接收顺序不等于业务顺序。里程碑按发生时间组织，状态快照还需要采集版本与获取语义。无法决定新旧时保留两条证据并触发重新读取，禁止简单 last-write-wins 清掉已知限制。

同一事务中保存新证据、投影、任务变化和新 revision。前端用 revision 标识一致快照；异步解释或求解输出只有其 input_revision 与当前适用版本一致时才能提交。

## 10 应用 API 合同

### 10.1 公共约定

基础路径为 `/api/v1`。Pydantic 模型生成 OpenAPI，前端由其生成类型。应用 API 用 `application/json`；提供方 JSON:API envelope 只存在于 connector 与原始记录层。日期、金额、枚举与空值按本规范校验，写入模型禁止未知字段，读取时对提供方新增字段保存原值并降级。

每个成功响应包含 `data` 与 `meta`。meta 至少有 `workspace_id`、`mode`、`revision`、`as_of`、`rule_version`。GET 返回 ETag；修改已有资源时携带 If-Match 和 Idempotency-Key。创建工作空间无已有 ETag，只需幂等键；提供方 webhook 按其验签和 notification ID 处理，不使用浏览器 If-Match。遗漏必要前置版本返回 428，版本不符返回 412，幂等键绑定不同正文返回 409。请求重试必须复用原幂等键。

服务端先按身份、路由、幂等键及正文摘要检查已提交请求，再检查当前版本：若请求已成功提交但客户端丢失响应，返回原结果，不因当前版本已变化而返回 412。相同幂等键的新正文返回 409；新请求才检查 If-Match。正在处理的同键请求返回明确的 pending 状态及 job 引用。

列表用稳定游标分页，默认 50、最大 200。排序必须有业务键和 ID 作为稳定次序。空结果、未知覆盖、无权限和上游错误返回不同语义，不用空数组掩盖错误。

### 10.2 路由

| 方法 | 路径 | 作用 |
|---|---|---|
| POST | `/auth/sessions` | 单租户试点登录；密码校验与限速，不接受客户端自报角色 |
| GET | `/auth/me` | 当前身份、组织、角色和可访问工作空间 |
| DELETE | `/auth/sessions/current` | 注销并撤销服务器会话 |
| POST | `/workspaces` | 创建隔离的 LIVE_T49、REPLAY_T49 或 SIMULATION 工作空间 |
| GET | `/workspaces/{w}` | 模式、版本、能力与工作空间状态 |
| GET | `/workspaces/{w}/overview` | 当前队列、来源状态和模式适用的指标 |
| GET | `/workspaces/{w}/containers` | 按码头、问题、准备状态、紧急度与搜索分页 |
| GET | `/workspaces/{w}/containers/{journey_id}` | 证据、来源、问题、动作条件、任务和历史 |
| GET | `/workspaces/{w}/tasks` | 当前与历史待办，可按负责人和状态筛选 |
| POST | `/workspaces/{w}/task-events` | 认领、进展、联系结果；不得修改外部事实 |
| GET | `/workspaces/{w}/timeline` | 分页的证据、任务、事件与决策变化 |
| GET | `/workspaces/{w}/capabilities` | 实际账号与本工作空间能力矩阵 |
| POST | `/workspaces/{w}/sync-jobs` | 排队进行本账号允许的同步；有频率限制 |
| GET | `/scenarios` | 场景目录、来源、模式要求与参数摘要 |
| GET | `/scenarios/{scenario_id}` | 事实、模拟假设、默认配置与 schema 版本 |
| POST | `/workspaces/{w}/replay-runs` | 以不可变 fixture 摘要创建重放，只用于 REPLAY_T49 |
| GET | `/workspaces/{w}/replay-runs/{replay}` | 当前重放游标、时钟、版本与来源摘要 |
| POST | `/workspaces/{w}/replay-runs/{replay}/commands` | pause、step、seek；seek 从固定事件流重建，不修改来源 |
| POST | `/workspaces/{w}/simulation-runs` | 从场景创建独立仿真运行，仅模拟工作空间 |
| GET | `/workspaces/{w}/simulation-runs/{run}` | 虚拟时钟、运行版本、状态和已观测快照 |
| POST | `/workspaces/{w}/simulation-runs/{run}/commands` | pause、advance、inject、fork；模式与角色受限 |
| POST | `/workspaces/{w}/plan-jobs` | 针对运行与输入版本生成候选计划 |
| GET | `/workspaces/{w}/plans/{plan}` | 求解状态、资源时间表、未安排理由与取舍 |
| POST | `/workspaces/{w}/simulation-runs/{run}/plan-selections` | 在仿真执行选定计划，启动前重新检查 |
| POST | `/workspaces/{w}/experiments` | 运行三策略、多种子的同条件实验 |
| GET | `/workspaces/{w}/experiments/{experiment}` | 进度、参数、逐运行结果和汇总 |
| POST | `/workspaces/{w}/explanation-jobs` | 可选证据解释或交班摘要 |
| GET | `/workspaces/{w}/jobs/{job}` | 异步任务进度、失败与可重试状态 |
| POST | `/workspaces/{w}/exports` | 将指定计划、实验或交班结果排队导出，返回 job |
| GET | `/workspaces/{w}/exports/{artifact}` | 下载去敏计划、实验与交班报告 |
| POST | `/webhooks/terminal49/{connection}` | 提供方验签入口；不使用浏览器会话凭据 |
| GET | `/health/live`、`/health/ready` | 进程与数据库/worker 就绪状态 |

同步、求解、实验、解释等长任务返回 202 与 job_id；不能让浏览器请求无限等待。旧 API 不自动共享新模式的状态；若做兼容适配，必须显式指定工作空间与版本。

重放 `step` 推进到下一可见事件；`seek` 指定范围内的业务时点，使用初始状态或检查点加事件重建，刷新 projection revision 并废弃旧的异步解释。fixture 摘要变化必须创建新 replay。向历史注入假设只能创建 SIMULATION 分支，不允许在 REPLAY_T49 改写来源。重放控制遵守相同幂等与并发合同。

### 10.3 创建模拟工作空间

```json
{
  "mode": "SIMULATION",
  "name": "LA incident rehearsal",
  "scenario_id": "battery_truck_access_2024",
  "seed": 17
}
```

响应示例：

```json
{
  "data": {
    "workspace_id": "workspace-demo-001",
    "initial_run_id": "run-demo-001",
    "capabilities": {"live_sync": false, "simulation": true, "physical_execution": false}
  },
  "meta": {
    "workspace_id": "workspace-demo-001",
    "mode": "SIMULATION",
    "revision": 1,
    "as_of": "2026-10-17T16:00:00Z",
    "rule_version": "readiness-1.0"
  }
}
```

示例 ID 便于阅读，实际实现使用不透明 ID，不把箱号作为权限令牌。

### 10.4 任务进展与外部事实

```json
{
  "task_id": "task-demo-001",
  "action": "record_contact",
  "result_code": "awaiting_carrier_response",
  "note": "Awaiting confirmation of the declaration basis.",
  "evidence_ids": ["ev-demo-001"]
}
```

`action` 允许 `acknowledge`、`start`、`record_contact`、`wait`、`record_result`。记录结果须符合任务类型允许的 result_code。任何动作都不接收 `clear_customs=true` 或任意 field patch。测试用模拟来源变化通过 run command 注入，与真实任务记录端点分开。

### 10.5 模拟事件命令

```json
{
  "command": "inject",
  "event": {
    "type": "resource.availability",
    "resource_ids": ["east-lane-1", "east-lane-2"],
    "state": "closed",
    "capacity": 0,
    "applies_at_min": 30,
    "published_at_min": 30,
    "observed_at_min": 32,
    "provenance": "synthetic"
  }
}
```

服务器只接受 schema 中定义的事件类型。仿真已经推进过某时刻后，不能原地注入过去事实重写历史；需 fork 到指定快照创建反事实分支。`advance` 的每次最大步长为 120 分钟、总量不超过场景 horizon；`pause` 幂等；同一运行只允许一个推进 job。

### 10.6 计划结果

```json
{
  "data": {
    "plan_id": "plan-demo-001",
    "run_id": "run-demo-001",
    "input_revision": 12,
    "solver_status": "FEASIBLE",
    "policy_version": "balanced-1.0",
    "horizon_minutes": 60,
    "objective_values": {"critical_service_penalty": 0, "projected_handoffs": 8},
    "optimality_proven": false,
    "operations": [
      {"operation_id": "op-demo-001", "task_id": "task-demo-001", "resource_ids": ["scale-1"], "start_min": 32, "end_min": 42, "commitment": "committed_safe", "evidence_ids": ["ev-demo-001"]}
    ],
    "unscheduled": [{"task_id": "task-demo-002", "reason_codes": ["ACTIVE_CUSTOMS_HOLD"]}],
    "comparison_scope": "simulation_cohort_only"
  },
  "meta": {"workspace_id": "workspace-demo-001", "mode": "SIMULATION", "revision": 12, "as_of": "2026-10-17T16:32:00Z", "rule_version": "readiness-1.0"}
}
```

计划开始、结束用相对 run start 的整数分钟；API 同时提供可显示的 UTC 时间。projected_handoffs 是计划估计，不进入 actual completed 指标。计划选择必须引用输入 revision，过期则 412 或返回明确 `PLAN_STALE`。

### 10.7 错误合同

```json
{
  "error": {
    "code": "SOURCE_PERMISSION_DENIED",
    "message": "The configured account cannot read this Terminal49 resource.",
    "retryable": false,
    "field_errors": []
  },
  "meta": {"request_id": "request-demo-001"}
}
```

至少定义 `VALIDATION_ERROR`、`MODE_NOT_ALLOWED`、`REVISION_CONFLICT`、`IDEMPOTENCY_CONFLICT`、`SOURCE_NOT_CONFIGURED`、`SOURCE_PERMISSION_DENIED`、`SOURCE_RATE_LIMITED`、`SOURCE_UNAVAILABLE`、`PLAN_STALE`、`PLAN_INFEASIBLE`、`SOLVER_TIMEOUT`、`JOB_FAILED`。用户文案不泄露上游密钥、响应隐私或堆栈。

### 10.8 其余请求的输入要求

| 请求 | 输入与校验 |
|---|---|
| 创建重放 | `fixture_id`、`fixture_sha256`、`start_at`；文件必须在已登记 fixture 中，摘要匹配 |
| 重放命令 | `command=pause/step/seek`；seek 另有 `target_at`，仅允许 fixture 时间范围 |
| 创建仿真 | `scenario_id`、`scenario_version`、`seed`、允许的 `parameter_overrides`；覆盖项经场景 schema 校验 |
| 求解计划 | `run_id`、`input_revision`、`profile_ids`；profile 只能选已登记且共用硬约束的策略 |
| 选择计划 | `plan_id`、`input_revision`；限定当前运行，无新事实时方可提交；启动前仍检查 |
| 创建实验 | `scenario_ids`、锁定版本、`seeds`、`strategies`、`horizon_minutes`；三策略完整，初始最多 30 seeds，每工作空间最多一个执行中实验 |
| 解释请求 | `subject_ids` 或 `plan_id`、`input_revision`、`purpose=decision/shift_handoff`；仅已授权对象 |
| 导出请求 | `subject_type=plan/experiment/handoff`、`subject_id`、`format=json/csv/html`；每种对象限定格式，不任意读取服务器路径 |
| 列表查询 | search、terminal、pickup_state、issue_kind、owner_role、cursor、limit；未支持的过滤项返回明确校验错误 |

异步 job 状态统一为 `queued/running/succeeded/failed/cancelled/superseded`。GET job 返回 progress、输入版本、结果资源引用、错误码和 retryable；后台 Job、协调 Task 和资源 Operation 的状态分别定义。参数越界返回 422，实例并发额度用尽返回 429 并带建议重试时间。导出在服务端再次检查范围，文件名与路径由服务端生成。

## 11 后端事务与可恢复执行

### 11.1 一致性

证据与用户事件追加写入，状态投影可重建。任务、来源、计划和 run 各自有 revision；工作空间顶层 revision 支持一致读取。worker 在提交前检查输入版本，过时输出保留为 superseded，不能覆盖新状态。

一个 accepted command 在同一事务中写幂等记录、审计事件和 job。worker 采用 lease 领取，续租失败停止提交。任务重试不会重复应用业务状态。进程重启后恢复 queued 和 lease 到期任务，完成的结果可再次读取。

### 11.2 查询与更新

普通 GET 读取当前投影，不触发提供方请求或求解。前端可以短周期读取本应用版本，不等于对每个柜重复请求 Terminal49。长任务只在明确事件触发或用户请求时运行，并按工作空间节流。

支持 SSE 推送 revision、job 状态与摘要；初始实现也可用带 ETag 的轮询，二者均不得丢失最终状态。客户端重新连接后重新读取权威快照，不依赖内存中是否收到全部推送。

### 11.3 权限与公开演示

公开演示只创建隔离的合成工作空间，不能列举其他会话。真实模式需要服务器身份验证和组织级数据范围控制；若认证未配置，拒绝真实数据模式。可使用已有身份系统或自托管会话，身份服务不提供业务事实。

planner 可处理任务，supervisor 可选择和版本化业务政策，viewer 只读，simulator 可修改合成事件。角色不授予外部机构权限。公开实例设置工作空间、job、请求和存储额度，过期合成会话可清理；真实资料不进入公开分享。

第一版的单租户试点采用本地 users、memberships 和服务器 sessions，密码以 Argon2id 哈希保存；首个管理员通过部署时一次性初始化命令创建，不提供默认密码。cookie 使用 HttpOnly、Secure 和合适的 SameSite，写请求校验 CSRF 与 Origin。公开访客只能操作绑定自己会话的合成空间。后续接企业身份系统作为独立适配，不阻塞离线成品。认证端点有自己的限速与错误合同，登录失败不泄露用户是否存在；初次登录无 If-Match，幂等和 CSRF 行为单独定义。注销当前会话天然幂等。

## 12 大模型接口与降级

### 12.1 结构化请求

解释服务接收当前证据摘要、已计算问题、许可和候选计划，不接收密钥。请求绑定 input_revision 和允许的证据 ID 集合。没有模型 key 时系统完整运行，解释显示 deterministic 模板。

```json
{
  "input_revision": 12,
  "established_facts": [{"text": "The provider reports an active customs hold.", "evidence_ids": ["ev-demo-001"]}],
  "hypotheses": [],
  "questions": ["Which party is awaiting the release update?"],
  "draft_actions": [{"kind": "coordinate_hold", "owner_role": "customs_broker", "evidence_ids": ["ev-demo-001"]}]
}
```

这是目标输出合同示例。响应经 JSON Schema、证据引用、允许动作和长度校验后显示；不能写回规则、资源或许可。无依据的“实际已放行”“道路已恢复”“货物安全”等事实声明不得呈现为确定结论。

### 12.2 未知事件处理

先确认来源、地点、范围、有效时段和缺失内容，生成核实任务。LLM 可提出多个可检验假设，运营人员确认后形成新的显式报告。真实模式缺少现场输入能力时维持 unknown，不把模型的常识补全当作收到的现场证据。

### 12.3 运行约束

每次请求有超时、最大输出、重试次数和费用预算；解释结果缓存与规则版本绑定。模型不可用、格式错误或证据不足时回退模板，不阻塞数据接收、任务显示或仿真。日志仅记录 provider、model、延迟、状态与脱敏引用。

本版本不训练 GRPO 或强化学习模型。已明确的约束优化与可重现实验足以构成技术核心；后续只有在积累数据、评价环境和可验证收益后才讨论学习策略。


## 13 前端页面与交互规范

本文定义待开发的独立产品，不代表现有代码已经实现。交付界面使用英文，规格与开发说明使用中文；不改动团队已有前端。建议 React、TypeScript、Vite，使用由后端 OpenAPI 生成的类型客户端。借鉴成熟可视化平台的货柜追踪、异常筛选、来源展示和时间线；项目差异集中在“证据 → 限制 → 多项任务 → 同约束方案对照 → 恢复过程”，不把通用看板或排序算法宣称为首创。

### 13.1 三种工作模式与可信边界

| 模式 | 持续显示的标识 | 数据与可用操作 |
|---|---|---|
| LIVE_T49 | `LIVE · Terminal49`，最近成功同步时间、覆盖货柜数 | 唯一外部业务数据源为 Terminal49。展示实际返回的状态与事件；允许创建内部协作待办。不得向海关、码头或设备执行放行、调度命令。 |
| REPLAY_T49 | `REPLAY · Recorded data`，记录版本与回放时间 | 重放已保存的 Terminal49 事件及内部事件，允许暂停、逐事件推进、定位历史时点；不能称为实时运营。假设性操作必须另建仿真分支。 |
| SIMULATION | `SIMULATION · Synthetic operations`，场景及模拟时间 | 使用明确标识的合成资源、到达过程和处理时间；可以测试封路、减容、断电及恢复。继承的真实观察与新生成的模拟事实分别标注。 |

模式由服务端会话上下文决定，不能仅靠前端切换颜色。切换模式时选择或创建独立上下文，禁止把仿真事件写回实时视图。页眉、详情页、导出文件和截图范围内都应保留模式标识。只连接 Terminal49 不代表能获得温度、地磅、车道、司机位置或冷藏插座状态；没有字段就显示 `Not provided`，不得由模型补造。概念场地图仅出现在仿真模式，标明 `Conceptual layout · Not an actual terminal map`。

### 13.2 页面结构与视觉要求

采用清晰的英文运营控制台：浅色背景、深色文字，青色表示已确认进展，琥珀色表示需关注，红色仅表示高优先级或限制；颜色必须伴随文字和图标。避免用大量同等权重的卡片淹没任务。

| 区域／组件 | 必须展示 | 主要交互 |
|---|---|---|
| `ContextBar` | 工作模式、数据范围、时钟、来源连接状态、会话名称 | 切换上下文、刷新、打开数据说明；刷新失败保留最后成功时间 |
| `MetricStrip` | 吞吐与积压优先，费用次要；指标口径、时间窗、覆盖率 | 点击进入构成该指标的货柜或事件；观察指标与仿真指标分组 |
| `AttentionQueue` | 紧急任务、货柜、原因、负责人、截止或等待时间、可执行性 | 搜索全部匹配记录，按任务状态、风险、证据质量筛选；排序依据可见 |
| `AvailabilityQueue` | 当前报告的可提状态、报告时间、限制及未知项 | 与关注队列并列；标签使用 `Reported available`，不得使用暗示本系统授权的 `Cleared by us` |
| `ContainerInspector` | 身份、当前问题、证据、并行任务、限制、决策变化 | 从任何列表打开同一货柜；支持深链接及浏览器返回 |
| `ScenarioWorkspace` | 合成资源、依赖关系、调度甘特图、受影响范围 | 仅仿真可编辑；改变参数后重新计算，展示变化依据 |
| `DecisionTimeline` | 来源事件、内部操作、规则版本、建议变化及因果引用 | 过滤单柜或全场景，跳到对应证据；不把重复投递显示成两次业务变化 |

桌面保持“队列＋详情”同时可见，长列表分页或虚拟化并保留总数；筛选作用于全部记录而非当前页。窄屏将详情改为独立页面或可访问抽屉，返回时恢复筛选和滚动位置。提供键盘焦点、语义表格、可见标签和屏幕阅读器状态通知；状态更新不抢焦点，不仅靠闪烁或动画提示。

### 13.3 指标必须回答的具体问题

**观察层指标只描述已追踪对象。** `Tracked full-out events` 按选定窗口内去重的有效 full-out 事件计数，使用事件发生时间；事件修正后重新计算，不能把接口请求数当吞吐量，也不能外推全港吞吐量。`Observed terminal dwell` 只计算同一运输周期、起止事件完整且时序有效的样本；显示样本数、缺失率和分位数。未出闸货柜显示“截至当前观察时间的等待时长”，不混入完整停留时长均值。来源未提供某指标时隐藏图表或展示缺失原因，不能填零。

**仿真层指标以实际模拟完成事件计算。** 首屏建议显示 `Modeled departures/hour`、`Backlog`、`Critical-task response`；详情增加车辆等待／周转时间和恢复时间。处理能力上限不等于完成吞吐量；没有模拟车辆到达、进闸与离闸事件时，不得展示车辆周转时间。费用只能标为 `Modeled fee exposure`，明确费率、计时、免租期、暂停计费假设和覆盖范围，不称为已实现节省。关键处置速度、完成吞吐量和约束违规数应与费用一起报告，不能用单个金额概括质量。

### 13.4 货柜详情与任务闭环

详情按“发生什么 → 证据是什么 → 目前不能做什么 → 下一步由谁做”排列。证据行必须有来源字段、业务含义、原值及单位、观察时间、接收时间、质量／缺失标识；禁止把“更新时间较新”自动等同于“权威更高”。系统推导与来源原文分开显示，并能展开规则解释。

一个柜子可以同时存在重量核验、冷藏维护和清关协调任务。任务展示负责人或责任团队、优先级理由、依赖条件、下一步、所需证据及状态。状态至少覆盖待认领、已确认、处理中、等待证据、已解决、已取消；终态由后端验证条件，前端不能用通用“完成”按钮跳过核验。缺少证据或来源离线时，展示具体阻碍和最后已知状态，不把未知解释为许可。

需要关注的柜子与可以安排出场的柜子分开排序。已知 hold 不被人工高优先级、费用权重或 LLM 文本消除。实时界面没有“解除海关扣留”按钮；仿真中的相应操作必须命名为 `Inject simulated authoritative release notice`，注明它只改变模拟来源。界面不把维护建议表述为已执行的移箱或已恢复供电。

### 13.5 资源规划、方案比较与恢复

仿真甘特图按资源行展示计划与实际模拟占用，任务条说明时间窗、依赖、等待原因和冲突；未知时长使用区间或明确假设，禁止假装精确。封闭道路、失效资源与受影响任务建立可追踪关系，局部事故只传播到有依赖的任务；恢复时检查所有剩余限制，不把“道路重开”解释为所有柜子恢复可提。

比较页最多推荐三套方案，固定为 `Throughput`、`Balanced waiting`、`Stable recovery`。三者使用相同初始状态、外部事件、种子、模拟时长、资源约束、hold 与安全规则；只允许调整明确列出的软目标。显示目标取舍、完成量、等待分位数、关键任务响应和费用。若使用 Pareto 标识，须说明是“当前生成候选中的非支配方案”，没有证明就不能称全局最优。无可行方案时显示原因，不放宽硬约束制造好结果。FIFO 基线同样执行全部限制，禁止通过让基线处理被扣留柜或忽略设备故障来夸大收益。

### 13.6 三条必须走通的用户旅程

1. **日常异常：** 在 LIVE_T49 或重放中进入多项 hold、日期差异或准备状态不一致的柜子，核对来源并创建协调任务。空重对照与温度异常的完整流程在 SIMULATION 中演示；收到新证据后只解决相关问题，全程保留历史。
2. **局部中断与恢复：** 在独立仿真中关闭某条接入道路，定位受影响资源和任务，查看其他可运行路径及方案对照。部分恢复后推进模拟时钟，观察实际完成事件与积压变化，再重开道路；每次状态变化都能解释。
3. **回溯与交接：** 从时间线定位某次建议，恢复当时的证据快照和规则版本，查看后续修正。刷新浏览器仍回到同一授权会话；分享只读上下文时保留模式、版本与权限，不泄露 API 密钥。

### 13.7 前后端状态与失败处理

统一调用 `/api/v1/...` 版本化接口；具体路径及模型由服务端 OpenAPI 约定，前端不硬编码旧接口。资源标识使用不透明 UUID，货柜编号作为业务字段展示。会话、回放、仿真分支与事件分别建模，缓存键包含上下文和版本，禁止切换会话后短暂显示另一会话的数据。

变更携带 `If-Match` 和幂等键。提交期间禁用重复按钮；超时后的未知结果用相同幂等键查询或重试，不另建事件。版本冲突时读取最新状态，展示差异后由用户重新提交；不得静默覆盖其他人的操作。权限错误、服务断开、校验失败分别提供明确文案；敏感状态不做乐观成功更新。

初次加载、局部刷新、空结果、无权限、陈旧数据、来源离线及缺失字段均有独立状态。断网时可保留明确标记的已加载视图，禁止假装保存成功；恢复连接后先重新同步。空列表要区分“没有匹配项”“没有权限”和“尚未取得数据”。表单错误定位到字段，保留用户输入并提供重试；服务端文本用安全文本组件渲染，不插入不可信 HTML。

### 13.8 验收矩阵与交付完成条件

所有测试使用固定 fixture、受控时钟和可复现种子；不得依赖开发机当前时间或生产 Terminal49 账户。端到端测试连接真实测试后端，网络异常通过受控代理或测试拦截注入。

| 验收用例 | 必须观察到的结果 |
|---|---|
| 模式切换／新建分支 | 标识、时钟、缓存和写入目标一致；仿真不会污染实时会话 |
| 温度风险＋hold 并存 | 高优先级维护任务可见，出场限制持续存在，无一键覆盖 |
| 缺失、陈旧、来源离线 | 显示未知或最后已知状态，不补造温度、重量、预约、位置或许可 |
| 两个客户端同时修改 | 版本冲突可见；旧客户端不能覆盖新结果 |
| 重复事件／提交超时重试 | 只产生一次业务变化、一次任务转换及正确指标 |
| 刷新／深链接／跨会话 | 恢复正确上下文；无授权会话返回明确错误，不降级为共享全局状态 |
| 局部封路／部分恢复 | 只影响依赖该资源的任务；其他 hold 和未知条件不被清除 |
| 指标与同约束比较 | 前端计数与服务端事件一致；完成吞吐不等于计划容量；基线与方案限制相同 |
| 键盘／窄屏／加载失败 | 核心旅程无需鼠标可完成；焦点可返回；错误可恢复且没有伪成功 |

完成标准：独立前端可构建、部署和配置 API 地址；路由刷新有效；类型检查、组件测试及上述端到端检查通过；附无密钥的配置示例、启动说明、数据模式说明、可复现演示脚本和测试报告。发布前记录后端兼容版本并验证健康状态。演示完成仅证明模拟流程可运行；真实运营适用性仍需码头用户验证及实际集成，不能在 UI 或 README 中宣称已接管港口调度。


## 14 约束调度与离散事件仿真详细规范

本节的排程作业 `Operation` 与第 5 节协调待办 `Task` 是不同对象。Task 管理人员接手与证据；Operation 管理资源和时段。第 6 节的证据字段是公共合同，本节 published/observed/applies 三个时间属于仿真世界的补充字段。下文示例场景标识 `east-access-closure` 在成品中统一使用第 15 节的 `battery_truck_access_2024`。

本文是待实现的技术设计。已有 `gate_triage/planner_engine.py` 是未接入、未验证的规则原型，没有 CP-SAT 优化器，也不能证明吞吐量改善。下列参数均为初始实验配置，须经测试确认。系统研究边界是被追踪的一组货柜及其闸口、堆场异常任务，不代表完整码头操作系统或洛杉矶港整体调度。

### 14.1 两个引擎，明确不同的承诺

**LIVE_T49：Terminal49 证据驱动的协调引擎。** 唯一外部业务数据服务为 Terminal49。接收经实际接口结构验证的货柜事件和状态，输出阻塞原因、缺失证据、任务负责人以及可提状态的变化。真实接口没有返回的重量、温度、设备、人员、预约、付款或授权信息，统一保持未知；不得用模拟默认值补齐，再把结果呈现为真实放行许可。此模式只能声明“根据已获取证据，需要协调什么”，不能声明拥有全部码头资源信息或可以直接执行物理调度。

**SIMULATION：资源约束下的滚动排程与实验引擎。** 使用明确标记的合成资源、时长、到达和事故事件，把多项工作排到具体资源和时段，检验哪些协调策略能提高有效出闸完成数、缩短等待并减少饥饿。采用本地 OR-Tools CP-SAT；它是算法库，不是新增外部业务服务。缺少模拟资源定义时，不展示优化吞吐量的结论。

两种模式共享证据解释、约束和任务状态定义，但数据库、会话、事件命名空间及前端标识隔离。真实回放只保留经验证的提供方结构；模拟增量放在独立 `simulation_overlay` 内，不伪装成 Terminal49 返回字段。

### 14.2 状态、证据与任务合同

每条证据记录内部字段 `source_ref、field_path、value、unit、weight_basis、published_at、observed_at、valid_until、provenance`。这些是本项目规范化字段，不声称均由 Terminal49 原生提供。缺少来源时间时保留空值，以接收时间单独展示，不能倒填成官方发布时间。对同一事实比较对象、单位、口径和有效期，不能给整家公司一个“可信度高，因此覆盖所有其他来源”的总开关。

可执行性分为 `allowed / blocked / unknown`，分别对信息核验、原地维护、场内移动和出闸判断。已知海关扣留属于出闸硬约束，断网、恢复道路、结束核验任务都不能清除；它也不能自动推导所有原地维护都被禁止。场内移动必须有对应权限与资源证据。空重冲突首先核对柜号、称重口径、自重及时间；未经确认的车组总重不能直接和箱体重量比较。

协调 Task 可展开成多条并行的资源作业 Operation，例如“核对重量→收到复称结果”“冷藏检查→收到温度结果”“请求相关方确认→收到新状态”。`operation_id` 按工作空间、运行、旅程、工作类型和问题周期稳定生成，并关联独立 `task_id`；Operation 生命周期为 `pending / ready / committed / running / waiting_evidence / completed / cancelled`，Task 使用第 5 节状态，后台 job 使用第 6 节持久任务状态，三者不能混用。问题重新出现时创建新周期，保留旧记录。资源作业结束只是工作完成，证据结果仍可为“问题存在”或“无法确认”。温度恢复不代表货物品质合格；演示若有独立品质复核政策，必须标明是模拟政策，不能称为普遍法定扣留。

### 14.3 场景文件与来源合同

场景文件必须经过 JSON Schema 校验；未知字段拒绝进入核心求解输入。以下是合成场景的精简有效结构示例，非真实港区设备清单：

```json
{
  "schema_version": "simulation-1",
  "scenario_id": "east-access-closure",
  "seed": 17,
  "start_at": "2026-10-17T09:00:00-07:00",
  "horizon_minutes": 240,
  "provenance": {
    "kind": "synthetic",
    "description": "Real-incident-inspired; all resources and timing below are invented",
    "source_refs": []
  },
  "containers_fixture": {
    "path": "fixtures/cohort-100.json",
    "sha256": "REPLACED_WITH_ACTUAL_CONTENT_HASH",
    "mode": "synthetic",
    "overlay_path": "fixtures/operational-overlay.json"
  },
  "planning": {"lookahead_minutes": 60, "replan_minutes": 5, "freeze_minutes": 5},
  "resources": [
    {"id": "east-lane-1", "kind": "gate_lane", "capacity": 1, "gate": "East"},
    {"id": "west-lane-1", "kind": "gate_lane", "capacity": 1, "gate": "West"},
    {"id": "scale-1", "kind": "scale", "capacity": 1},
    {"id": "yard-crew", "kind": "crew", "capacity": 2}
  ],
  "duration_models": {
    "gate_handoff": {"distribution": "triangular", "minutes": [3, 5, 9]},
    "weight_check": {"distribution": "triangular", "minutes": [6, 10, 16]}
  },
  "events": [
    {
      "event_id": "closure-1",
      "type": "resource.availability",
      "resource_ids": ["east-lane-1"],
      "state": "closed",
      "capacity": 0,
      "published_at_min": 30,
      "observed_at_min": 32,
      "applies_at_min": 30,
      "provenance": "synthetic"
    }
  ]
}
```

`sha256` 在构建 fixture 时必须替换为真实内容摘要，示例占位值不通过生产校验。每个 overlay 包含匿名利益相关方分组、模拟到达时刻、资源兼容集合、任务依赖、服务目标和授权证据；不得修改原始货柜记录。每项非提供方事实标记 `synthetic`，每条时间分布注明配置作者、版本、单位与依据。参数暂未校准时直接标为“演示假设”，不用“行业标准”包装。

如使用真实 Terminal49 响应回放，应保存去敏原始响应、接口/模式版本、采集时间及摘要，并针对实际取得的字段校验适配器。模拟 fixture 和真实回放的结构校验分开；字段缺失和未知枚举必须显式降级，不能偷偷转换成可放行。现场 lane、人员及 service time 不得增加到原始 Terminal49 对象里。

### 14.4 时间和可见性，防止提前知道答案

`published_at` 是消息在来源发布的时刻；`observed_at` 是系统实际收到消息的时刻；`applies_at` 是场景世界中状态生效的时刻。排程器在虚拟时间 t 只能读取 `observed_at≤t` 的信息。收到未来生效的已公布关闭通知，可以提前规划；尚未收到的恢复消息、未来故障、未发生的到达和检测结果不能读取。

仿真器可以保存完整世界事件队列，但向策略暴露的快照必须经过独立可见性过滤。物理道路已关闭而通知尚未送达时，世界执行器拒绝实际进入，并生成在当时可见的执行失败/阻塞观测；不能让车“穿过”已经关闭的路。该本地观测属于模拟器，不代表 LIVE_T49 模式已连接现场传感器。

任务未来可能成功，不等于现有前提已经成立。输出分 `committed_safe` 和 `projected_conditional`：前者仅包含当前证据和安全约束允许启动、且已经确认的动作；后者显示明确前提及预计窗口，不计入已完成吞吐量。核验任务可以排程，但其未知结果不能用于承诺之后的出闸。结果实际到达后，才重新生成可执行链。

### 14.5 资源、工序和安全约束

每项工作具有处理时长、可开始窗口、资源需求、允许位置、依赖和是否可中断。闸口交接、复称、场内运输和维护占用各自资源；如果一次作业同时需要车辆及司机，则必须同时预留，不能分别排出互相不重叠的“假计划”。资源台数不再换算成“每条道每天固定 12 柜”作为主要实验；吞吐量由具体作业耗时、到达、依赖和资源瓶颈共同产生。

闸口和设备使用互斥或累计容量约束；人员班次、开放窗口和已公告停用写入资源日历。冷藏插座、等待区及停放位是持续占用资源：入位至实际离位占用，跨越观察窗仍未释放时继续保留，不能在每次重算时凭空清空。换区移动须符合图上已定义的路线、兼容性和授权；默认不允许把 East 的柜子通过修改标签直接交给 West。

已开始作业不随重排改变。新事故影响运行作业时，按场景明确的作业类别执行“安全暂停”“完成当前安全步骤再停”或“取消并保留进度”；三种策略使用同一规则。禁止为了让优化器显得更快，随意中断对照组任务或允许优化组跳过安全检查。所有法律、身份、权限、容量与物理约束均为不可松弛条件，资源不足只能延后，不能支付罚分买通。

### 14.6 CP-SAT 数学模型

时间采用整数分钟，工作时长向上取整，精度及保守性在结果中披露。设当前时刻 t，滚动窗终点 H=t+60；作业集合 J，只包含当前已观测的对象与已知工作。每个工作 j 有选择变量 `x_j∈{0,1}`、开始 `s_j`、结束 `e_j`、计划时长 `d_j`，构成可选区间，存在时满足 `e_j=s_j+d_j`。可替代资源用 `a_jr` 选择，并要求 `Σr a_jr=x_j`；多种资源同时需求不能当作替代资源。

前后依赖 p→j 满足 `x_j≤x_p` 和条件约束 `s_j≥e_p`；已完成前置使用历史实际完成时刻。未观测到的授权结果不建立“必定通过”的依赖捷径，而是令相应出闸变量为零。单台设备使用 NoOverlap；同类多台或人员池使用 Cumulative。容量随时间变化时加入固定停用占用区间，或拆为带可用日历的具体资源；不可只看规划开始时的总容量。

货柜 i 的完成变量 `y_i` 只能在其最终出闸交接作业被选择且 `e_exit(i)≤H` 时为一，单柜最多记一次。`y_i` 表示模型内预计完成；实际成绩只由世界执行器确认。进入核验区、安排电话、提出 reroute、解除一项报警都不等于出闸。已经运行且跨窗结束的工作保留剩余占用，不因为 H 截断而消失。

区间和工序约束采用 [OR-Tools 官方 job shop 文档](https://developers.google.com/optimization/scheduling/job_shop)所述建模能力；本文的目标函数、时间窗和业务边界是本项目设计，并非其官方港口方案。

### 14.7 分层目标、公平性和可解释选择

用逐层求解实现字典序目标，避免随意相加的巨额权重掩盖取舍：

1. 满足不可放宽的安全约束，并最小化明确标记的关键服务政策违约量，例如已确认紧急维护任务的超时；服务目标可有 slack，安全条件没有 slack。关键任务未被选入时也计入未服务惩罚，不能靠忽略任务取得零违约。
2. 在第一层结果约束下，最大化固定规划窗内有效出闸完成数 `Σi y_i`。这是主要运营目标，费用不参与放宽限制。
3. 在前两层结果保持的条件下，最小化合格队列中的最大等待/迟到，再减少利益相关方之间的等待差异，最后降低已公布计划的变更次数与时间偏移。预计费用仅作为同等运营效果下的辅助比较。

等待公平性以“进入当前可执行集合后累计的合格等待时长”为基础，同时报告从到达起的总等待和被阻塞时长。不能把有海关扣留的时间算成排程器可自由服务的等待，也不能从报告中删掉这些困难柜。按模拟货主或卡车公司分组时使用匿名业务分组，展示样本量和合格需求分母；不强行给没有可执行需求的组分配资源。

对计划变更设置五分钟冻结窗，并固定已启动作业。安全事件可以撤销已承诺动作，但必须有显式原因和审计；“保持计划稳定”不能覆盖新出现的安全限制。每次重排输出 `previous_start、new_start、change_reason、binding_constraints`，让调度员知道为什么有一辆车被延后。

只有前一层被证明 OPTIMAL，才可说后续为该层最优解上的严格字典序优化。如果上一层仅 FEASIBLE，则锁定当前最好已知指标继续改进，并标明“保留当前可行结果”，不能宣称全局字典序最优。可另外生成 epsilon 方案，例如允许比当前最好已知完成数少 1 柜，换取更低最大等待；只在本次已找到的可行候选间筛选不被支配的方案，称“候选权衡方案”，不称完整 Pareto 前沿。

### 14.8 滚动执行与异常处理

每五分钟或重大证据/资源变化触发重排；先读取同一事件版本的快照，再建立模型、求解、独立校验，最后原子提交带 `snapshot_revision` 的计划。计算期间版本改变则拒绝提交旧计划并重算。动作启动前再次校验最新前提，防止求解后才收到的扣留被遗漏。

交互求解总预算暂定两秒，包括各目标层；离线实验暂定每次重排十秒。两者是待压测的工程预算，不是性能保证。记录各层状态、目标值、最优界、耗时和求解参数。根据 [CP-SAT 官方状态定义](https://developers.google.com/optimization/cp/cp_solver)，FEASIBLE 只表示找到可行解，OPTIMAL 才表示证明最优；UNKNOWN 不等于不可行。

超时已有可行解则校验后使用；没有可行解或发生求解错误时，回退到同一约束下的可行 FIFO。INFEASIBLE 单独报告冲突资源或固定任务，不放宽安全条件。因为普通任务允许延期，只有可选任务的空计划通常应当可行；若仍不可行，应优先检查已运行资源冲突、强制任务和数据错误。回退也无可行动作时，展示等待及协调事项，不能伪造吞吐量。

### 14.9 离散事件实验与共同随机数

虚拟时钟跳到下一次到达、资源变化、证据到达、作业完成或重排时刻；与真实墙钟和求解耗时分开记录。每次处理顺序固定为“世界资源变化→作业结果与证据到达→到达事件→安全再校验→排程→启动”。同一时刻的并列事件按稳定编号排序，所有策略共用。

比较三种策略：可行 FIFO 按当前可执行任务进入队列时间排序；优先级策略采用公开的紧急度和等待老化规则；CP-SAT 使用上述约束排程。三者都可跳过目前不可执行的柜子，都不能越过扣留，使用同样的任务链、资源、操作政策、观测延迟和启动检查。不得拿“盲目全部堵住”的错误基线作为主要对照。

每个 seed 提前生成世界到达、故障和结果样本，存放于策略不可读的世界层。耗时随机值由 `(seed, container_id, job_kind, episode, attempt, resource_class)` 稳定派生；不能按“这是本策略第几个随机调用”取值，否则重排会给不同策略换一套难度。策略仅知道公开分布或点估计，实际耗时在启动后由世界层执行并在完成时揭示。相同任务、尝试和资源类别采用共同随机数；策略造成的额外返工则显式计数，不能假称两者具有完全相同工作量。

### 14.10 场景、指标与验收矩阵

必备场景包括正常运营、参考真实电池货车事故背景的局部道路关闭、数据连接中断和到达拥堵。真实事件材料只用于说明背景；关闭范围、持续时长、开几条车道等实验参数全部标为合成。道路恢复采用 closed→restricted→open，受影响的是指定资源集合，不直接关闭整个港口。连接中断只改变信息可获得性和新鲜度，既不清除已知 hold，也不等于现场设备停机。拥堵可由到达变密、资源维护或作业时长波动形成，须分别留有可解释参数。

每个场景运行固定 30 个预先公布的 seeds，三策略逐 seed 配对；记录平均值、P90、配对差异及最差情形，失败和回退运行不得删除。主要指标是固定四小时内实际有效出闸数及每小时完成数；同时报告紧急服务迟到、队列面积、资源忙碌/空闲/不可用分钟、改计划次数和各业务组等待。费用仅列辅助估算，必须显示规则与是否计入免费期。

窗口结束仍未完成的货柜属于右删失：单列未完成数和已等待时长下界，报告整个 cohort 的等待累计面积。完成者平均等待单独标明条件，不能冒充全体平均。若超过一成对象尚未完成且无法识别总体 P90，则显示“未确定”或可证明的下界，不丢掉这些对象后报一个漂亮分位数。结论只适用于该组被追踪货柜与合成配置，不外推到全港吞吐量。

| 测试 | 必须成立的结果 |
|---|---|
| 空柜声明、经核实重柜、升温、海关扣留同时存在 | 并行产生对应任务；紧急维护不产生出闸许可 |
| 核验完成但结果未知/仍不一致 | 不自动解除限制；不得预测为肯定通过 |
| Customs 断网后道路恢复 | 已知扣留继续阻塞，无扣留但证据过期为未知 |
| East 关闭、West 正常及部分恢复 | 仅指定资源容量变化；禁止跨区偷换闸口 |
| 两工作争用同设备/人员/持续占用插座 | 任意时刻都不超容量，跨窗占用不丢失 |
| 隐藏未来故障/结果、改变其内容 | 观测前策略输入和输出不受影响 |
| 同 seed 重跑、跨策略同任务 | 世界样本一致；计划和日志可复现或明确记录求解差异 |
| 等时长、同窗口、无依赖、充足可提队列 | 完成数符合资源理论上限，不能编造 CP-SAT 增益 |
| 高费用柜挤压长等待低费用柜 | 费用不越过服务/公平性层，长等待在报告可见 |
| 求解超时、无解、旧快照提交 | 正确区分状态；回退或拒绝提交，硬约束零违规 |
| 大量未完成对象及临近窗口的到达 | 保留 cohort 分母，等待删失清楚显示 |

最终验收须通过独立计划检查器：核对证据版本、每条硬约束、资源占用、依赖、实际完成计数及随机样本归属。优化器能返回对象不是验收标准；必须在等服务时长负对照中承认没有吞吐量增益，并在存在真实资源竞争的合成场景中解释改善来自哪里、牺牲了什么，以及哪些运行没有改善。

### 14.11 开发接口和可计算的验收边界

排程模块入口约定为 `plan(observed_snapshot, prior_plan, policy_config)`，不能接收完整世界事件数组。输出包含模式、输入版本、当前时刻、规划终点、各层求解状态、目标值和界、已承诺动作、条件预测动作、未安排任务及原因、资源时间表、取舍候选和回退原因。每个动作列出工作编号、柜号、资源、预计起止、前提证据编号和操作类别。证据缺失要具体到哪一项，不能统一写“AI 信心不足”。

关键服务目标的形式化实现应包含未服务变量：令 `u_j=1-x_j`；未被选择的关键任务仍产生未服务代价和截至窗末的迟到量。迟到为完成时刻超出服务目标的正部，等待为累计合格等待加本窗新增等待。为避免通过删除对象优化最大等待，公平性统计集合在同一快照上固定；未安排但合格的对象至少累计等待到窗末。前一层目标未证明最优时，各层返回各自的界和状态，不把最终层 OPTIMAL 冒充整个分层问题都最优。

等服务时长负对照固定为：全部 N 个合格柜在零时刻到达，k 条完全相同且连续开放的通道，每次交接耗时 d，无其他资源和依赖，则四小时完成数应为 `min(N, k × floor(240/d))`。三个工作不空转的策略应相同。另设一份人工可穷举的小型多资源 fixture，与所有合法排列得到的最优完成数比较，以检验模型而非只检验返回格式。

随机实验的吞吐量 P90 是跨 30 次运行的分位数；货柜等待 P90 是个体等待分布，两者在接口和图例中分名保存。每次运行记录策略版本、场景摘要、种子、求解器版本、线程数和时间预算。若时间预算导致解不稳定，应保留各次差异，重现世界输入与严格的约束正确性仍是必达条件。

## 15 真实事件参考与场景库

### 15.1 事实与演练的关系

每个历史启发场景保存 `historical_facts`、`source_refs`、`simulation_assumptions` 和 `expected_invariants`。官方确认的事件背景不等于我们拥有历史逐柜数据。场景时长、箱号、资源台数、任务耗时、信息延迟和恢复比例都是模拟输入，界面、导出和演示讲稿须同时说明。

演练以 2026 年统一虚拟起点运行，历史发生日期单独保存；不把压缩的四小时情景称为真实事故时间线。历史资料属于离线文档，运行时唯一外部业务服务仍是 Terminal49。

### 15.2 日常运营基准

场景标识 `normal_operations`。生成 100 个合成货柜，包含准备状态已知、未知、active hold、pending hold、来源日期不一致、未取得预约信息及已完成旅程。运营 overlay 提供司机到达、资源需求和耗时；非运营字段不混入供应方对象。

该场景验证日常异常协调、合格队列中的公平等待、已确认任务与计划稳定性。不得预设优化相对 FIFO 的提升百分比；先用有限资源冲突的小模型验证，再运行完整 cohort。

### 15.3 2024 电池货车事故与通道中断

场景标识 `battery_truck_access_2024`。

**已核实事实**：2024 年 9 月 26 日，装载锂电池的货车在洛杉矶港附近侧翻起火。LAFD 记录 9 月 27 日转移车辆货物，晚间道路清理并重开。港方 9 月 27 日公告确认 Vincent Thomas Bridge 与 Seaside Avenue 开放，并称受影响码头预计周六恢复全面运营；“预计”不能改写为已确认全面恢复。[LAFD 复盘](https://lafd.org/news/lithiumion-batteries-burn-days-after-san-pedro-big-rig-crash)、[洛杉矶港恢复公告](https://portoflosangeles.org/references/2024-news-releases/news_092724_truck_accident)

ONE 的客户通知对其列明码头暂停出口 detention 和进口 demurrage 计时至重新开放。这是特定船公司的通知，不是所有船公司、所有费用均免收，也没有逐柜节省金额。[ONE 通知](https://us.one-line.com/news/us-los-angeles-terminal-truck-incident)

**演练设计**：使用概念码头 East 与 West 两组通道，均非真实码头地图。East 相关道路关闭，West 的兼容任务继续；同一主角柜有明确模拟重量疑点、温度报警和 active hold。资源规划应并行安排允许的核查，保留出闸限制，并显示正常交接继续发生。

| 相对分钟 | 模拟输入 | 可检验行为 |
|---|---|---|
| 0 | 正常资源、已知柜子与任务 | 建立初始计划和来源状态 |
| 30 生效、32 收到 | East 接入道路关闭 | 执行器遵守物理封闭；通知后重排并明确受影响任务 |
| 45 | 主角柜的复核结果到达 | 仅解除已经解决的重量疑点，不解除 hold 或温度核查 |
| 60 | 模拟维护结果与新温度记录 | 核查任务状态更新，不推断货物质量已获批准 |
| 90 | East 部分恢复 | 仅恢复明确开放的资源，保留其他限制 |
| 120 | East 正常开放 | 重排积压，保护长等待任务 |
| 140 | 模拟供应方确认相关 hold 移除 | 重新检查全部报告状态与其他条件，不能由人工确认任务直接放行 |

上述分钟数、通道数量和主角柜记录全部为演练设定。2024 真实公告没有提供这样的逐分钟恢复比例或主角货柜情况。主验收是范围正确、任务并行、已知限制保留、其他业务继续，以及恢复后积压变化。

### 15.4 2017 APM 网络中断与数据恢复

场景标识 `terminal_data_disruption_2017`。

**已核实事实**：Maersk 于 2017 年 6 月 28 日公告确认，6 月 27 日网络攻击导致多处系统及部分业务不可用。美国国会议员 Torres 6 月 29 日的官方声明明确提到洛杉矶港最大码头关闭。APM 6 月 30 日的官方更新描述 Los Angeles 闸口服务仍在扩大恢复；不据此宣称当日已全面恢复。[Maersk 公告](https://investor.maersk.com/news-releases/news-release-details/cyber-attack-update)、[Torres 官方声明](https://torres.house.gov/media-center/press-releases/torres-introduces-port-cybersecurity-legislation-following-cyber-attack)、[APM 阶段恢复更新](https://www.apmterminals.com/en/news/news-releases/2017/cyber-attack-updae-friday)

**演练设计**：在特定模拟码头冻结更新、增加消息延迟、重复与乱序，之后分批恢复。另用独立的运营事件表达模拟闸口中断；数据流中断与现场作业停止不能互相自动推导。不能说 Terminal49 在这次历史事故中发生了故障。

| 相对分钟 | 模拟输入 | 可检验行为 |
|---|---|---|
| 20 | 目标码头来源停止成功更新 | 保留最后已知事实；显示采集失联，创建核实任务 |
| 35 | 模拟现场报告部分闸口不可用 | 改变指定资源，而不是把采集失败直接当全港关闭 |
| 70 | 两条旧通知迟到，一条重复 | 不重复任务、不使旧状态覆盖较新的 hold |
| 100 | 来源分批恢复 | 重读当前状态，按来源与业务时间重建 |
| 130 | 部分资源恢复 | 核实当前证据后安排合法任务 |
| 160 | 数据与资源恢复正常 | 保留缺失历史区间与中断审计，不伪造事件发生时间 |

该场景重点检验可靠性与降级，不能用“少收到事件”判断网络攻击。普通货柜没有移动也会长时间没有运输事件，只有成功采集时间或明确故障报告才能支持对应判断。

### 15.5 2021 长滞箱拥堵

场景标识 `long_dwell_backlog_2021`。

**已核实事实**：洛杉矶港 2021 年 10 月 29 日公告称，当时约 40% 的进口箱在码头滞留至少 9 天，并公布额外滞留费方案。港方 2022 年 12 月 16 日后续公告明确说，该项额外费用从未启动收取。这是运营中的拥堵，不能称为洛杉矶港关闭；后续报道的两港合计改善也不能作为洛杉矶单港或本产品的效果。[2021 港方公告](https://portoflosangeles.org/references/2021-news-releases/news_102931_cargofee)、[费用计划结束公告](https://portoflosangeles.org/references/2022-news-releases/news_121622_dwell_fee)

**演练设计**：在合成 cohort 中，40% 货柜初始卸船停留不少于 9 天，用来表达当时的总体积压形态。这个比例不是历史箱号抽样。模拟到达率一度高于可处理能力，混有尚未解决的 hold、预约信息未知及资源竞争，再降低到达率观察积压恢复。

主验收包括合格长等待任务是否得到服务、未完成对象是否保留在指标分母、等待是否从一方转移到另一方，以及 throughput、等待和服务窗口的取舍。真实历史模式中该额外港方费用累计为零；若做“假如收费”的实验，要独立命名反事实政策并默认关闭。

### 15.6 天气预警对照

场景标识 `weather_warning_no_closure_2023`。港方关于 Hilary 的 2023 年 8 月 21 日更新报告无损坏、运营正常，因此不能把它作为严重停运实证。可用来测试系统收到预警后创建关注任务，但在没有实际关闭证据时不自动关闭通道。[港方 Hilary 更新](https://portoflosangeles.org/references/2023-news-releases/news_081823_hurricane_hilary)

### 15.7 其他必备测试场景

至少增加 `equal_service_control`、`multi_resource_bottleneck`、`stale_and_conflicting_data`、`all_departures_blocked`、`partial_recovery`、`solver_timeout`、`single_resource_failure`。它们是工程测试情景，不伪称对应某次真实事故。

`equal_service_control` 固定零时刻到达、相同服务时长与等价通道，检验不空转策略具有相同理论完成量。`all_departures_blocked` 应报告零实际出闸及可继续的协调任务，不为了好看的指标改变权限。

### 15.8 参考数据包

本规范配套 `docs/reference-pack/` 中的场景 schema、来源列表、合成 Terminal49 结构样例与运营 overlay。它们用于说明字段和生成可执行 fixture 的起点；不是历史逐柜重建。数据包必须通过结构、路径引用、内容摘要与事件时间校验。

参考包的 overlay `jobs[]` 是资源作业 Operation 模板，`jobs[].id` 导入后映射为 `operation_id`；它不是后台 jobs 表，也不是协调 Task 状态。参考配置内 `resource.availability.capacity` 表示列出的资源集合的总可用容量，按列出顺序分配槽位；未来若改成逐资源日历，应保持等价行为并升级 schema。

实现者将 reference-pack 转换或复制到正式 `fixtures/` 和 `scenarios/`，以配置驱动导入。转换过程不得静默忽略不支持的字段。场景 JSON 未连接仿真执行器前，只能称已验证的数据配置，不能称已经跑通的演练。

## 16 指标定义与实验验收

### 16.1 真实模式的观测指标

`tracked_full_out_count` 是指定业务时间窗内，同一旅程去重后的已报告 full-out 数量。显示覆盖货柜数与缺失率，只描述账号跟踪集合。使用事件发生时间和时间精度，迟到修正后可重新计算。

`observed_terminal_dwell` 为有效 full-out 时间减去同旅程卸船时间。未出闸对象单列截至观察时点的停留时长下界，不与完整样本均值混合。date-only 数据不用于分钟级比较，非正时序进入质量问题。

Terminal49 官方说明通常不能提供准确的“首次可提时刻”；因此不能默认用 webhook 接收时间计算准确的可提后等待。卡车外部到达与实际入闸也不在已核实核心合同中，真实模式不显示缺乏依据的 truck turn time。[首次可提时间说明](https://help.terminal49.com/articles/9903967000-why-don-t-i-see-a-timestamp-for-available-for-pickup-in-the-ui-or-api)

内部协调指标包括任务首次认领时间、联系到回复时间、待核实事项数和证据补齐后重新评估延迟。它们来源于本应用日志，不能与货物物理交接混算。

### 16.2 仿真指标

| 名称 | 计算口径 |
|---|---|
| actual_completed_handoffs | 世界执行器确认的最终交接，每旅程每类目标动作最多计一次 |
| modeled_departures_per_hour | 实际模拟完成数除以观察小时，不用计划容量替代 |
| external_queue_minutes | 入闸减去到达外部队列 |
| internal_terminal_minutes | 出闸减去入闸，包含内部等待 |
| truck_turn_minutes | 出闸减去外部到达，仅有完整三时刻时计算 |
| unfinished_backlog | 窗口结束未完成数、等待下界与原因分布 |
| critical_service_lateness | 关键服务任务按明确政策计算超时与未服务 |
| eligible_wait_by_group | 在可执行集合内累计等待，按匿名货主或运输组显示 |
| resource_utilization | busy、idle、unavailable、blocked 时间分别报告 |
| plan_churn | 已公布任务的开始时间或资源变更次数和幅度 |
| invalid_action_attempts | 权限、封闭、资源、依赖违规尝试及被执行器拒绝的原因 |
| modeled_fee_exposure | 明确模拟费率和适用条件后的辅助金额，不称为真实节省 |

执行拒绝需分为“违反当时已知条件”和“执行前刚观察到新的变化”。前者与实际不安全执行必须为零；后者可能因通知延迟出现，单独统计与比较，不能以算法提前知道未来作为通过条件。世界执行器始终阻止实际越过封闭或许可限制。

恢复指标定义为：明确的恢复参考事件之后，滚动 30 分钟实际完成速率达到事先配置目标，并连续两个窗口达到目标的首个时点。目标可取同种子正常情景的指定比例，但比例要在实验开始前写入配置。需求不足、未恢复到目标或观察窗不足时标记 not_reached 或 not_identifiable，不输出虚假的零分钟。

### 16.3 实验设计

默认 30 个固定种子逐一配对比较三策略。保存每次运行，不删除失败、超时回退或负收益。报告均值、运行间分布、配对差异和最差情况；若计算置信区间，方法、样本单位与可重复参数同时保存，不能把相关货柜当独立运行样本。

完整结果包含 arrival/fixture/scenario/policy/solver 的版本或摘要、信息可见规则、运行预算、resource calendars、随机样本索引及逐事件日志。主张只适用于这一合成环境；真实业务收益需要后续受控试点验证。

### 16.4 必过验收

| 编号 | 用例 | 通过条件 |
|---|---|---|
| A01 | 模式与数据来源 | 合成事实无法写入真实模式，所有视图与导出保留模式 |
| A02 | Terminal49 结构与权限 | 有效、空值、未知枚举、无权限、429、失联均有正确状态 |
| A03 | 多重异常 | 一个柜同时有多个问题；解决一个不解除其他限制 |
| A04 | 未知物理状态 | 无温度、独立称重、司机到达时不生成对应确定事实 |
| A05 | 并发与幂等 | 同键重试一次业务效果；旧版本写入不能覆盖 |
| A05b | 提交后响应丢失 | 相同幂等键重试返回原成功结果，不错误地返回版本冲突 |
| A05c | 历史定位重放 | seek 后状态等于从起点重建结果；fixture 不被修改 |
| A06 | 局部关闭 | 只影响关联资源和动作，恢复不清除其他 hold |
| A07 | 资源与依赖 | 独立检查器确认所有提交计划满足容量、日历与前置 |
| A08 | 无未来信息 | 隐藏未来结果改变前，当前策略输入不变 |
| A09 | 负对照 | 同质资源与等时长完成数匹配理论界限，三策略一致 |
| A10 | 公平对照 | 基线同样跳过不可执行工作，信息与资源完全一致 |
| A11 | 求解降级 | 正确区分 FEASIBLE、OPTIMAL、UNKNOWN、INFEASIBLE，超时不伪造计划 |
| A12 | 未完成样本 | backlog、删失和长等待显示完整，不只报成功样本 |
| A13 | 模型故障 | LLM 断开或返回越界内容，结构化功能仍正常 |
| A14 | 持久化恢复 | API/worker 重启后无重复任务，已接受操作可追查 |
| A15 | 前端可用性 | 三条核心旅程、键盘、窄屏、刷新与网络错误通过 |
| A16 | 独立运行 | 新环境按 README 可启动，不依赖当前电脑登录状态或秘密文件 |

以上是产品验收，不代表已经取得真实码头合规认证或现场适用性结论。

## 17 部署 运行与维护

### 17.1 本地与 Docker

完整仓库提供 Docker Compose：web 构建产物由 API 静态托管或同域反向代理，另有 API、worker 和 PostgreSQL。浏览器深链接刷新有效，健康检查区分进程存活和数据库迁移/worker 就绪。

本地无密钥默认打开 SIMULATION。显式指定 LIVE_T49 时才读取密钥；失败不自动切换数据源。离线演示的静态资源、字体与 fixture 都随部署提供，不依赖临场 CDN。数据库初始迁移和演示数据导入可重复执行。

建议的交付命令接口为 `docker compose up --build`；自动化测试、生成类型、构建前端、运行实验和导出报告分别有稳定脚本。命令在英文 README 中给出，并在干净环境实际执行验证，不写仅供展示的命令。

### 17.2 配置项

| 配置 | 默认或行为 |
|---|---|
| APP_MODE | `SIMULATION`；公开演示不自动启用真实数据 |
| DATABASE_URL | 本地 Compose PostgreSQL；演示 SQLite 必须明确单实例 |
| T49_API_KEY | 未设置；仅服务器使用 |
| T49_WEBHOOK_SECRET | 未设置；未配置则真实 webhook 入口不可用 |
| T49_REQUEST_BUDGET | 初始保守限额，按真实账号与响应调整 |
| SESSION_SECRET | 真实模式强制提供；公开演示也不写死到仓库 |
| CORS_ORIGINS | 同域或明确域名列表 |
| POLICY_VERSION | 锁定的规则和服务策略版本 |
| SOLVER_TIME_LIMIT_SECONDS | 交互初始 2 秒，离线 10 秒，经过压测后锁定 |
| SIMULATION_MAX_CONCURRENT_RUNS | 按部署资源限制，初始 1 |
| LLM_PROVIDER / MODEL / KEY | 可选，缺少时 deterministic fallback |
| LOG_LEVEL / RETENTION_DAYS | 结构化日志与数据保留配置 |

不要在 README、fixture、浏览器 bundle 或日志保存真实 API key、webhook secret 和账号数据。

### 17.3 云端

现有 Render 服务可用于兼容旧 API。完整产品需要持久数据库及可恢复 worker；免费临时文件系统不能被描述为可靠持久存储。先完成本地成品和部署配置，再选择已有服务或新资源；本规范不授权购买付费资源。

一次发布记录前端 build、API、schema、policy、scenario 和 solver 版本。数据库迁移采用 expand/contract 或兼容方式，部署前备份并演练回滚。回滚应用不能删除已接受的事件，遇到新 schema 应保持只读而非静默丢字段。

### 17.4 监测

记录来源最近成功采集、webhook 接受与处理延迟、幂等命中、隔离事件、job 失败、求解耗时/状态、陈旧计划拒绝、规则触发和约束检查结果。区分提供方限流、权限错误、本应用异常和模拟中的业务故障。

只显示本实例实际测得的性能。初始工程目标为 100 柜 overview 的本地 P95 响应不超过 500ms、交互求解在配置预算内返回可行结果或明确降级；这些是开发验收目标，测试报告必须说明硬件、并发与数据量，未压测前不得宣传为已达到。

## 18 开发工作包与顺序

| 工作包 | 具体产物 | 依赖 | 完成证据 |
|---|---|---|---|
| W01 数据合同 | Pydantic/OpenAPI、来源枚举、模式隔离、fixture schema | 本规范 | 合同测试，空值与未知枚举测试 |
| W02 持久化 | 表、迁移、revision、幂等、持久 job | W01 | 并发与重启恢复测试 |
| W03 T49 接入 | 凭据预检、读取、验签、补偿同步、能力面板 | W01 W02 | 官方样例合同测试；可选真实账号冒烟 |
| W04 状态与任务 | 独立问题、动作条件、并行待办、证据回流 | W01 W02 | 组合情景与无权限覆盖测试 |
| W05 场景与世界执行器 | 合成 cohort、资源模型、可见性隔离、历史案例配置 | W01 W04 | 时间与事件 schema 测试 |
| W06 优化器 | CP-SAT、多目标候选、独立检查器、回退 | W04 W05 | 小模型穷举对照与负对照 |
| W07 实验引擎 | 三策略、共同随机数、30 种子、完整指标 | W05 W06 | 配对输入一致性与可重现报告 |
| W08 产品前端 | 页面、详情、任务、甘特图、对照、来源与错误状态 | W01，可与 W04 后并行 | 类型检查、组件与 E2E |
| W09 可选解释 | 结构化解释与交班、引用校验、预算和降级 | W04 W06 | 虚构引用、未知事实、故障测试 |
| W10 打包与验收 | Docker、CI、英文 README、演示步骤、结果导出 | 全部核心工作包 | 干净环境启动及 A01 至 A16 |

W01 至 W08 及 W10 是完整交付范围，W09 的云端提供商可以缺省，但解释功能必须有模板版本。开发中可分阶段验收，最终不能把只有列表排序的阶段称为完成本规范。

现有团队接口先保留，新增前端和 v1 API 独立联调，避免同时大改队友代码。合并前使用实际团队前端调用样例检查合同；演示工作空间与全局旧 `/scenario` 不互相影响。

## 19 开发者交付清单与五分钟演示

### 19.1 必须交付的文件

提供源代码、依赖锁、无秘密的环境示例、数据库迁移、OpenAPI、JSON Schema、有效 fixture、场景配置、来源清单、规则政策、测试与实验报告、Docker/Compose/CI、英文 README、数据范围说明及五分钟演示脚本。所有已有贡献记录需准确，IBM Bob 的作用以实际贡献为准，不因文档要求虚构使用记录。

实验报告逐项列出已通过、失败和未执行；真实接入未测试时只写未测试，不能用离线 fixture 的通过代替真实账号验证。算法结果与吞吐提升只有运行后才填入，不预写宣传数字。

### 19.2 演示次序

| 时间 | 展示 | 应说明的事实 |
|---|---|---|
| 0:00 至 0:40 | 正常队列与指标 | 一个模拟码头、跟踪范围、准备状态与紧急任务分开 |
| 0:40 至 1:30 | 主角柜的多重异常与任务 | 来源、限制、并行核验和负责人 |
| 1:30 至 2:30 | 2024 事故启发的局部关闭 | 引用真实背景；资源变化和分钟数为合成；未受影响业务继续 |
| 2:30 至 3:30 | 候选安排与资源时间表 | 取舍对各方的影响，求解状态与当前可执行性 |
| 3:30 至 4:20 | 证据到达、部分恢复、积压变化 | 一个问题解除不消除其他限制；计划随有效信息变化 |
| 4:20 至 5:00 | 同条件实验与真实接入边界 | 有效完成、长尾等待、负对照和覆盖限制 |

辅助展示 2017 数据失灵与 2021 积压，可在问答或场景切换中打开。提前生成并保存一个完整实验报告；现场仍能运行单次推演。若云端或网络不可用，本地模拟照常工作，页面保留模式标识。

### 19.3 开发执行原则

实现者以本规范为产品合同，先核对现有代码和测试，再建立工作包与数据模型。任何删减必须在交付报告中列明；不能自行用随机指标、固定信任分或简单的每日容量乘法替代约束模型和事件实验。

开发期间遇到 Terminal49 字段、权限或真实 SOP 未取得时，维持 unknown 或使用明确隔离的合成模式。工程实现可以在授权范围内自主推进，但真实现场适用性需相应用户与数据验证。最终交付报告回答：哪些功能可操作、如何启动、如何复现结果、验证了什么、真实接入还缺什么。

## 20 来源与更新要求

本次核验以 2026 年 10 月 17 日可读取的官方文档和历史公告为基础。开发时重新确认账号权限、API schema 与事件目录；历史事实保留原日期，不把页面当前模板日期当事件日期。

| 来源 | 用途 |
|---|---|
| [Terminal49 API](https://terminal49.com/docs/api-docs/api-reference/introduction) | 认证、资源与读取边界 |
| [Container 资源](https://terminal49.com/docs/api-docs/api-reference/containers/get-a-container) | 货柜字段与关系 |
| [字段可用性](https://terminal49.com/docs/coverage/fields) | 来源依赖及里程碑 |
| [码头覆盖](https://terminal49.com/docs/coverage/terminals) | 路线映射与直接业务集成区别 |
| [船公司覆盖与解释](https://terminal49.com/docs/coverage/ocean-carriers) | 重量与日期精度等来源差异 |
| [Holds and fees](https://terminal49.com/docs/api-docs/in-depth-guides/holds-and-fees) | 结构化状态与费用语义 |
| [LFD 事件与来源顺序](https://terminal49.com/docs/api-docs/webhooks/use-cases/lfd-alerts) | 保留各来源，提醒政策单独计算 |
| [Webhook 设置](https://terminal49.com/docs/api-docs/in-depth-guides/webhooks) | 验签、幂等与接受通知 |
| [事件目录](https://terminal49.com/docs/api-docs/webhooks/event-catalog) | 实际可订阅事件 |
| [功能权限](https://terminal49.com/docs/api-docs/useful-info/entitlements) | 账号能力探测 |
| [首次可提时间限制](https://help.terminal49.com/articles/9903967000-why-don-t-i-see-a-timestamp-for-available-for-pickup-in-the-ui-or-api) | 观测指标边界 |
| [Terminal49 风险看板](https://help.terminal49.com/articles/1980719496-containers-at-risk) | 成熟产品基线 |
| [洛杉矶港运营指标](https://portoflosangeles.org/business/operations) | 运营环节指标与参与方 |
| [Kaleris N4](https://kaleris.com/solutions/terminal-operating-system/container-terminals/) | 成熟资源调度与堆场能力 |
| [APM TERMPoint](https://developer.apmterminals.com/sites/default/files/2025-01/TAS%20API%20Document%20v20240205_0.pdf) | 多项准备条件与预约语义 |
| [DCSA Track & Trace](https://dcsa.org/standards/track-and-trace) | 互操作事件思路 |
| [OSHA 1918.85](https://www.osha.gov/laws-regs/regulations/standardnumber/1918/1918.85) | 适用装卸作业的重量与空重信息 |
| [IMO 称重指南](https://wwwcdn.imo.org/localresources/en/OurWork/Safety/Documents/MSC.1%20Circ.1475.pdf) | 车载称重与空柜确认，注意适用范围 |
| [FEMA NIMS](https://emilms.fema.gov/_is0700b/groups/330.html) | 职责、资源与信息协作原则 |
| [OR-Tools 作业排程](https://developers.google.com/optimization/scheduling/job_shop) | 区间、资源与依赖建模 |
| [CP-SAT 状态](https://developers.google.com/optimization/cp/cp_solver) | 可行、最优、未知和无解的区别 |
| 第 15 节历史公告 | 事件背景及恢复措辞；不提供仿真参数 |

页面由供应商发布的能力介绍仅支持“供应商已提供或宣称该能力”，不能作为本项目实测效果。公开资料未覆盖的现场流程不得通过引用相邻资料扩大其适用范围。
