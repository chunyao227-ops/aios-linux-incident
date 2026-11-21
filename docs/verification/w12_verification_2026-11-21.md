# W12 验收记录

## 状态

已完成。W12 实现提交号在提交后补记于本文件。

## 基线与环境

- 日期：2026-11-21。
- 前置基线：`1f540b5`（W11 验收完成）。
- Docker Engine：29.1.3。
- 基础镜像：`aios-scenario-base:1.0`。
- Python 场景运行时：3.10 slim。
- 容器网络：`--network none`。
- 宿主机业务数据：未使用。

## 六个场景

| ID | 故障类型 | 失败信号 | 修复 |
|---|---|---|---|
| F1 | 端口配置错误 | 配置端口与监听端口不一致 | 恢复端口配置 |
| F2 | 文件权限错误 | 状态文件不可读 | 恢复文件权限 |
| F3 | 服务依赖缺失 | 数据库依赖进程停止 | 启动依赖 |
| F4 | 数据库连接配置错误 | 数据库端口错误 | 恢复数据库端口 |
| F5 | 磁盘空间异常 | 16 MiB tmpfs 使用率超阈值 | 删除故障填充文件 |
| F6 | 运行状态与配置不一致 | runtime mode 与 config mode 不同 | 恢复运行状态 |

## 场景目录

每个场景均提供：

```text
scenario.yaml
start.sh
inject.sh
repair.sh
verify.sh
pressure.sh
hash.sh
reset.sh
destroy.sh
```

`scenario.yaml` 保存预期根因和允许修复范围，仅用于测试和人工验收。
该文件不会挂载进容器，也不会通过 Agent、API、Prompt 或 ToolGateway 暴露。

## 容器隔离

- 根文件系统只读。
- `/etc/demo`、`/var/lib/demo`、`/run/demo` 和 `/tmp` 使用受限 tmpfs。
- F5 的 `/var/lib/demo` 限制为 16 MiB。
- 不开放宿主机端口。
- 容器内仅运行固定 Python 服务和依赖服务。
- 所有失败均可通过销毁容器恢复。

## 场景验收流程

每个场景执行：

```text
baseline verify
-> inject
-> verify must fail
-> repair
-> verify must pass
-> pressure must pass
-> reset
-> reset hash must equal baseline hash
-> destroy
```

测试还会为每个场景执行 W09 三对固定双向交互：

```text
LogAgent <-> ConfigAgent
MetricsAgent <-> DependencyAgent
RepairAgent <-> VerifierAgent
```

## 执行记录

### 默认回归

```powershell
.\tasks.ps1 verify
```

结果：

```text
All checks passed!
57 files already formatted
155 passed, 8 skipped in 4.97s
configuration valid: aios-linux-incident
```

8 个跳过项：

- 2 个真实 AIOS 测试；
- 6 个 Docker 场景测试。

### 六场景 Docker 测试

```powershell
.\tasks.ps1 scenarios
```

结果：6 个场景全部通过。

每个场景均验证：

- 基线健康；
- 注入后失败；
- 修复后健康、冒烟和回归通过；
- 20 次受控压力请求通过；
- 重置前后环境哈希一致；
- 三对 Agent 双向交互成立；
- 销毁后无残留容器。

### 全量真实环境

```powershell
$env:RUN_AIOS_INTEGRATION='1'
$env:RUN_DOCKER_SCENARIOS='1'
.\.venv\Scripts\python.exe -m pytest -o addopts='' -W error
```

结果：

```text
163 passed in 140.72s (0:02:20)
```

### 编译与安全

- 源码和场景控制程序 `compileall`：通过。
- `pip check`：`No broken requirements found.`
- 未发现 `shell=True`、`os.system`、rm -rf、sudo 或 mkfs 调用。
- Docker 场景控制程序仅使用固定参数调用 Python 子进程。

## 验收项对照

| W12 验收要求 | 结果 |
|---|---|
| 六个故障场景均可执行 | 通过 |
| 每个场景有启动脚本 | 通过 |
| 每个场景有故障注入脚本 | 通过 |
| 每个场景有重置脚本 | 通过 |
| 每个场景有销毁脚本 | 通过 |
| 每个场景有预期根因 | 通过，标准答案不暴露 |
| 每个场景有允许修复集合 | 通过 |
| 每个场景有验收脚本 | 通过 |
| 每个场景至少三对双向交互 | 通过 |
| 失败与成功结果可验证 | 通过 |
| 重置后环境哈希一致 | 通过 |
| 不直接修改宿主机 | 通过 |
| 不使用生产凭据或真实数据 | 通过 |

## 当前限制

- 场景为固定合成服务，不包含真实第三方业务系统。
- F5 使用受限 tmpfs 模拟磁盘压力，避免污染宿主机磁盘。
- 六场景必须通过显式 `RUN_DOCKER_SCENARIOS=1` 运行。
- 正式串行/并发测量属于 W13。

## 提交材料状态

- 场景夹具：`scenarios/f1` 至 `scenarios/f6`。
- 公共镜像和控制程序：`scenarios/common/`。
- 场景目录说明：`docs/scenarios/scenario_catalog.md`。
- 自动化测试：`tests/scenarios/test_all_scenarios.py`。
- 命令和结果：本文件。
- 六场景截图和录屏：尚未制作。

