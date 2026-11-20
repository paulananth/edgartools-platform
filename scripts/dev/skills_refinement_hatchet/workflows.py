from __future__ import annotations

from pydantic import BaseModel
from hatchet_sdk import Context, Hatchet

from runner import implement_ticket, test_ticket

hatchet = Hatchet()


class TicketInput(BaseModel):
    ticket_path: str
    repo: str | None = None
    review_feedback: str | None = None


workflow = hatchet.workflow(name="skills-refinement-ticket", input_validator=TicketInput)


@workflow.task(name="implement", execution_timeout=3600)
def implement(input: TicketInput, ctx: Context) -> dict[str, object]:
    result = implement_ticket(input.ticket_path, input.repo, input.review_feedback)
    ctx.log({
        "phase": "implementation",
        "primary_model": result.get("primary_model"),
        "model": result["model"],
        "fallback_used": result.get("fallback_used", False),
        "exit_code": result["returncode"],
    })
    if result["returncode"] != 0:
        raise RuntimeError(f"Implementation agent failed: {result['output']}")
    return result


@workflow.task(name="test", parents=[implement], execution_timeout=3600)
def test(input: TicketInput, ctx: Context) -> dict[str, object]:
    implementation = ctx.task_output(implement)
    if implementation["returncode"] != 0:
        raise RuntimeError("Refusing to test after implementation failure")
    result = test_ticket(input.ticket_path, input.repo)
    ctx.log({
        "phase": "testing",
        "model": result["model"],
        "fallback_used": result.get("fallback_used", False),
        "exit_code": result["returncode"],
    })
    if result["returncode"] != 0:
        raise RuntimeError(f"Test agent failed: {result['output']}")
    return result
