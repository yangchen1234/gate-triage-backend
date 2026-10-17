# Gate Triage Backend

Ports & Logistics hackathon 后端。当船司、地磅、海关和冷藏数据冲突时，给出处理建议并重排队列。

线上接口文档：<https://gate-triage-backend.onrender.com/docs>。Base URL：`https://gate-triage-backend.onrender.com`。前端 JavaScript、curl 和场景按钮示例见 [docs/api-usage.md](docs/api-usage.md)。

## 本地启动

需要 Python 3.12：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
```

交互接口文档：<http://localhost:8000/docs>。测试：`python -m pytest -q`。

服务启动后，也可以运行 IBM Bob 编写的真实 HTTP 验证脚本：

```bash
python scripts/smoke_api.py http://127.0.0.1:8000
```

将地址替换为部署后的 URL，即可检查接口、四种场景和费用公式。脚本会临时改变共享场景，并在结束时恢复原场景；恢复失败也会报错退出。

环境变量示例见 `.env.example`。本项目不会自动读取 `.env`；可以在部署平台设置变量，或在本地 shell 中导出后启动。真实 API key 只放本地环境或部署平台的 Secret 中。

## 前端接入

| 方法 | 路径 | 返回 |
|---|---|---|
| GET | `/containers` | 按 `priority` 降序排列的直接数组 |
| GET | `/containers/{container_id}` | 单柜完整对象；不存在时 404 |
| POST | `/scenario` | 修改场景后重排的直接数组 |
| GET | `/stats` | 四种 action 数量、baseline / optimized / savings 和当前场景 |
| GET | `/health` | 服务状态、实际解释模式、数据量和重打分耗时 |

柜子保留前端要求的 `container_id`、`cargo_type`、`consignee_type`、`sources`（含各来源 `trust`）、`demurrage_usd_per_day`、`free_days_left`、`zone`，并增加 FIFO 统计需要的 `arrived_at`。打分字段为 `priority`、`urgency`、`conflict_score`、`action`、`reason`。三个分数在 0–1 之间，非冷藏柜的 `sources.reefer` 为 `null`。

默认场景：

```json
{"lanes_open":8,"customs_online":true,"power_zone_b":true}
```

`POST /scenario` 合并当前状态。例如只传 `{"lanes_open":4}` 会保留海关和电力设置。Normal 按钮应发送完整默认场景以重置其他开关。`lanes_open` 接受 0–8 的整数，其余两项必须为 JSON 布尔值。未知字段、显式 `null` 或非法类型返回 422。

```bash
curl http://localhost:8000/containers
curl -X POST http://localhost:8000/scenario \
  -H 'Content-Type: application/json' \
  -d '{"lanes_open":4,"power_zone_b":false}'
curl http://localhost:8000/stats
curl http://localhost:8000/health
```

重排先返回规则/打分引擎理由；如果接入云端解释函数，后台只为前 20 个柜子更新 `reason`，前端随后刷新 `/containers` 即可获取。云端结果只更新说明文字，不能修改 action 或排名。`rule_reason` 保留原始打分理由。

**目前未配置云端 API，`/health` 如实返回 `llm: "template"`。前端需要兼容该值，以及模型超时后的模板回退。** 成功获得云端解释后返回 `llm: "cloud"`。`llm_status` 为 `disabled` / `pending` / `ready` / `fallback`；`llm_configured` 表示是否加载了解释函数。当前没有 Ollama 适配器。

## 费用模拟的口径

- 每日处理容量 = `lanes_open × CONTAINERS_PER_LANE_PER_DAY`，默认每条车道 12 个。
- baseline 按 `arrived_at` 从早到晚处理，累加当天未处理柜子的 `demurrage_usd_per_day`。
- optimized 按 `priority` 从高到低处理，累加剩余柜子的同一费用。
- savings = baseline − optimized，允许为零或负数；不预设演示收益。
- 这是文档指定的排序经济模拟：四类 action 都参与容量计算，不能把这里的“处理”当成海关放行许可。真实作业约束需要与 Ryan 的引擎一起扩展。
- 费用字段按当前每日计费额直接累加。`free_days_left` 保留给打分和界面，不额外扣减费用。日期相同时保持原始 JSON 顺序；无时区日期按 UTC 解析。

仓库只有 5 条虚构样例。默认 96 个名额或 4 车道的 48 个名额都足以处理这 5 条，因此三项费用均为 **$0**；收到 Ryan 的完整数据后再验证收益规模。场景变化仍会改变排名和建议。

## 替换 Ryan 的数据与打分

详见 [docs/integration.md](docs/integration.md)。将真实 JSON 放到指定位置，设置 `CONTAINERS_FILE` 和 `SCORER=模块名:score`。原始数据字段会保留，不需要把 JSON 改造成另一套字段名。

## 部署

线上服务已部署到 Render 免费实例：`https://gate-triage-backend.onrender.com`，实际 HTTP 接口、四种场景、费用公式、浏览器 CORS 和场景恢复验证通过。当前使用公开仓库 URL 部署；代码更新后，在 Render 的 Manual Deploy 菜单中部署最新提交。

仓库包含 `Dockerfile` 和 `render.yaml`。Render Blueprint 显式指定免费套餐，容器监听 `0.0.0.0:$PORT`，健康检查使用 `/health`。Railway 也可在 Dashboard 中连接仓库并使用 Dockerfile 构建，设置健康检查 `/health`、副本数 1 并生成域名。

Render 免费服务闲置后会休眠，演示前先访问 `/health` 唤醒。[免费服务说明](https://render.com/docs/free)。Railway 的旧 `railway.json` 配置格式已弃用，这里使用 Dashboard 部署流程。[Railway 配置说明](https://docs.railway.com/config-as-code/reference)。

队列和场景存于进程内存，**只运行 1 个 worker、1 个实例**。所有使用者共享当前场景，重启/重新部署恢复默认值。需要多个独立演示会话或多实例时，应增加会话标识与共享数据库。

CORS 默认允许所有来源，凭据关闭；部署时可以通过逗号分隔的 `CORS_ORIGINS` 限制为前端域名。公开演示中的场景接口没有鉴权，访问者可以改变共享场景。

## 分享给组员

公开仓库链接可直接发给组员，他们可以查看并 clone。共同推送代码时，在 GitHub 仓库 **Settings → Collaborators → Add people** 邀请其 GitHub 用户名，组员接受后即可推送。

仓库地址：<https://github.com/yangchen1234/gate-triage-backend>

```bash
git clone https://github.com/yangchen1234/gate-triage-backend.git
cd gate-triage-backend
```

建议各自使用分支，通过 Pull Request 合并，避免同时修改 `main`。前端可以独立部署，只需要配置后端 base URL。

## AI 开发工具记录

Codex 协助实现 API、临时打分、统计、部署配置和测试。IBM Bob 通过 IDE 实际编写 `scripts/smoke_api.py`，用于部署后的接口和场景验证；随后由 Codex 审查并修复异步说明比较、恢复失败处理等问题。95 项测试和本地真实 HTTP 验证通过。任务、贡献与验证记录见 [docs/ibm-bob.md](docs/ibm-bob.md)。
