# 本地环境检查记录

## 检查日期

2026-11-18

## 硬件与驱动

- 机型：HP Victus by HP Gaming Laptop 16-r1xxx。
- CPU：Intel Core i7-14650HX。
- 内存：16,869,285,888 字节，约 16 GiB。
- GPU：NVIDIA GeForce RTX 4060 Laptop GPU。
- 显存：8188 MiB。
- NVIDIA 驱动：566.43。
- CUDA 版本：12.7。
- 当前 GPU 占用：检查时为 10 MiB，GPU 利用率 0%。
- Git：2.55.0.windows.5。
- 磁盘：C 盘可用约 82.6 GiB，D 盘可用约 612.8 GiB。

## 当前阻塞项

### WSL2

- WSL2 已安装并通过验证。
- 发行版：Ubuntu 22.04.5 LTS。
- 内核：6.18.58.1-microsoft-standard-WSL2。
- `/home/zhang/Cerebrum` 已存在。
- `/home/zhang/venv-aios` 可激活，Python 为 3.10.12。

### Docker

- WSL2 内已安装 Docker Engine 29.1.3。
- Docker daemon 由 systemd 管理，状态 active。
- 当前用户 `zhang` 已加入 `docker` 组。
- Storage driver：overlayfs。
- Cgroup driver：systemd。
- Registry mirror：`https://docker.m.daocloud.io`。
- `hello-world` 已成功拉取并运行。

### Python

- 当前 `python` 为 3.9.7。
- 已通过 WinGet 安装 Python 3.10.11 到用户目录。
- 已创建项目隔离环境：`.venv`。
- 已验证 `.venv` Python 版本为 3.10.11。

### Cerebrum 版本

- 原计划版本 0.4.1 未在官方渠道发布。
- 团队已确认替代版本为 `aios-agent-sdk 0.0.3`。
- GitHub 当前 `main` 包版本为 0.0.3。
- `/home/zhang/venv-aios` 中已安装 `aios-agent-sdk 0.0.3`。
- `pip check` 返回 `No broken requirements found`。
- `cerebrum.llm.apis` 和 `cerebrum.memory.apis` 可成功导入。

### AIOS Kernel

- 已安装锁定源码提交 `292d98f78c835499df18cdb6de6325bba1895862` 到 `/home/zhang/AIOS`。
- AIOS FastAPI kernel 已启动于 `http://127.0.0.1:8000`。
- `/status` 返回 ok。
- `/core/status` 中所有组件为 active。
- `/query` 经 Ollama 返回 `AIOS_OK`。

### 远程模型

- 已确定使用远程 GPU vLLM、7B AWQ 4bit，但服务地址尚未提供。
- 本地使用 Ollama 作为 OpenAI 兼容替身，完成逻辑调试。
- Ollama 版本：0.40.16。
- 安装位置：`$HOME/.local/lib/ollama`。
- 模型：`qwen2:7b-instruct`。
- GGUF：`qwen2-7b-instruct-q4_k_m.gguf`。
- 模型 SHA-256：`ed93dfc426f926451fa3ec7f996a787a31cfd97e55d7769568fbffc2d69861c2`。
- 本地 OpenAI 基地址：`http://127.0.0.1:11434/v1`。
- 本地 API Key：不需要，设置为空。

## 已生成脚本

- `scripts/env/check_windows_gpu.ps1`：Windows、GPU、WSL、Docker、Python 和磁盘检查。
- `scripts/env/setup_aios_env.ps1`：Windows Conda 环境创建。
- `scripts/env/setup_aios_env.sh`：WSL2/Ubuntu 虚拟环境创建。
- `scripts/env/check_aios.py`：AIOS 健康检查。
- `scripts/env/check_model_endpoint.py`：远程 vLLM 模型接口检查。
- `scripts/env/concurrency_probe.py`：单请求、串行四请求和并发四请求测量。
- `scripts/env/install_ollama_wsl.sh`：安装并校验 Ollama。
- `scripts/env/start_ollama_wsl.sh` 与 `stop_ollama_wsl.sh`：控制本地 Ollama。
- `scripts/env/create_ollama_model_wsl.sh`：从 GGUF 导入 Ollama 模型。
- `scripts/env/activate_local_model.sh`：设置本地模型环境变量。
- `scripts/env/start_aios_wsl.sh` 与 `stop_aios_wsl.sh`：控制 AIOS kernel。
- `scripts/env/install_docker_wsl.sh`：安装并配置 Docker Engine。
- `scripts/env/check_docker_wsl.sh`：验证 Docker daemon 与容器。

## W01A 当前状态

| 检查项 | 状态 |
|---|---|
| 独立 GPU | 通过 |
| NVIDIA 驱动与 CUDA | 通过 |
| Git | 通过 |
| Python 3.10 | 通过，项目 `.venv` |
| WSL2 Ubuntu 22.04 | 通过 |
| Docker | 通过 |
| Cerebrum SDK API | 通过，实际 0.0.3 |
| Cerebrum 0.0.3 | 通过 |
| AIOS Kernel runtime | 通过 |
| 本地 Ollama | 通过 |
| 本地模型调用 | 通过 |
| JSON 输出 | 通过 |
| 四请求并发探测 | 通过 |
| 远程 vLLM | 待服务地址，不阻塞本地调试 |

## 运行依赖

- Torch：2.6.0+cpu。
- Transformers：5.20.2。
- sentence-transformers：6.3.0。
- Kubernetes client：28.1.0，用于满足 ChromaDB 依赖并避免 dateutil 冲突。
- Python `pip check`：No broken requirements found。

## 下一步

1. 启动本地 Ollama 并加载 `qwen2:7b-instruct`。
2. 启动 AIOS kernel。
3. 运行 `check_model_endpoint.py`、`check_aios.py` 和 `concurrency_probe.py`。
4. 新开 WSL shell 后可直接使用 `docker`；当前会话可通过 `sg docker -c ...` 使用。

## 本地并发测试结果

- 单请求：约 1.629 秒。
- 串行四请求：约 5.303 秒。
- 并发四请求：约 1.706 秒。
- 实测提速：约 67.8%。
- Ollama 并行槽：4。
- 说明：本地 Ollama 结果只用于验证逻辑与并发可行性，不能替代远程 vLLM 的最终验收数据。
- 服务配置：`OLLAMA_NUM_PARALLEL=4`、`OLLAMA_MAX_LOADED_MODELS=1`。
- 模型运行位置：100% GPU。

## 模型参数

```text
MODEL_BASE_URL=http://127.0.0.1:11434/v1
MODEL_NAME=qwen2:7b-instruct
MODEL_API_KEY=
MODEL_BACKEND=ollama-local
```

