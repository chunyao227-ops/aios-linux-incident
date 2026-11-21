# W04 验收记录

## 状态

已完成。W04 实现提交：`1393a20`。

## 基线与环境

- 日期：2026-11-21。
- 前置基线：`e8a5c32`（W03 验收完成）。
- W04 实现提交：`1393a20`。
- Python：3.10.11。
- AIOS：锁定提交 `292d98f78c835499df18cdb6de6325bba1895862`。
- AIOS 地址：`http://127.0.0.1:8000`。
- 本地模型服务：Ollama 0.40.16。
- 模型：`qwen2:7b-instruct`。

## 实现范围

### AIOS 客户端

- 仅通过 AIOS `/query` 调用模型能力，不直接调用供应商私有 SDK。
- 支持 `/status` 健康检查。
- 支持 POST `/query` 的 `agent_name`、`query_type` 和 `query_data`。
- 请求超时来自应用配置。
- 重试次数固定有限，默认最多为配置的 `max_retries` 次。
- 重试等待采用有上限的指数退避。

### LLM 适配器

- 支持普通文本聊天。
- 支持任务级 JSON 输出。
- JSON 调用生成 Draft 2020-12 Response Schema，并要求严格对象输出。
- 模型 JSON 必须直接解析；代码围栏、数组和猜测式修复均被拒绝。
- 模型输出使用 Pydantic 和 JSON Schema 双重校验。
- 失败、未完成和畸形 AIOS 响应转换为统一异常对象。
- 传播 AIOS 调用尝试次数和总耗时。

### Token 统计

- AIOS 或模型响应提供 usage 时，记录 `source=reported`。
- 当前本地 AIOS 不返回精确 token usage。
- 未上报时使用字符规则估算，并显式记录 `source=estimated`。
- 估算值不冒充精确 tokenizer 统计。

### 错误归一化

实现以下统一异常：

- `AdapterTimeoutError`
- `AdapterTransportError`
- `AdapterHTTPError`
- `AdapterProtocolError`
- `ModelResponseError`

所有异常继承 `AdapterInvocationError`，并带 `retryable` 和可选 HTTP
`status_code`。

## 执行记录

### 统一验证

```powershell
.\tasks.ps1 verify
```

结果：

```text
All checks passed!
27 files already formatted
89 passed, 1 skipped in 2.04s
configuration valid: aios-linux-incident
```

跳过的 1 项为真实 AIOS 集成测试，由独立命令显式开启。

### 真实 AIOS 冒烟

```powershell
.\tasks.ps1 integration
```

结果：

```text
tests/integration/test_aios_smoke.py . [100%]
1 passed in 4.68s
```

真实调用覆盖：

- AIOS `/status`；
- 经 AIOS 调用文本模型并返回 `W04_AIOS_OK`；
- 经 AIOS 调用 JSON 模型并返回
  `{"ok": true, "marker": "W04_JSON_OK"}`；
- JSON 经任务级 Schema 校验后转为强类型对象。

### 全量警告检查

```powershell
$env:RUN_AIOS_INTEGRATION='1'
.\.venv\Scripts\python.exe -m pytest -o addopts='' -W error
```

结果：

```text
90 passed in 5.01s
```

### 编译、依赖与安全检查

- `compileall`：通过。
- `pip check`：`No broken requirements found.`
- 凭据形态字符串扫描：未发现账号、API Key 或私钥。

## 验收项对照

| W04 验收要求 | 结果 |
|---|---|
| 模拟响应测试通过 | 通过，19 项 LLM 适配器单元测试 |
| 真实 AIOS 冒烟测试通过 | 通过，文本和 JSON 均成功 |
| 错误响应转换为统一错误对象 | 通过，覆盖 HTTP、连接失败、超时、非法 JSON 和失败响应 |
| JSON 输出不猜测字段 | 通过，非法 JSON、代码围栏和 Schema 不匹配均被拒绝 |
| 不绕过 AIOS | 通过，仅使用 AIOS `/query` |
| 不无限重试 | 通过，重试次数和退避均受配置控制 |

## 限制与后续

- 当前正式结果来自本地 Ollama，仅用于功能联调。
- 远程 vLLM 正式地址和认证信息尚未提供，不能据此声明远程正式性能结果。
- W04 不实现 Agent 调度、Blackboard、Trace、工具网关或故障 API。

## 提交材料状态

- 适配器源码：`src/aios_incident/adapters/`。
- 单元测试：`tests/unit/test_llm_adapter.py`。
- 真实冒烟测试：`tests/integration/test_aios_smoke.py`。
- 命令和结果：本文件。
- 终端截图：尚未制作。

