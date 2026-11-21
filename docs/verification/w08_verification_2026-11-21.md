# W08 验收记录

## 状态

已完成。W08 实现提交：`ce0666e`。

## 基线与环境

- 日期：2026-11-21。
- 前置基线：`11ab580`（W07 验收完成）。
- W08 实现提交：`ce0666e`。
- Python：3.10.11。
- 并发实现：线程池。
- 最大并发：4。
- 采集后端：W06 沙箱只读工具。

## 实现范围

### Planner

`src/aios_incident/orchestrator/planner.py` 已实现：

- 冻结 Agent 能力矩阵；
- 固定唯一 Agent ID；
- 节点唯一性校验；
- 依赖引用完整性；
- 无环 DAG 校验；
- DAG 能力匹配校验；
- 最低负载 Agent 选择；
- 同负载时按 Agent ID 固定排序；
- Agent 占用和释放。

Agent ID 与各 Agent 实现保持一致：

```text
coordinator-01
log-agent-01
metrics-agent-01
config-agent-01
dependency-agent-01
repair-agent-01
verifier-agent-01
```

### Scheduler

`src/aios_incident/orchestrator/scheduler.py` 已实现：

- 动态 READY 集合计算；
- N0 完成后一次性派发 N1—N4；
- 同一派发批次 ID；
- 线程池真实并发；
- 任务 ASSIGNED、RUNNING、VERIFYING 和终态迁移；
- N1—N4 全部成功后才将 N5 置为 READY；
- 可配置 N5 执行器继续派发 DIAGNOSE；
- 单任务有限重试；
- 重试耗尽进入 FAILED_FINAL；
- 任一采集任务最终失败后阻止下游；
- 调度事件严格单调递增时间戳；
- 已启动任务在单路失败后仍完成收尾。

### 新增采集 Agent

- `MetricsAgent`：资源指标证据。
- `ConfigAgent`：配置证据。
- `DependencyAgent`：进程和端口证据。
- `LogAgent`：复用原日志证据逻辑。

四个 Agent 均通过 W06 ToolGateway 和 Blackboard。

## 执行记录

### 统一验证

```powershell
.\tasks.ps1 verify
```

结果：

```text
All checks passed!
48 files already formatted
133 passed, 2 skipped in 3.24s
configuration valid: aios-linux-incident
```

两个跳过项分别是 W04 和 W07 的真实 AIOS 测试。

### 全量与真实 AIOS

```powershell
$env:RUN_AIOS_INTEGRATION='1'
.\.venv\Scripts\python.exe -m pytest -o addopts='' -W error
```

结果：

```text
135 passed in 9.97s
```

W08 新增测试 5 项：

- DAG 能力校验和 Agent 选择；
- 四路同一批次并发派发；
- 诊断门控晚于四路完成；
- 可重试失败恢复；
- 重试耗尽阻断诊断。

### 编译、依赖与安全

- `compileall`：通过。
- `pip check`：`No broken requirements found.`
- 源码执行原语扫描：未发现 Shell、删除、格式化、sudo 或权限修改。
- W04、W06、W07 回归通过。

## 验收项对照

| W08 验收要求 | 结果 |
|---|---|
| DAG 唯一性 | 通过 |
| 引用完整性 | 通过 |
| 无环校验 | 通过 |
| 能力匹配 | 通过 |
| READY 集合计算 | 通过 |
| N0 后派发四路采集 | 通过 |
| 四路并发上限不低于 4 | 通过 |
| 四路处于同一调度窗口 | 通过，使用相同 dispatch batch ID |
| 采集完成前不激活 DIAGNOSE | 通过 |
| DIAGNOSE 开始晚于四路完成 | 通过 |
| 单路失败按策略重试 | 通过 |
| 重试耗尽终止 | 通过 |
| 不以串行冒充并发 | 通过，线程屏障测试和同一派发批次 |

## 当前限制

- W08 完成调度器与四路采集；N5 之后完整诊断融合属于 W10。
- 三对双向 Agent 交互属于 W09。
- 当前调度测试使用文件沙箱，不连接真实 Docker 靶机。
- 调度器提供任务执行边界，后续将其接入完整 API 运行生命周期。

## 提交材料状态

- Planner：`src/aios_incident/orchestrator/planner.py`。
- Scheduler：`src/aios_incident/orchestrator/scheduler.py`。
- 四类采集 Agent：`src/aios_incident/agents/`。
- 并发测试：`tests/integration/test_parallel_dispatch.py`。
- 命令和结果：本文件。
- 并发时间线和调度截图：尚未制作。

