# IBM Bob 实际使用记录

日期：2026-10-16（America/Los_Angeles）。

方式：IBM Bob 桌面 IDE 的 Agent 模式，在 Gate Triage 项目目录中执行开发任务。Bob 先读取 API、服务、统计、配置、样例与测试，然后创建脚本。

## 实际任务

给 Bob 的任务是：仅创建 `scripts/smoke_api.py`，用 Python 标准库验证一个给定 base URL 的部署；检查 `/health`、`/containers`、单柜详情与 `/stats`，执行 Normal、Lanes −50%、Customs down、Zone B power out 四种场景，验证排序、action 计数和 savings 公式，并在 finally 中恢复开始时的场景。HTTP 超时设为 5 秒，保留正常 TLS 校验，不安装依赖、不部署或发布、不修改应用代码。

## Bob 的产出与后续审查

Bob 实际生成了 `scripts/smoke_api.py`。该脚本是 Bob 的代码贡献，主 API、打分引擎、费用统计和部署配置由 Codex 协助实现。

Codex 审查后修复了以下问题，并补充 `tests/test_smoke_api.py`：

- 比较队列/详情时忽略可能在后台变化的解释文字字段，避免云端理由更新造成误报。
- 恢复场景失败时返回失败，同时保留首次检查错误。
- 补充队列字段、优先级、ID 路径编码和 URL 校验，避免打印原始网络异常。

## 验证结果

- `python -m pytest -q`：95 项通过。
- `python scripts/smoke_api.py http://127.0.0.1:8000`：真实本地 HTTP 验证通过；四种场景全部通过，开始时的默认场景成功恢复。
- 当前只有 5 条虚构样例，测试输出的 savings 为 0，符合容量公式。
- 尚未对真实线上部署或团队云端 LLM 进行验证。

## Devpost 可用的贡献说明

We used IBM Bob's IDE agent to implement our deployment smoke-test CLI. It exercises the container queue, source-detail, scenario, health and savings endpoints over HTTP, then restores the original scenario. Codex assisted with the backend implementation and subsequent review, corrections and regression tests. We validated the script against our local running service.
