# 六个故障场景目录

## 场景总览

| ID | 故障类型 | 注入结果 | 允许修复 |
|---|---|---|---|
| F1 | 端口或网络配置错误 | 配置端口与监听端口不一致 | 恢复端口配置 |
| F2 | 文件权限错误 | 运行状态文件不可读 | 恢复状态文件权限 |
| F3 | 服务依赖缺失 | 数据库依赖进程停止 | 启动依赖进程 |
| F4 | 数据库连接配置错误 | 配置数据库端口错误 | 恢复数据库端口 |
| F5 | 磁盘空间异常 | 16 MiB tmpfs 使用率超过阈值 | 删除故障填充文件 |
| F6 | 运行状态与配置不一致 | 运行状态为 degraded，配置为 healthy | 恢复运行状态 |

## 每个场景的组成

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

公共镜像位于 `scenarios/common/`，所有场景使用同一个不可变 Python 3.10
基础镜像。

## 隔离边界

- 容器使用 `--network none`，仅可访问自身 loopback。
- 根文件系统只读。
- `/etc/demo`、`/var/lib/demo`、`/run/demo` 使用 tmpfs。
- F5 的 `/var/lib/demo` 限制为 16 MiB。
- 场景运行无需宿主机端口映射。
- 不使用生产凭据或真实用户数据。

## 标准答案隔离

`scenario.yaml` 包含预期根因和允许修复集合，仅用于场景测试与人工验收。
该目录不会挂载到容器中，也不会通过 API、Prompt 或 ToolGateway 暴露给 Agent。

## 验收流程

每个场景按以下顺序执行：

```text
start
-> baseline verify
-> inject
-> verify must fail
-> repair
-> verify must pass
-> pressure
-> reset
-> hash equals baseline
-> destroy
```

除容器验收外，每个场景还执行 W09 的三对双向 Agent 交互矩阵。

## 运行

```powershell
$env:RUN_DOCKER_SCENARIOS='1'
.\.venv\Scripts\python.exe -m pytest tests\scenarios\test_all_scenarios.py -v
```

Windows 环境通过 WSL2 Ubuntu 调用 Docker Engine。
