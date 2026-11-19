# AI 使用记录

## 使用原则

- AI 用于代码生成、配置、脚本、故障排查、测试和文档辅助。
- AI 不替代队员对系统设计、实现和验收结论的理解。
- 所有生成内容须人工审查并运行验证。
- 不在提示词和记录中填写账号、密码、AccessKey、SSH 私钥或模型 API Key。

## 记录

### 2026-11-18

- 工具：Codex Desktop。
- 用途：读取赛题和开发规格，生成 W00 项目基线、未决问题清单与环境检查说明。
- 修改文件：`docs/project_baseline.md`、`docs/open_questions.md`、本文件、环境脚本。
- 人工修改：待团队成员确认远程 GPU 地址、CPU ECS 决策和比赛规则。
- 验证方式：检查文档字段、基线版本和未决问题责任人。

### 2026-11-18 W01A

- 工具：Codex Desktop。
- 用途：检查本地 GPU、WSL2、Docker、Python 和磁盘状态；生成环境检查与并发探测脚本。
- 生成文件：`scripts/env/*`、`config/model.local.yaml`、`docs/environment/local_environment.md`。
- 约束：未安装真实模型，未伪造模型调用结果；未操作云账号。
- 验证方式：以实际命令输出为准，阻塞项写入环境文档。

### 2026-11-18 W01A 环境补齐

- 工具：Codex Desktop。
- 用途：安装 Python 3.10.11、创建 `.venv`、验证 pip、检查 Cerebrum 版本来源。
- 结果：Python 环境通过；后续确认 Cerebrum 使用官方替代版本 0.0.3。
- 人工修改：待账户持有人安装 WSL2/Docker 并提供比赛专用 Cerebrum 和模型服务地址。

### 2026-11-19 Ollama 本地替身

- 工具：Codex Desktop。
- 用途：通过国内代理下载官方 Ollama 发布包并校验 SHA-256；从 ModelScope 获取 Qwen2 7B Q4_K_M GGUF。
- 模型：`qwen2:7b-instruct`。
- 验证：普通对话、JSON 输出、OpenAI 兼容接口和四路并发均通过。
- 结果：四请求串行约 5.303 秒，并发约 1.706 秒，实测提速约 67.8%。
- 约束：本地 Ollama 只用于逻辑调试，不替代远程 vLLM 的正式验收。

### 2026-11-19 AIOS Kernel 与 Docker

- 工具：Codex Desktop。
- 用途：安装锁定提交的 AIOS，补齐运行依赖，生成内核配置，安装 WSL Docker Engine。
- AIOS：`292d98f7...`，`/status` 与 `/core/status` 通过，`/query` 返回 `AIOS_OK`。
- Docker：29.1.3，systemd active，国内 registry mirror 可用，`hello-world` 通过。
- 生成文件：AIOS 启动/停止脚本、Docker 安装/检查脚本、内核本地配置。

### 2026-11-19 版本确认

- Cerebrum 0.4.1 未在官方渠道发布。
- 经团队确认，项目替代版本固定为 `aios-agent-sdk 0.0.3`。
- 所有后续依赖检查以 0.0.3 为预期版本。

