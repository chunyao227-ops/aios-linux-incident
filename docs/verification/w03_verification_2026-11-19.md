# W03 验收记录

## 状态

已完成。W03 实现提交：`301b7ba`。

## 基线与环境

- 日期：2026-11-19。
- 前置基线：`a6e66a5`（W02 验收完成）。
- W03 实现提交：`301b7ba`。
- Python：3.10.11。
- Pydantic：2.14.4。
- jsonschema：4.26.0。

## 实现范围

### 公共数据契约

| 对象 | 主要约束 |
|---|---|
| `RunContext` | 故障目标、允许范围、预算、成功条件和工作流状态 |
| `TaskNode` | 唯一任务 ID、能力、依赖、尝试次数、期限、约束和状态 |
| `TaskDAG` | 唯一节点、引用完整、禁止自引用和成环、确定性拓扑排序 |
| `AgentCard` | 能力集合、心跳、并发数和当前负载 |
| `Evidence` | 四类证据、来源、事实、置信度，对象不可变 |
| `Message` | 七类消息、不同 Agent、REPLY 引用和证据引用 |
| `Diagnosis` | 根因候选、证据绑定、冲突证据和修复约束 |
| `RepairPlan` | 有序动作、前置条件、风险、回滚和超时 |
| `RepairResult` | 动作结果、回滚状态、错误和时间顺序 |
| `VerificationResult` | 检查项、失败原因、通过状态和时间顺序 |
| `TraceEvent` | 事件、状态、耗时、token、工具调用和重试信息 |

### 状态机

- 实现 `TaskStatus` 的 10 个状态。
- 实现 `WorkflowStatus` 的 7 个状态。
- `RUNNING` 不能跳过 `VERIFYING` 直接成功。
- `CREATED` 和 `BLOCKED` 的 READY 迁移强制检查依赖是否满足。
- `FAILED_RETRYABLE` 的后续迁移强制检查是否仍有重试次数。
- 所有未声明迁移均抛出 `InvalidStateTransitionError`。
- 工作流成功终态使用规格定义的 `SUCCESS`；任务成功状态使用 `SUCCEEDED`。

### JSON Schema 与序列化

- 使用 Pydantic 生成 Draft 2020-12 兼容 JSON Schema。
- 使用 `jsonschema` 执行运行时 Schema 校验。
- 所有对象禁止未知字段。
- 支持模型转 JSON、JSON 转模型和非法 JSON 错误归一化。
- 测试覆盖 11 类核心契约的 Schema 生成。

## 执行记录

### 依赖安装

```powershell
.\tasks.ps1 setup
```

结果：成功安装 Pydantic 2.14.4 和 jsonschema 4.26.0。

### 统一验证

```powershell
.\tasks.ps1 verify
```

结果：

```text
All checks passed!
23 files already formatted
70 passed in 0.77s
configuration valid: aios-linux-incident
```

### 编译检查

```powershell
.\.venv\Scripts\python.exe -m compileall -q src tests
```

结果：`compileall passed`。

### 依赖检查与密钥扫描

- `pip check`：`No broken requirements found.`
- 凭据形态字符串扫描：未发现身份凭据或私钥。

## 验收项对照

| W03 验收要求 | 结果 |
|---|---|
| 单元测试全部通过 | 通过，70 项 |
| 非法 DAG 被拒绝 | 通过，覆盖自引用、未知依赖和成环 |
| 非法消息被拒绝 | 通过，覆盖自消息和 REPLY 缺少引用 |
| 非法状态迁移被拒绝 | 通过，覆盖跳步、依赖和重试守卫 |
| 所有跨模块对象有类型标注 | 通过 |
| 冻结 DAG 可实例化 | 通过，支持两轮 N6/N7 |

## 提交材料状态

- 数据对象和 docstring：已保存于 `src/aios_incident/models.py`。
- 状态机：已保存于 `src/aios_incident/state.py`。
- JSON Schema 校验：已保存于 `src/aios_incident/validation.py`。
- W03 测试：已保存于 `tests/unit/`。
- 终端结果：已保存于本文件。
- 代码截图和演示视频片段：尚未制作。

