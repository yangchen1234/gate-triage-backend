# 前端调用说明

后端 Base URL：`https://gate-triage-backend.onrender.com`

- 接口文档与在线试用：<https://gate-triage-backend.onrender.com/docs>
- 健康检查：<https://gate-triage-backend.onrender.com/health>
- 当前柜子队列：<https://gate-triage-backend.onrender.com/containers>

当前演示接口无需 API key，允许前端跨域访问。团队云端模型的 key 将来放在后端环境变量中，不放前端代码。

## 接口

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/containers` | 直接返回柜子数组，按 priority 降序 |
| GET | `/containers/{container_id}` | 返回单个柜子及 sources、trust、reason |
| POST | `/scenario` | 合并场景参数、重新打分，直接返回新队列数组 |
| GET | `/stats` | 四种 action 数量、两种排队费用、省钱金额和当前场景 |
| GET | `/health` | 服务状态和实际解释模式 |

## JavaScript / React

```js
const API_BASE_URL = "https://gate-triage-backend.onrender.com";

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, options);
  if (!response.ok) throw new Error(`API request failed: ${response.status}`);
  return response.json();
}

// 页面初次加载。
const [queue, stats, health] = await Promise.all([
  api("/containers"),
  api("/stats"),
  api("/health"),
]);

// 点开某个柜子；使用实际返回的 container_id。
const detail = await api(`/containers/${encodeURIComponent(queue[0].container_id)}`);

// 每次修改场景后，同时刷新队列和统计数字。
async function changeScenario(patch) {
  const queue = await api("/scenario", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  const stats = await api("/stats");
  return { queue, stats };
}

const NORMAL = { lanes_open: 8, customs_online: true, power_zone_b: true };
const PRESETS = {
  normal: NORMAL,
  lanesHalf: { ...NORMAL, lanes_open: 4 },
  customsDown: { ...NORMAL, customs_online: false },
  powerOut: { ...NORMAL, power_zone_b: false },
};

const updated = await changeScenario(PRESETS.lanesHalf);
// React 中把 updated.queue 和 updated.stats 分别更新到对应 state。
```

上面的四个按钮是互斥预设，因此发送完整三项参数。若界面采用可叠加的开关，可以只传变动项，例如 `{ "lanes_open": 4 }`；其他当前参数会保留。Normal 按钮应发送完整默认值。

## curl

```bash
curl https://gate-triage-backend.onrender.com/health
curl https://gate-triage-backend.onrender.com/containers
curl https://gate-triage-backend.onrender.com/containers/MSCU1234567
curl -X POST https://gate-triage-backend.onrender.com/scenario \
  -H 'Content-Type: application/json' \
  -d '{"lanes_open":4}'
curl https://gate-triage-backend.onrender.com/stats
```

恢复默认场景：

```bash
curl -X POST https://gate-triage-backend.onrender.com/scenario \
  -H 'Content-Type: application/json' \
  -d '{"lanes_open":8,"customs_online":true,"power_zone_b":true}'
```

## 当前演示状态

- 只有 5 条虚构样例；车道为 8 或 4 时容量足够，因此三项费用均为 0。完整数据与正式打分等待 Ryan 接入。
- 费用字段为 `baseline_demurrage_usd_per_day`、`optimized_demurrage_usd_per_day`、`savings_usd_per_day`。
- 云端 LLM 尚未配置；`/health` 的 `llm` 为 `template`，理由来自临时规则。前端应兼容这个值。
- 场景由所有访问者共享，服务重启后恢复默认值。
- Render 免费实例闲置后会休眠；演示前先访问 `/health`，等待唤醒。
- 当前使用公开仓库 URL 部署。代码更新后，在 Render 服务的 Manual Deploy 菜单中部署最新提交；不要仅凭 GitHub 提交成功判断线上已经更新。
- 参数非法返回 422，柜子不存在返回 404，重新打分失败返回 503 并保留上一版场景与结果。

## 上线后验证

```bash
python scripts/smoke_api.py https://gate-triage-backend.onrender.com
```

该脚本会试验四种场景，并在结束时恢复最初场景。它会暂时改变共享状态，应在前端录制或正式演示前运行。
