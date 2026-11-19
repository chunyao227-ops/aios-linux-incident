# W02 验收记录

## 状态

已完成。W02 实现提交号在提交后补记于本文件。

## 基线与环境

- 日期：2026-11-19。
- 基线提交：`fb5a0f0`（W00/W01A 与 W02 结构同步文档）。
- Windows Python：3.10.11。
- 项目包版本：`aios-linux-incident 0.1.0`。
- 本地模型配置：`http://127.0.0.1:11434/v1`，`qwen2:7b-instruct`。

## 执行记录

### 依赖安装

```powershell
.\tasks.ps1 setup
```

结果：editable 安装成功；新增 PyYAML 6.0.3、pytest 8.4.2、Ruff 0.17.5。

```powershell
.\.venv\Scripts\python.exe -m pip check
```

结果：`No broken requirements found.`

### 静态检查

```powershell
.\tasks.ps1 lint
```

结果：`All checks passed!`

### 自动化测试

```powershell
.\tasks.ps1 test
```

结果：`21 passed in 0.17s`。

覆盖内容：

- 根包、公共占位模块和六个子包可导入；
- 仓库根目录不存在平行的代码目录；
- 示例配置可加载；
- 仅修改 YAML 即可切换到远程模型端点；
- 密钥仅从环境变量读取，公开配置不包含密钥；
- 配置中的未知字段和非 HTTP(S) 端点被拒绝；
- UTC 时间戳和唯一 ID 生成。

### 配置检查

```powershell
.\tasks.ps1 check-config
```

结果：

```text
configuration valid: aios-linux-incident
```

### 包入口

```powershell
.\.venv\Scripts\aios-incident.exe --config config/app.example.yaml
```

结果：

```text
configuration valid: aios-linux-incident
```

### 包导入

```powershell
.\.venv\Scripts\python.exe -c "import aios_incident, aios_incident.agents, aios_incident.orchestrator, aios_incident.adapters, aios_incident.tools, aios_incident.benchmark, aios_incident.ui; print(aios_incident.__version__)"
```

结果：`0.1.0`。

## 目录约束核验

- 唯一代码根目录：`src/aios_incident/`。
- 六个子包：`agents/`、`orchestrator/`、`adapters/`、`tools/`、`benchmark/`、`ui/`。
- 仓库根目录对应六个平行目录均不存在。
- W02 未实现 W03 数据契约、W04 适配器、Agent 业务逻辑或 W14 API。

## 提交材料状态

- 终端文本证据：本文件已保存。
- 源码注释和模块 docstring：已保存于 `src/`。
- 测试代码：已保存于 `tests/`。
- AI 使用说明：已更新 `docs/ai_usage/AI_USAGE.md`。
- 截图及最终演示视频：尚未制作。

