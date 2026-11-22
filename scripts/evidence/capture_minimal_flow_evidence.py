"""Run the W07 success and failure paths with the real local AIOS model."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from aios_incident.adapters.aios_client import AiosClient
from aios_incident.adapters.llm_adapter import LlmAdapter
from aios_incident.agents.coordinator_agent import CoordinatorAgent
from aios_incident.agents.log_agent import LogAgent
from aios_incident.agents.repair_agent import RepairAgent
from aios_incident.agents.verifier_agent import VerifierAgent
from aios_incident.config import load_config
from aios_incident.models import AllowedScope, IncidentTarget, RunContext
from aios_incident.orchestrator.blackboard import Blackboard
from aios_incident.orchestrator.minimal_flow import (
    MinimalFlowResult,
    MinimalFlowRunner,
    SimulatedFaultScenario,
    SimulatedRepairExecutor,
    SimulatedScenarioVerifier,
    seed_demo_target,
)
from aios_incident.orchestrator.trace import JsonlTraceStore
from aios_incident.tools.gateway import SandboxReadOnlyBackend, ToolGateway

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "docs" / "submission" / "evidence" / "workflow"


def make_context(
    incident_id: str,
    run_id: str,
    allowed_scope: AllowedScope,
) -> RunContext:
    return RunContext(
        run_id=run_id,
        incident_id=incident_id,
        objective="诊断并修复 web-app 不可用问题",
        target=IncidentTarget(
            host="sandbox-01",
            service="web-app",
            environment="docker",
        ),
        allowed_scope=allowed_scope,
        time_budget_seconds=600,
        max_repair_attempts=2,
        success_criteria=(
            "process_and_port_check",
            "health_endpoint",
            "smoke_test",
            "regression_test",
        ),
    )


def run_case(
    *,
    case_name: str,
    repair_succeeds: bool,
    llm: LlmAdapter,
) -> MinimalFlowResult:
    with TemporaryDirectory() as temporary:
        temp_root = Path(temporary)
        sandbox_root = temp_root / "sandbox"
        log_path, scope = seed_demo_target(sandbox_root)
        incident_id = f"inc-w07-evidence-{case_name}"
        context = make_context(
            incident_id,
            f"run-w07-evidence-{case_name}",
            scope,
        )
        trace = JsonlTraceStore(temp_root / "traces", incident_id, context.run_id)
        blackboard = Blackboard()
        gateway = ToolGateway(
            SandboxReadOnlyBackend(sandbox_root),
            scope_resolver=lambda _: scope,
            trace_resolver=lambda _: trace,
        )
        scenario = SimulatedFaultScenario(
            service="web-app",
            repair_succeeds=repair_succeeds,
        )
        runner = MinimalFlowRunner(
            coordinator=CoordinatorAgent(),
            log_agent=LogAgent(gateway, blackboard),
            repair_agent=RepairAgent(blackboard),
            verifier=VerifierAgent(blackboard),
            llm=llm,
            blackboard=blackboard,
            trace=trace,
            repair_executor=SimulatedRepairExecutor(scenario),
            verification_probe=SimulatedScenarioVerifier(scenario),
        )
        result = runner.run(context, log_path=log_path)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(
            trace.path,
            OUTPUT_DIR / f"W07_{case_name}_trace.jsonl",
        )
        trace_ref = f"docs/submission/evidence/workflow/W07_{case_name}_trace.jsonl"
        report = result.final_report.model_copy(update={"trace_ref": trace_ref})
        (OUTPUT_DIR / f"W07_{case_name}_report.json").write_text(
            report.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        summary = {
            "case": case_name,
            "workflow_status": result.context.workflow_status.value,
            "final_status": result.final_report.final_status.value,
            "root_cause": [
                root_cause.model_dump(mode="json")
                for root_cause in result.diagnosis.root_causes
            ],
            "repair_status": result.repair_result.status.value,
            "verification_passed": result.verification_result.passed,
            "timing": result.final_report.timing,
            "trace_ref": trace_ref,
        }
        (OUTPUT_DIR / f"W07_{case_name}_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        return result


def main() -> None:
    config = load_config()
    llm = LlmAdapter(AiosClient(config.aios), config.model)
    success = run_case(
        case_name="success",
        repair_succeeds=True,
        llm=llm,
    )
    failure = run_case(
        case_name="failure",
        repair_succeeds=False,
        llm=llm,
    )
    if success.context.workflow_status.value != "SUCCESS":
        raise RuntimeError("W07 success evidence did not reach SUCCESS")
    if failure.context.workflow_status.value != "UNRESOLVED":
        raise RuntimeError("W07 failure evidence did not reach UNRESOLVED")
    print("captured W07 success and failure traces with real AIOS")


if __name__ == "__main__":
    main()
