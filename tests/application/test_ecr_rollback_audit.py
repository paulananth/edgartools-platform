"""Pure-logic tests for ops-cost-control ticket 05's rollback-cleanup audit.

Focus is the fail-closed contract: every ambiguity from
.scratch/ops-cost-control/research/safe-ecr-rollback-protection.md's
"Fail-closed conditions" list must retain, never delete.
"""
from __future__ import annotations

from dataclasses import replace

from edgar_warehouse.application import ecr_rollback_audit as audit
from edgar_warehouse.application import ecr_rollback_registry as registry

ACCOUNT_ID = "690839588395"
REGION = "us-east-1"
REPOSITORY = "edgartools-prod-images"
AUDIT_STARTED_AT = "2026-08-11T12:00:00Z"


def _hexify(token: str) -> str:
    base = token.encode("utf-8").hex() or "0"
    return (base * (64 // len(base) + 1))[:64]


def _digest(token: str) -> str:
    return "sha256:" + _hexify(token)


def _tag(role: str, token: str) -> str:
    return f"{role}-sha-{_hexify(token)[:12]}"


def _arn(role: str, revision: int) -> str:
    return f"arn:aws:ecs:{REGION}:{ACCOUNT_ID}:task-definition/edgartools-prod-{role}:{revision}"


def _role_entry(role: str, token: str, *, revision: int = 1) -> dict:
    return {
        "repository": REPOSITORY,
        "digest": _digest(token),
        "immutable_tag": _tag(role, token),
        "task_definition_arns": [_arn(role, revision)],
    }


def _full_registry() -> dict:
    reg = registry.empty_registry(account_id=ACCOUNT_ID, region=REGION)
    for i, ts in enumerate(f"2026-08-{d:02d}T00:00:00Z" for d in (9, 10, 11)):
        reg = registry.advance_registry(
            reg,
            candidate_id=f"rc-202608{9 + i:02d}-{'a' * 12}",
            verified_at=ts,
            verification_evidence=f"evidence-{i}",
            warehouse=_role_entry("warehouse", f"wh{i}", revision=i + 1),
            mdm=_role_entry("mdm", f"mdm{i}", revision=i + 1),
            updated_at=ts,
        )
    return reg


def _image(token: str, tags: list[str], *, pushed_at: str = "2026-08-10T00:00:00Z", size: int = 300_000_000) -> dict:
    return {"digest": _digest(token), "tags": tags, "pushed_at": pushed_at, "size_bytes": size}


def _task_definition(arn: str, digest: str, *, repository: str = REPOSITORY) -> dict:
    image_ref = f"690839588395.dkr.ecr.us-east-1.amazonaws.com/{repository}@{digest}"
    return {"arn": arn, "images": [image_ref]}


def _registry_task_definitions(registry_obj: dict) -> list[dict]:
    definitions: list[dict] = []
    for cohort in registry_obj["cohorts"]:
        for role in registry.ROLE_NAMES:
            role_entry = cohort[role]
            definitions.extend(
                _task_definition(arn, role_entry["digest"])
                for arn in role_entry["task_definition_arns"]
            )
    return definitions


def _base_kwargs(registry_obj: dict) -> dict:
    mirrors = registry.expected_protected_tags(registry_obj)
    return {
        "registry": registry_obj,
        "account_id": ACCOUNT_ID,
        "region": REGION,
        "repository": REPOSITORY,
        "ecr_images": [],
        "mirror_tag_digests": dict(mirrors),
        "task_definitions": _registry_task_definitions(registry_obj),
        "workflow_task_definition_arns": {},
        "ecs_services": [],
        "live_tasks": [],
        "audit_started_at": AUDIT_STARTED_AT,
        "pagination_counts": {"ecr_describe_images_pages": 1},
        "errors": [],
    }


def test_full_registry_with_matching_mirror_tags_and_no_extra_images_is_appliable_with_no_candidates():
    reg = _full_registry()
    plan = audit.compute_plan(**_base_kwargs(reg))
    assert audit.is_appliable(plan)
    assert plan.candidate_digests == ()
    assert plan.fail_closed_reasons == ()


def test_fewer_than_three_cohorts_forces_retain_all_and_blocks_apply():
    reg = registry.empty_registry(account_id=ACCOUNT_ID, region=REGION)
    reg = registry.advance_registry(
        reg,
        candidate_id="rc-20260811-aaaaaaaaaaaa",
        verified_at=AUDIT_STARTED_AT,
        verification_evidence="evidence",
        warehouse=_role_entry("warehouse", "a"),
        mdm=_role_entry("mdm", "b"),
        updated_at=AUDIT_STARTED_AT,
    )
    kwargs = _base_kwargs(reg)
    kwargs["ecr_images"] = [_image("stale-candidate", [_tag("warehouse", "stale-candidate")])]
    plan = audit.compute_plan(**kwargs)
    assert not audit.is_appliable(plan)
    assert plan.candidate_digests == ()
    assert any("insufficient_history" in reason or "cohort" in reason for reason in plan.fail_closed_reasons)


def test_a_tagged_stale_image_with_full_history_becomes_a_deletion_candidate():
    reg = _full_registry()
    kwargs = _base_kwargs(reg)
    stale_tag = _tag("warehouse", "stale-old-build")
    kwargs["ecr_images"] = [_image("stale-old-build", [stale_tag])]
    plan = audit.compute_plan(**kwargs)
    assert audit.is_appliable(plan)
    assert plan.candidate_digests == (_digest("stale-old-build"),)
    assert plan.estimated_reclaimed_bytes == 300_000_000


def test_image_pushed_after_current_verified_cohort_is_protected_as_release_candidate():
    reg = _full_registry()
    kwargs = _base_kwargs(reg)
    kwargs["ecr_images"] = [
        _image(
            "next-release",
            [_tag("warehouse", "next-release")],
            pushed_at="2026-08-11T06:00:00Z",
        )
    ]
    plan = audit.compute_plan(**kwargs)
    assert audit.is_appliable(plan)
    assert plan.candidate_digests == ()
    assert plan.images[0].provenance == ("pushed_after_current_verified_cohort",)


def test_an_image_protected_by_the_registry_is_never_a_candidate_even_if_it_looks_stale():
    reg = _full_registry()
    kwargs = _base_kwargs(reg)
    # This digest is the rollback-2 cohort's warehouse image (wh0) -- protected.
    kwargs["ecr_images"] = [_image("wh0", [_tag("warehouse", "wh0")])]
    plan = audit.compute_plan(**kwargs)
    assert audit.is_appliable(plan)
    assert plan.candidate_digests == ()
    protected_image = next(i for i in plan.images if i.digest == _digest("wh0"))
    assert protected_image.disposition == "protected"


def test_an_image_referenced_by_a_live_task_is_protected_even_if_absent_from_the_registry():
    reg = _full_registry()
    kwargs = _base_kwargs(reg)
    kwargs["ecr_images"] = [_image("live-only", [_tag("warehouse", "live-only")])]
    kwargs["live_tasks"] = [
        {
            "task_arn": "arn:aws:ecs:us-east-1:690839588395:task/edgartools-prod-warehouse/abc",
            "task_definition_arn": _arn("warehouse", 99),
            "images": [{"repository": REPOSITORY, "image_digest": _digest("live-only")}],
        }
    ]
    kwargs["task_definitions"].append(_task_definition(_arn("warehouse", 99), _digest("live-only")))
    plan = audit.compute_plan(**kwargs)
    assert audit.is_appliable(plan)
    assert plan.candidate_digests == ()


def test_an_image_referenced_by_an_active_task_definition_via_digest_pin_is_protected():
    reg = _full_registry()
    kwargs = _base_kwargs(reg)
    kwargs["ecr_images"] = [_image("td-only", [_tag("warehouse", "td-only")])]
    kwargs["task_definitions"].append(_task_definition(_arn("warehouse", 42), _digest("td-only")))
    kwargs["live_tasks"] = [
        {
            "task_arn": "arn:aws:ecs:us-east-1:690839588395:task/edgartools-prod-warehouse/td-only",
            "task_definition_arn": _arn("warehouse", 42),
            "images": [
                {"repository": REPOSITORY, "image_digest": _digest("td-only")}
            ],
        }
    ]
    plan = audit.compute_plan(**kwargs)
    assert audit.is_appliable(plan)
    assert plan.candidate_digests == ()


def test_a_tag_pinned_task_definition_image_reference_fails_closed():
    reg = _full_registry()
    kwargs = _base_kwargs(reg)
    kwargs["ecr_images"] = [_image("some-image", [_tag("warehouse", "some-image")])]
    tag_only_ref = f"690839588395.dkr.ecr.us-east-1.amazonaws.com/{REPOSITORY}:warehouse-prod"
    kwargs["task_definitions"].append({"arn": _arn("warehouse", 42), "images": [tag_only_ref]})
    kwargs["live_tasks"] = [
        {
            "task_arn": "arn:aws:ecs:us-east-1:690839588395:task/edgartools-prod-warehouse/tag-only",
            "task_definition_arn": _arn("warehouse", 42),
            "images": [
                {"repository": REPOSITORY, "image_digest": _digest("some-image")}
            ],
        }
    ]
    plan = audit.compute_plan(**kwargs)
    assert not audit.is_appliable(plan)
    assert plan.candidate_digests == ()
    assert any("tag-pinned" in reason for reason in plan.fail_closed_reasons)


def test_a_similarly_named_external_repository_fails_closed():
    reg = _full_registry()
    kwargs = _base_kwargs(reg)
    external_arn = _arn("warehouse", 42)
    kwargs["task_definitions"].append(
        _task_definition(
            external_arn,
            _digest("external"),
            repository=f"{REPOSITORY}-copy",
        )
    )
    kwargs["live_tasks"] = [
        {
            "task_arn": "arn:aws:ecs:us-east-1:690839588395:task/edgartools-prod-warehouse/external",
            "task_definition_arn": external_arn,
            "images": [
                {
                    "repository": f"{REPOSITORY}-copy",
                    "image_digest": _digest("external"),
                }
            ],
        }
    ]

    plan = audit.compute_plan(**kwargs)

    assert not audit.is_appliable(plan)
    assert any(
        external_arn in reason and "outside the expected repository" in reason
        for reason in plan.fail_closed_reasons
    )


def test_unreferenced_legacy_repository_task_definition_is_stale_without_blocking_retirement():
    reg = _full_registry()
    kwargs = _base_kwargs(reg)
    legacy_arn = _arn("warehouse", 42)
    kwargs["task_definitions"].append(
        _task_definition(
            legacy_arn,
            _digest("legacy"),
            repository="edgartools-prod-warehouse",
        )
    )

    plan = audit.compute_plan(**kwargs)

    assert audit.is_appliable(plan)
    assert legacy_arn in plan.stale_task_definition_arns


def test_a_live_task_container_missing_image_digest_fails_closed():
    reg = _full_registry()
    kwargs = _base_kwargs(reg)
    kwargs["live_tasks"] = [
        {
            "task_arn": "arn:aws:ecs:us-east-1:690839588395:task/edgartools-prod-warehouse/abc",
            "task_definition_arn": _arn("warehouse", 99),
            "images": [{"repository": REPOSITORY, "image_digest": None}],
        }
    ]
    plan = audit.compute_plan(**kwargs)
    assert not audit.is_appliable(plan)
    assert any("imageDigest" in reason for reason in plan.fail_closed_reasons)


def test_a_live_task_with_an_unresolved_task_definition_fails_closed():
    reg = _full_registry()
    kwargs = _base_kwargs(reg)
    unresolved_arn = _arn("warehouse", 99)
    kwargs["live_tasks"] = [
        {
            "task_arn": "arn:aws:ecs:us-east-1:690839588395:task/edgartools-prod-warehouse/abc",
            "task_definition_arn": unresolved_arn,
            "images": [
                {"repository": REPOSITORY, "image_digest": _digest("live-only")}
            ],
        }
    ]

    plan = audit.compute_plan(**kwargs)

    assert not audit.is_appliable(plan)
    assert any(
        unresolved_arn in finding and "live task" in finding
        for finding in plan.reference_drift
    )


def test_any_ecs_service_present_fails_closed():
    reg = _full_registry()
    kwargs = _base_kwargs(reg)
    kwargs["ecs_services"] = [{"cluster": "edgartools-prod-warehouse", "service_arn": "arn:aws:ecs:...:service/unexpected"}]
    plan = audit.compute_plan(**kwargs)
    assert not audit.is_appliable(plan)
    assert any("ECS service" in reason for reason in plan.fail_closed_reasons)


def test_mismatched_mirror_tag_digest_fails_closed():
    reg = _full_registry()
    kwargs = _base_kwargs(reg)
    tag = registry.mirror_tag_for("warehouse", "current")
    kwargs["mirror_tag_digests"][tag] = _digest("something-else-entirely")
    plan = audit.compute_plan(**kwargs)
    assert not audit.is_appliable(plan)
    assert any("mirror tag" in reason for reason in plan.fail_closed_reasons)


def test_missing_mirror_tag_fails_closed():
    reg = _full_registry()
    kwargs = _base_kwargs(reg)
    tag = registry.mirror_tag_for("warehouse", "current")
    kwargs["mirror_tag_digests"][tag] = None
    plan = audit.compute_plan(**kwargs)
    assert not audit.is_appliable(plan)
    assert any("mirror tag" in reason for reason in plan.fail_closed_reasons)


def test_missing_recorded_immutable_tag_fails_closed():
    reg = _full_registry()
    kwargs = _base_kwargs(reg)
    immutable_tag = reg["cohorts"][0]["warehouse"]["immutable_tag"]
    kwargs["mirror_tag_digests"][immutable_tag] = None
    plan = audit.compute_plan(**kwargs)
    assert not audit.is_appliable(plan)
    assert any(immutable_tag in reason for reason in plan.fail_closed_reasons)


def test_recorded_cohort_repository_must_match_audited_repository():
    reg = _full_registry()
    reg["cohorts"][0]["warehouse"]["repository"] = f"{REPOSITORY}-copy"
    kwargs = _base_kwargs(reg)
    plan = audit.compute_plan(**kwargs)
    assert not audit.is_appliable(plan)
    assert any("cohort repository" in reason for reason in plan.fail_closed_reasons)


def test_upstream_gathering_errors_are_carried_into_fail_closed_reasons():
    reg = _full_registry()
    kwargs = _base_kwargs(reg)
    kwargs["errors"] = ["ecs:ListClusters pagination did not terminate cleanly"]
    plan = audit.compute_plan(**kwargs)
    assert not audit.is_appliable(plan)
    assert "ecs:ListClusters pagination did not terminate cleanly" in plan.fail_closed_reasons


def test_an_image_pushed_after_audit_start_is_never_a_candidate():
    reg = _full_registry()
    kwargs = _base_kwargs(reg)
    kwargs["ecr_images"] = [
        _image("too-new", [_tag("warehouse", "too-new")], pushed_at="2026-08-11T13:00:00Z")  # after AUDIT_STARTED_AT
    ]
    plan = audit.compute_plan(**kwargs)
    assert audit.is_appliable(plan)
    assert plan.candidate_digests == ()
    image = next(i for i in plan.images if i.digest == _digest("too-new"))
    assert image.disposition == "protected"
    assert "pushed_after_audit_start" in image.provenance


def test_a_moving_pointer_tag_is_never_a_candidate_even_if_digest_is_otherwise_unprotected():
    reg = _full_registry()
    kwargs = _base_kwargs(reg)
    kwargs["ecr_images"] = [_image("moving", ["warehouse-prod"])]
    plan = audit.compute_plan(**kwargs)
    assert audit.is_appliable(plan)
    assert plan.candidate_digests == ()
    image = next(i for i in plan.images if i.digest == _digest("moving"))
    assert image.disposition == "protected"
    assert image.provenance == ("moving_pointer_tag",)


def test_a_dependency_image_is_marked_out_of_scope_not_a_candidate():
    reg = _full_registry()
    kwargs = _base_kwargs(reg)
    kwargs["ecr_images"] = [_image("deps", ["warehouse-deps-abc123"])]
    plan = audit.compute_plan(**kwargs)
    assert audit.is_appliable(plan)
    assert plan.candidate_digests == ()
    image = next(i for i in plan.images if i.digest == _digest("deps"))
    assert image.disposition == "deps_out_of_scope"


def test_an_untagged_image_is_lifecycle_managed_not_a_candidate():
    reg = _full_registry()
    kwargs = _base_kwargs(reg)
    kwargs["ecr_images"] = [_image("untagged", [])]
    plan = audit.compute_plan(**kwargs)
    assert audit.is_appliable(plan)
    assert plan.candidate_digests == ()
    image = next(i for i in plan.images if i.digest == _digest("untagged"))
    assert image.disposition == "lifecycle_managed"


def test_an_unrecognized_tag_shape_is_retained_not_guessed_at():
    reg = _full_registry()
    kwargs = _base_kwargs(reg)
    kwargs["ecr_images"] = [_image("weird", ["some-random-tag-nobody-recognizes"])]
    plan = audit.compute_plan(**kwargs)
    assert audit.is_appliable(plan)
    assert plan.candidate_digests == ()
    image = next(i for i in plan.images if i.digest == _digest("weird"))
    assert image.disposition == "protected"
    assert "unrecognized_tag_shape" in image.provenance


def test_stale_task_definitions_are_flagged_when_not_referenced_by_anything_live():
    reg = _full_registry()
    kwargs = _base_kwargs(reg)
    referenced_arn = _arn("warehouse", 3)  # this is the 'current' cohort's warehouse task def
    # Revision 99 is not recorded by any cohort (registry only knows revisions
    # 1-3), not named by a workflow, and not running in a live task -- stale.
    stale_arn = _arn("warehouse", 99)
    kwargs["task_definitions"].append(_task_definition(stale_arn, _digest("some-old-image")))
    plan = audit.compute_plan(**kwargs)
    assert stale_arn in plan.stale_task_definition_arns
    assert referenced_arn not in plan.stale_task_definition_arns


def test_workflow_reference_outside_current_release_fails_closed_as_drift():
    reg = _full_registry()
    kwargs = _base_kwargs(reg)
    stale_arn = _arn("warehouse", 99)
    kwargs["task_definitions"].append(_task_definition(stale_arn, _digest("stale-workflow")))
    kwargs["workflow_task_definition_arns"] = {"edgartools-prod-gold-refresh": [stale_arn]}

    plan = audit.compute_plan(**kwargs)

    assert not audit.is_appliable(plan)
    assert plan.reference_drift == (
        (
            f"state machine 'edgartools-prod-gold-refresh' references {stale_arn!r}, "
            "which is outside the registry current release cohort"
        ),
    )
    assert plan.candidate_digests == ()


def test_workflow_reference_to_current_release_has_no_drift():
    reg = _full_registry()
    kwargs = _base_kwargs(reg)
    current_arn = _arn("warehouse", 3)
    kwargs["workflow_task_definition_arns"] = {"edgartools-prod-gold-refresh": [current_arn]}

    plan = audit.compute_plan(**kwargs)

    assert audit.is_appliable(plan)
    assert plan.reference_drift == ()


def test_current_release_task_definition_missing_from_active_inventory_fails_closed():
    reg = _full_registry()
    kwargs = _base_kwargs(reg)
    missing_arn = _arn("warehouse", 3)
    kwargs["task_definitions"] = [
        task_definition
        for task_definition in kwargs["task_definitions"]
        if task_definition["arn"] != missing_arn
    ]

    plan = audit.compute_plan(**kwargs)

    assert not audit.is_appliable(plan)
    assert any(missing_arn in finding and "not ACTIVE" in finding for finding in plan.reference_drift)


def test_current_release_task_definition_digest_mismatch_fails_closed():
    reg = _full_registry()
    kwargs = _base_kwargs(reg)
    current_arn = _arn("warehouse", 3)
    kwargs["task_definitions"] = [
        _task_definition(current_arn, _digest("unexpected"))
        if task_definition["arn"] == current_arn
        else task_definition
        for task_definition in kwargs["task_definitions"]
    ]

    plan = audit.compute_plan(**kwargs)

    assert not audit.is_appliable(plan)
    assert any(current_arn in finding and "expected release digest" in finding for finding in plan.reference_drift)


def test_workflow_reference_missing_from_active_inventory_fails_closed():
    reg = _full_registry()
    kwargs = _base_kwargs(reg)
    missing_arn = _arn("warehouse", 99)
    kwargs["workflow_task_definition_arns"] = {"edgartools-prod-gold-refresh": [missing_arn]}

    plan = audit.compute_plan(**kwargs)

    assert not audit.is_appliable(plan)
    assert any(missing_arn in finding and "cannot be resolved" in finding for finding in plan.reference_drift)


def test_account_or_region_mismatch_between_caller_and_registry_fails_closed():
    reg = _full_registry()
    kwargs = _base_kwargs(reg)
    kwargs["region"] = "eu-west-1"
    plan = audit.compute_plan(**kwargs)
    assert not audit.is_appliable(plan)
    assert any("does not match audit identity" in reason for reason in plan.fail_closed_reasons)


def test_plan_hash_is_deterministic_for_identical_inputs():
    reg = _full_registry()
    kwargs = _base_kwargs(reg)
    kwargs["ecr_images"] = [_image("stale", [_tag("warehouse", "stale")])]
    plan_a = audit.compute_plan(**kwargs)
    plan_b = audit.compute_plan(**kwargs)
    assert plan_a.plan_sha256 == plan_b.plan_sha256


def test_plan_hash_ignores_audit_timestamp_but_keeps_timestamp_in_output():
    reg = _full_registry()
    kwargs = _base_kwargs(reg)
    plan_a = audit.compute_plan(**kwargs)
    kwargs["audit_started_at"] = "2026-08-11T12:05:00Z"
    plan_b = audit.compute_plan(**kwargs)

    assert plan_a.audit_started_at != plan_b.audit_started_at
    assert plan_a.plan_sha256 == plan_b.plan_sha256


def test_plan_hash_changes_when_ecr_inventory_changes():
    reg = _full_registry()
    kwargs = _base_kwargs(reg)
    plan_a = audit.compute_plan(**kwargs)
    kwargs["ecr_images"] = [_image("stale", [_tag("warehouse", "stale")])]
    plan_b = audit.compute_plan(**kwargs)
    assert plan_a.plan_sha256 != plan_b.plan_sha256


def test_to_dict_round_trips_every_field():
    reg = _full_registry()
    kwargs = _base_kwargs(reg)
    kwargs["ecr_images"] = [_image("stale", [_tag("warehouse", "stale")])]
    plan = audit.compute_plan(**kwargs)
    body = plan.to_dict()
    assert body["plan_sha256"] == plan.plan_sha256
    assert body["candidate_digests"] == list(plan.candidate_digests)
    assert body["reference_drift"] == list(plan.reference_drift)
    assert len(body["images"]) == len(plan.images)


def test_post_deregistration_audit_accepts_the_same_reviewed_candidates():
    reg = _full_registry()
    kwargs = _base_kwargs(reg)
    kwargs["ecr_images"] = [_image("stale", [_tag("warehouse", "stale")])]
    reviewed = audit.compute_plan(**kwargs)
    post_deregistration = replace(reviewed, stale_task_definition_arns=())

    assert audit.post_deregistration_findings(reviewed, post_deregistration) == []


def test_post_deregistration_audit_accepts_only_the_expected_remaining_batch():
    reg = _full_registry()
    reviewed = audit.compute_plan(**_base_kwargs(reg))
    first_arn = _arn("warehouse", 88)
    second_arn = _arn("warehouse", 89)
    reviewed = replace(
        reviewed,
        stale_task_definition_arns=(first_arn, second_arn),
    )
    after_first_batch = replace(reviewed, stale_task_definition_arns=(second_arn,))

    assert audit.post_deregistration_findings(
        reviewed,
        after_first_batch,
        expected_remaining_stale_task_definition_arns=(second_arn,),
    ) == []


def test_post_deregistration_audit_rejects_a_candidate_that_is_no_longer_safe():
    reg = _full_registry()
    kwargs = _base_kwargs(reg)
    kwargs["ecr_images"] = [_image("stale", [_tag("warehouse", "stale")])]
    reviewed = audit.compute_plan(**kwargs)
    post_deregistration = replace(reviewed, candidate_digests=())

    findings = audit.post_deregistration_findings(reviewed, post_deregistration)

    assert findings == [
        f"reviewed deletion candidate {_digest('stale')!r} is no longer eligible after task-definition retirement"
    ]


def test_post_deregistration_audit_rejects_new_stale_task_definitions():
    reg = _full_registry()
    reviewed = audit.compute_plan(**_base_kwargs(reg))
    unexpected_arn = _arn("warehouse", 88)
    post_deregistration = replace(reviewed, stale_task_definition_arns=(unexpected_arn,))

    findings = audit.post_deregistration_findings(reviewed, post_deregistration)

    assert findings == [
        f"post-deregistration audit still reports stale task definitions: {unexpected_arn}"
    ]
