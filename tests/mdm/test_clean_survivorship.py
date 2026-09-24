"""Direct tests for Clean MDM's field selection and claim collapse.

`clean/survivorship.py` had no test of its own: everything reaching it went
through `MergeStage.apply` in the Docker-backed integration suite, so a
regression here reported itself as a merge failure. Company mastering tickets
01 and 02 land three changes in this file (the revision guard's key, where a
kind's field rules live, and which digest a field records), so it gets a seam
of its own first.
"""

from __future__ import annotations

import pytest

from edgar_warehouse.mdm.clean.evidence import assertion
from edgar_warehouse.mdm.clean.store import Conflict
from edgar_warehouse.mdm.clean.survivorship import current_claims, select_fields

AS_OF = "2026-09-22T00:00:00+00:00"


def company(
    *,
    record_key="0000320193",
    revision=0,
    publication_key="sec-2026-09-01",
    fields=None,
    source_code="sec.company",
    effective_at="2026-09-01T00:00:00+00:00",
    **extra,
):
    return assertion(
        source_code=source_code,
        record_key=record_key,
        publication_key=publication_key,
        revision=revision,
        effective_at=effective_at,
        kind="company",
        fields=fields if fields is not None else {"legal_name": "Apple Inc."},
        **extra,
    )


def rules(*sources, **extra):
    return {
        "company": {
            "legal_name": {"sources": list(sources), **extra},
        }
    }


class TestCurrentClaims:
    def test_one_publication_becomes_one_claim(self):
        a = company()
        claims = current_claims([a], AS_OF, set())
        assert list(claims) == [a["subject"]]
        assert claims[a["subject"]]["fields"]["legal_name"]["value"] == "Apple Inc."

    def test_a_later_revision_supersedes_an_earlier_one(self):
        first = company(revision=0, fields={"legal_name": "Apple Computer, Inc."})
        second = company(revision=1, fields={"legal_name": "Apple Inc."})
        claims = current_claims([second, first], AS_OF, set())
        chosen = claims[first["subject"]]["fields"]["legal_name"]
        assert chosen["value"] == "Apple Inc."
        assert chosen["assertion_id"] == second["assertion_id"]

    def test_a_retired_source_contributes_nothing(self):
        a = company()
        assert current_claims([a], AS_OF, {"sec.company"}) == {}

    def test_evidence_effective_after_as_of_is_not_yet_current(self):
        a = company(effective_at="2026-12-01T00:00:00+00:00")
        assert current_claims([a], AS_OF, set()) == {}

    def test_a_retract_removes_the_field(self):
        first = company(revision=0)
        second = company(revision=1, fields={"legal_name": {"op": "retract"}})
        claims = current_claims([second, first], AS_OF, set())
        assert claims[first["subject"]]["fields"] == {}

    def test_unknown_leaves_the_earlier_value_standing(self):
        first = company(revision=0)
        second = company(revision=1, fields={"legal_name": {"op": "unknown"}})
        claims = current_claims([second, first], AS_OF, set())
        assert claims[first["subject"]]["fields"]["legal_name"]["value"] == "Apple Inc."

    def test_two_contradictory_bodies_at_one_revision_are_refused(self):
        """The guard this file's ticket 01 amendment re-keys, in its own right.

        One source native revision published twice with different content is a
        defect in the source, and stays refused after the amendment.
        """
        first = company(revision=0, fields={"legal_name": "Apple Inc."})
        second = company(revision=0, fields={"legal_name": "Apple Computer, Inc."})
        with pytest.raises(Conflict, match="contradictory publications"):
            current_claims([first, second], AS_OF, set())


class TestMappingVersion:
    """Ticket 01, amendments 7 and 8: a re-read adds a row.

    Two readings of one publication differ only by `mapping_version`. Before
    the amendments the changed reading raised on the revision guard and the
    unchanged one collided on `assertion_id`, so neither could ever sit beside
    its predecessor.
    """

    def test_an_assertion_states_the_mapping_version_that_read_it(self):
        assert company(mapping_version=2)["mapping_version"] == 2

    def test_the_first_reading_says_nothing_so_no_written_id_moves(self):
        """Absent and 1 describe the same reading, so 1 has one canonical form.

        Stating it would re-hash every assertion already written and orphan
        the decisions that cite them.
        """
        assert "mapping_version" not in company()
        assert company()["assertion_id"] == company(mapping_version=1)["assertion_id"]

    def test_a_second_reading_of_one_publication_is_a_different_assertion(self):
        first = company(mapping_version=1, fields={"legal_name": "Apple Inc."})
        second = company(mapping_version=2, fields={"legal_name": "Apple Inc."})
        assert first["assertion_id"] != second["assertion_id"]

    def test_two_readings_of_one_revision_are_not_contradictory_publications(self):
        first = company(mapping_version=1, fields={"legal_name": "Apple Inc."})
        second = company(mapping_version=2, fields={"legal_name": "Apple Inc, Inc."})
        claims = current_claims([first, second], AS_OF, set())
        chosen = claims[first["subject"]]["fields"]["legal_name"]
        assert chosen["assertion_id"] == second["assertion_id"]
        assert chosen["value"] == "Apple Inc, Inc."

    def test_the_newest_reading_wins_whatever_order_it_arrives_in(self):
        first = company(mapping_version=1, fields={"legal_name": "Apple Inc."})
        second = company(mapping_version=2, fields={"legal_name": "Apple Inc, Inc."})
        forward = current_claims([first, second], AS_OF, set())
        backward = current_claims([second, first], AS_OF, set())
        assert forward == backward

    def test_a_later_revision_still_beats_a_newer_reading_of_an_older_one(self):
        """Mapping version orders within a revision, never across revisions."""
        reread = company(
            revision=0, mapping_version=2, fields={"legal_name": "Apple Computer"}
        )
        later = company(
            revision=1, mapping_version=1, fields={"legal_name": "Apple Inc."}
        )
        claims = current_claims([reread, later], AS_OF, set())
        assert claims[later["subject"]]["fields"]["legal_name"]["value"] == "Apple Inc."

    def test_the_guard_still_catches_one_revision_published_twice(self):
        first = company(revision=0, mapping_version=1, fields={"legal_name": "Apple"})
        second = company(revision=0, mapping_version=1, fields={"legal_name": "Pear"})
        with pytest.raises(Conflict, match="contradictory publications"):
            current_claims([first, second], AS_OF, set())

    def test_a_first_reading_and_a_re_read_are_one_revision_read_twice(self):
        """A body with no version is the first reading, not a missing one."""
        stored = company()
        reread = company(mapping_version=2, fields={"legal_name": "Apple Inc, Inc."})
        assert "mapping_version" not in stored
        claims = current_claims([stored, reread], AS_OF, set())
        chosen = claims[stored["subject"]]["fields"]["legal_name"]
        assert chosen["assertion_id"] == reread["assertion_id"]


class TestKindScopedRules:
    """Ticket 02, decision 1: a kind's field rules move under kinds.<kind>."""

    def test_rules_are_read_from_the_kind_block(self):
        a = company()
        claims = current_claims([a], AS_OF, set())
        fields, _, _ = select_fields(
            "company",
            sorted(claims),
            claims,
            {"kinds": {"company": {"fields": rules("sec.company")["company"]}}},
            [],
            as_of=AS_OF,
            policy_digest="digest-1",
        )
        assert fields["legal_name"]["value"] == "Apple Inc."

    def test_a_body_registered_under_the_old_shape_keeps_working(self):
        a = company()
        claims = current_claims([a], AS_OF, set())
        fields, _, _ = select_fields(
            "company",
            sorted(claims),
            claims,
            {"fields": rules("sec.company")},
            [],
            as_of=AS_OF,
            policy_digest="digest-1",
        )
        assert fields["legal_name"]["value"] == "Apple Inc."

    def test_a_body_carrying_both_shapes_is_refused(self):
        a = company()
        claims = current_claims([a], AS_OF, set())
        with pytest.raises(Conflict, match="one place"):
            select_fields(
                "company",
                sorted(claims),
                claims,
                {
                    "fields": rules("sec.company"),
                    "kinds": {"company": {"fields": rules("sec.company")["company"]}},
                },
                [],
                as_of=AS_OF,
                policy_digest="digest-1",
            )

    def test_a_field_records_its_own_kinds_digest_not_the_bodys(self):
        """A Person-only edit must not change what a Company value recorded."""
        a = company()
        claims = current_claims([a], AS_OF, set())
        company_block = {
            "version": "company-1",
            "fields": rules("sec.company")["company"],
        }
        before = select_fields(
            "company",
            sorted(claims),
            claims,
            {"kinds": {"company": company_block, "person": {"version": "person-1"}}},
            [],
            as_of=AS_OF,
            policy_digest="body-digest-before",
        )[0]
        after = select_fields(
            "company",
            sorted(claims),
            claims,
            {"kinds": {"company": company_block, "person": {"version": "person-2"}}},
            [],
            as_of=AS_OF,
            policy_digest="body-digest-after",
        )[0]
        assert before["legal_name"]["policy_digest"] != "body-digest-before"
        assert (
            before["legal_name"]["policy_digest"]
            == after["legal_name"]["policy_digest"]
        )

    def test_an_old_shape_body_still_records_the_body_digest(self):
        a = company()
        claims = current_claims([a], AS_OF, set())
        fields, _, _ = select_fields(
            "company",
            sorted(claims),
            claims,
            {"fields": rules("sec.company")},
            [],
            as_of=AS_OF,
            policy_digest="body-digest",
        )
        assert fields["legal_name"]["policy_digest"] == "body-digest"


class TestSelectFields:
    def test_the_highest_ranked_source_wins(self):
        sec = company(source_code="sec.company", fields={"legal_name": "Apple Inc."})
        gleif = company(
            source_code="gleif.lei",
            record_key="HWUPKR0MPOU8FGXBT394",
            fields={"legal_name": "APPLE INC."},
        )
        claims = current_claims([sec, gleif], AS_OF, set())
        fields, _, _ = select_fields(
            "company",
            sorted(claims),
            claims,
            {"fields": rules("gleif.lei", "sec.company")},
            [],
            as_of=AS_OF,
            policy_digest="digest-1",
        )
        assert fields["legal_name"]["value"] == "APPLE INC."
        assert [c["value"] for c in fields["legal_name"]["conflicts"]] == ["Apple Inc."]

    def test_a_source_the_rule_does_not_name_is_not_eligible(self):
        gleif = company(source_code="gleif.lei", record_key="HWUPKR0MPOU8FGXBT394")
        claims = current_claims([gleif], AS_OF, set())
        fields, _, _ = select_fields(
            "company",
            sorted(claims),
            claims,
            {"fields": rules("sec.company")},
            [],
            as_of=AS_OF,
            policy_digest="digest-1",
        )
        assert fields == {}

    def test_a_field_records_the_digest_it_was_selected_under(self):
        a = company()
        claims = current_claims([a], AS_OF, set())
        fields, _, _ = select_fields(
            "company",
            sorted(claims),
            claims,
            {"fields": rules("sec.company")},
            [],
            as_of=AS_OF,
            policy_digest="digest-1",
        )
        assert fields["legal_name"]["policy_digest"] == "digest-1"

    def test_an_unauthorized_clear_is_reviewed_not_applied(self):
        a = company(fields={"legal_name": {"op": "clear"}})
        claims = current_claims([a], AS_OF, set())
        fields, _, reviews = select_fields(
            "company",
            sorted(claims),
            claims,
            {"fields": rules("sec.company")},
            [],
            as_of=AS_OF,
            policy_digest="digest-1",
        )
        assert fields == {}
        assert [r["reason"] for r in reviews] == ["unauthorized_clear"]

    def test_a_named_clear_source_may_clear(self):
        a = company(fields={"legal_name": {"op": "clear"}})
        claims = current_claims([a], AS_OF, set())
        fields, _, reviews = select_fields(
            "company",
            sorted(claims),
            claims,
            {"fields": rules("sec.company", clear_sources=["sec.company"])},
            [],
            as_of=AS_OF,
            policy_digest="digest-1",
        )
        assert fields["legal_name"]["cleared"] is True
        assert reviews == []

    def test_evidence_older_than_the_rule_allows_is_not_eligible(self):
        a = company(effective_at="2020-01-01T00:00:00+00:00")
        claims = current_claims([a], AS_OF, set())
        fields, _, _ = select_fields(
            "company",
            sorted(claims),
            claims,
            {"fields": rules("sec.company", max_age_days=30)},
            [],
            as_of=AS_OF,
            policy_digest="digest-1",
        )
        assert fields == {}

    def test_a_steward_override_beats_every_source_and_keeps_the_disagreement(self):
        a = company()
        claims = current_claims([a], AS_OF, set())
        override = {
            "decision_id": "decision-1",
            "subject": a["subject"],
            "field": "legal_name",
            "value": "Apple Incorporated",
            "reason": "registrar correction",
        }
        fields, _, reviews = select_fields(
            "company",
            sorted(claims),
            claims,
            {"fields": rules("sec.company")},
            [override],
            as_of=AS_OF,
            policy_digest="digest-1",
        )
        assert fields["legal_name"]["value"] == "Apple Incorporated"
        assert fields["legal_name"]["winner"]["source_code"] == "steward"
        assert [r["reason"] for r in reviews] == ["override_source_disagreement"]

    def test_two_active_overrides_on_one_field_are_refused(self):
        a = company()
        claims = current_claims([a], AS_OF, set())
        overrides = [
            {
                "decision_id": f"decision-{n}",
                "subject": a["subject"],
                "field": "legal_name",
                "value": value,
                "reason": "correction",
            }
            for n, value in ((1, "Apple Incorporated"), (2, "Apple Inc"))
        ]
        with pytest.raises(Conflict, match="Conflicting active steward overrides"):
            select_fields(
                "company",
                sorted(claims),
                claims,
                {"fields": rules("sec.company")},
                overrides,
                as_of=AS_OF,
                policy_digest="digest-1",
            )


class TestWhatTheKindDigestCovers:
    """The digest answers "under which rules did this claim win?".

    Ticket 02 decision 3 said "computed from that kind's block". Digesting the
    block whole would move every field's recorded digest when a classification
    rule changed, which does not decide any field's winner — the churn the
    per-kind digest exists to stop, reappearing inside one kind.
    """

    def block(self, **extra):
        return {
            "kinds": {
                "company": {
                    "version": "company-1",
                    "fields": rules("sec.company")["company"],
                    **extra,
                }
            }
        }

    def recorded(self, policy):
        a = company()
        claims = current_claims([a], AS_OF, set())
        fields, _, _ = select_fields(
            "company",
            sorted(claims),
            claims,
            policy,
            [],
            as_of=AS_OF,
            policy_digest="body-digest",
        )
        return fields["legal_name"]

    def test_a_rule_that_does_not_decide_a_winner_does_not_move_the_digest(self):
        plain = self.recorded(self.block())
        with_rules = self.recorded(
            self.block(
                rules=[
                    {"rule_id": "C-J", "family": "classification", "version": "1"},
                    {"rule_id": "company-lei", "family": "binding", "version": "1"},
                ],
                bars={"min_precision": 0.999},
                projection={"fields": ["legal_name"]},
            )
        )
        assert plain["policy_digest"] == with_rules["policy_digest"]

    def test_a_changed_field_rule_does_move_the_digest(self):
        before = self.recorded(self.block())
        after = self.recorded(
            {
                "kinds": {
                    "company": {
                        "version": "company-1",
                        "fields": rules("sec.company", max_age_days=30)["company"],
                    }
                }
            }
        )
        assert before["policy_digest"] != after["policy_digest"]

    def test_the_kind_version_travels_beside_the_digest_not_inside_it(self):
        first = self.recorded(self.block())
        renamed = self.recorded(
            {
                "kinds": {
                    "company": {
                        "version": "company-2",
                        "fields": rules("sec.company")["company"],
                    }
                }
            }
        )
        assert first["kind_version"] == "company-1"
        assert renamed["kind_version"] == "company-2"
        assert first["policy_digest"] == renamed["policy_digest"]

    def test_two_kinds_with_identical_rules_still_record_different_digests(self):
        a = company()
        claims = current_claims([a], AS_OF, set())
        shared = {"version": "v1", "fields": rules("sec.company")["company"]}
        digests = []
        for kind in ("company", "government"):
            claims[a["subject"]]["kind"] = kind
            fields, _, _ = select_fields(
                kind,
                sorted(claims),
                claims,
                {"kinds": {kind: shared}},
                [],
                as_of=AS_OF,
                policy_digest="body-digest",
            )
            digests.append(fields["legal_name"]["policy_digest"])
        assert digests[0] != digests[1]

    def test_an_undeclared_section_is_refused_by_name(self):
        """The guard that stops this rotting: a new section is a decision."""
        with pytest.raises(Conflict, match="invented_section"):
            self.recorded(self.block(invented_section={"a": 1}))

    def test_every_section_of_the_real_company_policy_is_declared(self):
        from edgar_warehouse.mdm.clean.company_source import POLICY
        from edgar_warehouse.mdm.clean.survivorship import (
            AUTHORITY_SECTIONS,
            NON_AUTHORITY_SECTIONS,
        )

        declared = set(AUTHORITY_SECTIONS) | set(NON_AUTHORITY_SECTIONS)
        assert not set(AUTHORITY_SECTIONS) & set(NON_AUTHORITY_SECTIONS)
        for kind, block in POLICY["kinds"].items():
            assert set(block) <= declared, f"{kind} has an undeclared section"


class TestWhatAProfileFieldRecords:
    """A profile field records its role's digest, not the enclosing kind's.

    A role attaches to several kinds — `adviser` to both company and person,
    `fund` to both company and fund_structure (`evidence.PROFILE_KINDS`) — so
    its rules live in one top-level block. Recording the enclosing kind's
    digest made an edit to a role's rules invisible: it changed no recorded
    digest anywhere.
    """

    def adviser(self, **fields):
        return {
            "role": "adviser",
            "authority": "IAPD",
            "registration": "123",
            "valid_from": "2026-01-01T00:00:00+00:00",
            "fields": fields or {"aum": "1000"},
        }

    def policy(self, *, aum_sources=("sec.company",), company_max_age=None):
        company = {"sources": ["sec.company"]}
        if company_max_age:
            company["max_age_days"] = company_max_age
        return {
            "kinds": {
                "company": {"version": "company-1", "fields": {"legal_name": company}}
            },
            "profile_fields": {"adviser": {"aum": {"sources": list(aum_sources)}}},
        }

    def recorded(self, policy):
        a = company(profiles=[self.adviser()])
        claims = current_claims([a], AS_OF, set())
        fields, profiles, _ = select_fields(
            "company",
            sorted(claims),
            claims,
            policy,
            [],
            as_of=AS_OF,
            policy_digest="body-digest",
            entity_id="entity-1",
        )
        return fields["legal_name"], profiles[0]["fields"]["aum"]

    def test_a_profile_field_does_not_record_the_kinds_digest(self):
        kind_field, profile_field = self.recorded(self.policy())
        assert profile_field["policy_digest"] != kind_field["policy_digest"]

    def test_editing_a_role_rule_moves_the_profile_digest(self):
        _, before = self.recorded(self.policy())
        _, after = self.recorded(self.policy(aum_sources=("sec.company", "gleif.lei")))
        assert before["policy_digest"] != after["policy_digest"]

    def test_editing_a_role_rule_leaves_every_kind_field_alone(self):
        before, _ = self.recorded(self.policy())
        after, _ = self.recorded(self.policy(aum_sources=("sec.company", "gleif.lei")))
        assert before["policy_digest"] == after["policy_digest"]

    def test_editing_a_kind_rule_leaves_the_profile_digest_alone(self):
        _, before = self.recorded(self.policy())
        _, after = self.recorded(self.policy(company_max_age=30))
        assert before["policy_digest"] == after["policy_digest"]

    def test_a_profile_field_carries_its_role_not_a_kind_version(self):
        _, profile_field = self.recorded(self.policy())
        assert profile_field["kind_version"] == "adviser"

    def test_two_roles_with_identical_rules_record_different_digests(self):
        a = company(
            profiles=[
                self.adviser(),
                {
                    "role": "audit_firm",
                    "authority": "PCAOB",
                    "registration": "456",
                    "valid_from": "2026-01-01T00:00:00+00:00",
                    "fields": {"aum": "1000"},
                },
            ]
        )
        claims = current_claims([a], AS_OF, set())
        shared = {"aum": {"sources": ["sec.company"]}}
        _, profiles, _ = select_fields(
            "company",
            sorted(claims),
            claims,
            {
                "kinds": {"company": {"version": "c1", "fields": {}}},
                "profile_fields": {"adviser": shared, "audit_firm": shared},
            },
            [],
            as_of=AS_OF,
            policy_digest="body-digest",
            entity_id="entity-1",
        )
        digests = {p["role"]: p["fields"]["aum"]["policy_digest"] for p in profiles}
        assert digests["adviser"] != digests["audit_firm"]

    def test_an_old_shape_body_still_records_the_body_digest(self):
        """A body with no kinds block has no per-kind digest, and no per-role."""
        a = company(profiles=[self.adviser()])
        claims = current_claims([a], AS_OF, set())
        _, profiles, _ = select_fields(
            "company",
            sorted(claims),
            claims,
            {
                "fields": rules("sec.company"),
                "profile_fields": {"adviser": {"aum": {"sources": ["sec.company"]}}},
            },
            [],
            as_of=AS_OF,
            policy_digest="body-digest",
            entity_id="entity-1",
        )
        assert profiles[0]["fields"]["aum"]["policy_digest"] == "body-digest"


class TestAKindLevelDefault:
    """Operator, 2026-09-24: every field from every source; priority where both."""

    def claims(self):
        sec = company(fields={"name": "MICROSOFT CORP", "sic": "7372"})
        gleif = company(
            source_code="gleif.level1",
            record_key="INR2EJN1ERAN0W5ZP974",
            fields={"name": "MICROSOFT CORPORATION", "legal_form": "NHYA"},
        )
        return [sec["subject"], gleif["subject"]], current_claims(
            [sec, gleif], AS_OF, set()
        )

    def select(self, block):
        subjects, claims = self.claims()
        fields, _, _ = select_fields(
            "company",
            subjects,
            claims,
            {"kinds": {"company": block}},
            [],
            as_of=AS_OF,
            policy_digest="d",
        )
        return fields

    def test_every_field_any_source_supplies_is_selected(self):
        fields = self.select({"defaults": {"sources": ["sec.company", "gleif.level1"]}})
        assert {k: v["value"] for k, v in fields.items()} == {
            "name": "MICROSOFT CORP",
            "sic": "7372",
            "legal_form": "NHYA",
        }
        assert [c["value"] for c in fields["name"]["conflicts"]] == [
            "MICROSOFT CORPORATION"
        ]

    def test_a_field_may_state_its_own_order(self):
        fields = self.select(
            {
                "defaults": {"sources": ["sec.company", "gleif.level1"]},
                "fields": {"name": {"sources": ["gleif.level1", "sec.company"]}},
            }
        )
        assert fields["name"]["value"] == "MICROSOFT CORPORATION"
        assert fields["sic"]["value"] == "7372"

    def test_without_a_default_only_declared_fields_are_selected(self):
        fields = self.select(
            {"fields": {"name": {"sources": ["sec.company", "gleif.level1"]}}}
        )
        assert set(fields) == {"name"}

    def test_the_default_is_authority_so_it_moves_the_recorded_digest(self):
        one = self.select({"defaults": {"sources": ["sec.company", "gleif.level1"]}})
        two = self.select({"defaults": {"sources": ["gleif.level1", "sec.company"]}})
        assert one["sic"]["policy_digest"] != two["sic"]["policy_digest"]
