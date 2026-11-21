# AIOS Linux 服务故障诊断修复与回归验证系统交接文档

当前状态：W00、W01A、W02、W03、W04 已完成，准备进入 W05。区域赛提交截止为 2026-12-27，全国初赛提交截止为 2027-05-01。团队为学生 2 人，配备指导教师。

---

## 1. 项目目标

系统面向隔离 Linux 环境中的复合服务故障，完成：

```text
故障上报
  -> 四路证据并行采集
  -> 证据汇合与根因诊断
  -> 受控修复
  -> 健康、回归与压力验证
  -> 成功归档或失败重试
```

核心目标是使用 AIOS 与 AIOS-Agent SDK 实现多智能体协作，满足：

- 不少于 7 类职责不同的 Agent；
- 至少 4 个可并行证据任务；
- 至少 3 对异构 Agent 双向交互；
- 任务依赖由调度器执行；
- 并发相对串行平均提速不低于 20%；
- 修复结果由独立验证器判定。

当前不实现生产宿主机无限制运维。所有修复只允许作用于隔离 Docker 靶机，并使用白名单工具和回滚点。

---

## 2. 冻结技术架构

### 2.1 技术基线

| 项目 | 当前值 |
|---|---|
| Python | 3.10.12 |
| AIOS Kernel | 提交 `292d98f78c835499df18cdb6de6325bba1895862` |
| AIOS 源码位置 | `/home/zhang/AIOS` |
| Cerebrum SDK | `aios-agent-sdk 0.0.3`（已确认替代版本） |
| 正式模型 | 7B AWQ 4bit |
| 正式推理 | 远程 GPU vLLM，OpenAI 兼容接口 |
| 本地调试模型 | Ollama `qwen2:7b-instruct`，Q4_K_M |
| Agent 与靶机 | CPU 环境，本地 WSL2 或远程 CPU ECS |
| 容器运行时 | WSL2 Docker Engine 29.1.3 |

### 2.2 部署结构

```text
Windows 开发终端
  |
  +-- WSL2 Ubuntu 22.04
        |
        +-- AIOS Kernel
        |     http://127.0.0.1:8000
        |
        +-- 本地 Ollama 调试替身
        |     http://127.0.0.1:11434
        |
        +-- Docker 靶机
        |
        +-- 后续接入远程 GPU vLLM
              7B AWQ 4bit / OpenAI 兼容接口
```

### 2.3 两级调度

1. AIOS Kernel 调度单次 LLM、Memory、Storage 和 Tool 系统调用。
2. 项目任务调度器负责复杂任务的 DAG、能力匹配、依赖等待、并发派发和重试。

项目任务调度器不得替代 AIOS 资源接口。

### 2.4 固定 Agent 角色

| Agent | 职责 |
|---|---|
| CoordinatorAgent | 任务规划、证据汇合、根因诊断和最终结论 |
| LogAgent | 日志、错误链和时间线 |
| MetricsAgent | CPU、内存、磁盘、网络和连接指标 |
| ConfigAgent | 配置、权限、端口和配置生效状态 |
| DependencyAgent | 进程、服务、端口和依赖拓扑 |
| RepairAgent | 生成并执行受控修复计划 |
| VerifierAgent | 健康、业务回归和压力验证 |

### 2.5 固定主流程

```text
PLAN
  -> 四个 COLLECT 节点并行
  -> DIAGNOSE
  -> REPAIR
  -> VERIFY
  -> 成功 COMPLETED / 失败返回 REPAIR / 两轮后 FAILED
```

固定双向交互：

1. LogAgent ↔ ConfigAgent；
2. MetricsAgent ↔ DependencyAgent；
3. RepairAgent ↔ VerifierAgent。

---

## 3. 已完成功能与环境

### 3.1 W00 项目基线

已完成：

- 项目目标与赛题约束冻结；
- 技术版本和部署架构记录；
- Git 仓库初始化；
- 未决问题清单；
- AI 使用记录模板；
- 开发规格和 AI 工单纳入仓库。

注意：仓库当前尚无 Git 提交，所有文件仍为未跟踪状态。

### 3.2 WSL2 与 Python

已完成：

- Ubuntu 22.04.5 LTS；
- WSL2 内核 6.18.58.1；
- `/home/zhang/venv-aios` 虚拟环境可激活；
- Python 3.10.12；
- `pip check` 通过，无破损依赖。

关键依赖：

```text
torch 2.6.0+cpu
transformers 5.20.2
sentence-transformers 6.3.0
kubernetes 28.1.0
```

Torch 使用 CPU 版本，仅用于满足 AIOS 模块导入和本地工具依赖，不参与 Ollama 推理。

### 3.3 Cerebrum SDK

已完成：

- `aios-agent-sdk 0.0.3` 安装；
- `cerebrum.llm.apis` 可导入；
- `cerebrum.memory.apis` 可导入；
- 版本检查脚本预期值已改为 0.0.3。

### 3.4 本地模型替身

已完成：

- Ollama 0.40.16；
- 模型 `qwen2:7b-instruct`；
- Q4_K_M GGUF；
- SHA-256 校验通过；
- 普通文本调用；
- JSON 输出；
- OpenAI `/v1/models`；
- OpenAI `/v1/chat/completions`；
- `OLLAMA_NUM_PARALLEL=4`；
- 模型运行于 100% GPU。

实测四请求：

```text
单请求：约 1.629 秒
串行四请求：约 5.303 秒
并发四请求：约 1.706 秒
提速：约 67.8%
```

该结果只用于验证本地逻辑与并发可行性，不能替代正式远程 vLLM 实验。

### 3.5 AIOS Kernel

已完成：

- 锁定源码安装到 `/home/zhang/AIOS`；
- 本地内核配置；
- FastAPI 内核启动；
- `/status` 返回 ok；
- `/core/status` 中 LLM、Storage、Memory、Tool、Scheduler、Factory 全部 active；
- `/query` 成功调用 Ollama；
- 回归请求返回 `W01A_OK`。

当前地址：

```text
http://127.0.0.1:8000
```

### 3.6 Docker

已完成：

- Docker Engine 29.1.3；
- systemd 服务 active；
- storage driver overlayfs；
- cgroup driver systemd；
- 当前用户已加入 docker 组；
- 国内 registry mirror `https://docker.m.daocloud.io`；
- `hello-world` 容器成功运行。

Docker 位于 WSL 内，不在 Windows PATH 提供 Docker Desktop。

---

## 4. 关键文件位置

项目根目录：

```text
aios-linux-incident/
```

### 4.1 规格与基线

| 文件 | 作用 |
|---|---|
| `docs/project_baseline.md` | 项目目标、技术基线和 CPU 服务器决策 |
| `docs/specifications/development_spec_v1.0.md` | 冻结开发规格 |
| `docs/specifications/ai_work_orders_v1.0.md` | W00 至 W17 的开发工单 |
| `docs/open_questions.md` | 剩余未决问题 |
| `docs/ai_usage/AI_USAGE.md` | AI 使用记录 |

### 4.2 环境记录

| 文件 | 作用 |
|---|---|
| `docs/environment/local_environment.md` | 当前完整环境状态 |
| `docs/environment/w01a_verification_2026-11-19.md` | W01A 核验证据 |
| `docs/environment/cerebrum_version_resolution.md` | Cerebrum 版本历史 |
| `docs/environment/concurrency_probe_results.json` | 本地并发原始结果 |

### 4.3 配置

| 文件 | 作用 |
|---|---|
| `config/aios.kernel.local.yaml` | AIOS 本地内核配置 |
| `config/model.local.yaml` | Ollama 本地模型配置 |
| `config/model.remote.yaml.example` | 远程 vLLM 正式配置模板 |
| `config/docker-daemon.json` | Docker 国内 registry mirror |
| `config/ollama/Modelfile.qwen2-7b-instruct` | Qwen2 ChatML 模型模板 |

### 4.4 环境脚本

| 文件 | 作用 |
|---|---|
| `scripts/env/check_windows_gpu.ps1` | Windows、GPU、WSL、Docker 检查 |
| `scripts/env/setup_aios_env.ps1` | Windows Python 3.10 环境 |
| `scripts/env/setup_aios_env.sh` | WSL Python 环境 |
| `scripts/env/install_ollama_wsl.sh` | 镜像安装并校验 Ollama |
| `scripts/env/start_ollama_wsl.sh` | 启动 Ollama |
| `scripts/env/stop_ollama_wsl.sh` | 停止 Ollama |
| `scripts/env/create_ollama_model_wsl.sh` | 导入 GGUF 到 Ollama |
| `scripts/env/activate_local_model.sh` | 设置本地模型参数 |
| `scripts/env/check_model_endpoint.py` | OpenAI 兼容接口检查 |
| `scripts/env/concurrency_probe.py` | 四请求并发测量 |
| `scripts/env/start_aios_wsl.sh` | 启动 AIOS |
| `scripts/env/stop_aios_wsl.sh` | 停止 AIOS |
| `scripts/env/check_aios.py` | AIOS 健康检查 |
| `scripts/env/check_cerebrum.py` | Cerebrum 版本检查 |
| `scripts/env/install_docker_wsl.sh` | Docker Engine 安装 |
| `scripts/env/check_docker_wsl.sh` | Docker daemon 和容器检查 |

### 4.5 当前运行入口

进入 WSL：

```powershell
wsl -d Ubuntu-22.04
```

切换到项目目录后：

```bash
bash scripts/env/start_ollama_wsl.sh
bash scripts/env/start_aios_wsl.sh
bash scripts/env/check_docker_wsl.sh
```

健康检查：

```bash
curl -sS http://127.0.0.1:8000/status
curl -sS http://127.0.0.1:8000/core/status
curl -sS http://127.0.0.1:11434/api/version
```

本地模型参数：

```text
MODEL_BASE_URL=http://127.0.0.1:11434/v1
MODEL_NAME=qwen2:7b-instruct
MODEL_API_KEY=
MODEL_BACKEND=ollama-local
```

---

## 5. 当前问题与限制

### 5.1 尚未接入正式远程 GPU

远程 vLLM 的服务地址、模型名称和认证方式尚未提供。当前使用 Ollama 调试替身，正式性能数据不能使用本地 Ollama 结果代替。

### 5.2 业务功能尚未实现

W02 已创建正式 Python 包和配置加载，W03 已实现结构化数据契约、固定 DAG 和
状态机，W04 已实现经 AIOS 的文本/JSON 模型调用适配。后续调度执行、诊断、
修复、验证和 API 业务功能尚未实现。

实际代码根目录已经冻结为 `src/aios_incident/`。逻辑层目录
`agents/`、`orchestrator/`、`adapters/`、`tools/`、`benchmark/` 和 `ui/`
均是 `src/aios_incident/` 的子包，不得另建平行的顶层代码目录。

### 5.3 CPU ECS 尚未开通

建议在 W07 最小闭环联调前启用：

```text
ecs.e-c1m4.xlarge
4 vCPU / 16 GiB
Ubuntu 22.04
按量付费
```

W01A 不依赖 CPU ECS，W02—W04 已完成，W05 也可以继续本地开发。

### 5.4 Docker 当前会话权限

新 WSL 终端应直接拥有 docker 组权限。旧会话如遇 permission denied，可使用：

```bash
sg docker -c "docker info"
```

### 5.5 本地 AIOS 与 Ollama 不自动随 WSL 重建

AIOS 和 Ollama 使用项目脚本启动。WSL 重启后执行：

```bash
bash scripts/env/start_ollama_wsl.sh
bash scripts/env/start_aios_wsl.sh
```

Docker 由 systemd 自动启动。

### 5.6 Git 基线状态

W00/W01A 与同步文档已形成基线提交 `fb5a0f0`。W02 完成后另建独立提交，
后续每个工单均保留可追溯提交。

### 5.7 桌面工具与 Computer-use 尚未验收

AIOS Tool Manager 已初始化，但桌面 MCP、虚拟机控制器和 OSWorld 环境尚未进行实际任务验收。后续故障场景应优先使用 Docker Linux 靶机。

### 5.8 其他外部确认

仍需确认：

- 正式比赛是否允许远程 AIOS 内核和远程模型服务；
- 比赛提交仓库与视频格式；
- 队员分工和每周投入时间；
- AIOS 上游源码修改登记规则；
- 项目最终开源许可证和第三方许可清单。

---

## 6. 下一步任务

新 Codex 会话应先读取本文件、`docs/specifications/development_spec_v1.0.md` 和 `docs/specifications/ai_work_orders_v1.0.md`，检查 Git 与运行环境后从 W05 继续。不得重做 W00/W01A/W02/W03/W04，不得改变冻结流程，不得将本地 Ollama 数据当作远程 vLLM 正式实验结果。

### W02：仓库脚手架与配置

状态：已完成。

实际产出：

```text
src/aios_incident/
  agents/
  orchestrator/
  adapters/
  tools/
  benchmark/
  ui/
tests/
config/app.example.yaml
config/model.example.yaml
pyproject.toml
tasks.ps1
```

验收：

- Python 包已安装、可导入；
- 配置仅修改 YAML 即可切换本地 Ollama 与远程 vLLM；
- 配置强制使用环境变量引用密钥；
- pytest 21 项通过；
- Ruff 静态检查通过；
- W00/W01A 已先提交基线；
- 验收证据见 `docs/verification/w02_verification_2026-11-19.md`。

### W03：公共数据契约

状态：已完成。

实际产出：

- RunContext；
- TaskNode、TaskDAG；
- AgentCard；
- Evidence；
- Message；
- Diagnosis；
- RepairPlan、RepairResult；
- VerificationResult；
- TraceEvent；
- 任务与工作流状态机。

验收：

- Pydantic 强类型对象与 JSON Schema 校验已实现；
- 固定 DAG 可实例化并通过拓扑排序；
- 自引用、未知依赖和成环 DAG 均被拒绝；
- 非法消息和非法状态迁移均被拒绝；
- 70 项测试通过，Ruff 与格式检查通过；
- 验收证据见 `docs/verification/w03_verification_2026-11-19.md`。

### W04：AIOS 与 LLM 适配器

状态：已完成。

实际产出：

- `src/aios_incident/adapters/aios_client.py`；
- `src/aios_incident/adapters/llm_adapter.py`；
- `tests/unit/test_llm_adapter.py`；
- `tests/integration/test_aios_smoke.py`。

验收：

- 普通文本和严格 JSON 均经 AIOS `/query` 调用；
- 本地 AIOS 文本与 JSON 真实冒烟通过；
- HTTP、超时、连接、协议和模型失败均归一化；
- JSON 不使用代码围栏猜测或自动补字段；
- token usage 区分上报值与估算值；
- 90 项全量测试通过；
- 验收证据见 `docs/verification/w04_verification_2026-11-21.md`。

### W05：故障 API、黑板与 Trace

状态：下一步。

实现：

- 故障上报；
- 状态查询；
- 结果查询和取消；
- Blackboard 产物引用；
- JSONL Trace。

### W06：受控工具网关

实现：

- 工具白名单；
- Agent 权限；
- 路径规范化；
- 超时和输出限制；
- 日志、指标、配置、依赖只读工具；
- 修复占位工具。

### W07：最小核心闭环

实现：

```text
故障上报 -> Agent 分析 -> LLM -> 修复 -> 验证
```

W07 通过前不得开始前端、视频和性能优化。
