# W09 验收记录

## 状态

已完成。W09 实现提交：`0d1363a`。

## 基线与环境

- 日期：2026-11-21。
- 前置基线：`a54ee1d`（W08 验收完成）。
- W09 实现提交：`0d1363a`。
- Python：3.10.11。
- 消息存储：内存消息表、Blackboard 引用和 JSONL Trace。
- 外部模型和 Docker：本工单不依赖。

## 消息契约

支持以下消息类型：

- ASSIGN；
- RESULT；
- QUESTION；
- REPLY；
- QUERY；
- RESPONSE；
- REVIEW；
- FAILURE；
- VERIFIED；
- HANDOFF；
- FEEDBACK；
- ABORT。

每条消息强制包含：

- Incident ID；
- Task ID；
- 发送 Agent；
- 接收 Agent；
- correlation_id；
- 消息内容；
- 时间戳。

REPLY/RESPONSE 必须引用合法 query；QUESTION/QUERY 不得引用回复；同 Agent
不得向自身发送用于满足交互指标的消息。

## InteractionBus

`src/aios_incident/orchestrator/interaction_bus.py` 已实现：

- Agent 注册和在线状态；
- Agent 离线检测；
- QUERY/QUESTION 请求；
- REPLY/RESPONSE 响应；
- correlation_id 绑定；
- reply_to 业务引用验证；
- 同一查询禁止重复 correlation；
- 显式响应等待超时；
- 超时 Trace；
- 发送失败 Trace；
- 每条消息 SENT/RECEIVED 两条 Trace；
- 消息写入 Blackboard；
- 有向消息图和双向边计数。

## 三对固定交互

CoordinatorAgent 现在可以基于真实结构化数据执行：

### I1：LogAgent ↔ ConfigAgent

- 日志证据请求配置核对；
- 配置 Agent 返回配置摘要；
- 配置 Agent 反向请求日志时间线；
- 日志 Agent 返回结构化日志证据。

### I2：MetricsAgent ↔ DependencyAgent

- 指标证据请求进程和端口核对；
- 依赖 Agent 返回依赖证据；
- 依赖 Agent 反向请求指标趋势；
- 指标 Agent 返回负载和内存摘要。

### I3：RepairAgent ↔ VerifierAgent

- RepairAgent 发送 HANDOFF；
- 验证失败发送 FEEDBACK；
- 验证成功发送 VERIFIED 和最终 RESULT；
- 消息共享同一 correlation_id。

## 消息图

成功场景共生成 11 条业务消息：

- I1：4 条；
- I2：4 条；
- I3：3 条。

消息图产生 6 条有向边和 3 对双向边：

```text
ConfigAgent <-> LogAgent
DependencyAgent <-> MetricsAgent
RepairAgent <-> VerifierAgent
```

11 条消息均写入 Blackboard 和同一 Incident 的 JSONL Trace。

## 执行记录

### 统一验证

```powershell
.\tasks.ps1 verify
```

结果：

```text
All checks passed!
50 files already formatted
141 passed, 2 skipped in 2.94s
configuration valid: aios-linux-incident
```

### 全量与真实 AIOS

```powershell
$env:RUN_AIOS_INTEGRATION='1'
.\.venv\Scripts\python.exe -m pytest -o addopts='' -W error
```

结果：

```text
143 passed in 10.89s
```

W09 新增 8 项测试：

- 三对双向交互矩阵；
- 每条查询存在响应；
- correlation 和 reply_to 配对；
- 验证失败反馈路径；
- QUERY/RESPONSE；
- 响应超时；
- Agent 离线发送失败；
- REVIEW/FAILURE/VERIFIED 消息类型。

### 编译、依赖与安全

- `compileall`：通过。
- `pip check`：`No broken requirements found.`
- 源码执行原语扫描：未发现 Shell、删除、格式化、sudo 或权限修改。
- W04、W07、W08 回归通过。

## 验收项对照

| W09 验收要求 | 结果 |
|---|---|
| QUERY/RESPONSE 等消息 | 通过 |
| LogAgent 与 ConfigAgent 双向证据查询 | 通过 |
| MetricsAgent 与 DependencyAgent 双向核对 | 通过 |
| RepairAgent 与 VerifierAgent 修复验证反馈 | 通过 |
| 消息图 | 通过 |
| 至少三条双向边 | 通过，实际 3 条 |
| 禁止自消息 | 通过 |
| 查询有响应或明确超时 | 通过 |
| task_id 和 correlation_id 绑定 | 通过 |
| Agent 断开时发送失败记录 | 通过 |
| 消息存入 Blackboard | 通过 |

## 当前限制

- 消息内容由结构化证据生成，但尚未交给 W10 做证据融合。
- 消息总线目前从 Coordinator 显式调用，完整调度生命周期集成由后续编排完成。
- Docker 场景和多轮修复反馈仍属后续工单。

## 提交材料状态

- 总线：`src/aios_incident/orchestrator/interaction_bus.py`。
- 三对交互编排：`src/aios_incident/agents/coordinator_agent.py`。
- 交互测试：`tests/integration/test_interaction_matrix.py`。
- 命令和结果：本文件。
- 消息图和时间线截图：尚未制作。

