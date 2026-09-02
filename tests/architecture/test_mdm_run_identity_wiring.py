"""Generated ASL command expressions bind MDM evidence to one execution."""
from __future__ import annotations

import re
from pathlib import Path

DEPLOY_SCRIPT = Path("infra/scripts/deploy-aws-application.sh")
EVIDENCE_COMMANDS = {
    "mastering",
    "derive-relationships",
    "backfill-relationships",
    "load-relationships",
}


def test_all_generated_mdm_evidence_commands_bind_step_functions_execution_name() -> None:
    source = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    commands = re.findall(
        r"States\.Array\('mdm', '(?:mastering|derive-relationships|backfill-relationships|load-relationships)'[^\n]*",
        source,
    )

    assert commands, "deploy script must generate evidence-producing MDM commands"
    for command in commands:
        command = command.replace(r"\$", "$")
        operation = next(name for name in EVIDENCE_COMMANDS if f"'{name}'" in command)
        assert "'--run-id', $$.Execution.Name" in command, (
            f"generated {operation} command does not bind its Step Functions execution: {command}"
        )
