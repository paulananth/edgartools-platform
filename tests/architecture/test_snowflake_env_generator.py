"""Wayfinder snowflake-env-provisioning ticket 01 (Decide Terraform structure
for standing up an Nth independent Snowflake environment): validates
infra/scripts/generate-snowflake-env.py.

The load-bearing test here is `test_generating_prod_reproduces_live_prod_identifiers`.
The generator's templates were derived from the live
`infra/terraform/snowflake/accounts/prod` root, and the one bug class that
would actually hurt is a wrong name derivation: Snowflake role and warehouse
names are resource identity, so `EDGARTOOLS_PROD_DEPLOYER` becoming
`EDGARTOOLS_PROD-DEPLOYER` or `EDGARTOOLS_prod_DEPLOYER` is a rename, and a
rename is a *replace*, not a drift.

That test reads prod's real `main.tf` rather than asserting against a
hardcoded list, so it fails if either side moves -- template drifts from prod,
or prod is changed without the template following. Prod's root is never
written to by the generator; this is the cheap, offline, credential-free
substitute for the `terraform plan` that would otherwise be the only proof.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "infra" / "scripts" / "generate-snowflake-env.py"
LIVE_PROD_MAIN_TF = (
    REPO_ROOT / "infra" / "terraform" / "snowflake" / "accounts" / "prod" / "main.tf"
)

# The locals in main.tf whose values are Snowflake resource identity.
IDENTITY_LOCALS = (
    "deployer_role_name",
    "loader_role_name",
    "reader_role_name",
    "dashboard_owner_role_name",
    "refresh_warehouse_name",
    "reader_warehouse_name",
)


def _load_module():
    spec = importlib.util.spec_from_file_location("generate_snowflake_env", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def mod():
    return _load_module()


def _base_config(**overrides) -> dict:
    config = {
        "env_name": "example",
        "tfstate_bucket": "edgartools-example-tfstate-000000000000",
        "aws_region": "us-east-1",
        "snowflake": {
            "organization_name": "EXAMPLEORG",
            "account_name": "EXAMPLEACCT",
            "user": "EXAMPLEUSER",
        },
    }
    config.update(overrides)
    return config


def _parse_locals(main_tf: str) -> dict[str, str]:
    """Extract `name = "VALUE"` string locals from a main.tf locals block."""
    body = main_tf.split("locals {", 1)[1].split("\n}", 1)[0]
    return dict(re.findall(r'^\s*(\w+)\s*=\s*"([^"]*)"\s*$', body, re.MULTILINE))


def _generated(mod, config: dict) -> dict[str, str]:
    """Generate, returning {relative posix path: content}."""
    return {
        str(path.relative_to(REPO_ROOT).as_posix()): content
        for path, content in mod.generate(mod.validate_config(config)).items()
    }


# --------------------------------------------------------------------------
# The parity test: generating `prod` must reproduce prod's live identifiers.
# --------------------------------------------------------------------------


def test_generating_prod_reproduces_live_prod_identifiers(mod):
    live = _parse_locals(LIVE_PROD_MAIN_TF.read_text())
    # Guard the guard: if prod's main.tf stops exposing these as plain string
    # locals, this test would silently compare nothing at all.
    missing = [name for name in IDENTITY_LOCALS if name not in live]
    assert not missing, f"live prod main.tf no longer defines: {missing}"

    files = _generated(mod, _base_config(env_name="prod"))
    generated = _parse_locals(files["infra/terraform/snowflake/accounts/prod/main.tf"])

    for name in IDENTITY_LOCALS:
        assert generated[name] == live[name], (
            f"generated {name}={generated[name]!r} does not match live prod "
            f"{live[name]!r} -- this would rename (and therefore replace) a live "
            "Snowflake resource"
        )


def test_generating_prod_reproduces_live_prod_environment_and_schemas(mod):
    live = _parse_locals(LIVE_PROD_MAIN_TF.read_text())
    files = _generated(mod, _base_config(env_name="prod"))
    generated = _parse_locals(files["infra/terraform/snowflake/accounts/prod/main.tf"])

    assert generated["environment"] == live["environment"] == "prod"
    for name in ("source_schema_name", "gold_schema_name"):
        assert generated[name] == live[name]


def test_generated_prod_database_guard_matches_live_prod(mod):
    """Prod's variables.tf pins expected_database_name to EDGARTOOLS_PROD."""
    files = _generated(mod, _base_config(env_name="prod"))
    variables = files["infra/terraform/snowflake/accounts/prod/variables.tf"]
    assert 'default     = "EDGARTOOLS_PROD"' in variables
    assert 'var.expected_database_name == "EDGARTOOLS_PROD"' in variables


# --------------------------------------------------------------------------
# Slug handling
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("slug", "expected_segment"),
    [("prod", "PROD"), ("secondary", "SECONDARY"), ("eu-prod", "EU_PROD")],
)
def test_snowflake_segment_maps_hyphens_to_underscores(mod, slug, expected_segment):
    """Hyphens are legal in a slug and a directory name, but not in an
    unquoted Snowflake identifier."""
    assert mod.snowflake_segment(slug) == expected_segment


def test_hyphenated_slug_produces_valid_snowflake_identifiers(mod):
    files = _generated(mod, _base_config(env_name="eu-prod"))
    main_tf = files["infra/terraform/snowflake/accounts/eu-prod/main.tf"]
    locals_ = _parse_locals(main_tf)

    assert locals_["deployer_role_name"] == "EDGARTOOLS_EU_PROD_DEPLOYER"
    assert locals_["reader_warehouse_name"] == "EDGARTOOLS_EU_PROD_READER_WH"
    # The directory and state key keep the hyphen; only the Snowflake side maps it.
    assert "infra/terraform/snowflake/accounts/eu-prod/main.tf" in files
    assert (
        'key    = "snowflake/eu-prod/terraform.tfstate"'
        in files["infra/terraform/snowflake/accounts/eu-prod/backend.hcl"]
    )


@pytest.mark.parametrize(
    "bad_slug",
    [
        "",
        "Prod",  # uppercase
        "1prod",  # leading digit
        "eu_prod",  # underscore would collide with eu-prod
        "eu--prod",  # empty word
        "eu-prod-",  # trailing hyphen
        "eu prod",  # space
        "eu.prod",  # dot
    ],
)
def test_invalid_slugs_are_rejected(mod, bad_slug):
    with pytest.raises(mod.ConfigError, match="env_name"):
        mod.validate_config(_base_config(env_name=bad_slug))


def test_underscore_and_hyphen_slugs_cannot_collide(mod):
    """`eu_prod` is rejected precisely so it cannot map onto the same
    EDGARTOOLS_EU_PROD database as `eu-prod`."""
    assert mod.snowflake_segment("eu-prod") == "EU_PROD"
    with pytest.raises(mod.ConfigError):
        mod.validate_config(_base_config(env_name="eu_prod"))


# --------------------------------------------------------------------------
# Config validation fails closed
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field", ["env_name", "tfstate_bucket", "aws_region", "snowflake"]
)
def test_missing_required_top_level_field_is_rejected(mod, field):
    config = _base_config()
    del config[field]
    with pytest.raises(mod.ConfigError, match=field):
        mod.validate_config(config)


@pytest.mark.parametrize("field", ["organization_name", "account_name", "user"])
def test_missing_required_snowflake_field_is_rejected(mod, field):
    config = _base_config()
    del config["snowflake"][field]
    with pytest.raises(mod.ConfigError, match=field):
        mod.validate_config(config)


def test_partial_native_pull_is_rejected(mod):
    """native_pull is all-or-nothing: `local.native_pull_enabled` requires all
    three, so a partial set would silently disable the whole source layer."""
    config = _base_config(
        native_pull={
            "snowflake_storage_role_arn": "arn:aws:iam::1:role/r",
            # export_root_url and manifest_sns_topic_arn deliberately absent
        }
    )
    with pytest.raises(mod.ConfigError, match="snowflake_export_root_url"):
        mod.validate_config(config)


def test_render_fails_closed_on_unsubstituted_placeholder(mod):
    with pytest.raises(mod.ConfigError, match="UNKNOWN_TOKEN"):
        mod.render("value = {{UNKNOWN_TOKEN}}", {"ENV_NAME": "x"})


def test_render_leaves_terraform_interpolation_untouched(mod):
    """Terraform's `${...}` must survive rendering; only `{{...}}` is ours."""
    rendered = mod.render(
        'x = "edgartools-${local.environment}-{{ENV_NAME}}"', {"ENV_NAME": "secondary"}
    )
    assert rendered == 'x = "edgartools-${local.environment}-secondary"'


# --------------------------------------------------------------------------
# Emitted file set and cross-root consistency
# --------------------------------------------------------------------------


def test_generates_both_roots_with_expected_files(mod):
    files = _generated(mod, _base_config(env_name="secondary"))
    for root in (
        "infra/terraform/snowflake/accounts/secondary",
        "infra/terraform/access/snowflake/accounts/secondary",
    ):
        for name in (
            "main.tf",
            "variables.tf",
            "outputs.tf",
            "providers.tf",
            "versions.tf",
            "terraform.tfvars",
            "terraform.tfvars.example",
            "backend.hcl",
            "backend.hcl.example",
        ):
            assert f"{root}/{name}" in files, f"missing {root}/{name}"


def test_generator_never_writes_into_existing_prod_or_dev_roots(mod):
    """Generating some other environment must not touch prod's or dev's roots."""
    files = _generated(mod, _base_config(env_name="secondary"))
    for path in files:
        assert "/accounts/prod/" not in path
        assert "/accounts/dev/" not in path


def test_examples_match_the_local_config_they_document(mod):
    """The tracked `.example` files are generated from the same substitution as
    the gitignored real ones, so they cannot drift apart -- the failure mode
    behind the dev go-live blockers 5-whys #1."""
    files = _generated(mod, _base_config(env_name="secondary"))
    for root in (
        "infra/terraform/snowflake/accounts/secondary",
        "infra/terraform/access/snowflake/accounts/secondary",
    ):
        for name in ("terraform.tfvars", "backend.hcl"):
            assert files[f"{root}/{name}"] == files[f"{root}/{name}.example"]


def test_access_root_state_pointer_matches_provisioning_backend(mod):
    """The access root reads the provisioning root's state. Both sides are
    derived from one config value rather than typed twice -- a mismatch here is
    the dev go-live blockers 5-whys #1 failure."""
    files = _generated(mod, _base_config(env_name="secondary"))
    provisioning_backend = files[
        "infra/terraform/snowflake/accounts/secondary/backend.hcl"
    ]
    access_tfvars = files[
        "infra/terraform/access/snowflake/accounts/secondary/terraform.tfvars"
    ]

    backend = dict(
        re.findall(r'^(\w+)\s*=\s*"([^"]*)"$', provisioning_backend, re.MULTILINE)
    )
    tfvars = dict(re.findall(r'^(\w+)\s*=\s*"([^"]*)"$', access_tfvars, re.MULTILINE))

    assert tfvars["provisioning_state_bucket"] == backend["bucket"]
    assert tfvars["provisioning_state_key"] == backend["key"]
    assert tfvars["provisioning_state_region"] == backend["region"]


def test_two_environments_get_isolated_state_keys(mod):
    """Blast-radius isolation: one environment's apply must not be able to read
    or write another's state."""
    first = _generated(mod, _base_config(env_name="alpha"))
    second = _generated(mod, _base_config(env_name="beta"))

    def key_of(files: dict[str, str], slug: str, prefix: str) -> str:
        content = files[f"{prefix}/{slug}/backend.hcl"]
        return re.search(r'key\s*=\s*"([^"]*)"', content).group(1)

    for prefix in (
        "infra/terraform/snowflake/accounts",
        "infra/terraform/access/snowflake/accounts",
    ):
        assert key_of(first, "alpha", prefix) != key_of(second, "beta", prefix)


# --------------------------------------------------------------------------
# native_pull toggling and the MDM dashboard default
# --------------------------------------------------------------------------


def test_native_pull_absent_emits_commented_placeholders(mod):
    files = _generated(mod, _base_config(env_name="secondary"))
    tfvars = files["infra/terraform/snowflake/accounts/secondary/terraform.tfvars"]
    # Commented out, so local.native_pull_enabled is false and the module is skipped.
    assert "# snowflake_storage_role_arn" in tfvars
    assert re.search(r"^snowflake_storage_role_arn", tfvars, re.MULTILINE) is None


def test_native_pull_present_emits_real_assignments(mod):
    config = _base_config(
        env_name="secondary",
        native_pull={
            "snowflake_storage_role_arn": "arn:aws:iam::1:role/r",
            "snowflake_export_root_url": "s3://bucket/prefix/",
            "snowflake_manifest_sns_topic_arn": "arn:aws:sns:us-east-1:1:topic",
        },
    )
    tfvars = _generated(mod, config)[
        "infra/terraform/snowflake/accounts/secondary/terraform.tfvars"
    ]
    assert re.search(
        r'^snowflake_storage_role_arn\s+= "arn:aws:iam::1:role/r"$',
        tfvars,
        re.MULTILINE,
    )
    assert re.search(
        r'^snowflake_manifest_sns_topic_arn\s+= "arn:aws:sns:us-east-1:1:topic"$',
        tfvars,
        re.MULTILINE,
    )


def test_mdm_graph_review_dashboard_defaults_off(mod):
    """A brand-new account has no MDM_GRAPH_REVIEW contract yet, so enabling
    this by default would make the very first apply fail."""
    files = _generated(mod, _base_config(env_name="secondary"))
    tfvars = files["infra/terraform/snowflake/accounts/secondary/terraform.tfvars"]
    variables = files["infra/terraform/snowflake/accounts/secondary/variables.tf"]

    assert "mdm_graph_review_dashboard_enabled = false" in tfvars
    assert re.search(
        r'variable "mdm_graph_review_dashboard_enabled".*?default\s*=\s*false',
        variables,
        re.DOTALL,
    )


def test_mdm_graph_review_dashboard_can_be_enabled(mod):
    config = _base_config(env_name="secondary", mdm_graph_review_dashboard_enabled=True)
    tfvars = _generated(mod, config)[
        "infra/terraform/snowflake/accounts/secondary/terraform.tfvars"
    ]
    assert "mdm_graph_review_dashboard_enabled = true" in tfvars


# --------------------------------------------------------------------------
# The shipped example config must actually be valid
# --------------------------------------------------------------------------


def test_shipped_example_config_is_valid(mod):
    example = (
        REPO_ROOT / "infra" / "terraform" / "environments" / "example.json.example"
    )
    config = json.loads(example.read_text())
    validated = mod.validate_config(config)
    assert validated["env_name"] == "example"
    # It must also render end to end, not merely validate.
    assert mod.generate(validated)
