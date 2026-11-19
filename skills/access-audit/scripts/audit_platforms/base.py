"""What every platform is audited for: platform-neutral objectives, each mapped to SOX ITGC, SOC 2 and ITIL."""
from __future__ import annotations

OBJECTIVES = {
    "IND": ("The audit identity is read-only and independent of what it audits", "SOC2 CC1.3; SOX ITGC segregation of duties", "medium"),
    "ADM": ("At least two administrators (one break-glass), each with MFA; no standing root or owner credential", "SOX ITGC access; SOC2 CC6.1; ITIL service access", "high"),
    "OPS": ("Daily operations do not run as an administrator or default to one", "SOX ITGC operations; SOC2 CC6.3", "high"),
    "AUT": ("No password-only privileged login; service identities use keys or roles, not passwords", "SOC2 CC6.1; SOX ITGC access", "high"),
    "LPR": ("Least privilege: no unexpected ownership, grant-management or wildcard-admin power", "SOC2 CC6.3; SOX ITGC access", "high"),
    "NET": ("A network or public-exposure boundary applies", "SOC2 CC6.6 boundary protection", "medium"),
    "CST": ("Cost and capacity guards exist (monitors, budgets, connection limits)", "SOX ITGC operations; ITIL financial management", "medium"),
    "TMO": ("Execution is bounded (statement or session timeouts)", "SOC2 A1.1 capacity", "medium"),
    "POL": ("Credential policies exist and are enforced", "SOC2 CC6.1; SOX ITGC access", "medium"),
    "LOG": ("Access and data-changing activity is logged, and transport and storage are encrypted", "SOC2 CC7.2 monitoring; SOX ITGC operations", "high"),
    "CHG": ("Every access principal has a change record and is defined in code; changes are reviewed", "SOX ITGC program change; SOC2 CC8.1; ITIL change enablement", "medium"),
    "SEC": ("No secret is stored in plain text; secret files are private", "SOC2 CC6.1; SOX ITGC access", "high"),
    "ROT": ("Credentials are rotated on a dated, owned schedule", "SOC2 CC6.1; ITIL information security", "medium"),
    "REV": ("Access is reviewed on a schedule with a signed record", "SOX ITGC access review; SOC2 CC6.2", "medium"),
}


def control(platform: str, objective: str, ok: bool, evidence: dict, fix: str, tested: bool = True, title: str | None = None) -> dict:
    title_, refs, severity = OBJECTIVES[objective]
    return {"id": f"{objective}.{platform}", "platform": platform, "objective": objective, "title": title or title_, "refs": refs,
            "severity": severity, "result": ("PASS" if ok else "FAIL") if tested else "NOT_TESTED", "evidence": evidence, "fix": fix}
