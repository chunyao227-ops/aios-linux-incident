# 基于 AIOS 的 Linux 服务故障诊断、修复与回归验证系统

## AI 开发工单与执行约束

> 工单版本：1.0  
> 制定日期：2026-11-18  
> 使用方式：后续向 AI 发送“按 B 文档执行 Wxx”，AI 必须只执行当前工单及其前置未完成项。  
> 当前开发条件：本地 RTX 8 GB、16 GB 内存；云 GPU 仅在资源可用时用于正式测试。  
> 区域赛提交截止：2026-12-27。  
> 全国初赛提交截止：2027-05-01。

---

## 0. 强制约定

### 0.1 工单执行规则

1. AI 在执行任何工单前，必须先读取本文件、`02_AIOS_Linux故障协同诊断系统_开发规格_v1.0.md`、当前仓库结构和 Git 工作区状态。
2. AI 不得跳过前置未完成的工单，不得用提示词或临时脚本替代正式接口。
3. 每个工单完成后必须执行验收命令，并报告修改文件、测试结果、未解决问题和下一工单。
4. AI 不得在代码、配置、日志或文本文档中保存阿里云账号、密码、AccessKey、SSH 私钥或模型 API Key。
5. AI 不得直接操作云账号、购买资源、修改安全组或创建公网端口。账户持有人负责云端开通与费用确认。
6. 默认使用本地模型推进代码开发；云端 GPU 不可用不构成停止开发的理由。
7. 所有业务流程以开发规格中的固定 DAG、七类 Agent、四路并行、三对双向交互和最多两次修复重试为准。
8. 未经用户明确要求，AI 不新增无关框架、数据库、前端框架或外部模型 API。
9. 优先保证“故障上报 -> Agent 分析 -> LLM 调用 -> 修复 -> 验证”最小闭环，禁止先做视觉美化。
10. 代码修改使用最小覆盖面原则，先补测试再改流程代码。

### 0.2 工单请求模板

用户后续可以直接发送：

```text
按 B 文档执行 W01。
当前环境：<可用/不可用，补充异常信息>
本次不要执行后续工单。
```

AI 回复必须包含：

```text
工单：Wxx
前置检查：
完成内容：
修改文件：
验收结果：
剩余风险：
建议下一工单：
```

### 0.3 仓库基线

```text
aios-linux-incident/
  agents/
    coordinator/
    log/
    metrics/
    config/
    dependency/
    repair/
    verifier/
  orchestrator/
    planner.py
    scheduler.py
    interaction_bus.py
    blackboard.py
  tools/
    gateway.py
    logs.py
    metrics.py
    configs.py
    dependencies.py
    repair.py
    verify.py
  scenarios/
    common/
    f1/
    f2/
    f3/
    f4/
    f5/
    f6/
  benchmark/
    serial.py
    parallel.py
    metrics.py
    report.py
  api/
  ui/
  config/
  tests/
    unit/
    integration/
    scenarios/
    e2e/
  docs/
    architecture/
    specifications/
    ai_usage/
    experiment_reports/
  scripts/
  README.md
```

---

## 1. 总体依赖图

```text
W00 规则、版本、资源与仓库基线
  |
  +--> W01A 本地环境 -------------------------+
  |                                          |
  +--> W01B 云端 GPU（可选，并行） -----------+
                                             v
                              W02 仓库脚手架与配置
                                             |
                                             v
                              W03 公共数据契约
                                             |
                    +------------------------+-----------------------+
                    |                                                |
                    v                                                v
            W04 AIOS/LLM 适配器                             W05 故障 API/黑板/Trace
                    |                                                |
                    +------------------------+-----------------------+
                                             v
                              W06 受控工具网关
                                             |
                                             v
                              W07 最小核心闭环
                                             |
                        +--------------------+--------------------+
                        |                                         |
                        v                                         v
              W08 DAG 调度与四路采集                    W09 消息总线与三对交互
                        |                                         |
                        +--------------------+--------------------+
                                             v
                              W10 诊断融合与证据链
                                             |
                                             v
                              W11 修复与验证闭环
                                             |
                                             v
                              W12 六个故障场景
                                             |
                    +------------------------+-----------------------+
                    |                                                |
                    v                                                v
            W13 串行/并发基准                               W14 前端与可观测性
                    |                                                |
                    +------------------------+-----------------------+
                                             v
                              W15 测试、加固与复现
                                             |
                                             v
                              W16 文档、AI 使用说明、录屏与提交
                                             |
                                             v
                              W17 国赛阶段能力扩展
```

### 1.1 串行关键路径

```text
W00 -> W01A -> W02 -> W03 -> W04 -> W06 -> W07
    -> W08 -> W10 -> W11 -> W12 -> W13 -> W15 -> W16
```

### 1.2 可并行任务

- W01A 与 W01B 可以在不同机器并行，但 W01A 是必做路径。
- W04 与 W05 在 W03 完成后并行。
- W08 与 W09 在 W07 完成后并行开发，集成时必须共同验收。
- W12 场景夹具与 W14 界面可以在核心闭环结束后并行。
- 文档和 AI 使用记录从 W00 开始持续维护。

---

## 2. 工单 W00：规则、版本、资源与仓库基线

### 目的

冻结影响全部开发和提交的外部条件，避免中途因版本、服务器或赛题解释变化重做。

### 输入

- 赛题章程和技术方案；
- 指导教师关于云资源和 GPU 的确认；
- 阿里云权益、GPU 配额和费用承担方式；
- 当前 Git 仓库或空目录；
- 用户可投入时间与两名队员分工。

### 输出

```text
docs/project_baseline.md
docs/open_questions.md
docs/ai_usage/AI_USAGE.md
README.md
```

### 执行指令

1. 建立项目基线与未决问题清单。
2. 记录区域赛截止日、全国赛截止日、团队人数、指导教师和当前硬件。
3. 记录 AIOS、Cerebrum、Python、模型、量化格式和推理后端的候选版本。
4. 记录云 GPU 是否可用于正式评测，不能确认的项写入未决清单，不得假定。
5. 初始化 Git 仓库，建立 `.gitignore`，排除模型权重、缓存、日志、密钥和临时容器数据。
6. 建立 AI 使用记录模板，要求记录日期、工具、用途、提示词摘要、生成文件、人工修改和验证方式。

### 约束

- 不得把账号、AccessKey、密码或私有地址写入仓库。
- 不得在版本未确认前固定依赖到任意远程分支。
- 不得因云资源未批准而停止本地开发。

### 验收

- 四项日期、版本和资源条件均可在仓库中查询。
- 所有未确认事项均有负责人和解决期限。
- `git status` 仅包含预期文件。

---

## 3. 工单 W01A：本地 AIOS 与模型环境

### 前置

- W00 完成。

### 输入

- Windows 11 笔记本；
- RTX 8 GB 显卡；
- 16 GB 系统内存；
- WSL2 或可直接使用的 Ubuntu；
- 正式路径：远程 GPU vLLM 服务地址和 7B AWQ 4bit 模型；
- 本地调试替身：WSL2 Ollama 和 Qwen2 7B Q4_K_M。

### 输出

```text
scripts/env/check_windows_gpu.ps1
scripts/env/setup_aios_env.sh
scripts/env/check_aios.py
scripts/env/check_model_endpoint.py
scripts/env/install_ollama_wsl.sh
scripts/env/start_ollama_wsl.sh
scripts/env/stop_ollama_wsl.sh
scripts/env/create_ollama_model_wsl.sh
scripts/env/activate_local_model.sh
config/model.local.yaml
config/model.remote.yaml.example
docs/environment/local_environment.md
docs/environment/concurrency_probe_results.json
```

### 执行指令

1. 检查 GPU 型号、显存、驱动、CUDA 兼容性和当前占用：

```powershell
nvidia-smi
wsl --status
wsl -l -v
docker --version
python --version
git --version
```

2. 在 WSL2 Ubuntu 中建立 Python 3.10 或 3.11 虚拟环境。
3. 按已锁定版本安装 AIOS 和 Cerebrum，禁止在未记录的情况下升级依赖。
4. 正式路径配置远程 vLLM OpenAI 兼容接口，模型为 7B AWQ 4bit。
5. 远程接口暂不可用时，在 WSL2 安装 Ollama，并通过 ModelScope 获取 Qwen2 7B Q4_K_M GGUF 作为本地逻辑调试替身。
6. 补齐并验证以下三项模型参数：

```text
MODEL_BASE_URL=http://127.0.0.1:11434/v1
MODEL_NAME=qwen2:7b-instruct
MODEL_API_KEY=
```

7. 配置 AIOS 的模型后端、内核地址和日志目录。
8. 启动 AIOS，验证健康接口。
9. 调用一次普通文本和一次 JSON 输出，保存原始响应与耗时。
10. 编写并发探测脚本：同一 Prompt 分别执行 1 次、串行 4 次和并发 4 次，输出：

```json
{
  "model": "qwen2:7b-instruct",
  "backend": "ollama-local",
  "gpu_memory_total_mb": 8192,
  "serial_4_total_sec": 0.0,
  "parallel_4_total_sec": 0.0,
  "parallel_speedup": 0.0,
  "errors": []
}
```

### 约束

- 同一模型服务必须被所有 Agent 共享，禁止为每个 Agent 复制一份模型。
- 本地环境通过 `MODEL_BASE_URL`、`MODEL_NAME` 和可选 `MODEL_API_KEY` 访问模型服务。
- 本地 Ollama 仅用于逻辑调试，不得替代远程 vLLM 的正式性能验收。
- Ollama 本地调试应将 `OLLAMA_NUM_PARALLEL` 设置为 4。
- 模型上下文长度优先限制为 2048 至 4096。
- 单次输出 token 优先限制为 512 至 1024。
- 不安装无关大模型、图形编辑器和占用显存的程序。
- 记录真实耗时，不得用固定延时模拟并发。

### 验收

- `nvidia-smi` 能显示独立 GPU。
- Docker 可启动测试容器。
- AIOS `/status` 返回正常。
- 模型普通文本调用成功。
- 模型 JSON 调用可解析。
- 四请求探测产生原始记录。

### 阻塞处理

- 远程 vLLM 未就绪时，使用本地 Ollama 继续开发，不阻塞 W02。
- 若 16 GB 内存不足，关闭 Docker Desktop 非常用容器、减少上下文和并发限制。
- 若模型无法并发，记录队列行为，不修改业务指标。

---

## 4. 工单 W01B：云端 GPU 正式测试环境

### 前置

- W00 完成；
- 账户持有人已确认云资源、费用和访问方式；
- AI 不接触账号密码和支付信息。

### 输入

- 阿里云或实验室 GPU ECS；
- 建议 A10 24 GB 或同级别 GPU；
- Ubuntu 22.04 或可用的 Linux GPU 镜像；
- 公网或 VPN 访问方式；
- 已确认的代金券适用范围。

### 输出

```text
scripts/env/check_linux_gpu.sh
scripts/env/setup_cloud_aios.sh
docs/environment/cloud_environment.md
docs/environment/cloud_access_check.md
```

### 执行指令

1. 账户持有人创建按量付费 GPU 实例并限制安全组来源 IP。
2. 确认实例具备 NVIDIA 驱动、Docker、Python、Git。
3. 配置 80 至 100 GB 云盘用于依赖和模型缓存。
4. 安装锁定的 AIOS/Cerebrum。
5. 部署 7B/8B 的 AWQ/GPTQ 四比特模型或 Ollama 模型。
6. 固定服务端口与 SSH 访问方式，不向所有公网地址开放。
7. 执行单请求、串行四请求和并发四请求测试。
8. 形成开关机、模型缓存和成本控制说明。

### 约束

- 不得由 AI 操作云账号或费用。
- 不得把 AccessKey、SSH 私钥、模型 API Key 写入代码。
- 不得购买包月 GPU；默认按量付费，用完立即停机。
- 云端不可用时，项目继续使用 W01A 本地环境，不阻塞 W02。

### 验收

- `nvidia-smi`、`docker`、AIOS 健康检查和模型接口均成功。
- 四个并发请求有原始耗时。
- 服务器重启后可按文档恢复服务。
- 安全组未向 `0.0.0.0/0` 开放管理端口。

---

## 5. 工单 W02：仓库脚手架与配置

### 前置

- W01A 至少完成。

### 输入

- 冻结的工程结构；
- 已知 Python 版本；
- 模型后端与 AIOS 地址；
- 配置字段清单。

### 输出

```text
src/aios_incident/__init__.py
src/aios_incident/models.py
src/aios_incident/agent_base.py
src/aios_incident/agents/__init__.py
src/aios_incident/orchestrator/__init__.py
src/aios_incident/adapters/__init__.py
src/aios_incident/tools/__init__.py
src/aios_incident/benchmark/__init__.py
src/aios_incident/ui/__init__.py
config/app.example.yaml
config/model.example.yaml
tests/conftest.py
pyproject.toml
Makefile 或 tasks.ps1
```

### 执行指令

1. 以 `src/aios_incident/` 作为唯一 Python 包根目录，创建
   `agents/`、`orchestrator/`、`adapters/`、`tools/`、`benchmark/` 和 `ui/`
   子包，但暂不实现业务逻辑。
2. 建立配置加载机制，支持本地模型和云端模型切换。
3. 建立日志、异常、时间戳和 ID 生成工具。
4. 建立统一测试入口。
5. 添加 README 最小启动说明。

### 约束

- 配置中不得写真实密钥。
- 目录和数据模型必须与开发规格一致。
- 不在本工单实现 Agent 业务逻辑。

### 验收

- 包可安装或可导入。
- 空测试集可通过。
- `config/app.example.yaml` 可以在不修改代码的情况下切换模型地址。

---

## 6. 工单 W03：公共数据契约

### 前置

- W02 完成。

### 输入

- 开发规格中的数据对象定义；
- 固定任务 DAG；
- 状态枚举；
- 消息类型。

### 输出

```text
src/aios_incident/models.py
src/aios_incident/state.py
src/aios_incident/validation.py
tests/unit/test_models.py
tests/unit/test_state_machine.py
```

### 执行指令

1. 实现 RunContext、TaskNode、TaskDAG、AgentCard、Evidence、Message、Diagnosis、RepairPlan、RepairResult、VerificationResult、TraceEvent。
2. 实现 TaskNode 与 Workflow 状态枚举和合法迁移函数。
3. 实现 JSON Schema 校验入口。
4. 编写对象序列化、反序列化和非法字段测试。

### 约束

- 不得用自由文本替代结构化对象。
- 不得允许未知状态迁移。
- 不得允许 DAG 自引用或成环。

### 验收

- 单元测试全部通过。
- 非法 DAG、非法消息和非法状态迁移均被拒绝。
- 所有跨模块对象具有类型标注。

---

## 7. 工单 W04：AIOS 与 LLM 适配器

### 前置

- W03 完成。

### 输入

- AIOS/Cerebrum 运行地址；
- 模型配置；
- `LLMQuery` 与 `LLMResponse` 协议；
- Agent 名称和超时策略。

### 输出

```text
src/aios_incident/adapters/aios_client.py
src/aios_incident/adapters/llm_adapter.py
tests/unit/test_llm_adapter.py
tests/integration/test_aios_smoke.py
```

### 执行指令

1. 封装文本聊天和 JSON 输出调用。
2. 封装超时、重试、错误归一化和 token 统计。
3. 对模型响应执行任务级 Schema 校验。
4. 在测试中使用真实 AIOS 做最小冒烟，不在单元测试中依赖真实模型。

### 约束

- 不得直接调用供应商私有 SDK 绕过 AIOS。
- 不得默认无限重试。
- JSON 解析失败不得猜测字段。

### 验收

- 模拟响应测试通过。
- 真实 AIOS 冒烟测试通过。
- 错误响应能转换为统一错误对象。

---

## 8. 工单 W05：故障 API、黑板与 Trace

### 前置

- W03 完成。

### 输入

- Incident 输入 Schema；
- Blackboard 数据模型；
- Trace 字段。

### 输出

```text
src/aios_incident/api.py
src/aios_incident/orchestrator/blackboard.py
src/aios_incident/orchestrator/trace.py
tests/unit/test_blackboard.py
tests/integration/test_incident_api.py
```

### 执行指令

1. 实现故障上报、状态查询、结果查询和取消接口。
2. 实现 Blackboard 的写入、读取和产物引用。
3. 实现 JSONL Trace 记录。
4. 为每个故障生成唯一 Incident ID 和 Run ID。

### 约束

- API 不得包含云账号认证信息。
- Blackboard 不允许下游读取未完成产物。
- Trace 不允许覆盖已写入事件。

### 验收

- 可提交故障并查询运行状态。
- 一次运行可形成完整 JSONL Trace 文件。
- 非法 Incident 请求返回结构化错误。

---

## 9. 工单 W06：受控工具网关

### 前置

- W03 与 W05 完成。

### 输入

- Agent 工具权限表；
- 允许操作类型；
- 容器或目标环境信息；
- 路径、超时和输出限制。

### 输出

```text
src/aios_incident/tools/gateway.py
src/aios_incident/tools/base.py
tests/unit/test_tool_gateway.py
tests/integration/test_tool_isolation.py
```

### 执行指令

1. 实现统一 ToolRequest 与 ToolResult。
2. 实现工具白名单、Agent 权限、路径规范化和超时。
3. 先实现只读工具：日志读取、指标采集、配置读取、进程/端口查询。
4. 实现修复占位工具，但默认禁止真实写入。
5. 将所有工具调用写入 Trace。

### 约束

- 不得向 Agent 暴露任意 Shell。
- 不得访问宿主机工作目录之外的路径。
- 不得执行删除、格式化或权限提升操作。

### 验收

- 未授权工具调用被拒绝。
- 路径逃逸测试被拒绝。
- 只读工具能返回结构化结果。

---

## 10. 工单 W07：最小核心闭环

### 前置

- W01A、W02、W03、W04、W05、W06 完成。

### 输入

- 一个最小故障场景；
- 一个分析 Agent；
- 模拟或受控修复工具；
- 验证接口。

### 输出

```text
src/aios_incident/orchestrator/minimal_flow.py
agents/coordinator/
agents/log/
agents/repair/
agents/verifier/
tests/e2e/test_minimal_flow.py
docs/demo/minimal_flow.md
```

### 执行指令

1. 接收一个故障目标。
2. 调用 CoordinatorAgent 生成最小分析任务。
3. 调用 LogAgent 获取证据。
4. 调用 LLM 形成诊断。
5. 调用 RepairAgent 执行受控修复或受控模拟修复。
6. 调用 VerifierAgent 返回验证结果。
7. 保存完整 Trace 和最终报告。

### 约束

- 本工单只验证核心链路，不要求四路并行和三对交互。
- 不得跳过验证步骤直接返回成功。
- 修复失败必须进入失败分支。

### 验收

- 单场景可从上报走到验证完成。
- 成功和失败两条路径均可测试。
- 每个阶段均产生 Trace。

---

## 11. 工单 W08：DAG 调度与四路并行

### 前置

- W07 完成。

### 输入

- 固定七类 Agent；
- 四类证据采集任务；
- 任务 DAG；
- 并发上限和超时。

### 输出

```text
src/aios_incident/orchestrator/planner.py
src/aios_incident/orchestrator/scheduler.py
src/aios_incident/agents/log_agent.py
src/aios_incident/agents/metrics_agent.py
src/aios_incident/agents/config_agent.py
src/aios_incident/agents/dependency_agent.py
tests/integration/test_parallel_dispatch.py
```

### 执行指令

1. 实现 DAG 校验：唯一性、引用完整性、无环、能力匹配。
2. 实现 READY 集合计算和并发派发。
3. PLAN 完成后，同时启动四个采集节点。
4. 四个采集节点全部成功后才允许 DIAGNOSE 进入 READY。
5. 实现采集重试和失败终止规则。

### 约束

- 不得以串行方式调用四个采集 Agent 冒充并发。
- 并发上限不得低于 4。
- 不得在依赖未完成时提前启动下游节点。

### 验收

- Trace 中四路开始时间处于同一调度窗口。
- DIAGNOSE 开始时间晚于四个采集完成时间。
- 任一路失败会按策略重试或终止。

---

## 12. 工单 W09：消息总线与三对双向交互

### 前置

- W07 完成；可与 W08 并行开发，最终需共同验收。

### 输入

- 消息类型；
- 三对固定交互关系；
- correlation_id 规则；
- Trace 约束。

### 输出

```text
src/aios_incident/orchestrator/interaction_bus.py
src/aios_incident/agents/coordinator_agent.py
tests/integration/test_interaction_matrix.py
```

### 执行指令

1. 实现 QUERY、RESPONSE、REVIEW、FAILURE、VERIFIED 等消息。
2. 实现 LogAgent 与 ConfigAgent 的双向证据查询。
3. 实现 MetricsAgent 与 DependencyAgent 的双向核对。
4. 实现 RepairAgent 与 VerifierAgent 的修复验证反馈。
5. 生成消息图和双向边计数。

### 约束

- 同一 Agent 不得向自身发送用于满足交互指标的消息。
- 每条查询必须有对应响应或明确超时。
- 消息必须绑定 task_id 和 correlation_id。

### 验收

- 三对交互均有运行记录。
- 消息图中至少存在三条双向边。
- 断开任一 Agent 时，消息发送失败可被记录。

---

## 13. 工单 W10：诊断融合与证据链

### 前置

- W08 与 W09 完成。

### 输入

- 四类 Evidence；
- 交互消息；
- Diagnosis Schema。

### 输出

```text
src/aios_incident/orchestrator/diagnosis.py
tests/unit/test_diagnosis_fusion.py
tests/integration/test_evidence_chain.py
```

### 执行指令

1. 合并四类证据。
2. 建立时间、服务和实体关联。
3. 形成根因候选及支持证据引用。
4. 对被排除的假设保留理由。
5. 证据不足或冲突时发起条件式追问。

### 约束

- 每项根因至少引用一条有效 Evidence。
- 不得使用不存在的 evidence_id。
- 不得以自然语言结论替代结构化证据。

### 验收

- 根因—证据引用完整。
- 冲突证据能够触发追问。
- 空证据或缺失证据会失败关闭。

---

## 14. 工单 W11：修复与验证闭环

### 前置

- W10 完成。

### 输入

- Diagnosis；
- 允许修复集合；
- 验证用例；
- 最大修复轮次。

### 输出

```text
src/aios_incident/agents/repair_agent.py
src/aios_incident/agents/verifier_agent.py
src/aios_incident/tools/repair.py
src/aios_incident/tools/verify.py
tests/integration/test_repair_verification_loop.py
```

### 执行指令

1. 将诊断转换为受控修复计划。
2. 执行前校验权限、路径、目标容器和回滚条件。
3. 每次修复后发起 VerifierAgent REVIEW。
4. 验证失败返回 RepairAgent，最多两轮重试。
5. 两轮后仍失败则进入 FAILED。

### 约束

- 修复工具不得接受任意 Shell 字符串。
- RepairAgent 不得自行宣布成功。
- 验证失败不得被吞掉。

### 验收

- 一次成功修复完成闭环。
- 两次失败后正确终止。
- 每次修复均有 attempt_no 和验证结果。

---

## 15. 工单 W12：六个故障场景

### 前置

- W11 完成。

### 输入

- 六个已定义故障类型；
- Docker 或隔离 Linux 环境；
- 健康检查、业务回归和压力测试。

### 输出

```text
scenarios/common/
scenarios/f1/
scenarios/f2/
scenarios/f3/
scenarios/f4/
scenarios/f5/
scenarios/f6/
tests/scenarios/test_all_scenarios.py
docs/scenarios/scenario_catalog.md
```

### 执行指令

1. 为每个场景提供启动、故障注入、重置和销毁脚本。
2. 提供预期根因集合、允许修复集合和验收脚本。
3. 禁止向 Agent 暴露标准答案。
4. 每个场景至少产生三对双向交互。
5. 在干净快照上重复执行。

### 约束

- 不得直接修改宿主机。
- 不得使用不可恢复的手工环境。
- 不得用生产凭据或真实用户数据。

### 验收

- 六个场景均能执行。
- 每个场景均有可验证的失败与成功结果。
- 重置后环境哈希一致。

---

## 16. 工单 W13：串行与并发基准

### 前置

- W12 完成。

### 输入

- 六场景；
- 串行与并发模式；
- 固定模型、Prompt、工具权限和超时；
- 原始 Trace。

### 输出

```text
src/aios_incident/benchmark/serial.py
src/aios_incident/benchmark/parallel.py
src/aios_incident/benchmark/metrics.py
src/aios_incident/benchmark/report.py
docs/experiment_reports/benchmark_results.md
docs/experiment_reports/raw/
```

### 执行指令

1. 每场景预热一次，不计入统计。
2. 每场景每模式执行五次有效测量。
3. 记录开始、结束、模型耗时、工具耗时、token 和错误。
4. 计算每场景中位数和总体平均提速。
5. 输出正确性、消息完整性和越权操作统计。

### 约束

- 不得减少任务、缩短 Prompt 或降低验证标准制造提速。
- 不得混用本地和云端数据而不标注环境。
- 不得只保留汇总值而删除原始数据。

### 验收

- 原始数据和汇总表均存在。
- 平均提速不低于 20%。
- 正确性不因并发而下降。

---

## 17. 工单 W14：前端与可观测性

### 前置

- W07 至 W13 的数据结构稳定。

### 输入

- Trace Store；
- DAG 与状态；
- 消息记录；
- 修复与验证结果；
- 基准汇总。

### 输出

```text
src/aios_incident/ui/
src/aios_incident/api.py
tests/e2e/test_dashboard_flow.py
```

### 执行指令

1. 实现任务提交和状态查看。
2. 实现 DAG 节点状态和 Agent 分配展示。
3. 实现三对交互关系和消息计数。
4. 实现修复、验证时间线。
5. 实现串行/并发评测面板。
6. 提供任务取消接口。

### 约束

- UI 只读取真实数据，不得硬编码演示结果。
- 不先做动画和装饰。
- 核心流程图优先于样式美化。

### 验收

- 一次真实运行可在界面完整回放。
- 任务状态与 Trace 一致。
- 页面刷新后能够读取历史运行。

---

## 18. 工单 W15：测试、加固与复现

### 前置

- W14 完成。

### 输入

- 全部代码和场景；
- 依赖锁定；
- 干净 Ubuntu/WSL 环境。

### 输出

```text
tests/
scripts/install.sh
scripts/run_demo.sh
docs/testing/test_report.md
docs/environment/reproduce.md
```

### 执行指令

1. 运行单元、集成、场景和端到端测试。
2. 检查异常路径、超时、取消和恢复。
3. 在干净环境按 README 安装并运行。
4. 清理密钥、缓存、绝对路径和调试代码。
5. 校验所有许可证和第三方依赖说明。

### 约束

- 测试失败不得通过跳过标记隐藏。
- 不得把本机绝对路径写入提交脚本。
- 不得依赖未声明的全局环境。

### 验收

- 所有测试通过。
- 干净环境可复现。
- 无敏感信息。
- 无无效调试入口。

---

## 19. 工单 W16：文档、AI 使用说明、录屏与提交

### 前置

- W15 完成；
- 功能冻结。

### 输入

- 最终代码；
- 实验原始数据；
- 架构图、DAG 和流程图；
- AI 使用记录；
- 提交规则与视频要求。

### 输出

```text
README.md
docs/architecture/
docs/specifications/
docs/ai_usage/AI_USAGE.md
docs/experiment_reports/
docs/demo/demo_script.md
submission/
```

### 执行指令

1. 完成系统设计、实现、问题与解决过程文档。
2. 记录 AI 工具名称、版本、用途、提示词摘要、人工修改和验证。
3. 检查代码注释、目录说明和许可证。
4. 准备演示视频脚本，覆盖四路并行、三对交互、失败反馈和成功输出。
5. 录屏。
6. 在干净环境复演。
7. 打包提交。

### 约束

- 不得把 AI 使用说明遗漏到最后。
- 不得只展示结果而隐藏协作过程。
- 不得提交未验证版本。

### 验收

- 提交包包含所有必需材料。
- 视频与运行结果一致。
- README 可让他人复现。
- AI 使用说明完整。

---

## 20. 工单 W17：全国赛扩展

### 前置

- 区域赛提交已完成；
- 区域赛问题清单已形成。

### 输入

- 区域赛版本；
- 评审反馈；
- 新增故障场景和调度需求。

### 输出

```text
docs/national/roadmap.md
新增场景目录
调度策略对比实验
全国赛版本发布记录
```

### 执行指令

1. 在不破坏区域赛基线的前提下建立新版本分支。
2. 扩展动态任务分配、故障恢复、资源约束和场景数量。
3. 增加与串行、固定分配和本轮版本的可比较实验。
4. 更新全部文档和演示材料。

### 约束

- 全国赛扩展不得直接覆盖已提交区域赛版本。
- 涉及 DAG、状态机、消息和性能口径的修改必须进入变更流程。

### 验收

- 全国赛版本有独立版本号和变更记录。
- 新旧版本实验可比较。
- 原有核心流程不回归。

---

## 21. AI 执行命令速查

```text
按 B 文档执行 W00。
按 B 文档执行 W01A。
按 B 文档执行 W01B；账户持有人已完成云资源开通。
按 B 文档执行 W02。
按 B 文档执行 W03。
按 B 文档执行 W04。
按 B 文档执行 W05。
按 B 文档执行 W06。
按 B 文档执行 W07。
按 B 文档执行 W08。
按 B 文档执行 W09。
按 B 文档执行 W10。
按 B 文档执行 W11。
按 B 文档执行 W12。
按 B 文档执行 W13。
按 B 文档执行 W14。
按 B 文档执行 W15。
按 B 文档执行 W16。
按 B 文档执行 W17。
```

## 22. 当前执行建议

现在应依次执行：

1. `W00`
2. `W01A`
3. 若云资源已开通，再执行 `W01B`
4. `W02`
5. `W03`
6. `W04`
7. `W05`
8. `W06`
9. `W07`

在 W07 通过之前，不开展前端、视频和性能优化。
