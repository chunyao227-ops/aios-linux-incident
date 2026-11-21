# W06 验收记录

## 状态

已完成。W06 实现提交号在提交后补记于本文件。

## 基线与环境

- 日期：2026-11-21。
- 前置基线：`47ad011`（W05 验收完成）。
- Python：3.10.11。
- 工具后端：沙箱根目录只读后端。
- 工具执行方式：文件读取和受限 `/proc` 快照解析。
- Shell、subprocess 和修复写入：未使用。

## 工具权限表

| 工具 | 允许 Agent | 类型 | 超时上限 | 输出上限 |
|---|---|---|---:|---:|
| `log.read` | LogAgent | 只读 | 10 秒 | 64 KiB |
| `metrics.collect` | MetricsAgent | 只读 | 10 秒 | 64 KiB |
| `config.read` | ConfigAgent | 只读 | 10 秒 | 64 KiB |
| `dependency.inspect` | DependencyAgent | 只读 | 10 秒 | 96 KiB |
| `repair.apply` | RepairAgent | 默认禁止 | 5 秒 | 16 KiB |

`repair.apply` 即使由 RepairAgent 调用也始终失败关闭，直到 W11 完成受控写入和回滚审查。

## 实现范围

### 统一工具协议

- `ToolName` 固定工具清单。
- `ToolPolicy` 保存 Agent 权限、读写属性、参数、超时和输出限制。
- `ToolRequest` 强制 Incident、Task、Agent、工具和限制字段。
- `ToolResult` 返回结构化数据、截断状态、输出大小和执行耗时。
- 参数采用固定字段集合，未知参数直接拒绝。

### ToolGateway

- 工具必须在冻结合法清单中。
- Agent 类型不具备权限时拒绝调用。
- 每次调用开始和结束均写入 JSONL Trace。
- 失败调用记录异常类型和错误摘要。
- 超时和输出大小在网关层再次检查。
- 工具参数不直接写入 Trace，避免泄露大型内容。
- 未授权、越权、修复禁用和路径逃逸均失败关闭。

### 四类只读工具

- 日志读取：按允许路径读取末尾有限行，支持字节和行数限制。
- 指标采集：解析沙箱 `/proc` 中的负载、内存、CPU、网络摘要。
- 配置读取：读取允许范围内配置，返回内容、大小、摘要和截断状态。
- 依赖检查：解析沙箱 `/proc` 进程和 TCP 端口信息。

### 路径与宿主隔离

- 目标路径必须是绝对 Linux 路径。
- `..`、空字节和非绝对路径被拒绝。
- 读取路径必须位于 Incident 的 `allowed_scope.read_paths`。
- 后端最终路径必须位于配置的 sandbox root。
- 符号链接解析后再次检查 sandbox 边界。
- 工具目录不包含 `subprocess`、`os.system`、`shell=True`、`sudo`、
  删除、格式化或权限修改原语。

## 执行记录

### 统一验证

```powershell
.\tasks.ps1 verify
```

结果：

```text
All checks passed!
36 files already formatted
126 passed, 1 skipped in 2.51s
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
127 passed in 6.14s
```

W06 新增测试：

- ToolGateway 单元测试：10 项；
- 沙箱工具隔离集成测试：3 项。

### 编译、依赖与安全

- `compileall`：通过。
- `pip check`：`No broken requirements found.`
- 工具目录执行原语扫描：未发现 Shell 或破坏性操作。
- W04 真实 AIOS 文本与 JSON 冒烟回归通过。

## 验收项对照

| W06 验收要求 | 结果 |
|---|---|
| 统一 ToolRequest/ToolResult | 通过 |
| 工具白名单 | 通过 |
| Agent 权限控制 | 通过 |
| 路径规范化 | 通过 |
| 超时和输出限制 | 通过 |
| 日志只读工具 | 通过 |
| 指标只读工具 | 通过 |
| 配置只读工具 | 通过 |
| 进程/端口依赖工具 | 通过 |
| 修复占位默认禁止 | 通过 |
| 所有工具调用写入 Trace | 通过，开始和结束各一条 |
| 未授权工具被拒绝 | 通过 |
| 路径逃逸被拒绝 | 通过 |
| 只读工具返回结构化结果 | 通过 |

## 当前限制

- `SandboxReadOnlyBackend` 读取的是沙箱根目录中的文件系统快照。
- W07 需要把 Docker 靶机日志、配置和 `/proc` 数据映射到该根目录，或实现同协议容器后端。
- 当前没有真实修复写入能力。
- 极慢的第三方后端无法被线程强制终止；当前文件后端操作短且受路径限制。

## 提交材料状态

- 协议与权限：`src/aios_incident/tools/base.py`。
- 网关与只读后端：`src/aios_incident/tools/gateway.py`。
- 单元测试：`tests/unit/test_tool_gateway.py`。
- 隔离集成测试：`tests/integration/test_tool_isolation.py`。
- 命令和结果：本文件。
- 工具调用 Trace、越权拒绝和路径逃逸截图：尚未制作。

