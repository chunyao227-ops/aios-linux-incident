# AIOS Linux 服务故障协同诊断修复与回归验证系统交接文档

- 更新日期：2026-11-22
- 仓库根目录：`aios-linux-incident/`
- 当前分支：`master`
- 整理前提交：`559c7d9`
- 当前状态：W00、W01A、W02—W14 已完成，工作区干净，准备进入 W15

## 1. 项目目标

本项目参加全国大学生计算机系统能力大赛操作系统设计赛，OS 功能挑战赛道，中西部与华南区域赛。

关键日期：

- 区域赛提交截止：2026-12-27。
- 全国初赛提交截止：2027-05-01。

评分权重：

| 评分分项 | 权重 |
|---|---:|
| 项目 / 代码执行展示 | 30% |
| 文档撰写 | 20% |
| 文档撰写和代码注释符合软件工程规范 | 20% |
| AI 工具说明 | 10% |
| 演示视频 | 20% |

系统目标：

```text
故障上报
  -> 四类证据并行采集
  -> 证据融合与根因诊断
  -> 受控修复
  -> 健康、业务回归与压力验证
  -> 成功归档或失败重试
```

必须满足：

- 不少于 7 类职责不同的 Agent；
- 至少 4 个可并行的证据采集任务；
- 至少 3 对异构 Agent 双向交互；
- 任务依赖由调度器执行；
- 并发相对串行平均提速不低于 20%；
- 修复结果由独立验证器判定；
- 所有修复只允许作用于隔离 Docker 靶机；
- Agent 不得执行任意 Shell、权限提升或破坏性命令。

## 2. 技术架构

### 2.1 技术基线

| 项目 | 当前值 |
|---|---|
| Python | 3.10；本地验证版本 3.10.11 |
| AIOS Kernel | 提交 `292d98f78c835499df18cdb6de6325bba1895862` |
| Cerebrum SDK | `aios-agent-sdk 0.0.3` |
| 本地调试模型 | Ollama `qwen2:7b-instruct` Q4_K_M |
| 正式模型 | 远程 GPU vLLM，7B AWQ 4bit，OpenAI 兼容接口 |
| Agent 与靶机 | Windows/WSL2 本地环境，后续可部署至 CPU ECS |
| Docker | Engine 29.1.3，WSL2 Ubuntu 22.04 |
| Python 包入口 | `src/aios_incident/` |

本地服务地址：

```text
AIOS:   http://127.0.0.1:8000
Ollama: http://127.0.0.1:11434
API/UI: http://127.0.0.1:8080
```

### 2.2 部署结构

```text
Windows 开发终端
  |
  +-- WSL2 Ubuntu 22.04
        |
        +-- AIOS Kernel
        +-- Ollama 本地调试替身
        +-- Docker 六个故障靶机
        +-- FastAPI + 原生 Web 仪表盘
        |
        +-- 后续接入远程 GPU vLLM
              7B AWQ 4bit / OpenAI 兼容接口
```

正式性能实验必须记录 CPU 侧环境、远程 GPU 环境、网络链路、模型参数和原始数据。本地 Ollama 结果不能标记为正式 vLLM 结果。

### 2.3 代码边界

唯一代码根目录为 `src/aios_incident/`。禁止在仓库根目录另建平行的 `agents/`、`orchestrator/`、`adapters/`、`tools/`、`benchmark/` 或 `ui/`。

```text
src/aios_incident/
  agents/
  orchestrator/
  adapters/
  tools/
  benchmark/
  ui/
```

职责划分：

- AIOS Kernel 负责 LLM、Memory、Storage 和 Tool 系统调用。
- 项目调度器负责任务 DAG、能力匹配、依赖门控、并发派发和重试。
- FastAPI 负责故障提交、状态、DAG、事件、结果、取消、历史和基准查询。
- UI 只读取真实 API、Trace 和基准数据。
- JSONL Trace 保存追加式事件；`meta.json` 保存可恢复的运行元数据。

### 2.4 Agent 与主流程

| Agent | 职责 |
|---|---|
| CoordinatorAgent | 规划、证据汇合、根因诊断和最终结论 |
| LogAgent | 日志、错误链和时间线 |
| MetricsAgent | CPU、内存、磁盘、网络和连接指标 |
| ConfigAgent | 配置、权限、端口和配置生效状态 |
| DependencyAgent | 进程、服务、端口和依赖拓扑 |
| RepairAgent | 生成并执行受控修复计划 |
| VerifierAgent | 健康、业务回归和压力验证 |

固定流程：

```text
PLAN
  -> N1—N4 四路并行采集
  -> DIAGNOSE
  -> REPAIR
  -> VERIFY
  -> SUCCESS / UNRESOLVED
  -> 最多两轮修复与反馈
```

固定双向交互：

1. LogAgent ↔ ConfigAgent；
2. MetricsAgent ↔ DependencyAgent；
3. RepairAgent ↔ VerifierAgent。

## 3. 已完成的功能

| 工单 | 状态 | 核心成果 |
|---|---|---|
| W00 | 完成 | 项目基线、冻结规格、工单、AI 使用记录和 Git 初始化 |
| W01A | 完成 | WSL2、Python、AIOS、Ollama、Docker 本地环境 |
| W02 | 完成 | 唯一 Python 包、六个子包、严格 YAML 配置和任务入口 |
| W03 | 完成 | RunContext、DAG、Evidence、Message、诊断、修复、验证和状态机 |
| W04 | 完成 | 经 AIOS `/query` 的文本与严格 JSON 调用、错误归一化和 token 记录 |
| W05 | 完成 | Incident API、Blackboard、JSONL Trace 和取消接口 |
| W06 | 完成 | 五类工具权限、四类只读工具、受控网关和失败关闭 |
| W07 | 完成 | 日志证据、模型诊断、模拟修复、独立验证和最终报告闭环 |
| W08 | 完成 | 固定 DAG、最低负载匹配、四路并发、门控、重试和失败终止 |
| W09 | 完成 | 消息总线、请求响应、超时、断连失败和三对双向交互 |
| W10 | 完成 | 四类证据融合、事实去重、冲突阻断、追问和根因证据绑定 |
| W11 | 完成 | 受控修复、回滚、两轮 REVIEW/FEEDBACK/RESULT 闭环 |
| W12 | 完成 | F1—F6 六个 Docker 场景、注入、修复、验证、压力、重置和销毁 |
| W13 | 完成 | 串行/并发基准、统计、原始 JSON 和 Markdown 报告 |
| W14 | 完成 | 仪表盘、历史持久化、Trace 回放、取消和真实基准面板 |

当前验证结果：

- 默认统一回归：`161 passed, 8 skipped`。
- 已记录全量本地环境回归：`169 passed`。
- 本轮材料专项验证：123 项通过，F1—F6 六个 Docker 场景全部通过。
- Ruff、格式、配置和警告检查通过。
- 本地六场景基准：平均提速 37.92%，最低单场景提速 15.79%，越权操作 0。
- 提交证据：`docs/submission/evidence/` 下 87 个文件，包含测试、Trace、图表和截图。

本地基准不是正式性能结论。正式提交前必须在远程 7B AWQ 4bit vLLM 上重新测试。

## 4. 关键文件位置

| 路径 | 作用 |
|---|---|
| `README.md` | 安装、配置、API、UI 和基准入口 |
| `docs/project_baseline.md` | 赛道、日期、技术基线和 CPU 服务器决策 |
| `docs/specifications/development_spec_v1.0.md` | 冻结开发规格 |
| `docs/specifications/ai_work_orders_v1.0.md` | W00—W17 工单及验收条件 |
| `docs/open_questions.md` | 尚待外部确认的问题 |
| `docs/ai_usage/AI_USAGE.md` | AI 工具、用途、生成范围和验证记录 |
| `docs/verification/` | W02—W14 分阶段验收记录 |
| `docs/environment/` | W01A 环境和本地运行时核验 |
| `docs/experiment_reports/` | W13 汇总表和原始基准 JSON |
| `docs/submission/ARTIFACT_LEDGER.md` | 评分材料映射、已收集和当前缺少 |
| `docs/submission/evidence/EVIDENCE_MANIFEST.md` | 证据目录、复现命令和数据边界 |
| `pyproject.toml` | Python 依赖、测试和 Ruff 配置 |
| `tasks.ps1` | 安装、测试、检查、API、场景和基准入口 |
| `config/app.example.yaml` | 应用配置；修改 model 段切换本地/远程模型 |
| `config/model.remote.yaml.example` | 远程 vLLM 配置模板，不保存真实密钥 |
| `src/aios_incident/models.py` | 公共数据契约和固定 DAG |
| `src/aios_incident/state.py` | 任务与工作流状态机 |
| `src/aios_incident/api.py` | FastAPI、历史和静态 UI |
| `src/aios_incident/adapters/` | AIOS 与 LLM 适配器 |
| `src/aios_incident/orchestrator/` | Planner、Scheduler、InteractionBus、诊断、Blackboard 和 Trace |
| `src/aios_incident/agents/` | 七类 Agent |
| `src/aios_incident/tools/` | 只读工具、受控修复和验证工具 |
| `src/aios_incident/benchmark/` | 串行、并发、统计和报告 |
| `src/aios_incident/ui/` | 无构建步骤的 HTML/CSS/JavaScript 仪表盘 |
| `tests/` | 单元、集成、E2E 和 Docker 场景测试 |
| `scenarios/` | F1—F6 场景脚本、清单和受限容器配置 |
| `scripts/env/` | AIOS、Ollama、Docker 和模型检查脚本 |
| `scripts/evidence/` | 环境、API、模型、W07、六场景和图表证据生成脚本 |
| `runs/` | 运行时 Incident 元数据和 JSONL Trace，默认不提交 |

常用命令：

```powershell
.\tasks.ps1 setup
.\tasks.ps1 verify
.\tasks.ps1 api
.\tasks.ps1 integration
.\tasks.ps1 scenarios
.\tasks.ps1 benchmark
```

启动 API 后：

```text
http://127.0.0.1:8080/
http://127.0.0.1:8080/docs
```

## 5. 当前问题与限制

### 5.1 正式远程环境尚未接入

尚缺少：

- 远程 GPU vLLM 地址；
- 正式模型名称；
- API Key 环境变量名称；
- GPU、CUDA、驱动和模型参数；
- 正式环境与验证结果。

因此 W01B 尚未完成，正式性能数据仍为空缺。

### 5.2 CPU ECS 尚未部署

本地开发不依赖 CPU ECS。若最终方案采用 CPU ECS，建议：

```text
ecs.e-c1m4.xlarge
4 vCPU / 16 GiB
Ubuntu 22.04
按量付费
```

如不采用，应在 W15/W16 保存正式决策、本地 CPU 参数和等价测试记录。

### 5.3 正式提交材料尚未齐全

仍需补充：

- W07—W12 连续操作录屏；
- 仪表盘成功、失败重试和无修复结果截图；
- 仪表盘取消、刷新恢复的连续录屏；
- 正式远程 vLLM 性能数据和性能录屏；
- 完整故障注入到历史回放的演示视频；
- 比赛平台的最终文档模板、视频格式和提交清单。

现有证据已覆盖测试结果、Trace、图表和静态截图，但视频评分仍需正式录制。

### 5.4 当前 UI 的产品化限制

- 当前为单机开发部署；
- 没有用户认证和权限隔离；
- 页面每 3 秒轮询，不使用 WebSocket；
- API 创建 Incident 后不会自动启动完整 Docker 工作流；
- 完整工作流当前由对应测试、场景脚本和证据生成脚本执行。

### 5.5 本地运行依赖脚本

WSL 重启后，AIOS 和 Ollama 不会自动恢复：

```bash
bash scripts/env/start_ollama_wsl.sh
bash scripts/env/start_aios_wsl.sh
```

Docker 由 systemd 启动。旧会话若出现权限问题，可执行：

```bash
sg docker -c "docker info"
```

## 6. 下一步任务

新 Codex 会话应按以下顺序接手：

1. 读取本文件、开发规格和 W15 工单；
2. 执行 `git status` 和 `git log -1`；
3. 检查 AIOS、Ollama 和 Docker；
4. 执行 `.\tasks.ps1 verify`；
5. 从 W15 开始，不重做 W00—W14。

### 第一优先：W15 测试、加固与复现

当前即可开始，不依赖远程 GPU。

应完成：

- 运行单元、集成、场景和 E2E 测试；
- 检查超时、取消、恢复、异常和失败关闭；
- 在干净 Ubuntu/WSL 环境安装并运行；
- 清理绝对路径、调试入口、缓存和敏感信息；
- 校验依赖锁定、许可证和第三方说明；
- 新增以下文件：

```text
scripts/install.sh
scripts/run_demo.sh
docs/testing/test_report.md
docs/environment/reproduce.md
```

W15 验收标准：

- 全量测试通过；
- 干净环境可复现；
- 无敏感信息；
- 无无效调试入口。

### 第二优先：W01B 正式远程环境

资源和凭证就绪后立即执行：

1. 使用 `config/model.remote.yaml.example` 建立未提交的正式配置；
2. 验证 `/v1/models`、AIOS `/query`、文本和严格 JSON；
3. 执行全量测试；
4. 使用相同 W13 口径重新运行串行/并发基准；
5. 保存环境、网络、模型参数、原始 JSON 和汇总报告；
6. 将正式数据写入提交材料，不覆盖或混淆本地 Ollama 数据。

### 第三优先：W16 文档、录屏与提交

W15 完成且功能冻结后：

- 完成系统设计、实现和测试文档；
- 更新 AI 使用说明、许可证和第三方依赖说明；
- 编写 `docs/demo/demo_script.md`；
- 录制四路并行、三对交互、失败反馈、受控修复和独立验证；
- 在干净环境复演；
- 打包提交仓库、文档、证据和视频。

### 后续：W17

W16 完成后进入国赛阶段能力扩展。当前不得为 W17 提前改动已验证的主链路。
