# AIOS 竞赛项目交接与复现文档

本文档是仓库的唯一接班入口，面向两类使用：

1. 在全新电脑拉取仓库后完成部署、复现和继续开发；
2. 新 Codex 会话读取后准确识别当前状态、约束和下一步任务。

文档中的所有项目文件均使用仓库根目录相对路径。命令如无特别说明，均在仓库根目录执行。

当前基线：

- 分支：`master`
- 整理前提交：`fd89699`
- 当前阶段：W00、W01A、W02—W14 已完成，准备进入 W15
- 工作区状态：整理本文件前为干净状态

## 1. 项目简介与竞赛目标

### 1.1 项目定位

项目名称：基于 AIOS 的 Linux 服务故障协同诊断、修复与回归验证系统。

所属赛道：全国大学生计算机系统能力大赛操作系统设计赛，OS 功能挑战赛道，中西部与华南区域赛。

系统接收 Linux 服务故障，完成：

```text
故障上报
  -> 四类证据并行采集
  -> 证据融合与根因诊断
  -> 受控修复
  -> 健康、业务回归与压力验证
  -> 成功归档或失败重试
```

### 1.2 必须满足的技术目标

- 至少 7 类职责不同的 Agent；
- 至少 4 个并行证据采集任务；
- 至少 3 对异构 Agent 双向交互；
- 任务依赖由 DAG 调度器执行；
- 并发相对串行平均提速不低于 20%；
- 修复成功由独立 VerifierAgent 判定；
- 最多两轮修复反馈；
- 所有修复只允许作用于隔离 Docker 靶机；
- Agent 不得执行任意 Shell、权限提升或破坏性命令；
- 场景标准答案不得暴露给 Agent。

### 1.3 时间与评审

- 区域赛提交截止：2026-12-27。
- 全国初赛提交截止：2027-05-01。

| 评分分项 | 权重 |
|---|---:|
| 项目 / 代码执行展示 | 30% |
| 文档撰写 | 20% |
| 文档撰写和代码注释符合软件工程规范 | 20% |
| AI 工具说明 | 10% |
| 演示视频 | 20% |

最终交付至少包括：

- 可安装、可运行的源代码；
- 架构、部署、测试、复现和用户说明；
- 真实执行日志、测试结果、Trace、图表和截图；
- AI 工具使用说明；
- 串行/并发实验原始数据和汇总结论；
- 完整演示视频；
- 比赛平台要求的最终提交清单。

### 1.4 评审证据归档原则

每完成一个工单，同时完成：

1. 保存实际执行命令和结果；
2. 保存原始 JSON、JSONL、JUnit 或文本输出；
3. 保存无敏感信息的截图或录屏；
4. 更新 `docs/submission/ARTIFACT_LEDGER.md`；
5. 更新 `docs/ai_usage/AI_USAGE.md`；
6. 记录 Git 提交号；
7. 在 `docs/verification/` 保存本工单验收记录。

## 2. 仓库目录说明

### 2.1 核心目录

```text
.
├─ src/aios_incident/           # 唯一业务代码根目录
│  ├─ agents/                   # 七类 Agent
│  ├─ orchestrator/             # DAG、调度、消息、黑板、Trace、诊断
│  ├─ adapters/                 # AIOS 与 LLM 适配器
│  ├─ tools/                    # 只读、修复和验证工具
│  ├─ benchmark/                # 串行、并发、统计和报告
│  └─ ui/                       # 原生 Web 仪表盘
├─ tests/                       # 单元、集成、E2E 和场景测试
├─ scenarios/                   # F1—F6 Docker 场景
├─ scripts/                     # 环境、基准和证据生成脚本
├─ config/                      # 模板配置与本地配置目录
├─ docs/                        # 规格、设计、验收和提交材料
├─ pyproject.toml               # Python 依赖与工具配置
├─ tasks.ps1                    # Windows 统一任务入口
├─ README.md                    # 快速启动说明
└─ .gitignore                   # Git 忽略规则
```

禁止在仓库根目录另建平行的 `agents/`、`orchestrator/`、`adapters/`、`tools/`、`benchmark/` 或 `ui/`。

### 2.2 规格、架构和验收文件

| 路径 | 用途 |
|---|---|
| `docs/specifications/development_spec_v1.0.md` | 冻结开发规格 |
| `docs/specifications/ai_work_orders_v1.0.md` | W00—W17 工单、约束和验收条件 |
| `docs/project_baseline.md` | 赛道、版本、硬件、模型和部署基线 |
| `docs/open_questions.md` | 尚待外部确认的问题 |
| `docs/verification/` | 各工单实际验收记录 |
| `docs/submission/ARTIFACT_LEDGER.md` | 评分分项与提交材料台账 |
| `docs/submission/evidence/EVIDENCE_MANIFEST.md` | 现有证据索引与生成命令 |
| `docs/ai_usage/AI_USAGE.md` | AI 工具使用记录 |
| `docs/experiment_reports/` | 性能实验汇总和原始数据 |

### 2.3 模板文件（可提交 Git）

| 路径 | 说明 |
|---|---|
| `config/app.example.yaml` | 应用配置模板和字段示例 |
| `config/model.example.yaml` | 通用模型配置示例 |
| `config/model.local.yaml` | 本地 Ollama 基线记录 |
| `config/model.remote.yaml.example` | 远程 vLLM 字段参考模板，不可直接替代应用配置 |
| `config/aios.kernel.local.yaml` | AIOS Kernel 配置模板；使用前必须替换机器相关目录 |
| `config/docker-daemon.json` | Docker registry mirror 模板 |
| `config/ollama/Modelfile.qwen2-7b-instruct` | Qwen2 Ollama ChatML 模板 |

### 2.4 本地私有文件（禁止提交 Git）

| 路径或类型 | 说明 |
|---|---|
| `config/local.secret.yaml` | 本机应用配置，可由 `config/app.example.yaml` 复制 |
| `.env`、`.env.local` | 本地环境变量 |
| `*.key`、`*.pem`、`secrets.yaml` | 密钥和私钥 |
| `.venv/`、`venv/`、`.python310/` | Python 虚拟环境 |
| `runs/` | Incident 元数据和运行 Trace |
| `logs/`、`work/`、`cache/` | 运行日志和临时数据 |
| `models/`、`vendor/`、`*.gguf` | 模型权重和大型外部文件 |
| `config/*.secret.yaml` | 其他本机正式配置 |
| `docs/submission/evidence/**/*.png` | 新增截图，外部归档，不进入源码历史 |
| `docs/submission/evidence/**/*.{jpg,jpeg,webp}` | 新增图片证据 |
| `docs/submission/evidence/**/*.{mp4,mov,mkv,webm}` | 新增录屏和视频证据 |

说明：

- 仓库在 W14 前已跟踪的历史证据图片继续保留引用；从本交接版本起，新增图片和视频按本地私有材料管理。
- 实际比赛提交包可以单独打包截图和视频，但不得通过日常源码提交持续膨胀 Git 历史。

## 3. 环境部署流程

### 3.1 前置条件

Windows 电脑需要：

- Git；
- Python 3.10 和 Python Launcher；
- WSL2；
- 可选 NVIDIA GPU，用于本地 Ollama 调试；
- 允许执行 PowerShell 脚本的当前用户；
- 可访问项目仓库、AIOS 源码和模型下载渠道的网络。

首次安装 WSL2：

```powershell
wsl --install -d Ubuntu-22.04
```

安装完成后重启电脑，并按提示创建 Ubuntu 用户。

### 3.2 拉取项目

将 `<REPOSITORY_URL>` 替换为团队提供的项目仓库地址：

```powershell
git clone <REPOSITORY_URL> aios-linux-incident
Set-Location aios-linux-incident
git remote -v
git log -1 --oneline
```

如果已有本地仓库但没有远端：

```powershell
git remote add origin <REPOSITORY_URL>
git remote -v
```

### 3.3 PowerShell 执行策略

仅对当前 PowerShell 进程放开执行策略：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

不要把执行策略永久设置为 `Unrestricted`。

### 3.4 创建 Windows 项目环境

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\tasks.ps1 setup
```

然后初始化本地应用配置：

```powershell
Copy-Item config/app.example.yaml config/local.secret.yaml
$env:AIOS_INCIDENT_CONFIG = "config/local.secret.yaml"
.\tasks.ps1 check-config
.\tasks.ps1 verify
```

本地应用配置覆盖整个当前 PowerShell 进程树。重新打开终端后需要重新设置 `AIOS_INCIDENT_CONFIG`。

### 3.5 安装 WSL2 基础依赖

```powershell
wsl -d Ubuntu-22.04 -u root -- bash -lc "apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y python3.10 python3.10-venv python3-pip git curl zstd build-essential"
```

计算当前仓库的 WSL 路径，供后续命令复用：

```powershell
$repoWsl = (wsl -d Ubuntu-22.04 -- wslpath -a ".").Trim()
```

### 3.6 安装锁定 AIOS 源码

```powershell
wsl -d Ubuntu-22.04 -- bash -lc 'git clone https://github.com/agiresearch/AIOS.git "$HOME/AIOS"'
wsl -d Ubuntu-22.04 -- bash -lc 'cd "$HOME/AIOS" && git fetch --all && git checkout 292d98f78c835499df18cdb6de6325bba1895862'
```

创建 AIOS 独立 WSL 虚拟环境并安装依赖：

```powershell
wsl -d Ubuntu-22.04 -- bash -lc 'python3.10 -m venv "$HOME/venv-aios"'
wsl -d Ubuntu-22.04 -- bash -lc 'source "$HOME/venv-aios/bin/activate" && python -m pip install --upgrade pip'
wsl -d Ubuntu-22.04 -- bash -lc 'source "$HOME/venv-aios/bin/activate" && python -m pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cpu'
wsl -d Ubuntu-22.04 -- bash -lc 'cd "$HOME/AIOS" && source "$HOME/venv-aios/bin/activate" && python -m pip install -r requirements.txt'
wsl -d Ubuntu-22.04 -- bash -lc 'source "$HOME/venv-aios/bin/activate" && python -m pip install "aios-agent-sdk==0.0.3" "kubernetes==28.1.0" && python -m pip check'
```

检查 Cerebrum API：

```powershell
wsl -d Ubuntu-22.04 -- bash -lc 'source "$HOME/venv-aios/bin/activate" && python -c "import cerebrum.llm.apis, cerebrum.memory.apis; print(\"cerebrum-ok\")"'
```

### 3.7 初始化 AIOS Kernel 配置

在新电脑上，`config/aios.kernel.local.yaml` 仅作为模板。将其中机器相关的 home 路径替换为当前 WSL home：

```powershell
$wslHome = (wsl -d Ubuntu-22.04 -- bash -lc 'printf "%s" "$HOME"').Trim()
New-Item -ItemType Directory -Force work | Out-Null
$aiosConfig = Get-Content config/aios.kernel.local.yaml -Raw
$aiosConfig = $aiosConfig -replace '(?m)(?<=^  root_dir: ").*(?="$)', "$wslHome/AIOS/root"
$aiosConfig = $aiosConfig -replace '(?m)(?<=^  mcp_server_script_path: ").*(?="$)', "$wslHome/AIOS/aios/tool/mcp_server.py"
$aiosConfig | Set-Content -NoNewline work/aios.kernel.wsl.yaml
```

写入 AIOS 实际配置：

```powershell
Get-Content work/aios.kernel.wsl.yaml -Raw | wsl -d Ubuntu-22.04 -- bash -lc 'cat > "$HOME/AIOS/aios/config/config.yaml"'
```

检查 AIOS 配置中的模型 backend、hostname、storage 和 MCP 路径。`work/` 和 AIOS 外部配置均不得提交 Git。

### 3.8 安装 Docker

```powershell
$wslUser = (wsl -d Ubuntu-22.04 -- whoami).Trim()
wsl -d Ubuntu-22.04 -u root -- bash "$repoWsl/scripts/env/install_docker_wsl.sh" $wslUser
```

安装完成后打开新的 WSL shell，再检查：

```powershell
wsl -d Ubuntu-22.04 -- bash "$repoWsl/scripts/env/check_docker_wsl.sh"
```

如果当前旧会话仍无 Docker 权限：

```powershell
wsl -d Ubuntu-22.04 -- bash -lc 'sg docker -c "docker info"'
```

### 3.9 安装并启动 Ollama

```powershell
wsl -d Ubuntu-22.04 -- bash "$repoWsl/scripts/env/install_ollama_wsl.sh"
wsl -d Ubuntu-22.04 -- bash "$repoWsl/scripts/env/start_ollama_wsl.sh"
```

快速本地重建：

```powershell
wsl -d Ubuntu-22.04 -- bash -lc '"$HOME/.local/bin/ollama" pull qwen2:7b-instruct'
```

严格按锁定 GGUF 重建时，将批准的 `qwen2-7b-instruct-q4_k_m.gguf` 放入 WSL 本地模型目录，验证 SHA-256 后执行：

```powershell
wsl -d Ubuntu-22.04 -- bash "$repoWsl/scripts/env/create_ollama_model_wsl.sh" "$HOME/.cache/models/qwen2-7b-instruct-q4_k_m.gguf"
```

基线模型的预期 SHA-256：

```text
ed93dfc426f926451fa3ec7f996a787a31cfd97e55d7769568fbffc2d69861c2
```

模型文件和 GGUF 不得进入 Git。

### 3.10 启动并核验 AIOS

```powershell
wsl -d Ubuntu-22.04 -- bash "$repoWsl/scripts/env/start_aios_wsl.sh"
```

核验：

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/status"
Invoke-RestMethod -Uri "http://127.0.0.1:8000/core/status"
Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/version"
```

预期：

```text
AIOS /status       -> status = ok
AIOS /core/status  -> 核心组件 active
Ollama /api/version -> 返回版本
```

### 3.11 启动应用和浏览器页面

```powershell
$env:AIOS_INCIDENT_CONFIG = "config/local.secret.yaml"
.\tasks.ps1 api
```

浏览器访问：

```text
http://127.0.0.1:8080/
http://127.0.0.1:8080/docs
```

### 3.12 完整回归

默认回归：

```powershell
.\tasks.ps1 verify
```

真实 AIOS：

```powershell
.\tasks.ps1 integration
```

六个 Docker 场景：

```powershell
.\tasks.ps1 scenarios
```

一次执行全部真实环境测试：

```powershell
$env:RUN_AIOS_INTEGRATION = "1"
$env:RUN_DOCKER_SCENARIOS = "1"
.\.venv\Scripts\python.exe -m pytest -o addopts="" -W error
```

当前预期默认结果：

```text
161 passed, 8 skipped
```

8 个默认跳过项为 2 个 AIOS 集成测试和 6 个 Docker 场景测试。

## 4. 已完成进度清单

| 工单 | 状态 | 已实现内容 | 主要证据 |
|---|---|---|---|
| W00 | 完成 | 赛道、版本、资源和 Git 基线 | `docs/project_baseline.md`、`docs/open_questions.md` |
| W01A | 完成 | WSL2、Python、AIOS、Ollama 和 Docker 本地环境 | `docs/environment/w01a_verification_2026-11-19.md` |
| W02 | 完成 | 唯一 Python 包、配置加载和统一任务入口 | `docs/verification/w02_verification_2026-11-19.md`、`docs/submission/evidence/terminal/W02_verify.txt` |
| W03 | 完成 | 公共数据契约、固定 DAG 和状态机 | `docs/verification/w03_verification_2026-11-19.md`、`docs/submission/evidence/workflow/W03_task_dag.json` |
| W04 | 完成 | AIOS `/query` 文本、严格 JSON、错误和 token | `docs/verification/w04_verification_2026-11-21.md`、`docs/submission/evidence/terminal/W04_aios_responses.json` |
| W05 | 完成 | Incident API、Blackboard 和 JSONL Trace | `docs/verification/w05_verification_2026-11-21.md`、`docs/submission/evidence/api/W05_api_capture.json` |
| W06 | 完成 | 工具权限矩阵、只读工具和受控网关 | `docs/verification/w06_verification_2026-11-21.md`、`docs/submission/evidence/security/W06_tool_gateway.txt` |
| W07 | 完成 | 最小诊断、修复、验证和报告闭环 | `docs/verification/w07_verification_2026-11-21.md`、`docs/submission/evidence/workflow/W07_success_report.json` |
| W08 | 完成 | Planner、四路并发 Scheduler、重试和门控 | `docs/verification/w08_verification_2026-11-21.md`、`docs/submission/evidence/workflow/W08_parallel_events.json` |
| W09 | 完成 | 消息总线、请求响应、超时和三对双向交互 | `docs/verification/w09_verification_2026-11-21.md`、`docs/submission/evidence/workflow/W09_message_graph.json` |
| W10 | 完成 | 四类证据融合、冲突阻断、追问和根因引用 | `docs/verification/w10_verification_2026-11-21.md`、`docs/submission/evidence/workflow/W10_evidence_chain.json` |
| W11 | 完成 | 受控修复、回滚和两轮修复验证 | `docs/verification/w11_verification_2026-11-21.md`、`docs/submission/evidence/workflow/W11_repair_verification.txt` |
| W12 | 完成 | F1—F6 Docker 场景、注入、修复、压力、重置和销毁 | `docs/verification/w12_verification_2026-11-21.md`、`docs/submission/evidence/scenarios/W12_lifecycle_summary.json` |
| W13 | 完成 | 六场景串行/并发基准和报告 | `docs/verification/w13_verification_2026-11-22.md`、`docs/experiment_reports/raw/local_ollama_2026-11-22.json` |
| W14 | 完成 | 仪表盘、历史持久化、Trace 回放、取消和基准面板 | `docs/verification/w14_verification_2026-11-22.md`、`docs/submission/evidence/ui/W14_history_api.json` |

当前材料总索引：

```text
docs/submission/evidence/EVIDENCE_MANIFEST.md
```

当前本地基准结果：

- 平均提速：37.92%；
- 最低单场景提速：15.79%；
- 并发正确性不低于串行；
- 越权操作：0。

该结果来自本地 Ollama，只能标识为开发验证，不能作为正式远程 vLLM 结论。

## 5. 当前待完成任务清单

### 5.1 第一步：W15 测试、加固与复现

当前即可开始，不依赖远程 GPU。

执行完整回归：

```powershell
$env:RUN_AIOS_INTEGRATION = "1"
$env:RUN_DOCKER_SCENARIOS = "1"
.\.venv\Scripts\python.exe -m pytest -o addopts="" -W error
```

重新生成当前证据：

```powershell
.\.venv\Scripts\python.exe scripts\evidence\capture_aios_evidence.py
.\.venv\Scripts\python.exe scripts\evidence\capture_minimal_flow_evidence.py
.\.venv\Scripts\python.exe scripts\evidence\capture_scenario_evidence.py
.\.venv\Scripts\python.exe scripts\evidence\render_evidence.py
```

启动 API 后生成 API 和环境快照：

```powershell
.\tasks.ps1 api
```

在另一个仓库根目录 PowerShell 终端执行：

```powershell
.\.venv\Scripts\python.exe scripts\evidence\capture_api_evidence.py
.\.venv\Scripts\python.exe scripts\evidence\capture_environment_evidence.py
```

W15 必须产出：

| 产出物 | 路径 | 证据要求 |
|---|---|---|
| 通用安装脚本 | `scripts/install.sh` | 干净 Ubuntu/WSL 安装日志 |
| 演示运行脚本 | `scripts/run_demo.sh` | 成功执行记录 |
| 测试报告 | `docs/testing/test_report.md` | 命令、结果、失败分析 |
| 复现说明 | `docs/environment/reproduce.md` | 干净环境实际记录 |
| 全量测试证据 | `docs/submission/evidence/terminal/` | 原始文本和 JUnit |
| 环境快照 | `docs/submission/evidence/environment/` | 系统、依赖、服务版本和配置哈希 |

W15 还需要：

- 检查超时、取消、恢复和异常路径；
- 清理绝对路径、调试入口、缓存和敏感信息；
- 固定或锁定依赖；
- 校验许可证和第三方依赖；
- 验证 README 可从干净环境完成安装。

### 5.2 第二步：W01B 正式远程 vLLM

需要先取得：

- vLLM OpenAI 兼容地址；
- 正式 served model name；
- 认证环境变量名；
- API Key；
- GPU、驱动、CUDA、量化和部署参数；
- 网络白名单和访问方式。

本地 PowerShell 设置，不写入仓库：

```powershell
$env:MODEL_BASE_URL = "<REMOTE_VLLM_BASE_URL>"
$env:MODEL_NAME = "<REMOTE_MODEL_NAME>"
$env:MODEL_API_KEY = "<REMOTE_API_KEY>"
```

同步修改 `config/local.secret.yaml` 的 `model` 段：

```yaml
model:
  deployment: remote
  backend: openai-compatible
  name: "<REMOTE_MODEL_NAME>"
  base_url: "<REMOTE_VLLM_BASE_URL>"
  served_model_name: "<REMOTE_MODEL_NAME>"
  api_key_env: "MODEL_API_KEY"
  timeout_seconds: 120
  max_retries: 2
  temperature: 0.0
  max_tokens: 1024
```

同时更新 AIOS 实际配置 `$HOME/AIOS/aios/config/config.yaml` 中的模型 backend、hostname 和服务名。项目适配器通过 AIOS `/query` 调用模型，不能只改项目配置。

接口核验：

```powershell
.\.venv\Scripts\python.exe scripts\env\check_model_endpoint.py --base-url $env:MODEL_BASE_URL --model $env:MODEL_NAME
.\tasks.ps1 check-config
.\tasks.ps1 integration
.\.venv\Scripts\python.exe scripts\evidence\capture_aios_evidence.py
```

正式性能实验必须在相同场景、Prompt、采样次数和验证口径下运行。当前 `scripts/benchmark/run_local_benchmark.py` 的 metadata 固定为本地 Ollama 环境，执行正式实验前必须增加远程环境标识和 `official_result=true` 参数，禁止把本地标识直接改写成正式结果。

正式输出路径：

```text
docs/environment/w01b_remote_vllm_verification_<DATE>.md
docs/experiment_reports/raw/remote_vllm_<DATE>.json
docs/experiment_reports/remote_vllm_results.md
docs/submission/evidence/environment/remote_vllm_<DATE>/
docs/submission/evidence/benchmark/remote_vllm_<DATE>/
```

### 5.3 第三步：W16 文档、录屏与提交

前置条件：W15 完成，功能冻结。

执行：

```powershell
.\tasks.ps1 verify
.\tasks.ps1 api
```

应产出：

| 产出物 | 路径 |
|---|---|
| 架构与设计文档 | `docs/architecture/` |
| AI 使用说明 | `docs/ai_usage/AI_USAGE.md` |
| 演示脚本 | `docs/demo/demo_script.md` |
| 原始录屏和剪辑稿 | `docs/submission/evidence/video/` |
| 最终视频 | 比赛平台要求的独立提交包 |
| 最终提交清单 | `docs/submission/` |

视频至少展示：

1. 环境和服务；
2. 故障注入；
3. 四路证据并行；
4. 三对 Agent 双向交互；
5. 根因诊断及证据引用；
6. 受控修复；
7. 健康、冒烟、回归和压力验证；
8. 串行/并发结果；
9. API 重启后的历史回放。

### 5.4 第四步：W17 国赛扩展

W16 完成后启动。不得在 W15/W16 验收前改动已验证主链路。

## 6. 已知问题与约束

### 6.1 命令执行

- 所有项目命令默认从仓库根目录执行。
- PowerShell 脚本若被策略阻止，先执行：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

- 不要永久使用 `Unrestricted`。
- Windows 项目使用 `.venv`；AIOS 的 WSL 环境使用 `$HOME/venv-aios`，两者不能混用。
- Windows API 依赖 WSL 内的 AIOS 和 Ollama；WSL 重启后需要重新启动服务。

### 6.2 Git 和配置

- 当前本地仓库可能没有项目 `origin`；新电脑必须使用团队正式仓库地址。
- `config/aios.kernel.local.yaml` 含机器相关目录，只是模板；使用前必须按第 3.7 节替换。
- 远程正式配置、API Key、token 和私有地址禁止提交 Git。
- `config/model.remote.yaml.example` 只是字段参考，不是应用可直接加载的完整配置。
- `runs/`、`.venv/`、模型、缓存、日志、正式配置和新增截图/录屏不得提交 Git。

### 6.3 DAG、状态机和可视化

- DAG 和状态机图必须从代码定义和实际 Trace 导出。
- 禁止手工绘制后冒充实际结构。
- 当前 DAG 导出命令：

```powershell
.\.venv\Scripts\python.exe scripts\evidence\render_evidence.py
```

- 当前 DAG 文件：

```text
docs/submission/evidence/workflow/W03_task_dag.json
docs/submission/evidence/workflow/W03_task_dag.mmd
docs/submission/evidence/workflow/W03_task_dag.svg
```

- 状态机独立导出尚未实现，W15/W16 应从 `src/aios_incident/state.py` 自动生成，不能手绘。
- 图表中的时间、消息数、并发批次、根因和证据 ID 必须来自实际对象或 Trace。

### 6.4 远程 vLLM

- 正式模型为 7B AWQ 4bit，不能使用本地 Ollama 数据替代正式实验。
- 只通过 HTTPS、VPN 或受限安全组访问远程服务。
- API Key 只放在本地环境变量，不写入 YAML、命令日志或截图。
- 必须核验 `/v1/models`、`/chat/completions`、AIOS `/query`、文本和严格 JSON。
- 必须记录网络延迟、超时、重试、部署地域和模型参数。
- 当前 `scripts/benchmark/run_local_benchmark.py` 默认标记 `official_result=false`；正式运行前必须参数化环境标识。
- 远程服务不可达时，失败应显式记录，不得回退后仍标记为正式数据。

### 6.5 Docker

- Docker 安装在 WSL2；Windows PATH 不保证存在 Docker 命令。
- `scripts/env/install_docker_wsl.sh` 需要 root，并显式传入 WSL 用户名。
- 加入 `docker` 组后需要新 shell 或 `sg docker`。
- 六个场景只能在隔离容器内执行。
- 场景标准答案不得挂载进容器或写入提交证据。

### 6.6 当前应用限制

- 仪表盘为单机开发部署，没有认证和权限隔离。
- 页面使用 3 秒轮询，不使用 WebSocket。
- API 创建 Incident 后不会自动启动完整 Docker 工作流。
- 完整工作流当前由测试、场景脚本和证据生成脚本执行。
- API、UI 和运行数据仅绑定本机回环地址。

### 6.7 当前缺失

- 远程 vLLM 正式环境与性能结果；
- CPU ECS 部署或正式替代决策；
- W15 安装/演示/复现脚本；
- W07—W12 连续操作录屏；
- 仪表盘成功、失败重试和无修复结果截图；
- 完整演示视频；
- 比赛平台最终模板和视频规格；
- 依赖锁定和许可证清单。

## 7. 证据归档规范

### 7.1 统一目录

```text
docs/submission/evidence/
├─ environment/
├─ terminal/
├─ api/
├─ security/
├─ workflow/
├─ scenarios/
├─ benchmark/
├─ ui/
└─ video/
```

用途：

| 目录 | 内容 |
|---|---|
| `environment/` | 系统、AIOS、Ollama、Docker、网络和配置快照 |
| `terminal/` | 测试、静态检查、模型调用的原始文本和截图 |
| `api/` | HTTP 请求、响应、错误、OpenAPI 和 Trace |
| `security/` | 权限、越权、路径逃逸和失败关闭 |
| `workflow/` | DAG、并行、交互、诊断、修复和验证 |
| `scenarios/` | F1—F6 生命周期、哈希、压力和销毁 |
| `benchmark/` | 串行/并发 CSV、原始摘要和图表 |
| `ui/` | 仪表盘、历史、取消和状态截图 |
| `video/` | 原始录屏、字幕、剪辑稿和最终视频 |

### 7.2 文件命名

统一格式：

```text
<WORK_ORDER>_<TOPIC>_<YYYY-MM-DD>.<EXT>
```

示例：

```text
W05_api_capture_2026-11-22.json
W07_minimal_flow_2026-11-22.txt
W12_scenario_matrix_2026-11-22.png
W13_remote_vllm_2026-12-01.json
W14_dashboard_cancel_2026-12-01.png
```

同一材料同时保存原始数据和渲染件时：

- 原始数据：`.json`、`.jsonl`、`.xml`、`.txt`；
- 可视化：`.svg`；
- 图片或视频：`.png`、`.mp4`。

### 7.3 内容要求

每项证据至少记录：

- 执行日期；
- Git 提交号；
- 命令；
- 运行环境和版本；
- 输入参数；
- 原始结果；
- 是否通过；
- 与对应工单验收项的映射。

禁止：

- 只保存最终截图而没有原始日志；
- 修改原始 JSON；
- 把失败样本删除后只提交成功样本；
- 截入 API Key、私钥、账号或私有地址；
- 将本地 Ollama 结果标记为远程 vLLM 正式结果。

### 7.4 ARTIFACT_LEDGER 更新规则

每次新增或补齐材料后更新 `docs/submission/ARTIFACT_LEDGER.md`：

1. 在“已收集材料”新增一行；
2. 写明材料名称、仓库相对路径、状态和支撑的评分项；
3. 新增对应 Git 提交号；
4. 从“当前缺少”删除已经完成的条目；
5. 不重复登记同一材料；
6. 本地私有媒体应在状态中明确标记“外部归档，不提交 Git”。

每次工单完成还需：

1. 更新 `docs/ai_usage/AI_USAGE.md`；
2. 在 `docs/verification/` 增加或更新验收记录；
3. 更新 `docs/submission/evidence/EVIDENCE_MANIFEST.md`；
4. 运行 `.\tasks.ps1 verify`；
5. 提交代码和文档，保持工作区干净。
