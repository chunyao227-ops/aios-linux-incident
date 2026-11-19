# W01A 实际核验记录

## 检查日期

2026-11-19

## 第 1 项：Cerebrum 与 AIOS 环境

### 已验证

- WSL2 Ubuntu 22.04 运行正常。
- Python 3.10.12 可执行。
- `/home/zhang/venv-aios` 可激活。
- `aios-agent-sdk 0.0.3` 已安装。
- `pip check` 未发现破损依赖。
- `cerebrum.llm.apis.llm_chat` 可导入。
- `cerebrum.memory.apis.create_memory` 可导入。

### 版本确认

- 团队确认 `aios-agent-sdk 0.0.3` 为本项目采用版本。
- W01A 原 0.4.1 版本阻塞项关闭。

### AIOS Kernel

- 已安装锁定源码提交 `292d98f78c835499df18cdb6de6325bba1895862`。
- AIOS 运行于 `/home/zhang/AIOS`。
- FastAPI 服务：`http://127.0.0.1:8000`。
- `/status`：ok。
- `/core/status`：全部组件 active。
- `/query`：经 Ollama 返回 `AIOS_OK`。
- 重启后回归：`/query` 返回 `W01A_OK`。

## 第 2 项：WSL Ollama 作为本地替身

### 已完成

- Ollama 0.40.16 安装到 `$HOME/.local/lib/ollama`。
- 服务运行于 `http://127.0.0.1:11434`。
- 模型 `qwen2:7b-instruct` 已导入。
- 普通文本调用通过。
- JSON 输出通过。
- OpenAI `/v1/models` 和 `/v1/chat/completions` 通过。
- 三项参数已补齐。

## 第 3 项：Ollama 安装与模型获取

### 安装

- 官方源和 GitHub 直连在 WSL 中受 DNS 超时影响。
- 使用 `gh-proxy.com` 下载官方 Ollama v0.40.16 发布包。
- 下载文件 SHA-256 与官方清单一致。
- 未使用系统目录 root 权限，安装到用户目录。

### 模型

- Ollama 官方模型仓库拉取在约 1 GB 时因 Cloudflare DNS 超时失败。
- 切换 ModelScope 下载 `qwen2-7b-instruct-q4_k_m.gguf`。
- 模型大小：4,683,071,264 字节。
- SHA-256：`ed93dfc426f926451fa3ec7f996a787a31cfd97e55d7769568fbffc2d69861c2`。
- 通过自定义 ChatML Modelfile 导入 Ollama。

## 并发结果

```json
{
  "model": "qwen2:7b-instruct",
  "backend": "ollama-local",
  "one_request": {
    "elapsed_sec": 1.6289414280008714
  },
  "serial_4_total_sec": 5.30290167199928,
  "parallel_4_total_sec": 1.7059310859995094,
  "parallel_speedup": 0.6783023349259377,
  "errors": []
}
```

## 当前结论

- 本地 Ollama 替身：完成。
- 模型参数：完成。
- 模型并联能力：验证通过。
- Cerebrum 0.0.3：完成。
- AIOS kernel：完成。
- Docker Engine 29.1.3：完成。
- `hello-world` 容器：通过。
