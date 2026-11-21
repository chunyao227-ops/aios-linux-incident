"""Raw benchmark and Markdown report writers."""

from __future__ import annotations

import json
from pathlib import Path

from .metrics import RawBenchmarkBundle


def write_raw_bundle(bundle: RawBenchmarkBundle, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": bundle.summary.model_dump(mode="json"),
        "metadata": bundle.metadata,
        "measurements": [
            measurement.model_dump(mode="json") for measurement in bundle.measurements
        ],
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_markdown_report(bundle: RawBenchmarkBundle, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = bundle.summary
    lines = [
        "# 串行与并发基准结果",
        "",
        "## 环境",
        "",
        f"- 环境：{summary.environment}",
        f"- 模型：{summary.model}",
        f"- 后端：{summary.backend}",
        f"- 每场景每模式有效样本：{summary.samples_per_mode}",
        "",
        "## 场景结果",
        "",
        "| 场景 | 串行中位数(s) | 并发中位数(s) | 提速 | 串行正确率 | 并发正确率 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for comparison in summary.comparisons:
        lines.append(
            f"| {comparison.scenario_id} | {comparison.serial.median_seconds:.4f} | "
            f"{comparison.parallel.median_seconds:.4f} | "
            f"{comparison.median_speedup:.2%} | "
            f"{comparison.serial.correctness_rate:.1%} | "
            f"{comparison.parallel.correctness_rate:.1%} |"
        )
    lines.extend(
        [
            "",
            "## 汇总",
            "",
            f"- 平均提速：{summary.average_speedup:.2%}",
            f"- 最低场景提速：{summary.minimum_speedup:.2%}",
            f"- 并发正确性不低于串行：{'是' if summary.correctness_preserved else '否'}",
            f"- 越权操作：{summary.unauthorized_operations}",
            f"- 自动补跑的失败尝试：{summary.invalid_sample_count}",
            "",
            "## 原始数据",
            "",
            f"- 原始文件：`{bundle.metadata.get('raw_path', '')}`",
            "- 原始文件包含预热、五次有效测量、模型/工具耗时、token、Trace 和错误。",
            "",
            "## 数据范围",
            "",
            "本报告使用本地 Ollama 调试模型，仅用于开发验证。正式比赛性能结论必须使用",
            "远程 vLLM 7B AWQ 4bit 重新执行并单独归档。",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
