# W13 验收记录

## 状态

已完成本地开发基准。W13 实现提交号在提交后补记于本文件。

## 基线与环境

- 日期：2026-11-22。
- 前置基线：`16addbc`（W12 验收完成）。
- Python：3.10.11。
- 环境：WSL2 + 本地 Ollama 开发环境。
- 模型：`qwen2:7b-instruct`。
- 后端：OpenAI 兼容本地接口，经由 AIOS。
- 场景：F1—F6。
- 每场景每模式：1 次预热 + 5 次有效测量。

## 公平性控制

- 串行和并发使用同一场景、同一容器镜像和同一数据；
- 使用相同四类采集 Prompt 版本；
- 使用相同模型、温度和最大输出 token；
- 使用相同修复、健康、冒烟、回归和压力验证；
- 每组均先预热一次；
- 每次测量从场景重置并注入完成后开始计时；
- 在最终验证和报告生成后停止计时；
- 无效尝试保留在原始数据中，但不进入统计；
- 本轮无自动补跑失败尝试。

## 实现范围

### serial.py

- 按 N1 → N2 → N3 → N4 执行采集；
- 完成 N5 诊断、N6 修复、N7 验证；
- 记录总耗时、采集耗时、模型耗时、工具耗时、token 和错误。

### parallel.py

- 使用四线程同时派发 N1—N4；
- 保持相同 DAG、Prompt、模型参数和验证标准；
- N5—N7 仍按依赖顺序执行。

### metrics.py

- 预热与无效样本排除；
- 每场景每模式均值、中位数和 p95；
- 每场景中位数提速；
- 平均提速和最低提速；
- 正确性保持检查；
- token、工具调用、重试和越权操作汇总。

### report.py

- 输出完整原始 JSON；
- 输出 Markdown 汇总表；
- 原始数据保留模型/工具耗时、token、Trace 和失败样本。

## 实验结果

| 场景 | 串行中位数 | 并发中位数 | 中位数提速 | 串行正确率 | 并发正确率 |
|---|---:|---:|---:|---:|---:|
| F1 | 16.7680s | 14.1205s | 15.79% | 100% | 100% |
| F2 | 15.9211s | 9.6153s | 39.61% | 100% | 100% |
| F3 | 16.7052s | 9.4112s | 43.66% | 100% | 100% |
| F4 | 15.8994s | 10.9167s | 31.34% | 100% | 100% |
| F5 | 13.9415s | 8.4939s | 39.07% | 100% | 100% |
| F6 | 16.3902s | 6.8775s | 58.04% | 100% | 100% |

总体：

- 平均提速：**37.92%**；
- 最低单场景提速：15.79%；
- 并发正确性不低于串行：**是**；
- 越权操作：**0**；
- 无效补跑样本：**0**。

区域赛验收要求为平均提速不低于 20%，本轮本地开发结果满足。

## 执行记录

### 默认回归

```powershell
.\tasks.ps1 verify
```

结果：

```text
All checks passed!
62 files already formatted
158 passed, 8 skipped in 2.30s
configuration valid: aios-linux-incident
```

### 本地性能实验

```powershell
.\tasks.ps1 benchmark
```

结果：

```text
average_speedup=0.3792
minimum_speedup=0.1579
correctness_preserved=True
```

运行次数：

- 6 场景；
- 2 模式；
- 每模式 1 次预热和 5 次有效测量；
- 共 72 次流程。

### 全量真实环境回归

```powershell
$env:RUN_AIOS_INTEGRATION='1'
$env:RUN_DOCKER_SCENARIOS='1'
.\.venv\Scripts\python.exe -m pytest -o addopts='' -W error
```

结果：

```text
166 passed in 93.60s (0:01:33)
```

## 验收项对照

| W13 验收要求 | 结果 |
|---|---|
| 每场景预热一次 | 通过 |
| 每场景每模式五次有效测量 | 通过 |
| 记录开始和结束时间 | 通过 |
| 记录模型耗时 | 通过 |
| 记录工具耗时 | 通过 |
| 记录 token 和错误 | 通过 |
| 计算场景中位数 | 通过 |
| 计算总体平均提速 | 通过 |
| 平均提速不低于 20% | 通过，本地 37.92% |
| 正确性不低于串行 | 通过 |
| 输出消息完整性和越权统计 | 通过，消息完整，越权 0 |
| 原始数据与汇总表均存在 | 通过 |

## 数据范围限制

本轮数据来自本地 Ollama 开发替身，只用于开发验证，不是正式远程 vLLM 性能结论。
正式提交前必须使用远程 7B AWQ 4bit vLLM 按相同口径重新执行，并单独保存环境、
网络、模型参数和原始数据。

## 当前限制

- F1 单场景提速低于 20%，但总体平均提速满足验收要求。
- 本地模型和容器为开发环境，不代表远程 GPU 吞吐。
- 正式比赛前仍需 W01B 远程环境复测。

## 提交材料状态

- 串行运行器：`src/aios_incident/benchmark/serial.py`。
- 并发运行器：`src/aios_incident/benchmark/parallel.py`。
- 统计模块：`src/aios_incident/benchmark/metrics.py`。
- 报告模块：`src/aios_incident/benchmark/report.py`。
- 原始数据：`docs/experiment_reports/raw/local_ollama_2026-11-22.json`。
- 汇总表：`docs/experiment_reports/benchmark_results.md`。
- 图表和正式录屏：尚未制作。

