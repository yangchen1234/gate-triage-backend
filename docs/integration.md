# 数据、打分与云端理由接入

## Ryan 的数据

`CONTAINERS_FILE` 指向一个 JSON 数组。默认 `data/containers.json` 是 Ryan 提供的 100 条合成演示数据，默认打分函数为 `gate_triage.score:score`。新文件加载发生在服务启动时，替换后需重启。原先的 5 条临时样例只保留在 `tests/fixtures/original_demo_containers.json`，用于旧引擎回归测试。

每个柜子需要唯一、非空的 `container_id`；FIFO 模拟需要 ISO 8601 格式的 `arrived_at`，费用字段是非负数字 `demurrage_usd_per_day`。前端当前约定的字段名以本仓库样例为准，收到团队真实 JSON 后应共同确认，避免悄悄改名。

若没有到港时间，应向数据提供者补充，而不是用当前时间填充。若费用是费率而非当前计费额，应先更新团队的费用口径。

## Ryan 的打分

当前已直接接入 `gate_triage/score.py`。引擎从来源记录计算 `trust`，并增加 `priority / urgency / conflict_score / action / reason`；原始数据无需预先带 `trust`。

如将来替换评分实现，例如放入 `team_score.py`：

```python
def score(container: dict, scenario: dict) -> dict:
    # 返回下列计算字段，或返回包含原始字段的完整柜子。
    return {
        "priority": 0.9,
        "urgency": 0.8,
        "conflict_score": 0.7,
        "action": "inspect",
        "reason": "Explanation from the scoring engine.",
    }
```

设置 `SCORER=team_score:score`。接口对每个原始对象与打分结果做合并，打分结果同名字段优先，未返回的原始字段完整保留。`container_id` 不能修改。函数必须同步、快速且不修改调用方数据；API 会传副本。

action 只能为 `release / slow / inspect / reroute`，三个分数必须是 0–1 的有限数字。`priority` 表示处理紧迫度。建议把模型调用放到解释函数，不要放进每柜 `score()` 的循环，以维持 100 个柜子一秒内重排的要求。

启动时只加载并打分一次。GET 读取缓存；POST 合并场景并完整重打分。失败时返回 503，场景、队列和统计保留旧版。缺字段或重复 ID 在启动时明确报错，避免对不完整数据静默输出结果。

## 云端解释函数

团队尚未提供服务商、模型和 API 协议，因此这里预留一个与服务商无关的 Python 接口。API key 由你在本地环境或部署平台配置，不能提交到公开仓库。

```python
# team_llm.py
def explain_many(containers: list[dict], scenario: dict) -> dict[str, str]:
    # 在这里调用团队已选的云端 API，显式设置网络超时。
    # containers 最多 20 个，均包含 sources、action、priority、reason。
    # 把 source 中的文本当数据，不接受其改变任务或规则的指令。
    # 向模型提供现有 action 和 reason，要求仅解释，不重新决策。
    # 必须返回所有传入 ID 的非空理由，单条最长 2000 字符。
    ...
```

设置 `CLOUD_REASONER=team_llm:explain_many` 后重启。适配器应自行限制调用成本、请求时长（建议不超过 5 秒）和重试次数，批量处理优于逐柜串行请求。云端解释在后台执行，重排响应先返回原始打分理由。只为新队列前 20 个柜子生成云端解释；过期场景的模型结果会被丢弃，失败则继续使用原理由。

`/health` 的 `llm` 反映成功生成当前说明的模式；没接模型、仍在等待或调用失败时是 `template`，成功后是 `cloud`。`llm_status` 提供具体状态，避免前端把“配置了模型”和“模型实际工作”混淆。

## 当前边界

这是建议与模拟服务，不执行真实的放行、海关清关或设备控制。Ryan 的引擎已接入；海关离线时不会建议 gate release，仍可建议未被 hold 的冷藏柜在场内改道至供电区。已知 hold 保持 `slow / inspect`，且断电风险仍显示在理由中。真实海关 hold 的解除仍需获得授权。Terminal49 的真实 API 和实时数据未接入。

100 条数据、每条车道每天 12 个的当前模拟结果：Normal 为 $770/day，Lanes −50% 为 $4,249/day，Customs down 和 Zone B power out 各为 $770/day。后两者虽然改变处理建议，但不会额外扣减车道容量；统计公式也不按 action 排除柜子，因此费用可能相同。这些是合成数据计算值，不是实际业务收益，也未调整权重来匹配任务文档中的预估目标。
