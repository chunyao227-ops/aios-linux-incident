# W11 验收记录

## 状态

已完成。W11 实现提交号在提交后补记于本文件。

## 基线与环境

- 日期：2026-11-21。
- 前置基线：`1cfa974`（W10 验收完成）。
- Python：3.10.11。
- 修复后端：受控脚本化后端，不使用 Shell。
- 验证后端：固定检查项脚本化后端。
- 最大修复轮次：2。

## 实现范围

### RepairPlan

新增：

- `attempt_no`；
- `previous_failure_id`。

第 2 轮修复必须显式引用第 1 轮 VerificationResult，否则模型和 Agent 均拒绝。

第 2 轮修复动作会包含“根据验证反馈采用替代策略”的说明，避免无修改重复同一方案。

### 受控修复工具

`src/aios_incident/tools/repair.py` 已实现：

- 固定操作类型白名单；
- 参数白名单；
- 禁止 command、shell、script、cmd、sudo、rm、mkfs 参数；
- Incident 一致性校验；
- 目标服务范围校验；
- 目标容器一致性校验；
- 写入路径白名单和 `..` 拒绝；
- 回滚计划非空校验；
- 关键动作失败后停止后续操作；
- 失败时调用受控回滚；
- RepairResult 记录 attempt_no、返回码、摘要和回滚状态。

### 受控验证工具

`src/aios_incident/tools/verify.py` 已实现固定验证顺序：

1. 进程和端口；
2. 健康接口；
3. 冒烟测试；
4. 回归测试；
5. 可选受控压力测试。

每个检查记录 attempt_no、repair_id、结果和失败原因。

### RepairVerificationLoop

RepairAgent 中新增两轮闭环：

- 每轮生成独立 N6.k RepairPlan；
- 执行 RepairPlan；
- 每轮发送 REVIEW 消息给 VerifierAgent；
- 执行独立验证；
- 失败发送 FEEDBACK；
- 成功发送 RESULT；
- 验证失败后生成 N6.(k+1)，并引用上一轮失败；
- 两轮后仍失败进入 `UNRESOLVED`；
- 成功由 VerifierAgent 决定，RepairAgent 不自行宣布成功。

Trace 包含：

```text
REPAIR_ATTEMPT_STARTED
REPAIR_PLAN_CREATED
REPAIR_FINISHED
VERIFICATION_FINISHED
REPAIR_RETRY_SCHEDULED
REPAIR_LOOP_SUCCEEDED / REPAIR_LOOP_UNRESOLVED
```

消息总线同时记录 REVIEW、FEEDBACK 或 RESULT。

## 执行记录

### 统一验证

```powershell
.\tasks.ps1 verify
```

结果：

```text
All checks passed!
56 files already formatted
155 passed, 2 skipped in 3.53s
configuration valid: aios-linux-incident
```

### 全量与真实 AIOS

```powershell
$env:RUN_AIOS_INTEGRATION='1'
.\.venv\Scripts\python.exe -m pytest -o addopts='' -W error
```

结果：

```text
157 passed in 11.19s
```

W11 新增 5 项集成测试：

- 第一轮成功完成闭环；
- 两轮验证失败后进入 UNRESOLVED；
- 第二轮引用第一轮失败并采用不同描述；
- 修复动作失败后执行回滚；
- 拒绝 shell 工具和越权写路径。

### 编译、依赖与安全

- `compileall`：通过。
- `pip check`：`No broken requirements found.`
- 精确执行原语扫描：
  - 未发现 subprocess、os.system、shell=True、Popen 或 check_output；
  - 未发现 sudo、rm -rf 或 mkfs 调用；
  - 禁止字符串仅存在于显式拒绝名单。
- W04、W07—W10 回归通过。

## 验收项对照

| W11 验收要求 | 结果 |
|---|---|
| Diagnosis 转换为修复计划 | 通过 |
| 执行前校验权限、路径、目标和回滚 | 通过 |
| 每次修复发送 REVIEW | 通过 |
| 每次修复均有 attempt_no | 通过 |
| 每次修复均有结构化验证结果 | 通过 |
| 验证失败返回 RepairAgent | 通过 FEEDBACK |
| 最多两轮重试 | 通过 |
| 两轮失败后终止 | 通过 UNRESOLVED |
| RepairAgent 不自行宣布成功 | 通过 |
| 修复工具不接受任意 Shell | 通过 |
| 修复失败可回滚 | 通过 |

## 当前限制

- 修复和验证后端目前为受控脚本化实现，不操作真实 Docker 服务。
- 真实容器动作和夹具属于 W12/W13。
- 当前只有一次成功路径和两轮失败路径，六个正式场景尚未覆盖。

## 提交材料状态

- 修复工具：`src/aios_incident/tools/repair.py`。
- 验证工具：`src/aios_incident/tools/verify.py`。
- 修复验证闭环：`src/aios_incident/agents/repair_agent.py`。
- 集成测试：`tests/integration/test_repair_verification_loop.py`。
- 命令和结果：本文件。
- 两轮修复时间线和回滚截图：尚未制作。

