# 本地提交证据索引

## 范围

- 采集日期：2026-11-22。
- 前置代码基线：`f166f14`。
- 环境：Windows 11 + WSL2 Ubuntu 22.04 + Python 3.10.11。
- AIOS、Ollama、Docker 和 FastAPI 均使用本地实际运行环境。
- 本地 Ollama 数据只用于开发验证，不代表正式远程 vLLM 结果。

## 材料清单

| 工单 | 已保存材料 | 主要文件 |
|---|---|---|
| 环境 | AIOS、Ollama、Docker、API、配置哈希 | `environment/local_runtime_snapshot.json`、`.md` |
| W02 | 统一回归截图和文本 | `terminal/W02_verify.png`、`.txt` |
| W03 | 数据契约与状态机测试、实际 DAG | `terminal/W03_contracts.txt`、`workflow/W03_task_dag.*` |
| W04 | AIOS 文本与 JSON 响应、冒烟测试 | `terminal/W04_aios_responses.*`、`W04_aios_smoke.txt` |
| W05 | API 请求、404、OpenAPI、Trace、运行元数据 | `api/W05_*` |
| W06 | 权限、越权、路径逃逸、限制和失败关闭测试 | `security/W06_*` |
| W07 | 真实模型成功/失败 Trace 和最终报告 | `workflow/W07_*` |
| W08 | 四路批次、事件时间线、Trace 和门控摘要 | `workflow/W08_*` |
| W09 | 三对双向消息图、11 条消息和 Trace | `workflow/W09_*` |
| W10 | 四类证据链、融合结果和 Trace | `workflow/W10_*` |
| W11 | 两轮失败、回滚和危险计划拒绝 | `workflow/W11_*` |
| W12 | 六场景逐步生命周期、哈希和销毁结果 | `scenarios/W12_*` |
| W13 | 串行/并发 CSV、耗时图和提速图 | `benchmark/W13_*` |
| W14 | 历史运行、取消状态和真实基准面板截图 | `ui/dashboard_*`、`W14_history_api.json` |
| 汇总 | 专项测试数量和状态总览 | `TEST_EVIDENCE.md`、`W03_W12_test_matrix.*` |

## 证据生成入口

测试原始日志和 JUnit：

```powershell
.\tasks.ps1 verify
.\.venv\Scripts\python.exe -m pytest -o addopts='' -W error tests\... -v
```

API 证据需要先启动服务：

```powershell
.\tasks.ps1 api
```

在另一个终端执行：

```powershell
.\.venv\Scripts\python.exe scripts\evidence\capture_environment_evidence.py
.\.venv\Scripts\python.exe scripts\evidence\capture_api_evidence.py
```

真实 AIOS 和 W07 证据：

```powershell
.\.venv\Scripts\python.exe scripts\evidence\capture_aios_evidence.py
.\.venv\Scripts\python.exe scripts\evidence\capture_minimal_flow_evidence.py
```

六场景生命周期证据：

```powershell
.\.venv\Scripts\python.exe scripts\evidence\capture_scenario_evidence.py
```

图表和测试矩阵：

```powershell
.\.venv\Scripts\python.exe scripts\evidence\render_evidence.py
```

## 数据边界

- 六场景生命周期文件不保存场景标准答案。
- 环境快照不包含账号、密码、API Key 或 SSH 私钥。
- SVG 和 PNG 来自实际 API、Trace、测试结果或 W13 原始 JSON。
- W07 本地失败路径用于验证失败关闭，不表示真实生产事故。
- 正式比赛性能结论仍需远程 7B AWQ 4bit vLLM 重新测量。
