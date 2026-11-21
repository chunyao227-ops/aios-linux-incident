# W07 验收记录

## 状态

已完成。W07 实现提交号在提交后补记于本文件。

## 基线与环境

- 日期：2026-11-21。
- 前置基线：`dd98947`（W06 验收完成）。
- Python：3.10.11。
- AIOS：`http://127.0.0.1:8000`。
- 本地模型：`qwen2:7b-instruct`。
- 场景存储：临时文件沙箱和内存模拟故障状态。

## 最小链路

```text
RunContext
  -> CoordinatorAgent 生成分析任务
  -> LogAgent 通过受控网关读取日志
  -> AIOS/LLM 生成结构化根因与修复建议
  -> RepairAgent 生成修复计划和回滚方案
  -> 模拟修复执行
  -> VerifierAgent 执行四项结构化检查
  -> SUCCESS 或 UNRESOLVED
  -> FinalReport
```

## 实现范围

### Agent 实现

- `CoordinatorAgent`：最小分析任务、LLM 诊断和根因候选。
- `LogAgent`：经 W06 ToolGateway 获取日志证据。
- `RepairAgent`：生成修复计划、回滚方案并委托模拟执行器。
- `VerifierAgent`：基于结构化检查判定结果。

实际代码均位于冻结包路径：

```text
src/aios_incident/agents/
```

未创建平行顶层 `agents/` 目录。

### CoordinatorAgent

- 校验 RunContext 的 Incident/Run 范围。
- 创建单个日志分析任务。
- 固定输入证据，不向模型提供未采集事实。
- 使用严格 JSON Schema 接收根因、置信度和修复建议。
- 模型不负责宣布最终成功。

### LogAgent

- 只能通过 ToolGateway 读取日志。
- 使用 Incident `read_paths` 和 sandbox 边界。
- 返回结构化 Evidence。
- Evidence 写入 Blackboard。

### RepairAgent

- 修复计划绑定根因和证据。
- 计划包含动作、前置条件、预期效果、风险和回滚步骤。
- 默认执行器只修改内存模拟状态。
- 不调用宿主机 Shell、文件删除、权限修改或真实服务写入。

### VerifierAgent

包含四项检查：

- 进程和端口；
- 服务健康；
- 冒烟测试；
- 回归测试。

只有所有检查通过才产生 `SUCCESS`。修复失败或验证失败产生 `UNRESOLVED`。

### FinalReport

最终报告包含：

- Incident ID 和 Run ID；
- 最终状态；
- 根因候选；
- 证据；
- 修复动作；
- 回滚信息；
- 验证结果；
- 阶段耗时；
- Agent 调用摘要；
- Trace 路径。

## Trace 覆盖

最小闭环产生以下关键事件：

```text
MINIMAL_FLOW_STARTED
MINIMAL_PLAN_CREATED
TOOL_CALL_STARTED
TOOL_CALL_FINISHED
LOG_EVIDENCE_COLLECTED
DIAGNOSIS_COMPLETED
REPAIR_PLAN_CREATED
REPAIR_FINISHED
VERIFICATION_FINISHED
FINAL_REPORT_CREATED
MINIMAL_FLOW_FINISHED
```

工具调用 Trace 仍由 W06 网关生成，阶段 Trace 由 W07 运行器生成。

## 执行记录

### 统一验证

```powershell
.\tasks.ps1 verify
```

结果：

```text
All checks passed!
42 files already formatted
128 passed, 2 skipped in 2.61s
configuration valid: aios-linux-incident
```

两个跳过项分别是：

- W04 真实 AIOS 冒烟；
- W07 真实 AIOS 最小闭环。

### 全量与真实 AIOS

```powershell
$env:RUN_AIOS_INTEGRATION='1'
.\.venv\Scripts\python.exe -m pytest -o addopts='' -W error
```

结果：

```text
130 passed in 14.90s
```

包含：

- W07 成功路径；
- W07 修复失败路径；
- W07 真实本地 AIOS 模型闭环；
- W04/W05/W06 全部回归。

### 编译、依赖与安全

- `compileall`：通过。
- `pip check`：`No broken requirements found.`
- 源码执行原语扫描：未发现 Shell、删除、格式化、sudo 或权限修改。

## 验收项对照

| W07 验收要求 | 结果 |
|---|---|
| 接收故障目标 | 通过 |
| Coordinator 生成分析任务 | 通过 |
| LogAgent 获取证据 | 通过，受控工具调用 |
| LLM 形成诊断 | 通过，模拟和真实 AIOS 均通过 |
| RepairAgent 执行受控模拟修复 | 通过 |
| VerifierAgent 返回验证结果 | 通过 |
| 保存完整 Trace | 通过，工具与阶段事件齐全 |
| 保存最终报告 | 通过，JSON 序列化往返通过 |
| 成功路径 | 通过，最终 `SUCCESS` |
| 失败路径 | 通过，最终 `UNRESOLVED` |
| 不跳过验证 | 通过，修复后始终执行验证 |
| 修复失败不得返回成功 | 通过 |
| 每个阶段均有 Trace | 通过 |

## 当前限制

- 修复是内存模拟，不修改真实 Docker 靶机。
- 只执行一次最小修复和验证。
- 不实现四路并行。
- 不实现三对 Agent 消息总线交互。
- 真实 Docker 场景、多轮修复反馈和并行调度属于 W08 以后。

## 提交材料状态

- 最小闭环：`src/aios_incident/orchestrator/minimal_flow.py`。
- Agent 实现：`src/aios_incident/agents/`。
- 端到端测试：`tests/e2e/test_minimal_flow.py`。
- 演示说明：`docs/demo/minimal_flow.md`。
- 命令和结果：本文件。
- 闭环 Trace 和最终报告截图：尚未制作。

