# Gate Triage 开发文档包

本包定义一个可以独立运行的全栈码头异常协调与运营仿真产品。主要目标是提高有效完成量、减少等待并在中断后恢复运营，真实外部业务数据仅来自 Terminal49。

**先阅读 [完整技术规范](gate-triage-technical-specification.zh-CN.md)。** 需要阅读排版时打开 [HTML 阅读版](gate-triage-technical-specification.zh-CN.html)。本包提供的是开发合同和数据配置；完整产品尚待按规范实现。

**独立分支更新：** 实时决策与参照 Port Optimizer 的交互补充在 [补充规范](realtime-decision-contract.zh-CN.md)。运行应用请用仓库中的 [README-workbench.md](../README-workbench.md)，并核对 [实际验收记录](workbench-verification.md)。文档压缩包仍是规范与参考数据包，不代替整个源代码仓库。

## 给产品负责人的阅读次序

先看完整规范第 2 节的范围、第 3 节的成熟方案与创新点、第 4 节的数据边界、第 8 节的多方取舍，以及第 15 节的真实事件参考。第 16 节定义如何证明有效，不能用演示中的漂亮数字代替验证。

## 给开发者的实施次序

1. 读取技术规范并检查当前仓库。现有 FastAPI API、Ryan 的 100 个模拟柜和测试需要保留；未接入的 planner 草稿不等于已实现优化。
2. 按 W01 至 W10 工作包实现；先统一数据来源、模式、时间和证据，再实现任务、仿真、CP-SAT、前端与部署。
3. 将 [参考数据包](reference-pack/README.md) 导入正式 fixture 与场景目录，保持真实资料、合成 Terminal49 响应和模拟运营参数的边界。
4. 生成并校验 OpenAPI、JSON Schema 和前端类型，按验收矩阵执行单元、合同、集成和端到端测试。
5. 在相同世界、资源与信息条件下比较可行 FIFO、优先级策略和优化器；报告持平、负结果、回退和未完成对象。
6. 从干净环境验证部署。没有真实密钥时完整模拟仍可运行；真实接入必须显示未配置或实际权限状态。

## 核心约束

- 三种模式为 LIVE_T49、REPLAY_T49、SIMULATION，工作空间、时钟和写入隔离。
- Terminal49 的重量不是独立地磅读数，reefer 类型不是温度，预约时间不是创建预约的权限。
- 并行任务、紧急程度和动作许可分别建模。人工任务结束不能解除外部 hold。
- 用资源、耗时、依赖与窗口建立 CP-SAT 模型，用离散事件仿真验证吞吐量，不能用固定日容量代替。
- 候选计划在相同安全与关键服务底线下比较吞吐、等待公平性和恢复稳定性。
- 大模型负责解释、问题拆解和交班草稿，不能补造现场事实或更改许可。
- 真实事故是场景背景，演练箱号、时长、资源和恢复比例均为明确合成设定。

## 案例范围

2024 年锂电池货车侧翻起火对应局部通道中断；2017 年 APM 网络中断对应来源失联和分阶段恢复；2021 年长滞箱拥堵对应积压与多方服务压力。Hilary 预警但运营正常的案例用于防止无依据自动关闭。每例的官方链接、事实范围与模拟假设在完整规范第 15 节和来源清单中。

## 完成交付

最终交付包括前后端源代码、数据库迁移、依赖锁、无密钥配置示例、接口合同、场景与 fixture、测试和实验报告、Docker 与 CI、英文 README 及五分钟演示步骤。README 需区分已实现、已验证及真实接入未验证的部分。

本包中的 HTML 是技术文档阅读器，不是已经完成的 Gate Triage 产品界面。不要把文档渲染器、结构校验通过或规范中的目标性能写成产品运行结果。

## 校验文档与参考数据

使用 Python 3.12，在解压后的根目录运行：

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r docs/spec-tools-requirements.txt
python docs/reference-pack/validate_reference_pack.py
python scripts/render_technical_spec.py
```

包中保留 `data/containers.json`，供原始数据映射与摘要校验。参考配置的构建脚本只写参考包目录，不启动产品，也不发网络请求。完整应用的依赖和部署由开发者按技术规范交付。
