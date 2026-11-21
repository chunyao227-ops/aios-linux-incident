# W14 验收记录

## 状态

已完成前端、历史持久化和可观测性验收。W14 实现提交：`8846da4`。

## 基线与环境

- 日期：2026-11-22。
- 前置基线：`7d9fefb`（W13 验收完成）。
- W14 实现提交：`8846da4`。
- 开发环境：Windows PowerShell + Python 3.10.11。
- 后端：FastAPI / Uvicorn。
- 前端：原生 HTML、CSS、JavaScript，无构建步骤和额外前端框架。
- 浏览器验收：Microsoft Edge Headless。

## 实现范围

### 仪表盘

- 故障任务提交；
- 历史运行列表；
- 工作流状态、修复轮次和耗时查看；
- DAG 节点状态、依赖和 Agent 分配；
- LogAgent/ConfigAgent、MetricsAgent/DependencyAgent、RepairAgent/VerifierAgent
  三对双向消息计数；
- 修复与验证时间线；
- 完整 Trace 时间线；
- W13 真实串行/并发基准面板；
- 任务取消；
- 页面每 3 秒刷新当前运行。

前端文件：

```text
src/aios_incident/ui/index.html
src/aios_incident/ui/styles.css
src/aios_incident/ui/app.js
```

页面只使用 API 返回的真实运行、Trace 和基准数据，不包含硬编码演示结果。

### API 与历史持久化

- `GET /` 返回仪表盘；
- `GET /ui-assets/*` 返回前端静态资源；
- `GET /api/v1/incidents` 返回历史运行；
- `GET /api/v1/benchmarks/latest` 返回 W13 真实基准摘要；
- 原有创建、状态、DAG、事件、结果和取消接口保持不变。

每个运行的元数据写入：

```text
runs/{incident_id}/{run_id}.meta.json
```

元数据包含 RunContext、DAG、最终报告和修复轮次。API 启动时扫描元数据恢复历史，
状态变化和最终结果会更新同一条元数据。JSONL Trace 继续作为事件事实源。

### Trace 扩展

`MESSAGE_SENT` 事件新增：

```text
from_agent_type
to_agent_type
```

仪表盘据此稳定聚合 Agent 类型之间的双向消息，不依赖实例 ID 的字符串前缀。

## 自动化验收

### E2E 覆盖

`tests/e2e/test_dashboard_flow.py` 覆盖：

1. 仪表盘与静态资源加载，真实基准摘要可读；
2. 新建运行、写入完整回放事件、API 重启后恢复历史、状态、DAG、Trace 和结果；
3. 取消任务后状态与历史同步。

### 默认统一验证

```powershell
.\tasks.ps1 verify
```

结果：

```text
All checks passed!
63 files already formatted
161 passed, 8 skipped in 2.70s
```

跳过项为 2 项真实 AIOS 集成测试和 6 项 Docker 场景测试，均需显式启用。

### 全量真实环境验证

```powershell
$env:RUN_AIOS_INTEGRATION='1'
$env:RUN_DOCKER_SCENARIOS='1'
.\.venv\Scripts\python.exe -m pytest -o addopts='' -W error
```

结果：

```text
169 passed in 104.47s
```

验证包含真实 AIOS 调用、六个 Docker 故障场景和新增 W14 E2E，零警告。

## 浏览器验收

使用 Edge Headless 实际加载 API 服务并渲染仪表盘，人工检查以下内容：

- 桌面布局完整；
- 历史列表和任务表单可用；
- DAG、Agent 分配和依赖展示正常；
- 三对交互计数与修复验证时间线正常；
- W13 串行/并发基准数据正常；
- 无控件重叠、文本裁切或静态资源加载失败。

截图：

```text
docs/submission/evidence/ui/dashboard_2026-11-22.png
```

## 验收项对照

| W14 验收要求 | 结果 |
|---|---|
| 实现任务提交和状态查看 | 通过 |
| 实现 DAG 节点状态和 Agent 分配展示 | 通过 |
| 实现三对交互关系和消息计数 | 通过 |
| 实现修复、验证时间线 | 通过 |
| 实现串行/并发评测面板 | 通过，读取 W13 真实数据 |
| 提供任务取消接口 | 通过 |
| UI 只读取真实数据 | 通过 |
| 一次真实运行可在界面完整回放 | 通过 E2E 完整事件回放 |
| 任务状态与 Trace 一致 | 通过 E2E |
| 页面刷新后可读取历史运行 | 通过 API 重启恢复 E2E |

## 当前限制

- 当前为单机开发部署，未接入用户认证和权限隔离。
- 页面使用 3 秒轮询，不使用 WebSocket 推送。
- 当前截图用于功能和布局证据，完整故障流程演示视频尚未录制。
- 本地 Ollama 和 Docker 数据仅用于开发验收，正式性能结论仍需远程 vLLM 复测。

## 提交材料状态

- 仪表盘实现：`src/aios_incident/ui/`。
- API 与历史持久化：`src/aios_incident/api.py`。
- Trace 扩展：`src/aios_incident/orchestrator/interaction_bus.py`。
- E2E：`tests/e2e/test_dashboard_flow.py`。
- 页面截图：`docs/submission/evidence/ui/dashboard_2026-11-22.png`。
- W14 实现提交：`8846da4`。
- 演示录屏和最终视频：尚未制作。
