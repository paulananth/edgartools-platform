"""PROTOTYPE -- throwaway TUI shell over logic.py. Run:

    uv run python .scratch/release-readiness/prototypes/07-dashboard-acceptance/tui.py

Drives the DashboardAcceptanceState by hand to check whether the schema can
represent: an in-progress checklist, a stale-watermark view after a new gold
refresh lands, a thin-sample "pass" missing a sub-check, and a clean READY.
"""

import json
import os
import sys

import logic

BOLD = "\x1b[1m"
DIM = "\x1b[2m"
RESET = "\x1b[0m"
GREEN = "\x1b[32m"
RED = "\x1b[31m"
YELLOW = "\x1b[33m"


def glyph(status: logic.Status) -> str:
    return {
        logic.Status.PASS: f"{GREEN}✔{RESET}",
        logic.Status.FAIL: f"{RED}✘{RESET}",
        logic.Status.NOT_CHECKED: f"{DIM}·{RESET}",
    }[status]


def render(state: logic.DashboardAcceptanceState) -> None:
    os.system("clear" if os.name != "nt" else "cls")
    print(f"{BOLD}Release-Bound Dashboard Acceptance -- prototype{RESET}")
    print(
        f"{DIM}release_candidate={RESET} {state.release_candidate}   "
        f"{DIM}release_watermark={RESET} {state.release_watermark}"
    )
    print()
    stale = set(logic.stale_views(state))
    thin = set(logic.thin_sample_views(state))
    for i, view in enumerate(logic.VIEWS, start=1):
        key = view.key
        c = state.views[key]
        flags = []
        if key in stale:
            flags.append(f"{YELLOW}STALE{RESET}")
        if key in thin:
            flags.append(f"{YELLOW}THIN-SAMPLE{RESET}")
        flag_str = f"  {' '.join(flags)}" if flags else ""
        print(
            f"{i:2d}. {glyph(c.status)} [{view.dashboard:20s}] {view.label}{flag_str}"
        )
    print()
    print(f"{BOLD}Overall: {logic.overall_status(state).value}{RESET}")
    print()
    print(
        f"{BOLD}Commands{RESET}  "
        f"{BOLD}pass <n>{RESET}{DIM}/{RESET}{BOLD}fail <n>{RESET} mark a view  "
        f"{BOLD}thin <n>{RESET}{DIM} mark pass w/ a sub-check left unset{RESET}  "
        f"{BOLD}watermark <w>{RESET}{DIM} rebase (simulate new gold refresh){RESET}  "
        f"{BOLD}json{RESET} dump artifact  {BOLD}q{RESET} quit"
    )


def record_simulated_check(
    state: logic.DashboardAcceptanceState,
    index_text: str,
    *,
    status: logic.Status,
    safety: logic.SafetyChecks,
    note: str | None = None,
) -> logic.DashboardAcceptanceState:
    index = int(index_text) - 1
    if index < 0 or index >= len(logic.VIEWS):
        return state
    return logic.record_check(
        state,
        logic.VIEWS[index].key,
        status=status,
        watermark_checked=state.release_watermark,
        operator=logic.AttestingRole.DASHBOARD_REVIEWER,
        safety=safety,
        row_count_observed=0,
        note=note,
    )


def main() -> None:
    state = logic.init_state(
        release_candidate="rc-20260729-e0fa0eaafb09",
        release_watermark="wm-2026-07-29T02:00Z",
    )
    render(state)
    while True:
        try:
            line = input("> ").strip()
        except EOFError:
            break
        if not line:
            render(state)
            continue
        parts = line.split()
        cmd = parts[0].lower()
        if cmd == "q":
            break
        elif cmd == "pass" and len(parts) == 2 and parts[1].isdigit():
            state = record_simulated_check(
                state,
                parts[1],
                status=logic.Status.PASS,
                safety=logic.SafetyChecks(True, True, True),
            )
        elif cmd == "thin" and len(parts) == 2 and parts[1].isdigit():
            # Deliberately leaves unbounded_output_clear unset -- simulates an
            # operator eyeballing the screen without checking for a row cap.
            state = record_simulated_check(
                state,
                parts[1],
                status=logic.Status.PASS,
                safety=logic.SafetyChecks(True, True, False),
                note="simulated thin-sample: unbounded_output not confirmed",
            )
        elif cmd == "fail" and len(parts) == 2 and parts[1].isdigit():
            state = record_simulated_check(
                state,
                parts[1],
                status=logic.Status.FAIL,
                safety=logic.SafetyChecks(True, True, True),
                note="simulated failure",
            )
        elif cmd == "watermark" and len(parts) == 2:
            state = logic.rebase_watermark(state, parts[1])
        elif cmd == "json":
            render(state)
            print(json.dumps(logic.to_evidence_json(state), indent=2))
            input("-- press enter to continue --")
        render(state)


if __name__ == "__main__":
    sys.exit(main())
