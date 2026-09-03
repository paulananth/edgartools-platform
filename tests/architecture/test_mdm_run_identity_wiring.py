"""Generated ASL command expressions bind MDM evidence to one execution.

state-machine-consolidation wayfinder map, ticket 07: MDM Run Identity now
has two tiers. Commands generated inside write_mdm_definition (the single
MDM machine, invoked as a nested execution by daily_incremental/
load_history/the seed machine) must use $.run_id -- the calling execution's
own $$.Execution.Name, explicitly propagated as input by
mdm_tail_helper.py's call_mdm_machine() -- because $$.Execution.Name
*inside* a nested execution resolves to that execution's own auto-generated
name, not the caller's (would otherwise silently fragment one logical run's
MDM Run Identity across disconnected identities in MDM Postgres -- Ticket
30, e45bcd30). Every other evidence-producing command (the always-
standalone, directly-triggered mdm_utility machine's mastering/
derive-relationships modes) is never nested, so it keeps using
$$.Execution.Name directly, unaffected.
"""
from __future__ import annotations

import re
from pathlib import Path

DEPLOY_SCRIPT = Path("infra/scripts/deploy-aws-application.sh")
EVIDENCE_COMMANDS = {
    "mastering",
    "derive-relationships",
    "infer-relationships",
    "load-relationships",
}
COMMAND_PATTERN = r"States\.Array\('mdm', '(?:mastering|derive-relationships|infer-relationships|load-relationships)'[^\n]*"

_MDM_MACHINE_START = "write_mdm_definition() {\n"
_MDM_MACHINE_END = "\nPY\n}\n"


def _mdm_machine_source() -> str:
    text = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = text.index(_MDM_MACHINE_START)
    end = text.index(_MDM_MACHINE_END, start) + len(_MDM_MACHINE_END)
    return text[start:end]


def test_mdm_machine_evidence_commands_bind_the_propagated_run_id() -> None:
    source = _mdm_machine_source()
    commands = re.findall(COMMAND_PATTERN, source)

    assert commands, "write_mdm_definition must generate evidence-producing MDM commands"
    for command in commands:
        command = command.replace(r"\$", "$")
        operation = next(name for name in EVIDENCE_COMMANDS if f"'{name}'" in command)
        assert "'--run-id', $.run_id" in command, (
            f"MDM machine's generated {operation} command must bind the propagated "
            f"run_id input, not a fresh execution name: {command}"
        )
        assert "$$.Execution.Name" not in command, (
            f"MDM machine's generated {operation} command must not reference "
            f"$$.Execution.Name -- inside a nested execution that resolves to its own "
            f"auto-generated name, not the calling machine's: {command}"
        )


def test_every_other_generated_evidence_command_still_binds_execution_name() -> None:
    """Every evidence-producing command generated OUTSIDE write_mdm_definition
    (currently: mdm_utility's always-standalone, directly-triggered mastering/
    derive-relationships modes) is never nested, so $$.Execution.Name is
    already the right, stable identity -- must stay unaffected by ticket 07."""
    full_source = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    mdm_machine_source = _mdm_machine_source()
    outside_source = full_source.replace(mdm_machine_source, "")

    commands = re.findall(COMMAND_PATTERN, outside_source)
    assert commands, "expected mdm_utility to still generate evidence-producing MDM commands"
    for command in commands:
        command = command.replace(r"\$", "$")
        operation = next(name for name in EVIDENCE_COMMANDS if f"'{name}'" in command)
        assert "'--run-id', $$.Execution.Name" in command, (
            f"generated {operation} command outside the MDM machine does not bind its "
            f"own Step Functions execution: {command}"
        )
