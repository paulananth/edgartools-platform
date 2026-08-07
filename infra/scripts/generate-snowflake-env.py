#!/usr/bin/env python3
"""Generate the two Snowflake Terraform roots for an independent environment.

Implements wayfinder ticket 01 of the snowflake-env-provisioning map
(`.scratch/snowflake-env-provisioning/issues/01-terraform-structure-for-nth-environment.md`):
new environments get a **generated directory per account** rather than a
hand-copied, hand-edited one, and are identified by an operator-chosen
free-form slug rather than a closed `dev|prod` enum.

Given a JSON config describing one environment, this emits:

    infra/terraform/snowflake/accounts/<slug>/            (provisioning root)
    infra/terraform/access/snowflake/accounts/<slug>/     (access root)

Each root gets `main.tf`, `variables.tf`, `outputs.tf`, `providers.tf`,
`versions.tf` (rendered or copied from
`infra/terraform/templates/snowflake_env/`), plus the two gitignored local
config files `terraform.tfvars` and `backend.hcl` and their tracked
`.example` counterparts.

Design constraints this script deliberately honours:

* **Pure.** Config in, files out. It never shells out to `terraform`, `aws`,
  or `snow`. Fetching the four AWS precondition values (wayfinder ticket 04)
  is a documented separate step -- `terraform output -json` against
  `infra/terraform/access/aws/accounts/<env>` -- whose result is pasted into
  the config. Purity is what keeps the prod-parity test cheap and offline.
* **Existing roots are never touched.** `accounts/prod` and `accounts/dev`
  are left exactly as they are; a bad name derivation here must not be able
  to rename a live prod role or warehouse. The parity test in
  `tests/architecture/test_snowflake_env_generator.py` asserts that
  generating with slug `prod` reproduces prod's live identifiers, which is
  the one bug class that would matter if these roots were ever regenerated.

Usage:

    uv run python infra/scripts/generate-snowflake-env.py \\
        --config infra/terraform/environments/<slug>.json

    # preview without writing
    uv run python infra/scripts/generate-snowflake-env.py \\
        --config <path> --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_ROOT = REPO_ROOT / "infra" / "terraform" / "templates" / "snowflake_env"

PROVISIONING_DEST = REPO_ROOT / "infra" / "terraform" / "snowflake" / "accounts"
ACCESS_DEST = REPO_ROOT / "infra" / "terraform" / "access" / "snowflake" / "accounts"

# A slug becomes three different things with three different legal alphabets:
# a directory name, an S3 key segment, and (uppercased) a segment of Snowflake
# identifiers such as EDGARTOOLS_<SLUG>_DEPLOYER. Hyphen-separated lowercase is
# the intersection that is safe in all three once hyphens are mapped to
# underscores for the Snowflake side. Underscores are disallowed in the slug
# itself so that `eu-prod` and `eu_prod` cannot collide onto one database name.
SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")

# Rendered into every generated root. Files without a `.tmpl` suffix in the
# template tree are copied verbatim -- they are already fully variable-driven
# and contain no per-environment values.
TEMPLATED_FILES = ("main.tf", "variables.tf", "outputs.tf")
VERBATIM_FILES = ("providers.tf", "versions.tf")
LOCAL_CONFIG_FILES = ("terraform.tfvars", "backend.hcl")

NATIVE_PULL_KEYS = (
    "snowflake_storage_role_arn",
    "snowflake_export_root_url",
    "snowflake_manifest_sns_topic_arn",
)


class ConfigError(ValueError):
    """Raised when an environment config is missing or malformed."""


def snowflake_segment(slug: str) -> str:
    """Map an environment slug onto its Snowflake identifier segment.

    `prod` -> `PROD`, `eu-prod` -> `EU_PROD`. Hyphens are not legal in an
    unquoted Snowflake identifier, so they become underscores here.
    """
    return slug.replace("-", "_").upper()


def load_config(path: Path) -> dict:
    """Read and validate an environment config."""
    if not path.is_file():
        raise ConfigError(f"config file not found: {path}")
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path} is not valid JSON: {exc}") from exc
    return validate_config(raw)


def validate_config(raw: dict) -> dict:
    """Validate a config mapping, returning it unchanged when it is sound.

    Fails closed and names the offending field, so a typo surfaces here
    rather than as an opaque Terraform or Snowflake error much later in a
    provisioning run.
    """
    if not isinstance(raw, dict):
        raise ConfigError("config must be a JSON object")

    slug = raw.get("env_name")
    if not isinstance(slug, str) or not slug:
        raise ConfigError("'env_name' is required and must be a non-empty string")
    if not SLUG_PATTERN.match(slug):
        raise ConfigError(
            f"env_name {slug!r} is not a valid slug: use lowercase letters and "
            "digits in hyphen-separated words, starting with a letter "
            "(e.g. 'secondary', 'eu-prod'). Underscores are not allowed, so that "
            "'eu-prod' and 'eu_prod' cannot map onto the same Snowflake database."
        )

    for field in ("tfstate_bucket", "aws_region"):
        value = raw.get(field)
        if not isinstance(value, str) or not value:
            raise ConfigError(f"'{field}' is required and must be a non-empty string")

    snowflake = raw.get("snowflake")
    if not isinstance(snowflake, dict):
        raise ConfigError("'snowflake' is required and must be an object")
    for field in ("organization_name", "account_name", "user"):
        value = snowflake.get(field)
        if not isinstance(value, str) or not value:
            raise ConfigError(
                f"'snowflake.{field}' is required and must be a non-empty string"
            )

    native_pull = raw.get("native_pull")
    if native_pull is not None:
        if not isinstance(native_pull, dict):
            raise ConfigError("'native_pull' must be an object when present")
        missing = [key for key in NATIVE_PULL_KEYS if not native_pull.get(key)]
        if missing:
            raise ConfigError(
                "'native_pull' must set all of "
                f"{', '.join(NATIVE_PULL_KEYS)} when present; missing: "
                f"{', '.join(missing)}. Snowflake's native_pull module is "
                "all-or-nothing -- a partial set silently disables it. Pull "
                "these from `terraform output -json` against "
                "infra/terraform/access/aws/accounts/<env> (wayfinder ticket 04)."
            )
    return raw


def build_native_pull_block(config: dict) -> str:
    """Render the native-pull assignments for a generated terraform.tfvars.

    When the AWS side is not yet stood up these are emitted commented out, so
    `local.native_pull_enabled` evaluates false and the module is skipped --
    the environment still applies cleanly, just without the source layer.
    """
    native_pull = config.get("native_pull")
    if not native_pull:
        return (
            "# AWS-side native-pull inputs are not set yet, so the native_pull module\n"
            "# stays disabled and this environment applies without its source layer.\n"
            "# Fill these in from `terraform output -json` against\n"
            "# infra/terraform/access/aws/accounts/<env> (wayfinder ticket 04), then\n"
            "# re-apply to enable the source layer:\n"
            + "".join(f"# {key} = \"...\"\n" for key in NATIVE_PULL_KEYS)
            + "# snowflake_storage_external_id = \"...\"  # optional; defaults to "
            "edgartools-<env>-snowflake-native-pull\n"
        )

    lines = [f'{key:<32} = "{native_pull[key]}"' for key in NATIVE_PULL_KEYS]
    external_id = native_pull.get("snowflake_storage_external_id")
    if external_id:
        lines.append(f'{"snowflake_storage_external_id":<32} = "{external_id}"')
    return "\n".join(lines) + "\n"


def build_substitutions(config: dict) -> dict[str, str]:
    """Derive every template placeholder value from the validated config."""
    slug = config["env_name"]
    segment = snowflake_segment(slug)
    snowflake = config["snowflake"]
    return {
        "ENV_NAME": slug,
        "ENV_UPPER": segment,
        "DATABASE_NAME": f"EDGARTOOLS_{segment}",
        "TFSTATE_BUCKET": config["tfstate_bucket"],
        "AWS_REGION": config["aws_region"],
        "SNOWFLAKE_ORG": snowflake["organization_name"],
        "SNOWFLAKE_ACCOUNT": snowflake["account_name"],
        "SNOWFLAKE_USER": snowflake["user"],
        "SNOWFLAKE_AUTHENTICATOR": snowflake.get("authenticator", "externalbrowser"),
        "SNOWFLAKE_ADMIN_ROLE": snowflake.get("admin_role", "ACCOUNTADMIN"),
        "MDM_DASHBOARD_ENABLED": (
            "true" if config.get("mdm_graph_review_dashboard_enabled") else "false"
        ),
        "NATIVE_PULL_BLOCK": build_native_pull_block(config),
    }


def render(template: str, substitutions: dict[str, str]) -> str:
    """Substitute `{{PLACEHOLDER}}` tokens, failing closed on any left over.

    Terraform's own `${...}` interpolation uses a different delimiter, so
    rendering here cannot disturb it.
    """
    rendered = template
    for key, value in substitutions.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    leftover = re.findall(r"\{\{([A-Z_]+)\}\}", rendered)
    if leftover:
        raise ConfigError(
            f"template left unsubstituted placeholders: {', '.join(sorted(set(leftover)))}"
        )
    return rendered


def render_root(template_dir: Path, substitutions: dict[str, str]) -> dict[str, str]:
    """Render one Terraform root, returning {filename: content}.

    Emits the `.example` copies alongside the real local config files. Those
    examples are the only committed per-environment artifacts, and generating
    them is precisely what prevents the tracked-example drift that broke dev's
    `terraform init` (CLAUDE.md, dev go-live blockers 5-whys #1).
    """
    files: dict[str, str] = {}

    for name in TEMPLATED_FILES:
        template_path = template_dir / f"{name}.tmpl"
        files[name] = render(template_path.read_text(), substitutions)

    for name in VERBATIM_FILES:
        files[name] = (template_dir / name).read_text()

    for name in LOCAL_CONFIG_FILES:
        content = render((template_dir / f"{name}.tmpl").read_text(), substitutions)
        files[name] = content
        files[f"{name}.example"] = content

    return files


def generate(config: dict) -> dict[Path, str]:
    """Render both Terraform roots, returning {absolute path: content}."""
    substitutions = build_substitutions(config)
    slug = config["env_name"]

    outputs: dict[Path, str] = {}
    for template_subdir, dest_root in (
        ("provisioning", PROVISIONING_DEST),
        ("access", ACCESS_DEST),
    ):
        rendered = render_root(TEMPLATE_ROOT / template_subdir, substitutions)
        for filename, content in rendered.items():
            outputs[dest_root / slug / filename] = content
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate the provisioning and access Snowflake Terraform roots for "
            "an independent environment."
        )
    )
    parser.add_argument(
        "--config",
        required=True,
        type=Path,
        help="Path to the environment's JSON config.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the files that would be written without writing them.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Overwrite an existing generated root. Refused by default so a "
            "regeneration cannot silently clobber a live environment's local "
            "terraform.tfvars or backend.hcl."
        ),
    )
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
        outputs = generate(config)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    existing = sorted(path for path in outputs if path.exists())
    if existing and not args.force:
        print(
            "error: refusing to overwrite existing files (pass --force to "
            "regenerate):",
            file=sys.stderr,
        )
        for path in existing:
            print(f"  {path.relative_to(REPO_ROOT)}", file=sys.stderr)
        return 1

    for path in sorted(outputs):
        rel = path.relative_to(REPO_ROOT)
        if args.dry_run:
            print(f"would write {rel}")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(outputs[path])
        print(f"wrote {rel}")

    if not args.dry_run:
        slug = config["env_name"]
        print()
        print(f"Generated Terraform roots for environment {slug!r}. Next:")
        print(
            f"  cd infra/terraform/snowflake/accounts/{slug} && "
            "terraform init -backend-config=backend.hcl && terraform plan"
        )
        print(
            "  (the tfstate bucket named in backend.hcl must already exist -- "
            "it is provisioned by the one-shot flow's bootstrap step)"
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
