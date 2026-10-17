# 在 Render 保存 Claude 密钥

打开现有 `gate-triage-backend` 服务的 **Environment** 页面，配置下面三个变量。真实值直接填在 Render，不要发进聊天或提交到 GitHub。

| 变量 | 填写内容 |
|---|---|
| `ANTHROPIC_API_KEY` | 你的 Anthropic API Key |
| `ANTHROPIC_MODEL` | 账号可用的准确模型 ID；表单预填 `claude-sonnet-4-6`，可按账号实际权限修改 |
| `CONSOLE_TEAM_ACCESS_CODE` | 你自己设置的私有团队访问码，至少 16 个字符，不含空格 |

填好后点击 **Save, rebuild, and deploy**，等待部署成功。环境变量会在后续部署中保留；代码和前端构建不包含这些值。

只配置 API Key 不会开放共享调用：密钥、模型和团队码三项都必须有效。团队码只交给允许使用团队模型预算的组员，不要公开发布。

网页使用步骤：

1. 打开线上 Gate Triage，点击 **Connect Claude**。
2. 输入团队访问码，启用当前会话的团队 Claude 连接。网页不需要再次输入 API Key。
3. 选择港口与场景，进入 **Action assistant**，勾选 **Use Claude**，点击 **Generate action plan**。
4. 查看实际调用模式、结果、草稿和失败回退，再记录人工决定。不会自动发送消息或放行。

每次会话授权 15 分钟。断开只撤销当前会话，不删除 Render 上的密钥。部署重启会清除临时会话，但 Render 的配置保留；重新开始会话并输入团队码即可。

首次真实调用仍取决于密钥、账号余额和模型权限。Anthropic Console 的项目费用上限应单独设置；应用的调用次数和并发限制不是精确的美元预算。

环境连接不可用时，先检查三项是否完整，并确认保存后已经部署成功。不要用 `/health` 的旧版解释器字段判断这个连接；应查看网页连接状态和实际生成结果。
