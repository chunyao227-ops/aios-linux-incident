# 基于 AIOS 的 Linux 服务故障协同诊断与修复系统

## 开发实现规格 受控基线

| 文档属性 | 内容 |
|---|---|
| 文档版本 | 1.0.0 |
| 文档状态 | 基线版本 |
| 编制日期 | 2026-11-15 |
| 适用阶段 | 2026 年区域赛开发、联调、测试、提交及全国赛扩展 |
| 适用系统 | 基于 Linux、AIOS 与 AIOS-Agent SDK 的多智能体协作系统 |
| 主流程状态 | 冻结，未经变更流程不得修改 |

> 本文件是后续编码、接口实现、测试和代码审查的统一依据。实现不得通过提示词、私有分支或局部硬编码改变本文规定的任务结构、状态迁移、交互关系、依赖约束、修复闭环和验收口径。

---

## 1. 文档目的与效力

### 1.1 目的

本文档定义“AI 小队自动排查并修复 Linux 故障系统”的总体边界、任务分解、协作流程、状态迁移、接口契约、异常处理、评测口径与变更规则。

本文档是后续需求分析、架构设计、编码实现、测试验收、演示材料编写和全国赛扩展的统一基线。

### 1.2 规范用语

- “应”表示必须遵守的规范性要求。
- “不得”表示禁止性要求。
- “宜”表示推荐但允许实现层调整。
- “可”表示可选能力。

### 1.3 文档效力

凡涉及以下内容的条款，均属于冻结项：

1. 主任务 DAG 的节点、依赖和并行关系；
2. 任务生命周期与状态迁移；
3. 至少三类 Agent 双向交互；
4. 诊断、修复、验证的先后顺序；
5. 串行与并发对比的实验口径；
6. 正确性与提速验收门槛；
7. 安全边界和失败关闭原则。

实现语言、线程或异步框架、数据库选型、前端样式和日志存储方式可在不改变上述语义的前提下调整。

---

## 2. 系统定义与范围

### 2.1 系统定义

本系统面向隔离 Linux 环境中的复合服务故障，采用多智能体协作方式完成多源证据采集、联合诊断、受控修复与回归验证。

系统由任务级编排层与 AIOS 资源层构成：

- 任务级编排层负责复杂任务分解、依赖管理、能力匹配、消息协作和结果融合；
- AIOS 资源层负责 LLM 调用、上下文管理、记忆、存储和工具系统调用。

任务级编排层不得替代 AIOS 对外资源接口；Agent 的模型、工具和记忆操作应通过 AIOS-Agent SDK 或 AIOS Kernel 规定的接口完成。

### 2.2 典型任务

用户提交如下目标：

> 在限定时间内诊断指定 Linux 服务不可用的原因，执行允许范围内的修复，并使服务通过健康检查、压力测试和回归测试。

系统应在诊断前同时采集至少四类相互独立的证据：

1. 应用与系统日志；
2. CPU、内存、磁盘、网络和连接指标；
3. 服务配置、权限和文件状态；
4. 进程、端口和服务依赖关系。

### 2.3 非目标

本版本不包括以下内容：

1. 对生产宿主机执行无限制的 root 级运维；
2. 未经验证的自动删除、格式化或大范围文件修改；
3. 跨多个物理主机的大规模分布式运维；
4. 完全由模型生成任意执行计划并绕过固定依赖约束；
5. 与故障修复无关的通用聊天或内容生成。

---

## 3. 赛题约束与设计映射

| 赛题要求 | 本系统实现 |
|---|---|
| 自行拟定单个 Agent 难以稳定完成的复杂任务 | Linux 服务复合故障诊断、修复与回归验证 |
| 至少 4 种可协作 Agent | 定义 7 种职责不同的 Agent |
| 至少 4 个可并行子任务 | 第一轮并行执行日志、指标、配置、依赖四类采集任务 |
| 自动分配给不同 Agent | 基于能力标签、Agent 状态和负载的任务调度 |
| 至少 3 对 Agent 双向交互 | 日志与配置、指标与依赖、修复与验证 |
| 满足先后顺序和依赖约束 | 固定 DAG、拓扑排序和就绪队列控制 |
| 并发总时间较串行减少不少于 20% | 固定环境的串行与并发对照实验 |
| 正确完成任务 | 根因识别、服务恢复和回归测试三类验收 |

---

## 4. 总体架构

### 4.1 分层结构

```text
用户接口层
  ├─ 事件提交
  ├─ 任务状态查询
  ├─ DAG 图与 Agent 交互图展示
  └─ 最终诊断报告展示
        │
任务编排层
  ├─ Incident Manager
  ├─ Planner
  ├─ Capability Matcher
  ├─ DAG Scheduler
  ├─ Interaction Bus
  ├─ Shared Blackboard
  ├─ Retry Controller
  └─ Trace Recorder
        │
Agent 执行层
  ├─ CoordinatorAgent
  ├─ LogAgent
  ├─ MetricsAgent
  ├─ ConfigAgent
  ├─ DependencyAgent
  ├─ RepairAgent
  └─ VerifierAgent
        │
AIOS 资源层
  ├─ LLM Core
  ├─ Context Manager
  ├─ Memory Manager
  ├─ Storage Manager
  └─ Tool Manager
        │
隔离 Linux 环境
  ├─ 故障目标容器或虚拟机
  ├─ 日志与指标数据源
  ├─ 配置与文件系统
  └─ 健康检查、压力测试与回归测试
```

### 4.2 控制面与数据面

系统应区分控制面和数据面。

**控制面**保存任务状态、DAG 依赖、Agent 状态、消息和重试计数。控制面数据不得仅以自然语言形式存储，应由结构化对象或数据库记录。

**数据面**保存日志摘要、指标结果、配置证据、依赖图、修复方案和验证结果。数据面可通过 AIOS Memory、AIOS Storage 或受控文件系统实现。

调度器不得根据模型生成的自由文本直接推断任务是否完成，应以结构化状态和事件为准。

---

## 5. Agent 规格

### 5.1 Agent 通用接口

每个 Agent 应实现统一接口：

```python
class BaseAgent:
    agent_id: str
    agent_type: str
    capabilities: set[str]

    def execute(self, task: TaskEnvelope) -> AgentResult:
        ...

    def ask(self, message: AgentMessage) -> None:
        ...

    def reply(self, message: AgentMessage) -> None:
        ...
```

`AgentResult` 应至少包含：

| 字段 | 含义 |
|---|---|
| `agent_id` | Agent 唯一标识 |
| `task_id` | 对应任务 |
| `status` | `SUCCEEDED`、`FAILED` 或 `BLOCKED` |
| `summary` | 结果摘要 |
| `findings` | 结构化发现列表 |
| `evidence_ids` | 证据引用 |
| `requests` | 对本任务有直接影响的后续查询 |
| `metrics` | 开始时间、结束时间、token 与工具调用次数 |

### 5.2 Agent 类型与能力

| Agent 类型 | 能力标签 | 主要输出 | 允许工具 |
|---|---|---|---|
| `CoordinatorAgent` | `planning`、`fusion` | 任务分配、根因候选、最终报告 | LLM、Memory |
| `LogAgent` | `log_analysis` | 异常事件、时间线、日志证据 | 日志读取、全文检索、向量检索 |
| `MetricsAgent` | `metrics_analysis` | 资源异常、趋势和阈值判断 | 指标采集、统计脚本 |
| `ConfigAgent` | `config_analysis` | 配置冲突、权限和端口证据 | 文件读取、配置解析 |
| `DependencyAgent` | `dependency_analysis` | 进程、端口、服务依赖图 | 进程、端口和依赖查询 |
| `RepairAgent` | `repair` | 修复步骤、风险和回滚方案 | 受控命令、文件写入 |
| `VerifierAgent` | `verification` | 健康、压力和回归测试结果 | 测试脚本、健康检查 |

同一 Agent 实现代码不得因承担不同职责而绕过能力标签与工具白名单。

### 5.3 自动任务分配

调度器应维护 Agent 注册表，字段至少包括：

- `agent_type`；
- `capabilities`；
- `status`；
- `current_task_count`；
- `max_concurrency`；
- `last_heartbeat`。

任务分配应满足以下规则：

1. Agent 具备任务声明的全部必需能力；
2. Agent 状态为 `IDLE` 或未超过并发上限；
3. 在全部合格 Agent 中优先选择当前负载最低者；
4. 负载相同时按固定顺序选择，以保证实验可复现；
5. 分配结果应写入 `ASSIGN` 消息和 Trace。

---

## 6. 输入与输出契约

### 6.1 故障事件输入

```json
{
  "incident_id": "inc-20261115-001",
  "objective": "诊断并修复目标服务不可用问题",
  "target": {
    "host": "sandbox-01",
    "service": "web-app",
    "environment": "docker"
  },
  "allowed_scope": {
    "read_paths": ["/var/log", "/etc/web-app", "/opt/web-app"],
    "write_paths": ["/etc/web-app"],
    "allowed_services": ["web-app", "nginx", "redis", "postgresql"]
  },
  "time_budget_seconds": 600,
  "max_repair_attempts": 2,
  "success_criteria": [
    "health_endpoint_returns_200",
    "smoke_test_passes",
    "regression_test_passes"
  ]
}
```

### 6.2 任务信封

```json
{
  "incident_id": "inc-20261115-001",
  "task_id": "N1",
  "attempt": 1,
  "task_type": "log_analysis",
  "required_capabilities": ["log_analysis"],
  "depends_on": ["N0"],
  "input_artifact_ids": [],
  "deadline": "2026-11-15T12:10:00+08:00",
  "constraints": {
    "max_tokens": 2048,
    "max_tool_calls": 12
  }
}
```

### 6.3 结构化证据记录

```json
{
  "evidence_id": "evi-N1-001",
  "incident_id": "inc-20261115-001",
  "task_id": "N1",
  "producer_agent": "LogAgent",
  "kind": "log",
  "summary": "web-app 连续报告数据库连接被拒绝",
  "source_ref": "/var/log/web-app/error.log:318",
  "observed_at": "2026-11-15T12:01:21+08:00",
  "facts": {
    "error_code": "ECONNREFUSED",
    "target": "127.0.0.1:5432"
  },
  "confidence": 0.91
}
```

### 6.4 最终报告

最终报告应至少包含：

| 字段 | 内容 |
|---|---|
| `incident_id` | 故障事件编号 |
| `final_status` | `SUCCESS`、`UNRESOLVED`、`BLOCKED` 或 `ABORTED` |
| `root_causes` | 结构化根因列表 |
| `evidence` | 根因对应证据 |
| `repair_actions` | 实际执行的修复动作 |
| `rollback_record` | 回滚信息 |
| `verification` | 健康、压力和回归结果 |
| `timing` | 总耗时、各任务耗时和重试次数 |
| `agent_interactions` | 双向交互摘要和 Trace 引用 |

---

## 7. 固定任务 DAG

### 7.1 节点定义

| 节点 | 任务 | 执行者 | 前置依赖 |
|---|---|---|---|
| `N0` | 校验事件、加载约束、实例化任务 DAG、分配第一轮任务 | `CoordinatorAgent` | 无 |
| `N1` | 采集并分析日志证据 | `LogAgent` | `N0` |
| `N2` | 采集并分析资源指标 | `MetricsAgent` | `N0` |
| `N3` | 检查配置、权限和文件状态 | `ConfigAgent` | `N0` |
| `N4` | 构建进程、端口和服务依赖关系 | `DependencyAgent` | `N0` |
| `N5` | 汇合证据、识别根因、形成修复约束 | `CoordinatorAgent` | `N1`、`N2`、`N3`、`N4` |
| `N6.k` | 第 k 次修复，k 从 1 开始 | `RepairAgent` | `N5`；k 大于 1 时依赖 `N7.(k-1)` 的失败结果 |
| `N7.k` | 第 k 次健康、压力和回归验证 | `VerifierAgent` | `N6.k` |

### 7.2 主流程图

```text
N0 规划与分配
   │
   ├──────────┬──────────┬──────────┐
   ▼          ▼          ▼          ▼
 N1 日志    N2 指标    N3 配置    N4 依赖
   │          │          │          │
   └──────────┴────┬─────┴──────────┘
                   ▼
             N5 证据融合与诊断
                   │
                   ▼
             N6.1 执行修复
                   │
                   ▼
             N7.1 回归验证
              │          │
              │失败      │成功
              ▼          ▼
         N6.2 → N7.2   最终报告
              │
              │失败且未超过次数
              ▼
         N6.3 → N7.3
```

### 7.3 并行约束

1. `N1`、`N2`、`N3`、`N4` 应在同一调度周期进入就绪队列。
2. 四个节点不得被实现为顺序调用。
3. `N5` 仅当四个前置节点均达到终态后才能执行。
4. `N6.k` 不得在 `N5` 完成前执行。
5. `N7.k` 不得在 `N6.k` 完成前执行。
6. 修复失败触发的下一轮是新的任务实例，不形成循环 DAG。
7. 修复累计尝试次数不得超过 `max_repair_attempts`。

### 7.4 证据完整性要求

`N5` 启动前应满足：

- `N1` 至 `N4` 均存在结构化结果；
- 每个结果至少引用一条可定位证据；
- 关键证据包含来源路径或工具返回引用；
- 任一前置节点失败时，不得直接进入修复。

若前置节点重试后仍失败，系统状态应转为 `BLOCKED`，最终结论为“证据不足，无法安全修复”。

---

## 8. 任务状态机

### 8.1 任务状态

| 状态 | 含义 |
|---|---|
| `CREATED` | 任务已创建，尚未检查依赖 |
| `BLOCKED` | 依赖未满足或资源不可用 |
| `READY` | 依赖已满足，可进入调度 |
| `ASSIGNED` | 已分配 Agent，尚未执行 |
| `RUNNING` | Agent 正在执行 |
| `VERIFYING` | 正在校验 Agent 输出结构 |
| `SUCCEEDED` | 任务成功完成 |
| `FAILED_RETRYABLE` | 可重试失败 |
| `FAILED_FINAL` | 重试耗尽或不可恢复失败 |
| `CANCELLED` | 因超时、安全终止或上游取消 |

### 8.2 状态迁移

```text
CREATED
  ├─ 依赖未满足 → BLOCKED
  └─ 依赖已满足 → READY

BLOCKED
  └─ 依赖满足 → READY

READY
  └─ 能力匹配成功 → ASSIGNED

ASSIGNED
  └─ Agent 开始执行 → RUNNING

RUNNING
  ├─ 输出进入校验 → VERIFYING
  ├─ 可恢复异常 → FAILED_RETRYABLE
  └─ 超时或取消 → CANCELLED

VERIFYING
  ├─ 校验通过 → SUCCEEDED
  ├─ 可重试错误 → FAILED_RETRYABLE
  └─ 不可恢复错误 → FAILED_FINAL

FAILED_RETRYABLE
  ├─ 未超过次数 → READY
  └─ 超过次数 → FAILED_FINAL
```

任何实现不得将 `RUNNING` 直接置为 `SUCCEEDED` 而跳过结构化输出校验。

---

## 9. 调度流程

### 9.1 调度主循环

```text
1. 从事件输入创建 Incident 和 N0
2. 校验事件及允许操作范围
3. 实例化固定 DAG
4. 计算拓扑顺序与入度
5. 将入度为 0 的任务置于 READY
6. 对 READY 任务执行能力匹配
7. 并发派发可执行任务
8. 接收 Agent 结果并执行结构校验
9. 更新任务终态和后继节点入度
10. 将新就绪任务加入 READY
11. 重复步骤 6 至 10，直至全部任务终态或触发终止条件
12. 生成最终报告
```

### 9.2 第一轮并发启动规则

`N0` 完成后，调度器应一次性完成 `N1`、`N2`、`N3`、`N4` 的能力匹配和入队。首个任务派发前，四个任务均应处于 `READY` 或 `ASSIGNED` 状态。

系统应以任务派发时间、开始时间和结束时间记录并发关系。仅在线程或协程已创建但任务尚未派发的情况下，不得宣称已实现并行。

### 9.3 调度终止条件

出现以下任一情况时，系统应终止后续调度：

1. `N7.k` 成功，系统结果为 `SUCCESS`；
2. 修复次数超过上限且验证仍失败，系统结果为 `UNRESOLVED`；
3. `N1` 至 `N4` 在重试后仍有不可恢复失败，系统结果为 `BLOCKED`；
4. 超过总时间预算，系统结果为 `ABORTED`；
5. 检测到越权、危险命令或安全策略阻断，系统结果为 `ABORTED`；
6. 用户或管理员主动取消。

---

## 10. 双向交互规格

### 10.1 消息类型

| 类型 | 发送方 | 用途 |
|---|---|---|
| `ASSIGN` | Coordinator | 分配任务 |
| `RESULT` | 工作 Agent | 返回结构化结果 |
| `QUESTION` | 任一 Agent | 请求证据或判断 |
| `REPLY` | 被询问 Agent | 返回针对性答复 |
| `HANDOFF` | 当前执行者 | 将修复或验证结果移交下一 Agent |
| `FEEDBACK` | Verifier | 返回验证失败原因 |
| `ABORT` | Coordinator 或安全模块 | 终止任务 |

每条消息至少包含：

```json
{
  "message_id": "msg-0001",
  "incident_id": "inc-20261115-001",
  "task_id": "N1",
  "from_agent": "LogAgent",
  "to_agent": "ConfigAgent",
  "type": "QUESTION",
  "content": "请核对 web-app 的实际监听端口。",
  "evidence_ids": ["evi-N1-001"],
  "reply_to": null,
  "timestamp": "2026-11-15T12:02:03+08:00"
}
```

### 10.2 必须实现的三对双向交互

#### I1：LogAgent 与 ConfigAgent

1. `LogAgent` 发现连接拒绝、权限拒绝或配置加载异常；
2. `LogAgent` 向 `ConfigAgent` 发送 `QUESTION`，请求核对对应配置；
3. `ConfigAgent` 发送 `REPLY`，附带配置路径和值；
4. `ConfigAgent` 可反向请求日志时间线，`LogAgent` 应返回带时间戳的日志证据。

#### I2：MetricsAgent 与 DependencyAgent

1. `MetricsAgent` 发现资源或连接数异常；
2. 向 `DependencyAgent` 查询相应进程、端口和依赖状态；
3. `DependencyAgent` 返回依赖图证据；
4. `DependencyAgent` 可反向请求相关时间段指标，`MetricsAgent` 应返回结构化趋势。

#### I3：RepairAgent 与 VerifierAgent

1. `RepairAgent` 通过 `HANDOFF` 提交修复结果；
2. `VerifierAgent` 执行验证；
3. 验证失败时通过 `FEEDBACK` 返回具体失败项；
4. `RepairAgent` 根据反馈生成下一次修复；
5. 验证成功后由 `VerifierAgent` 返回最终 `RESULT`。

### 10.3 交互计数规则

一对 Agent 构成“双向交互”应同时满足：

1. 两个 Agent 类型不同；
2. 双方各自至少发送一条消息；
3. 消息存在明确的业务引用关系；
4. 消息可在 Trace 中追溯到同一故障事件；
5. 不得使用预置文本伪造交互。

Coordinator 与四个工作 Agent 的 `ASSIGN`/`RESULT` 也可计为有效双向交互，但 I1、I2、I3 为本系统固定验收项，不得省略。

---

## 11. Agent 执行规范

### 11.1 CoordinatorAgent

职责：

1. 校验输入并实例化固定 DAG；
2. 生成任务信封；
3. 依据能力标签分配任务；
4. 接收各 Agent 的结构化结果；
5. 在 `N5` 中融合证据并生成根因候选；
6. 根据风险与证据决定是否进入修复；
7. 在终止条件满足时生成最终报告。

约束：

- 不得跳过 `N1` 至 `N4`；
- 不得在所有前置证据未完成时直接给出根因；
- 不得擅自增加删除、格式化等高风险操作；
- 不得修改主 DAG 的依赖方向。

### 11.2 证据分析类 Agent

`LogAgent`、`MetricsAgent`、`ConfigAgent` 和 `DependencyAgent` 应遵守以下规则：

1. 仅访问事件允许的读取范围；
2. 输出结构化证据，不得只返回自由文本；
3. 明确区分观测事实、推断和不确定性；
4. 所有关键结论应引用 `evidence_id`；
5. 必要时发起跨 Agent 查询，但不得自行执行修复。

### 11.3 RepairAgent

职责：

1. 根据根因和证据生成修复方案；
2. 为每一步说明预期效果和风险；
3. 在执行前生成回滚方案；
4. 通过受控工具执行修复；
5. 保存命令、返回码、标准输出和标准错误；
6. 接收验证失败反馈并生成下一次修复。

禁止行为：

- 执行白名单之外的命令；
- 修改允许范围之外的文件；
- 删除未明确列入目标的目录或数据；
- 绕过审计日志直接调用宿主系统；
- 在无回滚方案时执行高风险变更。

### 11.4 VerifierAgent

职责：

1. 运行事件声明的健康检查；
2. 运行冒烟测试；
3. 运行回归测试；
4. 必要时运行受控压力测试；
5. 记录每项检查的命令、返回码、耗时和结果；
6. 验证失败时向 RepairAgent 返回可操作的 `FEEDBACK`。

验证通过条件必须由结构化测试结果确定，不得仅由 LLM 判断“看起来已修复”。

---

## 12. 共享黑板与记忆使用

### 12.1 黑板数据结构

共享黑板以 `incident_id` 为隔离边界，按 `artifact_id` 保存以下对象：

- 任务输入；
- 证据记录；
- 根因候选；
- 修复计划；
- 执行记录；
- 验证结果；
- Agent 消息。

每个对象应包含：

```json
{
  "artifact_id": "art-001",
  "incident_id": "inc-20261115-001",
  "producer_agent": "LogAgent",
  "kind": "evidence",
  "content_ref": "evi-N1-001",
  "created_at": "2026-11-15T12:02:03+08:00",
  "immutable": true
}
```

### 12.2 AIOS Memory 使用规则

1. Agent 的上下文记忆和可共享证据应通过 AIOS Memory 接口写入；
2. 共享对象应设置明确的 `incident_id`、`owner_agent`、`sharing_policy` 和 `memory_type`；
3. 故障事件之间应保持隔离；
4. 调度器依赖的任务状态不得只存在于向量记忆或自然语言上下文中；
5. 读取共享证据时应校验其 `incident_id`，不得跨事件混用。

### 12.3 证据不可变性

原始证据写入后不得被覆盖。Agent 的后续判断应作为新对象写入，并通过 `evidence_ids` 引用原始证据。

---

## 13. 诊断融合规则

`N5` 应执行以下步骤：

1. 聚合 `N1` 至 `N4` 的结构化结果；
2. 校验事件类型、时间范围和对象标识；
3. 去重相同事实；
4. 标记相互冲突的证据；
5. 生成一个或多个根因候选；
6. 为每个根因候选绑定证据；
7. 评估候选的置信度和修复风险；
8. 选择具备可执行修复路径的根因；
9. 输出修复约束和回滚要求。

根因候选格式：

```json
{
  "root_cause_id": "rc-001",
  "description": "数据库服务未运行",
  "supporting_evidence": ["evi-N2-003", "evi-N4-002"],
  "contradicting_evidence": [],
  "confidence": 0.88,
  "repair_risk": "medium",
  "required_scope": ["postgresql"]
}
```

若证据冲突且无法在允许范围内消解，应终止修复并返回 `BLOCKED`。

---

## 14. 修复与验证闭环

### 14.1 修复计划

`RepairAgent` 在执行前应生成：

| 字段 | 内容 |
|---|---|
| `repair_id` | 修复编号 |
| `root_cause_ids` | 对应根因 |
| `actions` | 有序操作列表 |
| `preconditions` | 执行前置条件 |
| `expected_effect` | 预期效果 |
| `risk_level` | `low`、`medium` 或 `high` |
| `rollback_plan` | 回滚步骤 |
| `timeout` | 单个操作超时时间 |

### 14.2 执行要求

1. 每个操作执行前检查时间预算；
2. 每个操作必须设置超时；
3. 命令执行后记录返回码和输出摘要；
4. 任一关键操作失败时停止后续操作；
5. 必要时立即执行回滚；
6. 每轮完成修复后进入验证，不得自行宣布成功。

### 14.3 验证顺序

1. 基础进程和端口检查；
2. 服务健康接口；
3. 基本业务冒烟测试；
4. 回归测试；
5. 受控压力测试；
6. 生成结构化验证结果。

### 14.4 重试规则

1. 默认最大修复次数为 2；
2. 验证失败后，`VerifierAgent` 应返回具体失败项；
3. `RepairAgent` 的新方案应显式引用上一轮失败结果；
4. 不得无修改地重复同一修复方案；
5. 达到上限后返回 `UNRESOLVED`；
6. 每轮重试形成新的 `N6.k` 和 `N7.k` 任务实例。

---

## 15. 异常处理

| 异常 | 处理策略 | 最终状态 |
|---|---|---|
| 模型调用超时 | 按任务策略重试，超过次数后终止该任务 | `FAILED_FINAL` |
| 工具执行超时 | 终止当前操作并按计划回滚 | `FAILED_RETRYABLE` 或 `ABORTED` |
| Agent 输出不符合 Schema | 请求一次结构修复，仍失败则任务失败 | `FAILED_FINAL` |
| 前置证据缺失 | `N5` 不启动，返回证据不足 | `BLOCKED` |
| 证据相互冲突 | 停止修复，报告冲突项 | `BLOCKED` |
| 修复验证失败 | 进入下一轮修复，直至达到上限 | `UNRESOLVED` |
| 越权操作 | 立即终止并保留审计记录 | `ABORTED` |
| 总时间耗尽 | 停止派发新任务，执行必要清理 | `ABORTED` |
| 容器或目标失联 | 终止修复并记录环境错误 | `ABORTED` |

任何异常均不得静默忽略。

---

## 16. 可观测性

### 16.1 Trace 字段

每条 Trace 至少包含：

```json
{
  "trace_id": "trace-0001",
  "incident_id": "inc-20261115-001",
  "task_id": "N1",
  "agent_id": "log-agent-01",
  "event_type": "TASK_FINISHED",
  "status": "SUCCEEDED",
  "timestamp": "2026-11-15T12:04:10+08:00",
  "duration_ms": 5230,
  "token_usage": {
    "prompt": 1800,
    "completion": 420
  },
  "tool_calls": 6,
  "retry_count": 0,
  "parent_task_id": "N0"
}
```

### 16.2 必须记录的事件

1. 故障事件创建；
2. DAG 实例化；
3. 任务进入就绪队列；
4. 任务分配；
5. Agent 开始和结束；
6. Agent 消息发送与接收；
7. 工具调用和结果；
8. 状态迁移；
9. 重试；
10. 修复动作与回滚；
11. 验证项结果；
12. 最终报告生成。

### 16.3 可视化要求

界面应至少展示：

- 当前任务 DAG 及节点状态；
- 各 Agent 当前职责；
- 并行任务时间线；
- Agent 双向消息图；
- 根因证据链；
- 修复与验证轮次；
- 串行与并发总耗时对比。

---

## 17. 外部接口

### 17.1 故障事件接口

| 方法 | 路径 | 功能 |
|---|---|---|
| `POST` | `/api/v1/incidents` | 创建故障处理任务 |
| `GET` | `/api/v1/incidents/{incident_id}` | 查询状态与最终报告 |
| `GET` | `/api/v1/incidents/{incident_id}/dag` | 查询任务 DAG |
| `GET` | `/api/v1/incidents/{incident_id}/events` | 查询 Trace 和消息 |
| `POST` | `/api/v1/incidents/{incident_id}/cancel` | 取消任务 |

### 17.2 状态响应

```json
{
  "incident_id": "inc-20261115-001",
  "state": "RUNNING",
  "current_tasks": ["N1", "N2", "N3", "N4"],
  "completed_tasks": ["N0"],
  "repair_attempt": 0,
  "elapsed_seconds": 42,
  "final_report": null
}
```

接口字段一旦被前端、测试和评测代码使用，应按第 20 章变更控制处理。

---

## 18. 安全与隔离

1. 所有修复操作应在 Docker 容器或虚拟机内执行；
2. 不得默认操作比赛宿主机；
3. 工具应使用命令白名单和路径白名单；
4. 文件写入必须限制在 `allowed_scope.write_paths`；
5. 读取操作应限制在 `allowed_scope.read_paths`；
6. 高风险命令执行前必须完成回滚方案生成；
7. 敏感信息不得写入模型 Prompt 或公开日志；
8. 每次工具调用应记录调用方、命令、参数、返回码和时间；
9. 应提供容器快照重置机制，保证评测可重复；
10. 系统应支持一键停止和清理运行资源。

---

## 19. 评测规范

### 19.1 测试场景要求

区域赛基准集应不少于 6 个场景，并覆盖至少 4 类故障：

1. 端口或网络配置错误；
2. 文件权限错误；
3. 服务依赖缺失；
4. 数据库连接配置错误；
5. 磁盘空间异常；
6. 运行状态与配置文件不一致。

每个场景应包含：

- 固定基础镜像；
- 故障注入脚本；
- 环境重置脚本；
- 预期根因；
- 健康检查；
- 冒烟测试；
- 回归测试；
- 压力测试配置；
- 允许操作范围。

### 19.2 正确性指标

| 指标 | 定义 |
|---|---|
| 服务恢复率 | 验证通过的事件数 / 总事件数 |
| 根因识别准确率 | 正确识别根因的事件数 / 总事件数 |
| 回归通过率 | 通过的回归测试项 / 总回归测试项 |
| 修复成功率 | 首次或重试后修复通过的事件数 / 总事件数 |
| 越权操作次数 | 被安全策略阻止或实际越界的操作次数 |

区域赛内部验收目标：

- 服务恢复率不低于 90%；
- 根因识别准确率不低于 80%；
- 回归测试通过率不低于 95%；
- 越权操作次数为 0。

### 19.3 串行基线

串行基线应按如下顺序执行同一组 Agent：

```text
N0 → N1 → N2 → N3 → N4 → N5 → N6.1 → N7.1
```

发生重试验证时继续顺序执行：

```text
N6.2 → N7.2 → N6.3 → N7.3
```

### 19.4 并发执行

并发模式应保持相同 DAG、Agent 和 Prompt，仅允许满足依赖关系的任务并发执行。`N1` 至 `N4` 必须同时派发。

### 19.5 公平性控制

串行组和并发组应满足：

1. 相同硬件；
2. 相同模型、量化和推理后端；
3. 相同 Prompt 版本；
4. 相同温度、最大输出 token 和工具上限；
5. 相同容器快照和场景数据；
6. 相同预热次数；
7. 从环境重置完成后开始计时；
8. 在最终报告生成后停止计时；
9. 模型加载和服务启动时间不计入主流程耗时，但应单独记录；
10. 每组至少执行 5 次，并报告均值、中位数和 p95。

### 19.6 提速指标

```text
speedup = (serial_time - parallel_time) / serial_time
```

正式验收要求：

- 平均总时间减少不少于 20%；
- 并发模式正确性不得低于串行模式；
- 不得通过减少任务、缩短 Prompt 或降低输出上限制造虚假提速。

内部开发目标宜不低于 30%，以抵消现场环境波动。

### 19.7 实验产物

每次正式实验应输出：

- 场景版本；
- 软件版本；
- 模型与后端配置；
- 串行和并发原始耗时；
- 正确性结果；
- token 使用量；
- 工具调用次数；
- 重试次数；
- 失败样本与日志。

---

## 20. 变更控制

### 20.1 冻结项

以下内容变更应新建变更请求，并形成文档新版本：

1. Agent 类型及其核心职责；
2. `N0` 至 `N7` 的节点定义；
3. 主 DAG 的依赖关系；
4. 第一轮四任务并行约束；
5. I1、I2、I3 三组双向交互；
6. 任务状态机；
7. 修复次数上限及其语义；
8. 安全边界；
9. 串行和并发评测口径；
10. 正确性与 20% 提速门槛；
11. 外部接口字段。

### 20.2 可调整项

以下内容可在不改变流程语义的前提下调整：

1. 线程、协程或消息队列实现；
2. 向量数据库和结构化数据库选型；
3. 前端框架与图形样式；
4. 日志格式的附加字段；
5. Prompt 文案；
6. 工具内部实现；
7. 场景数量增加；
8. 性能优化手段。

### 20.3 变更流程

任何冻结项变更应完成：

1. 建立 `CR-xxx` 变更请求；
2. 说明变更原因；
3. 分析对 DAG、接口、测试和评测的影响；
4. 两人共同确认；
5. 指导教师审核；
6. 更新版本号；
7. 新增兼容性测试；
8. 保留旧版本结果。

未经上述流程，开发代码不得偏离本规格。

---

## 21. 工程结构

本节定义实际仓库路径。唯一 Python 包根目录为
`src/aios_incident/`；架构文档中的 Agent、编排、适配器和工具层均落实为该包内模块。
场景夹具、配置、测试、脚本和文档保留在仓库根目录。

```text
aios-linux-incident/
├─ src/
│  └─ aios_incident/
│     ├─ __init__.py
│     ├─ models.py
│     ├─ state.py
│     ├─ validation.py
│     ├─ agent_base.py
│     ├─ api.py
│     ├─ agents/
│     │  ├─ __init__.py
│     │  ├─ coordinator_agent.py
│     │  ├─ log_agent.py
│     │  ├─ metrics_agent.py
│     │  ├─ config_agent.py
│     │  ├─ dependency_agent.py
│     │  ├─ repair_agent.py
│     │  └─ verifier_agent.py
│     ├─ orchestrator/
│     │  ├─ __init__.py
│     │  ├─ incident_manager.py
│     │  ├─ dag.py
│     │  ├─ scheduler.py
│     │  ├─ capability_matcher.py
│     │  ├─ interaction_bus.py
│     │  ├─ blackboard.py
│     │  ├─ trace.py
│     │  ├─ diagnosis.py
│     │  └─ minimal_flow.py
│     ├─ adapters/
│     │  ├─ __init__.py
│     │  ├─ aios_client.py
│     │  ├─ llm_adapter.py
│     │  ├─ memory_adapter.py
│     │  └─ tool_adapter.py
│     ├─ tools/
│     │  ├─ __init__.py
│     │  ├─ gateway.py
│     │  ├─ base.py
│     │  ├─ log_reader.py
│     │  ├─ metrics_collector.py
│     │  ├─ config_inspector.py
│     │  ├─ dependency_inspector.py
│     │  ├─ repair.py
│     │  └─ verify.py
│     ├─ benchmark/
│     │  ├─ __init__.py
│     │  ├─ serial.py
│     │  ├─ parallel.py
│     │  ├─ metrics.py
│     │  └─ report.py
│     └─ ui/
│        └─ __init__.py
├─ scenarios/
│  ├─ common/
│  ├─ f1/
│  ├─ f2/
│  ├─ f3/
│  ├─ f4/
│  ├─ f5/
│  └─ f6/
├─ config/
├─ scripts/
├─ tests/
├─ docs/
├─ pyproject.toml
└─ README.md
```

### 21.1 逻辑层与包路径对应关系

| 规格中的逻辑层 | 实际代码路径 |
|---|---|
| Agent 执行层 | `src/aios_incident/agents/` |
| 任务编排层 | `src/aios_incident/orchestrator/` |
| AIOS、LLM、记忆与工具适配层 | `src/aios_incident/adapters/` |
| 受控工具层 | `src/aios_incident/tools/` |
| 评测层 | `src/aios_incident/benchmark/` |
| Web 后端/API | `src/aios_incident/api.py` |
| Web 前端 | `src/aios_incident/ui/` |
| 故障场景与容器夹具 | 仓库根目录 `scenarios/` |

跨模块公共对象放在包根目录的 `models.py`、`state.py`、`validation.py` 和
`agent_base.py`。任何实现不得再创建平行的顶层 `agents/`、`orchestrator/` 或
`adapters/` 目录。

---

## 22. 测试要求

### 22.1 单元测试

至少覆盖：

- DAG 拓扑排序；
- 依赖满足判断；
- 能力匹配；
- 任务状态迁移；
- 双向消息配对；
- 证据去重与冲突检测；
- 修复次数上限；
- 超时与取消；
- 命令白名单；
- 路径白名单；
- 报告序列化。

### 22.2 集成测试

至少覆盖：

- `N1` 至 `N4` 并发派发；
- `N5` 等待全部前置任务；
- I1、I2、I3 三组双向交互；
- 首次修复成功；
- 首次验证失败后二次修复；
- 二次修复失败后终止；
- 前置证据缺失时阻塞；
- 越权操作被阻断；
- 最终报告字段完整。

### 22.3 回归测试

每次影响调度器、Agent 协议、状态机或修复工具的修改，均应重新执行：

1. 单元测试；
2. 六个基准场景；
3. 串行与并发对照；
4. 正确性检查；
5. 安全策略检查。

---

## 23. 区域赛交付与全国赛扩展

### 23.1 区域赛最低交付

- 可运行源码；
- Docker 或虚拟机环境配置；
- 固定故障场景；
- 七类 Agent；
- 固定 DAG 调度器；
- 三组双向交互；
- 串行与并发测试脚本；
- 正确性测试脚本；
- 设计文档；
- 代码注释；
- AI 工具使用说明；
- 演示视频及 README 链接；
- 合法开源许可证及第三方组件声明。

### 23.2 全国初赛扩展方向

在不修改主流程语义的前提下，可增加：

1. 动态能力匹配策略；
2. 多故障并发场景；
3. Agent 超时后的任务重分配；
4. 共享记忆与历史事件复用；
5. 调度策略对照实验；
6. 资源占用与 token 成本分析；
7. 更完整的任务可视化和证据链；
8. 扩展场景数量与故障类型。

若全国赛需要修改主 DAG 或状态机，应按第 20 章建立新版本，不得在区域赛基线版本中直接覆盖。

---

## 24. 最终验收条件

本系统达到以下条件后，方可视为区域赛基线实现完成：

1. 七类 Agent 均可独立注册并接受调度；
2. `N1` 至 `N4` 在同一次调度中并发启动；
3. `N5` 严格等待四路证据完成；
4. 至少实现 I1、I2、I3 三组真实双向交互；
5. 修复流程具备回滚方案和最多两次重试；
6. 验证结果由自动测试产生；
7. 六个场景中服务恢复率不低于 90%；
8. 根因识别准确率不低于 80%；
9. 回归测试通过率不低于 95%；
10. 越权操作为 0；
11. 并发平均总时间较串行减少不少于 20%；
12. 全部状态、消息、工具调用和重试均有 Trace；
13. 系统可在干净环境中按文档重新部署；
14. 文档、代码注释、AI 使用说明和演示视频齐备。

未满足上述任一条件时，不得将系统标记为“区域赛基线完成”。

