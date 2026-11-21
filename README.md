# 基于 AIOS 的 Linux 服务故障诊断、修复与回归验证系统

本仓库用于实现 AIOS 多智能体 Linux 服务故障协同诊断与修复系统。
当前阶段：W06 已完成，下一阶段 W07 最小核心闭环。

## 当前基线

- Python：3.10
- Cerebrum：0.0.3（官方替代版本，已确认）
- 模型：7B AWQ 4bit
- 推理：远程 GPU vLLM，OpenAI 兼容接口
- 本地逻辑调试：WSL2 Ollama + Qwen2 7B Q4_K_M
- CPU 侧：Agent 编排与 Linux 故障靶机
- 本地开发：Windows 11 + RTX 4060 Laptop 8 GB
- 区域赛提交：2026-12-27

## 文档

- `docs/HANDOVER.md`：当前工作交接入口
- `docs/project_baseline.md`：项目基线
- `docs/open_questions.md`：未决问题
- `docs/environment/local_environment.md`：本机环境检查
- `docs/ai_usage/AI_USAGE.md`：AI 使用记录
- `docs/specifications/`：冻结开发规格与开发工单
- `docs/submission/ARTIFACT_LEDGER.md`：比赛评分与提交材料台账
- `docs/verification/`：分阶段验收记录

## W02 最小启动

仓库唯一 Python 包根目录为 `src/aios_incident/`。不得在仓库根目录另建平行的
`agents/`、`orchestrator/`、`adapters/`、`tools/`、`benchmark/` 或 `ui/`。

PowerShell：

```powershell
.\tasks.ps1 setup
.\tasks.ps1 verify
```

配置检查：

```powershell
.\tasks.ps1 check-config
```

也可以直接执行：

```powershell
.\.venv\Scripts\python.exe -m aios_incident --config config/app.example.yaml
```

`config/app.example.yaml` 的 `model` 段用于切换本地 Ollama 与远程 vLLM。
远程认证只填写 `api_key_env` 环境变量名，不填写真实密钥。

## W05 API 启动

```powershell
.\tasks.ps1 api
```

API 默认监听：

```text
http://127.0.0.1:8080
```

OpenAPI 文档：

```text
http://127.0.0.1:8080/docs
```

## W00/W01A

Windows PowerShell：

```powershell
.\scripts\env\check_windows_gpu.ps1
.\scripts\env\setup_aios_env.ps1
```

本机已验证：

- Python 3.10.11；
- 项目虚拟环境 `.venv`；
- NVIDIA RTX 4060 Laptop 8 GB；
- NVIDIA 驱动 566.43、CUDA 12.7。

当前 W01A 核心环境已安装并验证。

最新核验结果：

- WSL2 Ubuntu 22.04：通过；
- 本地 Ollama 0.40.16：通过；
- 模型 `qwen2:7b-instruct`：已导入；
- OpenAI 兼容接口：通过；
- 四路并发探测：通过；
- Cerebrum SDK API：可导入，当前实际版本为 `aios-agent-sdk 0.0.3`；
- AIOS kernel runtime：已安装，`/status` 与 `/query` 通过；
- Docker Engine：已安装，`hello-world` 通过。

WSL2/Ubuntu 安装完成后：

```bash
bash scripts/env/setup_aios_env.sh
```

模型与 AIOS 检查：

```bash
bash scripts/env/start_ollama_wsl.sh
source scripts/env/activate_local_model.sh
bash scripts/env/start_aios_wsl.sh
python scripts/env/check_model_endpoint.py
python scripts/env/check_aios.py --base-url "$AIOS_BASE_URL"
python scripts/env/concurrency_probe.py
```

本地调试模型为 `qwen2:7b-instruct`，基地址为
`http://127.0.0.1:11434/v1`。本地 Ollama 仅用于逻辑调试，最终基线仍为远程
vLLM 上的 7B AWQ 4bit 模型。

Docker 检查：

```bash
bash scripts/env/check_docker_wsl.sh
```

AIOS 与 Ollama 默认运行在 WSL2：

```text
AIOS:   http://127.0.0.1:8000
Ollama: http://127.0.0.1:11434
```

## 安全约束

- 不提交账号、密码、AccessKey、SSH 私钥或模型 API Key。
- 不在 Agent 中执行任意 Shell。
- 不以固定延时模拟并发。
- 不篡改串行与并发测试口径。

