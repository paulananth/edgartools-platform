from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from edgar_warehouse.mdm.database import GUID


def _uuid_string() -> str:
    return str(uuid.uuid4())


class AcquisitionBase(DeclarativeBase):
    """Metadata boundary for the acquisition ledger tables."""


class SourceObservationCursor(AcquisitionBase):
    __tablename__ = "source_observation_cursor"

    source_family: Mapped[str] = mapped_column(Text, primary_key=True)
    logical_source_key: Mapped[str] = mapped_column(Text, primary_key=True)
    last_position: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "last_position > 0", name="ck_source_observation_position_positive"
        ),
    )


class SourceFetchDecisionRecord(AcquisitionBase):
    __tablename__ = "source_fetch_decision"

    decision_id: Mapped[str] = mapped_column(
        GUID(), primary_key=True, default=_uuid_string
    )
    candidate_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source_family: Mapped[str] = mapped_column(Text, nullable=False)
    logical_source_key: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    observation_position: Mapped[int] = mapped_column(Integer, nullable=False)
    cause: Mapped[str] = mapped_column(Text, nullable=False)
    cause_reference: Mapped[str] = mapped_column(Text, nullable=False)
    owner_role: Mapped[str] = mapped_column(Text, nullable=False)
    fetch_disposition: Mapped[str] = mapped_column(Text, nullable=False)
    blocker: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_action: Mapped[str] = mapped_column(Text, nullable=False)
    verified_evidence_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope_proof_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    operator_authorization_reference: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    next_eligible_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        UniqueConstraint(
            "source_family",
            "logical_source_key",
            "observation_position",
            name="uq_source_fetch_decision_observation",
        ),
        CheckConstraint(
            "cause IN ('CAPTURED_DISCOVERY','DUE_POLICY','OPERATOR_REQUEST')",
            name="ck_source_fetch_decision_cause",
        ),
        CheckConstraint(
            "owner_role IN ('ACQUISITION_COORDINATOR','ACQUISITION_OPERATOR')",
            name="ck_source_fetch_decision_owner_role",
        ),
        CheckConstraint(
            "fetch_disposition IN ("
            "'FETCH_AUTHORIZED','DOWNLOAD_DEFERRED','ALREADY_CAPTURED_VERIFIED',"
            "'OUT_OF_SCOPE','OPERATOR_EXCLUDED')",
            name="ck_source_fetch_decision_disposition",
        ),
        CheckConstraint(
            "(cause = 'OPERATOR_REQUEST' AND owner_role = 'ACQUISITION_OPERATOR') OR "
            "(cause IN ('CAPTURED_DISCOVERY','DUE_POLICY') AND "
            "owner_role = 'ACQUISITION_COORDINATOR')",
            name="ck_source_fetch_decision_cause_owner",
        ),
        CheckConstraint(
            "fetch_disposition <> 'OPERATOR_EXCLUDED' OR "
            "(cause = 'OPERATOR_REQUEST' AND owner_role = 'ACQUISITION_OPERATOR')",
            name="ck_source_fetch_decision_operator_exclusion",
        ),
        CheckConstraint(
            "fetch_disposition <> 'DOWNLOAD_DEFERRED' OR "
            "(blocker IS NOT NULL AND next_eligible_at IS NOT NULL AND "
            "next_action <> 'NONE')",
            name="ck_source_fetch_decision_deferred_open",
        ),
        CheckConstraint(
            "fetch_disposition NOT IN ("
            "'ALREADY_CAPTURED_VERIFIED','OUT_OF_SCOPE','OPERATOR_EXCLUDED') "
            "OR (next_action = 'NONE' AND next_eligible_at IS NULL)",
            name="ck_source_fetch_decision_terminal_no_download",
        ),
        CheckConstraint(
            "fetch_disposition <> 'ALREADY_CAPTURED_VERIFIED' OR "
            "verified_evidence_reference IS NOT NULL",
            name="ck_source_fetch_decision_verified_evidence",
        ),
        CheckConstraint(
            "fetch_disposition <> 'OUT_OF_SCOPE' OR scope_proof_reference IS NOT NULL",
            name="ck_source_fetch_decision_scope_proof",
        ),
        CheckConstraint(
            "fetch_disposition <> 'OPERATOR_EXCLUDED' OR "
            "operator_authorization_reference IS NOT NULL",
            name="ck_source_fetch_decision_operator_authorization",
        ),
    )


class SourceFetchWorkRecord(AcquisitionBase):
    __tablename__ = "source_fetch_work"

    decision_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("source_fetch_decision.decision_id"),
        primary_key=True,
    )
    source_family: Mapped[str] = mapped_column(Text, nullable=False)
    logical_source_key: Mapped[str] = mapped_column(Text, nullable=False)
    fetch_state: Mapped[str] = mapped_column(Text, nullable=False)
    fencing_token: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_owner: Mapped[str | None] = mapped_column(Text, nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_transition_role: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        CheckConstraint(
            "fetch_state IN ('READY','LEASED','CAPTURED','FAILED')",
            name="ck_source_fetch_work_state",
        ),
        CheckConstraint(
            "fencing_token >= 0", name="ck_source_fetch_work_fencing_token"
        ),
        CheckConstraint(
            "last_transition_role IN ("
            "'ACQUISITION_COORDINATOR','ACQUISITION_OPERATOR','ACQUISITION_WORKER')",
            name="ck_source_fetch_work_transition_role",
        ),
        CheckConstraint(
            "(fetch_state = 'READY' AND fencing_token = 0 AND lease_owner IS NULL "
            "AND lease_expires_at IS NULL AND "
            "last_transition_role IN ("
            "'ACQUISITION_COORDINATOR','ACQUISITION_OPERATOR')) OR "
            "(fetch_state = 'LEASED' AND fencing_token > 0 AND lease_owner IS NOT NULL "
            "AND lease_expires_at IS NOT NULL AND "
            "last_transition_role = 'ACQUISITION_WORKER') OR "
            "(fetch_state IN ('CAPTURED','FAILED') AND fencing_token > 0 AND "
            "lease_owner IS NULL AND lease_expires_at IS NULL AND "
            "last_transition_role = 'ACQUISITION_WORKER')",
            name="ck_source_fetch_work_state_shape",
        ),
        Index(
            "uq_source_fetch_work_active_key",
            "source_family",
            "logical_source_key",
            unique=True,
            sqlite_where=text("fetch_state IN ('READY','LEASED','FAILED')"),
            postgresql_where=text("fetch_state IN ('READY','LEASED','FAILED')"),
        ),
    )


class SourceFetchTransitionRecord(AcquisitionBase):
    __tablename__ = "source_fetch_transition"

    transition_id: Mapped[str] = mapped_column(
        GUID(), primary_key=True, default=_uuid_string
    )
    decision_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("source_fetch_decision.decision_id"), nullable=False
    )
    from_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    to_state: Mapped[str] = mapped_column(Text, nullable=False)
    owner_role: Mapped[str] = mapped_column(Text, nullable=False)
    fencing_token: Mapped[int] = mapped_column(Integer, nullable=False)
    worker_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        CheckConstraint(
            "to_state IN ('READY','LEASED','CAPTURED','FAILED')",
            name="ck_source_fetch_transition_state",
        ),
        CheckConstraint(
            "(from_state IS NULL AND to_state = 'READY' AND "
            "owner_role IN ('ACQUISITION_COORDINATOR','ACQUISITION_OPERATOR') "
            "AND fencing_token = 0) OR "
            "(from_state IN ('READY','LEASED','FAILED') AND to_state = 'LEASED' AND "
            "owner_role = 'ACQUISITION_WORKER' AND fencing_token > 0) OR "
            "(from_state = 'LEASED' AND to_state IN ('CAPTURED','FAILED') AND "
            "owner_role = 'ACQUISITION_WORKER' AND fencing_token > 0)",
            name="ck_source_fetch_transition_owner",
        ),
    )
