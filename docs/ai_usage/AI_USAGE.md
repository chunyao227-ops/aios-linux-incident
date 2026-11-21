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

### 2026-11-19 W02

- 工具：Codex Desktop。
- 用途：按更新后的 W02 工单建立唯一 Python 包根目录、六个子包、严格 YAML 配置加载、安全密钥引用、日志/异常/时间戳/ID 工具和测试入口。
- 生成文件：`pyproject.toml`、`tasks.ps1`、`src/aios_incident/`、`tests/`、`config/app.example.yaml`、`config/model.example.yaml`。
- 边界：未实现 W03 数据契约、W04 适配器、Agent 业务逻辑或 W14 API。
- 人工审查要求：确认本地与远程配置字段、密钥环境变量名称、比赛提交格式。
- 验证方式：pytest、Ruff、配置检查命令与 Git 提交记录；不得仅凭 AI 输出视为验收完成。

### 2026-11-19 W03

- 工具：Codex Desktop。
- 用途：按冻结规格实现跨模块数据契约、固定任务 DAG、任务与工作流状态机、JSON Schema 校验及序列化。
- 生成文件：`src/aios_incident/models.py`、`state.py`、`validation.py`、`tests/unit/test_models.py`、`tests/unit/test_state_machine.py`。
- 依赖调整：增加 Pydantic 2.x 和 jsonschema，用于强类型契约与 Draft 2020-12 Schema 校验。
- 边界：未实现 AIOS/LLM 调用、调度执行、黑板、Trace 存储、Agent 业务逻辑或 API。
- 人工审查重点：字段命名、状态终态、DAG 重试依赖和错误信息。
- 验证方式：统一静态检查与格式检查、70 项测试、编译检查、依赖检查和凭据扫描。

### 2026-11-21 W04

- 工具：Codex Desktop。
- 用途：实现经 AIOS `/query` 的文本和 JSON 模型调用、有限重试、错误归一化、token 使用记录及任务级 Schema 校验。
- 生成文件：`src/aios_incident/adapters/aios_client.py`、`llm_adapter.py`、`tests/unit/test_llm_adapter.py`、`tests/integration/test_aios_smoke.py`。
- 接口依据：直接核对锁定 AIOS 源码 `/query` 路由和 Cerebrum `LLMQuery`/`LLMResponse` 结构，不猜测请求字段。
- 边界：未实现 Agent 调度、Blackboard、Trace 存储、工具网关或故障 API。
- token 说明：优先采用上报 usage；本地 AIOS 未上报时明确标记为估算，不作为精确 tokenizer 结果。
- 验证方式：19 项模拟响应单元测试、真实本地 AIOS 文本与 JSON 冒烟、90 项全量测试、Ruff、编译、依赖和凭据检查。

### 2026-11-21 W05

- 工具：Codex Desktop。
- 用途：实现故障 Incident API、唯一 ID、固定 DAG/状态/结果/事件/取消查询、隔离 Blackboard 和追加式 JSONL Trace。
- 生成文件：`src/aios_incident/api.py`、`orchestrator/blackboard.py`、`orchestrator/trace.py`、对应单元和 API 集成测试。
- 依赖处理：固定 FastAPI、Uvicorn、httpx 和 AnyIO 兼容范围，消除测试客户端弃用警告。
- 边界：未实现 Agent 调度、工具网关、真实修复、独立验证或 UI。
- 人工审查重点：API 字段、错误响应结构、产物完成后不可变、Trace 追加语义。
- 验证方式：24 项 W05 测试、114 项全量警告即错误测试、真实 AIOS 回归、编译、依赖和凭据检查。

### 2026-11-21 W06

- 工具：Codex Desktop。
- 用途：实现 Agent 工具权限表、统一 ToolRequest/ToolResult、路径与输出限制、四类只读工具、禁用修复占位和全量调用 Trace。
- 生成文件：`src/aios_incident/tools/base.py`、`gateway.py`、`tests/unit/test_tool_gateway.py`、`tests/integration/test_tool_isolation.py`。
- 安全边界：未引入 subprocess、任意 Shell、sudo、删除、格式化或权限提升操作。
- 人工审查重点：Agent 权限矩阵、Incident 读取范围、sandbox 路径映射、超时与输出限制、Trace 失败记录。
- 验证方式：13 项 W06 测试、127 项全量警告即错误测试、执行原语扫描、真实 AIOS 回归、编译和依赖检查。

### 2026-11-21 W07

- 工具：Codex Desktop。
- 用途：实现 Coordinator、Log、Repair、Verifier 四个最小 Agent 以及日志证据、模型诊断、模拟修复、结构化验证和最终报告闭环。
- 生成文件：`agents/coordinator_agent.py`、`log_agent.py`、`repair_agent.py`、`verifier_agent.py`、`orchestrator/minimal_flow.py`、`tests/e2e/test_minimal_flow.py`、`docs/demo/minimal_flow.md`。
- 安全边界：模拟修复只修改内存状态，不执行真实宿主写入或 Shell。
- 人工审查重点：Agent 职责、修复回滚、验证判定、失败分支和最终报告字段。
- 验证方式：成功与失败 E2E、真实本地 AIOS 闭环、130 项全量警告即错误测试、编译、依赖和执行原语扫描。

### 2026-11-21 W08

- 工具：Codex Desktop。
- 用途：实现固定 Agent 能力矩阵、DAG 校验、最低负载匹配、四路线程并发、N5 门控、有限重试和失败终止。
- 生成文件：`orchestrator/planner.py`、`orchestrator/scheduler.py`、`agents/metrics_agent.py`、`config_agent.py`、`dependency_agent.py`、`tests/integration/test_parallel_dispatch.py`。
- 并发证据：四路使用同一 dispatch batch ID，线程屏障确保真实重叠。
- 人工审查重点：READY 扩散、能力匹配、失败收尾、重试计数和严格时间顺序。
- 验证方式：5 项 W08 并发集成测试、135 项全量警告即错误测试、真实 AIOS 回归、编译、依赖和安全扫描。

### 2026-11-21 W09

- 工具：Codex Desktop。
- 用途：实现 Agent 消息总线、correlation/reply 协议、三对固定双向交互、消息图和 Blackboard/Trace 记录。
- 生成文件：`orchestrator/interaction_bus.py`、扩展的 `coordinator_agent.py`、`tests/integration/test_interaction_matrix.py`。
- 数据来源：交互内容来自 Evidence、RepairResult 和 VerificationResult，不使用预置对话伪造指标。
- 人工审查重点：固定三对关系、双向边计数、查询响应、超时、离线失败和消息入黑板。
- 验证方式：8 项 W09 交互测试、143 项全量警告即错误测试、真实 AIOS 回归、编译、依赖和安全扫描。

### 2026-11-21 W10

- 工具：Codex Desktop。
- 用途：实现四类 Evidence 校验、事实去重、冲突检测、证据链、根因候选、排除假设和结构化条件追问。
- 生成文件：`orchestrator/diagnosis.py`、`tests/unit/test_diagnosis_fusion.py`、`tests/integration/test_evidence_chain.py`。
- 数据完整性：根因和冲突只引用输入中真实存在的 evidence_id，缺失证据失败关闭。
- 人工审查重点：融合规则、冲突判定、证据链关联和修复阻断条件。
- 验证方式：9 项 W10 测试、152 项全量警告即错误测试、W08/W09 链式回归、编译、依赖和安全扫描。

### 2026-11-21 W11

- 工具：Codex Desktop。
- 用途：实现受控修复工具、固定验证工具、attempt_no、上一轮失败引用、REVIEW/FEEDBACK/RESULT 和最多两轮修复验证闭环。
- 生成文件：`tools/repair.py`、`tools/verify.py`、扩展的 `repair_agent.py`、`verifier_agent.py`、`tests/integration/test_repair_verification_loop.py`。
- 安全边界：修复工具只接受固定操作和参数，拒绝 Shell、权限提升、破坏性命令和越权写路径。
- 人工审查重点：计划授权、回滚、验证独立性、失败反馈、两轮上限和最终状态。
- 验证方式：5 项 W11 集成测试、157 项全量警告即错误测试、真实 AIOS 回归、编译、依赖和执行 API 扫描。

### 2026-11-21 W12

- 工具：Codex Desktop。
- 用途：实现六个 Docker 故障场景、不可变公共镜像、故障注入、修复、验证、压力、重置哈希和销毁脚本。
- 生成文件：`scenarios/common/`、`scenarios/f1` 至 `scenarios/f6`、`tests/scenarios/test_all_scenarios.py`、`docs/scenarios/scenario_catalog.md`。
- 隔离措施：只读根文件系统、tmpfs 数据目录、无网络映射、不挂载预期答案、不使用生产数据。
- 人工审查重点：场景故障真实性、允许修复范围、答案隔离、重置一致性和容器清理。
- 验证方式：六场景 Docker E2E、每场景三对交互、163 项全量警告即错误测试、编译、依赖和安全扫描。

### 2026-11-22 W13

- 工具：Codex Desktop。
- 用途：实现六场景串行/并发基准、统计、原始数据和 Markdown 报告。
- 生成文件：`benchmark/serial.py`、`parallel.py`、`metrics.py`、`report.py`、`scripts/benchmark/run_local_benchmark.py`、原始 JSON 和汇总报告。
- 测量口径：同一模型、Prompt、场景、工具权限和验证标准；每模式 1 次预热和 5 次有效测量。
- 结果：本地 Ollama 平均提速 37.92%，正确性保持，越权 0。
- 数据边界：本地结果仅用于开发验证，正式比赛仍需远程 vLLM 重测。
- 验证方式：统计单元测试、72 次真实流程、真实 AIOS 调用、W12 容器和 166 项全量测试。

### 2026-11-22 W14

- 工具：Codex Desktop。
- 用途：实现原生 HTML/CSS/JavaScript 仪表盘、任务提交与取消、DAG/Agent 展示、三对交互计数、修复验证时间线、Trace 回放、历史运行和真实基准面板。
- 生成文件：`src/aios_incident/ui/index.html`、`styles.css`、`app.js`、扩展的 `src/aios_incident/api.py`、`tests/e2e/test_dashboard_flow.py`。
- 持久化实现：运行元数据写入 `runs/{incident_id}/{run_id}.meta.json`，API 重启时恢复，JSONL Trace 继续作为事件事实源。
- 数据真实性：界面只使用 API、Trace 和 W13 原始基准数据，不硬编码演示结果。
- 人工审查重点：历史恢复、状态与 Trace 一致、三对交互聚合、取消同步、静态资源路径和页面布局。
- 验证方式：默认 161 项测试、真实 AIOS 与六个 Docker 场景共 169 项全量测试、Edge Headless 实际渲染和截图人工检查。

