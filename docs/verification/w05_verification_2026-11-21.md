# W05 验收记录

## 状态

已完成。W05 实现提交号在提交后补记于本文件。

## 基线与环境

- 日期：2026-11-21。
- 前置基线：`c6ed2e6`（W04 验收完成）。
- Python：3.10.11。
- FastAPI：0.116.2。
- Starlette：0.48.0。
- Uvicorn：0.35.0。
- AnyIO：4.10.0。
- HTTP 测试客户端：httpx 0.28.1。

## 实现范围

### 故障 API

实现以下接口：

```text
POST /api/v1/incidents
GET  /api/v1/incidents/{incident_id}
GET  /api/v1/incidents/{incident_id}/dag
GET  /api/v1/incidents/{incident_id}/events
GET  /api/v1/incidents/{incident_id}/result
POST /api/v1/incidents/{incident_id}/cancel
```

- API 默认只绑定本机 `127.0.0.1:8080`。
- 创建故障时由服务端生成唯一 Incident ID 和 Run ID。
- 创建时实例化冻结的 `N0—N7` 任务 DAG。
- 支持状态、结果、DAG、事件和取消查询。
- 取消操作幂等，并写入独立取消 Trace。
- 非法请求返回 `INVALID_INCIDENT_REQUEST` 结构化 422 错误。
- 未知 Incident 返回 `INCIDENT_NOT_FOUND` 结构化 404 错误。
- API 不包含云账号认证信息。

### Blackboard

- 以 `incident_id` 和 `artifact_id` 双重隔离。
- 支持写入、读取和 `content_ref` 解析。
- `PENDING` 产物不可被下游读取。
- `PENDING` 只能转换为一次 `READY`。
- `READY` 产物不可覆盖。
- 同一 Incident 内同一 `content_ref` 不能绑定多个产物。
- 不向其他 Incident 暴露内容引用。

### JSONL Trace

- 每个 Incident/Run 保存为独立 JSONL 文件。
- 路径格式：`runs/{incident_id}/{run_id}.jsonl`。
- 只追加，不覆盖已有事件。
- 重复 Trace ID 被拒绝。
- 服务重启后加载已有 Trace ID，继续阻止重复写入。
- Trace 文件路径拒绝 `..`、空格和路径分隔符。
- 创建运行至少写入 `INCIDENT_CREATED` 和 `DAG_INSTANTIATED`。
- 取消运行追加 `INCIDENT_CANCELLED`。

## 依赖稳定性处理

首次安装的最新 FastAPI/Starlette 组合出现测试客户端弃用警告。为避免建立在易变接口上，
依赖固定为：

- `fastapi>=0.116,<0.117`
- `uvicorn>=0.35,<0.36`
- `httpx>=0.28,<0.29`
- `anyio>=4.6,<4.11`

最终测试无警告。

## 执行记录

### 统一验证

```powershell
.\tasks.ps1 verify
```

结果：

```text
All checks passed!
32 files already formatted
113 passed, 1 skipped in 2.12s
configuration valid: aios-linux-incident
```

跳过项仅为默认不执行的 W04 真实 AIOS 冒烟测试。

### 全量警告检查

```powershell
$env:RUN_AIOS_INTEGRATION='1'
.\.venv\Scripts\python.exe -m pytest -o addopts='' -W error
```

结果：

```text
114 passed in 15.95s
```

W05 新增测试分布：

- Blackboard：7 项；
- JSONL Trace：10 项；
- Incident API：7 项。

### 编译、依赖与安全

- `compileall`：通过。
- `pip check`：`No broken requirements found.`
- 凭据形态字符串扫描：未发现账号、API Key 或私钥。
- W04 真实 AIOS 文本与 JSON 冒烟仍通过。

## 验收项对照

| W05 验收要求 | 结果 |
|---|---|
| 可提交故障并查询运行状态 | 通过，HTTP 201 创建、GET 查询 |
| 结果查询 | 通过，结果接口返回当前状态和最终报告字段 |
| DAG 查询 | 通过，返回 10 个固定任务节点 |
| 取消接口 | 通过，状态转为 CANCELLED 并写入 Trace |
| 唯一 Incident ID 和 Run ID | 通过 |
| Blackboard 未完成产物不可读 | 通过 |
| Blackboard 不可覆盖 | 通过 |
| Trace 不允许覆盖 | 通过，追加写、重复 ID 拒绝 |
| 一次运行形成 JSONL 文件 | 通过 |
| 非法 Incident 返回结构化错误 | 通过 |

## 当前限制

- Incident 运行元数据保存在进程内存中，API 重启后需要由后续编排器恢复或重建。
- JSONL Trace 已持久化到磁盘。
- W05 不执行 Agent，不启动任务调度。
- W05 不实现工具网关、修复或独立验证，这些属于后续工单。

## 提交材料状态

- 源码：`api.py`、`orchestrator/blackboard.py`、`orchestrator/trace.py`。
- 单元测试：`tests/unit/test_blackboard.py`、`tests/unit/test_trace.py`。
- API 集成测试：`tests/integration/test_incident_api.py`。
- 命令和结果：本文件。
- API 终端截图和 OpenAPI 页面截图：尚未制作。
