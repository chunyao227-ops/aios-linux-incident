# W05 API 本地证据

服务地址：`http://127.0.0.1:8080`。

| 操作 | 方法 | 路径 | 状态码 |
|---|---|---|---:|
| create | POST | `/api/v1/incidents` | 201 |
| status | GET | `/api/v1/incidents/inc-20261122T084720705550Z-0872cd7f2194` | 200 |
| dag | GET | `/api/v1/incidents/inc-20261122T084720705550Z-0872cd7f2194/dag` | 200 |
| events_before_cancel | GET | `/api/v1/incidents/inc-20261122T084720705550Z-0872cd7f2194/events` | 200 |
| result_before_cancel | GET | `/api/v1/incidents/inc-20261122T084720705550Z-0872cd7f2194/result` | 200 |
| cancel | POST | `/api/v1/incidents/inc-20261122T084720705550Z-0872cd7f2194/cancel` | 200 |
| events_after_cancel | GET | `/api/v1/incidents/inc-20261122T084720705550Z-0872cd7f2194/events` | 200 |
| unknown_incident_404 | GET | `/api/v1/incidents/inc-does-not-exist` | 404 |
| create_second | POST | `/api/v1/incidents` | 201 |
| cancel_second | POST | `/api/v1/incidents/inc-20261122T084720867984Z-fd73e62723d4/cancel` | 200 |
| create_third | POST | `/api/v1/incidents` | 201 |
| history | GET | `/api/v1/incidents` | 200 |
| benchmark | GET | `/api/v1/benchmarks/latest` | 200 |

完整响应体保存在 `W05_api_capture.json`，OpenAPI 文档保存在
`W05_openapi.json`。
