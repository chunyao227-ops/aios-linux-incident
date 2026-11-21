"""Fixed-order structured verification execution."""

from __future__ import annotations

from typing import Protocol

from ..models import RepairResult, RunContext, VerificationCheck

VERIFICATION_ORDER = (
    "process_and_port_check",
    "health_endpoint",
    "smoke_test",
    "regression_test",
)
PRESSURE_CHECK = "controlled_pressure_test"


class VerificationBackend(Protocol):
    def run_check(
        self,
        context: RunContext,
        repair_result: RepairResult,
        check_name: str,
    ) -> VerificationCheck:
        """Run one fixed verification check."""


class ControlledVerificationTool:
    """Run checks in the frozen order and attach attempt metadata."""

    def __init__(
        self,
        backend: VerificationBackend,
        *,
        include_pressure: bool = False,
    ) -> None:
        self.backend = backend
        self.include_pressure = include_pressure

    def run_checks(
        self,
        context: RunContext,
        repair_result: RepairResult,
    ) -> tuple[VerificationCheck, ...]:
        names = VERIFICATION_ORDER + ((PRESSURE_CHECK,) if self.include_pressure else ())
        checks: list[VerificationCheck] = []
        for name in names:
            check = self.backend.run_check(context, repair_result, name)
            checks.append(
                VerificationCheck(
                    name=name,
                    passed=check.passed,
                    details={
                        **check.details,
                        "attempt_no": repair_result.attempt_no,
                        "repair_id": repair_result.repair_id,
                    },
                )
            )
        return tuple(checks)
