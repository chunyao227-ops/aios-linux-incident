# W10 验收记录

## 状态

已完成。W10 实现提交：`b4f017c`。

## 基线与环境

- 日期：2026-11-21。
- 前置基线：`649216a`（W09 验收完成）。
- W10 实现提交：`b4f017c`。
- Python：3.10.11。
- 证据来源：W08 四类采集 Agent。
- 交互来源：W09 InteractionBus。
- 外部模型：不依赖。

## 实现范围

### 输入校验

- 必须包含 Log、Metrics、Config、Dependency 四类 Evidence。
- 空证据、缺失类别和重复 evidence_id 失败关闭。
- Evidence 和交互消息必须属于同一 Incident。
- 消息只能引用本次输入中存在的 evidence_id。

### 事实融合

- 按 observed_at 对证据进行时间排序。
- 建立 evidence_id、Agent、服务、来源和时间链。
- 读取 Evidence 的顶层结构化 facts。
- 对相同 fact_key 和相同规范化值进行合并。
- 合并记录保留来源 evidence_ids 和 EvidenceKind。
- 不同来源的相同事实不会重复计入。

### 冲突检测

- 同一 fact_key 出现不同规范化值时形成冲突。
- 冲突记录引用实际 evidence_ids。
- 冲突状态返回 `BLOCKED`。
- 冲突状态不选择可修复根因。
- 修复约束加入 `repair_blocked_until_conflicts_resolved`。
- 为每个冲突生成结构化 FollowUpRequest。

### 根因候选

当前确定性基线规则：

- 依赖进程、端口或连接拒绝信号；
- 可用内存临界偏低；
- 配置损坏或截断；
- 无明确规则时生成需要进一步隔离的候选。

每项根因：

- 至少绑定一条真实 supporting_evidence；
- 不从不存在或未输入的 evidence_id 编造引用；
- 保留 confidence、repair_risk 和 required_scope；
- 冲突时仍保留候选和矛盾证据，但不选中修复。

### 排除假设

保留排除理由：

- 依赖证据正常时排除依赖中断；
- 资源和负载正常时排除资源耗尽；
- 配置完整可读时排除配置损坏。

### 交互消息关联

- EvidenceChainEntry 记录引用该证据的消息 ID。
- DiagnosisFusionResult 记录本次融合使用的全部消息 ID。
- 消息中未知 evidence_id 会失败关闭。

## 执行记录

### 统一验证

```powershell
.\tasks.ps1 verify
```

结果：

```text
All checks passed!
53 files already formatted
150 passed, 2 skipped in 2.99s
configuration valid: aios-linux-incident
```

### 全量与真实 AIOS

```powershell
$env:RUN_AIOS_INTEGRATION='1'
.\.venv\Scripts\python.exe -m pytest -o addopts='' -W error
```

结果：

```text
152 passed in 10.63s
```

W10 新增 9 项测试：

- 四类证据融合；
- 时间链排序；
- 相同事实去重；
- 冲突阻断和条件追问；
- 空证据失败关闭；
- 缺失证据类别失败关闭；
- 重复 evidence_id 失败关闭；
- 消息引用未知证据失败关闭；
- 根因证据引用合法性。

### 编译、依赖与安全

- `compileall`：通过。
- `pip check`：`No broken requirements found.`
- 源码执行原语扫描：未发现 Shell、删除、格式化、sudo 或权限修改。
- W04、W07、W08、W09 回归通过。

## 验收项对照

| W10 验收要求 | 结果 |
|---|---|
| 合并四类证据 | 通过 |
| 建立时间、服务和实体关联 | 通过 |
| 相同事实去重 | 通过 |
| 根因候选绑定支持证据 | 通过 |
| 排除假设保留理由 | 通过 |
| 冲突证据触发追问 | 通过 |
| 根因至少引用一条有效 Evidence | 通过 |
| 不使用不存在的 evidence_id | 通过 |
| 空证据失败关闭 | 通过 |
| 缺失证据类别失败关闭 | 通过 |
| 不产生自然语言替代结构 | 通过 |

## 当前限制

- 当前根因规则是确定性基线，覆盖依赖中断、资源异常和配置损坏。
- 冲突会生成结构化追问请求；实际消息发送由 W09 总线和上层流程执行。
- Docker 场景和多轮修复反馈尚未接入 W10。

## 提交材料状态

- 融合器：`src/aios_incident/orchestrator/diagnosis.py`。
- 单元测试：`tests/unit/test_diagnosis_fusion.py`。
- 证据链集成测试：`tests/integration/test_evidence_chain.py`。
- 命令和结果：本文件。
- 证据链与冲突追问截图：尚未制作。

