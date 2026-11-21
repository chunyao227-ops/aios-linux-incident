# 比赛提交材料台账

## 评分分项与证据映射

| 评分分项 | 权重 | 本项目对应材料 |
|---|---:|---|
| 项目 / 代码执行展示 | 30% | 可运行代码、真实终端执行记录、DAG 与并发演示、修复验证闭环 |
| 文档撰写 | 20% | 需求规格、设计说明、部署运维说明、测试报告、用户操作说明 |
| 文档撰写和代码注释符合软件工程规范 | 20% | 模块边界、类型标注、docstring、测试、静态检查、Git 提交历史 |
| AI 工具说明 | 10% | AI 使用记录、提示与产出范围、人工审查记录、验证方式 |
| 演示视频 | 20% | 环境启动、故障注入、四路证据并行、诊断、受控修复、独立验证、提速对比 |

## W02 评分对应

- **项目 / 代码执行展示（30%）**：唯一代码包、配置检查入口、导入测试和配置切换测试。
- **文档撰写（20%）**：README 最小启动说明、W02 验收记录、本材料台账。
- **软件工程规范（20%）**：严格配置校验、类型标注、模块 docstring、pytest、Ruff、基线/W02 分次提交。
- **AI 工具说明（10%）**：`docs/ai_usage/AI_USAGE.md` 中 W02 条目。
- **演示视频（20%）**：W02 可录制“修改 YAML 后切换模型端点”的短演示，作为最终视频的工程流程片段。

## 已收集材料

| 材料 | 路径 | 状态 | 用途 |
|---|---|---|---|
| W00 项目基线 | `docs/project_baseline.md` | 已保存 | 文档、工程规范 |
| 未决问题清单 | `docs/open_questions.md` | 已保存 | 文档、项目管理 |
| W01A 环境核验 | `docs/environment/w01a_verification_2026-11-19.md` | 已保存 | 执行展示、文档 |
| 本地并发原始结果 | `docs/environment/concurrency_probe_results.json` | 已保存 | 执行展示、性能证据 |
| AI 使用记录 | `docs/ai_usage/AI_USAGE.md` | 已保存，持续更新 | AI 工具说明 |
| W02 源码与测试 | `src/`、`tests/` | 已创建并通过验证 | 代码执行、工程规范 |
| W02 验收记录 | `docs/verification/w02_verification_2026-11-19.md` | 已保存实际命令和结果 | 文档、执行展示 |
| W02 Git 记录 | 基线 `fb5a0f0`；实现 `d1d5eee` | 已保存 | 工程规范、代码执行 |
| W03 数据契约与状态机 | `models.py`、`state.py`、`validation.py` | 已完成并通过 70 项测试 | 代码执行、工程规范 |
| W03 验收记录 | `docs/verification/w03_verification_2026-11-19.md` | 已保存命令与验收对照 | 文档、执行展示 |
| W03 Git 记录 | 实现提交 `301b7ba` | 已保存 | 工程规范、代码执行 |
| W04 AIOS/LLM 适配器 | `adapters/aios_client.py`、`adapters/llm_adapter.py` | 已完成，真实 AIOS 文本与 JSON 冒烟通过 | 代码执行、工程规范 |
| W04 验收记录 | `docs/verification/w04_verification_2026-11-21.md` | 已保存 90 项全量测试与真实冒烟结果 | 文档、执行展示 |
| W04 token 与错误证据 | 单元测试及验收记录 | 已保存“上报/估算”区分和统一错误覆盖 | 代码执行、文档 |
| W04 Git 记录 | 实现提交 `1393a20` | 已保存 | 工程规范、代码执行 |
| W05 Incident API | `api.py` | 已完成创建、状态、DAG、事件、结果和取消接口 | 代码执行、UI 数据来源 |
| W05 Blackboard | `orchestrator/blackboard.py` | 已完成 Incident 隔离和产物就绪控制 | 代码执行、工程规范 |
| W05 JSONL Trace | `orchestrator/trace.py` | 已完成追加写和重复事件保护 | 执行展示、文档 |
| W05 验收记录 | `docs/verification/w05_verification_2026-11-21.md` | 已保存 114 项全量测试结果 | 文档、执行展示 |
| W05 Git 记录 | 实现提交 `52c851d` | 已保存 | 工程规范、代码执行 |
| W06 工具权限矩阵 | `tools/base.py` | 已完成五类工具权限和限制定义 | 代码执行、文档 |
| W06 受控工具网关 | `tools/gateway.py` | 已完成四类只读工具、失败关闭和 Trace | 代码执行、安全展示 |
| W06 隔离测试 | `test_tool_gateway.py`、`test_tool_isolation.py` | 已保存 13 项权限、路径、限制和沙箱测试 | 工程规范、执行展示 |
| W06 验收记录 | `docs/verification/w06_verification_2026-11-21.md` | 已保存 127 项全量测试结果 | 文档、执行展示 |
| W06 Git 记录 | 实现提交 `4e026d6` | 已保存 | 工程规范、代码执行 |
| W07 最小 Agent | `agents/` | Coordinator、Log、Repair、Verifier 已实现 | 代码执行、多智能体说明 |
| W07 最小闭环 | `orchestrator/minimal_flow.py` | 日志、LLM、模拟修复、验证与报告完整贯通 | 核心执行展示 |
| W07 E2E 与演示 | `test_minimal_flow.py`、`docs/demo/minimal_flow.md` | 成功、失败和真实 AIOS 路径已保存 | 执行展示、文档、视频 |
| W07 验收记录 | `docs/verification/w07_verification_2026-11-21.md` | 已保存 130 项全量测试结果 | 文档、执行展示 |
| W07 Git 记录 | 实现提交 `846758e` | 已保存 | 工程规范、代码执行 |
| W08 Planner | `orchestrator/planner.py` | 已完成能力矩阵、DAG 校验和最低负载匹配 | 工程规范、多 Agent 说明 |
| W08 Scheduler | `orchestrator/scheduler.py` | 已完成四路并发、门控、重试和失败终止 | 核心执行展示、性能证据 |
| W08 四路采集 Agent | Metrics、Config、Dependency 和既有 Log Agent | 已通过 ToolGateway 返回结构化证据 | 代码执行、多智能体说明 |
| W08 验收记录 | `docs/verification/w08_verification_2026-11-21.md` | 已保存 135 项全量测试结果 | 文档、执行展示 |
| W08 Git 记录 | 实现提交 `ce0666e` | 已保存 | 工程规范、代码执行 |
| W09 消息总线 | `orchestrator/interaction_bus.py` | 已完成请求响应、超时、离线失败和消息图 | 代码执行、多智能体说明 |
| W09 三对双向交互 | `coordinator_agent.py` | Log↔Config、Metrics↔Dependency、Repair↔Verifier 已运行 | 核心合规展示、视频 |
| W09 交互测试 | `test_interaction_matrix.py` | 已保存 11 消息、3 双向边及异常路径 | 工程规范、执行展示 |
| W09 验收记录 | `docs/verification/w09_verification_2026-11-21.md` | 已保存 143 项全量测试结果 | 文档、执行展示 |
| W09 Git 记录 | 实现提交 `0d1363a` | 已保存 | 工程规范、代码执行 |
| W10 证据融合 | `orchestrator/diagnosis.py` | 已完成去重、时间链、冲突和根因证据绑定 | 核心代码、诊断说明 |
| W10 条件追问 | FollowUpRequest 结构和冲突测试 | 已保存冲突阻断与追问证据 | 工程规范、执行展示 |
| W10 验收记录 | `docs/verification/w10_verification_2026-11-21.md` | 已保存 152 项全量测试结果 | 文档、执行展示 |
| W10 Git 记录 | 实现提交 `b4f017c` | 已保存 | 工程规范、代码执行 |
| W11 受控修复工具 | `tools/repair.py` | 已完成白名单、路径、回滚和拒绝 Shell | 安全展示、代码执行 |
| W11 固定验证工具 | `tools/verify.py` | 已完成固定顺序和 attempt 元数据 | 工程规范、执行展示 |
| W11 两轮闭环 | `repair_agent.py` | 成功、两轮失败、REVIEW/FEEDBACK/RESULT 已实现 | 核心执行展示、视频 |
| W11 验收记录 | `docs/verification/w11_verification_2026-11-21.md` | 已保存 157 项全量测试结果 | 文档、执行展示 |
| W11 Git 记录 | 实现提交 `b05d9f8` | 已保存 | 工程规范、代码执行 |
| W12 六场景夹具 | `scenarios/f1` 至 `f6`、`scenarios/common` | 六个故障均可注入、修复和重置 | 执行展示、视频 |
| W12 场景目录 | `docs/scenarios/scenario_catalog.md` | 故障类型、允许修复和隔离边界已记录 | 文档、合规说明 |
| W12 Docker 测试 | `test_all_scenarios.py` | 六场景失败/成功/压力/哈希和交互通过 | 工程规范、执行展示 |
| W12 验收记录 | `docs/verification/w12_verification_2026-11-21.md` | 已保存 163 项全量测试结果 | 文档、执行展示 |
| W12 Git 记录 | 实现提交 `d856227` | 已保存 | 工程规范、代码执行 |
| W13 基准代码 | `benchmark/` | 串行、并发、统计和报告均已实现 | 代码执行、性能说明 |
| W13 原始数据 | `docs/experiment_reports/raw/local_ollama_2026-11-22.json` | 72 次流程及模型/工具/token/Trace 已保存 | 性能证据、原始实验 |
| W13 汇总表 | `docs/experiment_reports/benchmark_results.md` | 平均提速 37.92%，正确性保持 | 文档、演示、性能证据 |
| W13 验收记录 | `docs/verification/w13_verification_2026-11-22.md` | 已保存 166 项全量测试结果 | 文档、执行展示 |
| W13 Git 记录 | 实现提交 `835ff97` | 已保存 | 工程规范、代码执行 |
| W14 仪表盘 | `src/aios_incident/ui/` | 已实现任务、历史、DAG、交互、时间线、基准和取消展示 | 核心执行展示、视频 |
| W14 历史持久化 | `src/aios_incident/api.py` | 已实现元数据持久化和 API 重启恢复 | 代码执行、工程规范 |
| W14 E2E | `tests/e2e/test_dashboard_flow.py` | 已保存页面、回放、重启恢复和取消测试 | 工程规范、执行展示 |
| W14 页面截图 | `docs/submission/evidence/ui/dashboard_2026-11-22.png` | Edge Headless 实际渲染并人工检查 | 文档、演示、执行展示 |
| W14 验收记录 | `docs/verification/w14_verification_2026-11-22.md` | 已保存 169 项全量测试结果和截图 | 文档、执行展示 |
| W14 Git 记录 | 实现提交 `8846da4` | 已保存 | 工程规范、代码执行 |

## 当前缺少

- W02 终端测试与静态检查的截图。
- 远程 vLLM 地址、模型名称、认证变量和正式环境核验结果。
- CPU ECS 开通与部署记录。
- W03 以后的 DAG、证据并行、双向交互、修复和验证演示材料。
- W03 数据契约和状态机的终端截图及可视化 DAG 图。
- W04 AIOS 文本调用、JSON 输出和真实冒烟测试的终端截图。
- W05 API 请求、结构化错误、JSONL Trace 和 OpenAPI 页面截图。
- W06 工具调用、越权拒绝、路径逃逸拒绝和 Trace 截图。
- W07 成功/失败闭环 Trace、最终报告和真实 AIOS 运行截图、录屏。
- W08 四路派发批次、并发时间线和重试终止截图、录屏。
- W09 三对消息图、双向边计数、超时和断连 Trace 截图、录屏。
- W10 四类证据链、冲突追问和根因引用截图、录屏。
- W11 两轮修复时间线、回滚和危险计划拒绝截图、录屏。
- W12 六场景注入、失败、修复、重置哈希和容器销毁截图、录屏。
- W13 串行/并发图表、正式远程 vLLM 数据、性能录屏。
- 更多历史运行、失败重试和取消任务的界面截图、录屏。
- 从故障注入到诊断、修复、验证、历史回放的完整演示视频。
- 比赛平台要求的最终文档模板、视频格式与提交清单。

## 持续记录规则

1. 每个工单完成后保存测试命令、结果摘要和 Git 提交号。
2. 关键终端步骤保留文本输出，并补充无敏感信息的截图。
3. 每次模型或性能实验保存原始 JSON、配置快照、环境参数和汇总表。
4. 新增 AI 生成代码或文档时，当次更新 `docs/ai_usage/AI_USAGE.md`。
5. 所有提交材料不得包含账号、密钥、私钥或个人敏感信息。

