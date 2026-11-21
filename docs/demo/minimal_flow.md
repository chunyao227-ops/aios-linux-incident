# 最小核心闭环演示

## 目标

W07 验证一条最小事故处理链路：

```text
结构化故障上下文
  -> CoordinatorAgent 生成分析任务
  -> LogAgent 通过受控网关读取日志证据
  -> LLM 输出结构化根因和修复建议
  -> RepairAgent 生成含回滚方案的修复计划
  -> 模拟修复执行
  -> VerifierAgent 执行进程、健康、冒烟和回归检查
  -> 成功 SUCCESS / 失败 UNRESOLVED
```

本工单只验证单个日志分析 Agent 的最小链路，不实现四路并行和三对双向交互。

## 安全边界

- 日志读取仍经过 W06 ToolGateway。
- 读取路径必须位于 Incident 允许范围。
- 修复只修改内存中的模拟场景状态。
- W07 不执行真实宿主机写入或任意 Shell。
- 修复结束后必须执行结构化验证。
- 修复失败不能返回成功。

## 自动化演示

成功路径和失败路径：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\e2e\test_minimal_flow.py -v
```

使用真实本地 AIOS 模型：

```powershell
$env:RUN_AIOS_INTEGRATION='1'
.\.venv\Scripts\python.exe -m pytest tests\e2e\test_minimal_flow.py -v
```

真实 AIOS 测试需要：

- AIOS 运行于 `http://127.0.0.1:8000`；
- Ollama 运行于 `http://127.0.0.1:11434`；
- `qwen2:7b-instruct` 已导入。

## Trace 阶段

最小闭环至少产生：

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

所有事件写入同一 Incident/Run 对应的 JSONL 文件。

## 当前实现限制

- 场景日志和 `/proc` 数据来自文件沙箱。
- LLM 只负责根因候选和修复建议，不能宣布成功。
- 成功由 VerifierAgent 的结构化检查决定。
- 真实 Docker 靶机夹具、失败反馈重试和四路并行属于后续工单。
