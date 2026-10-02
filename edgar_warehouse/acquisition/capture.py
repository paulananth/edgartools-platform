"""Configured acquisition capability using only Bookkeeping and source manifests.

Provider selection is by named capability; source identity never dispatches
code. Capture returns a source-owned immutable outcome manifest, not a row in
the journal. A 304 must reference previously verified captured bytes.
"""

from __future__ import annotations

import hashlib
import io
import os
import zipfile
from urllib.parse import unquote, urlparse

from .decisions import (
    DecisionCause,
    DecisionOwnerRole,
    FetchDecisionRequest,
    FetchDisposition,
    validate_decision_owner,
    validate_terminal_evidence,
)
from edgar_warehouse.bookkeeping.clean.artifacts import json_value
from edgar_warehouse.bookkeeping.clean.config import (
    Blocked,
    Capability,
    canonical,
    digest,
)

from edgar_warehouse.rules.acquisition_authority import frozen_authority


def complete(data: bytes, definition: dict) -> bool:
    if (
        len(data) > definition["max_bytes"]
        or not data
        and not definition["allow_empty"]
    ):
        return False
    try:
        if definition["format"] in {"json", "ticker_catalog"}:
            value = json_value(data)
            if definition["format"] == "ticker_catalog":
                from edgar_warehouse.acquisition.source_family_registry import (
                    _is_valid_ticker_catalog_json,
                )

                if not _is_valid_ticker_catalog_json(data):
                    return False
            if not value and not definition["allow_empty"]:
                return False
            for path in definition["required"]:
                selected = value
                for field in path.split("."):
                    selected = selected[field]
                if selected is None:
                    return False
        elif definition["format"] == "xml":
            from lxml import etree

            root = etree.fromstring(
                data, parser=etree.XMLParser(resolve_entities=False, no_network=True)
            )
            if any(
                not root.xpath(
                    path,
                    namespaces={"n": root.nsmap[None]} if None in root.nsmap else {},
                )
                for path in definition["required"]
            ):
                return False
        elif definition["format"] == "zip":
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if (
                    sum(info.file_size for info in archive.infolist())
                    > definition["max_bytes"]
                    or not archive.namelist()
                    and not definition["allow_empty"]
                    or not set(definition["required"]) <= set(archive.namelist())
                    or archive.testzip() is not None
                ):
                    return False
        elif any(term not in data.decode("utf-8") for term in definition["required"]):
            return False
        return True
    except (
        ValueError,
        KeyError,
        TypeError,
        IndexError,
        UnicodeError,
        zipfile.BadZipFile,
    ):
        return False


def _approved_url(url: str, prefixes: list[str]) -> bool:
    if not isinstance(url, str) or any(ord(c) <= 32 or c == "\\" for c in url):
        return False
    try:
        parsed = urlparse(url)
        # Inspect the decoded path that an HTTP client/provider may normalize.
        # Reject nested escapes rather than accepting ambiguous coverage.
        path = unquote(parsed.path, errors="strict")
        if "%" in path or "\\" in path or any(ord(c) < 32 for c in path):
            return False
        if any(part in {".", ".."} for part in path.split("/")):
            return False
        _ = parsed.port
    except (ValueError, UnicodeError):
        return False
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        return False
    for prefix in prefixes:
        approved = urlparse(prefix)
        if (
            parsed.netloc == approved.netloc
            and parsed.path.startswith(approved.path)
            and path.startswith(approved.path)
        ):
            return True
    return False


def _http(url, identity, *, etag, last_modified, before_request, definition):
    from edgar_warehouse.infrastructure.sec_client import (
        download_provider_conditionally,
    )

    return download_provider_conditionally(
        url,
        identity,
        etag=etag,
        last_modified=last_modified,
        before_request=before_request,
        max_bytes=definition["completeness"]["max_bytes"],
    )


def _sec(url, identity, *, etag, last_modified, before_request, definition):
    from edgar_warehouse.infrastructure.sec_client import (
        download_authorized_sec_conditionally,
    )

    return download_authorized_sec_conditionally(
        url,
        identity,
        etag=etag,
        last_modified=last_modified,
        before_request=before_request,
        max_bytes=definition["completeness"]["max_bytes"],
    )


def register_capture(registry, journal, *, fetchers=None):
    fetchers = fetchers or {"http.conditional": _http, "sec.conditional": _sec}

    def command(book, item):
        run, _, _, _ = book._frozen(str(item["run_id"]))
        submission = run["submission"]
        export = book.artifacts.json(submission["rules"])
        authority = frozen_authority(export, submission["scope"].get("feed"))
        spec = book.artifacts.json(item["unit"]["input"])
        if (
            set(spec)
            != {"version", "source", "feed", "scope", "request", "prior", "evidence"}
            or type(spec["version"]) is not int
            or spec["version"] != 1
            or spec["source"] != authority["name"]
            or spec["feed"] != authority["feed"]
            or not isinstance(spec["scope"], dict)
            or set(spec["scope"]) != set(authority["configuration"]["scope"])
            or any(item["unit"]["keys"].get(k) != v for k, v in spec["scope"].items())
        ):
            raise Blocked("Capture decision differs from frozen source/feed scope")
        try:
            request = FetchDecisionRequest(
                **{
                    **spec["request"],
                    "cause": DecisionCause(spec["request"]["cause"]),
                    "owner_role": DecisionOwnerRole(spec["request"]["owner_role"]),
                    "disposition": FetchDisposition(spec["request"]["disposition"]),
                }
            )
            validate_decision_owner(request)
            validate_terminal_evidence(request)
        except (KeyError, TypeError, ValueError) as exc:
            raise Blocked("Invalid frozen acquisition decision") from exc
        if request.disposition is FetchDisposition.DOWNLOAD_DEFERRED:
            raise Blocked(
                "Deferred acquisition remains pending; it is not successful zero work"
            )
        if (
            request.cause is DecisionCause.OPERATOR_REQUEST
            and not request.operator_authorization_reference
        ):
            raise Blocked(
                "Operator request requires its explicit authorization evidence"
            )
        definition = authority["configuration"]
        if "page_completeness" in definition and spec["scope"].get("file") != "main":
            definition = {**definition, "completeness": definition["page_completeness"]}
        if request.source_family != definition["family"] or not _approved_url(
            request.source_url, definition["url_prefixes"]
        ):
            raise Blocked("Request is outside approved feed coverage")
        if item["unit"]["keys"].get("candidate_id") != request.candidate_id:
            raise Blocked("Capture must retain the original candidate identity")
        if (
            "logical_key" in spec["scope"]
            and spec["scope"]["logical_key"] != request.logical_source_key
        ):
            raise Blocked("Capture logical identity differs from the frozen scope")
        if not spec["evidence"]:
            raise Blocked("Acquisition requires immutable authorization evidence")
        verified = {
            ref["uri"]
            for ref in spec["evidence"]
            if book.artifacts.verified(ref) is not None
        }
        for ref in (
            request.cause_reference,
            request.operator_authorization_reference,
            request.scope_proof_reference,
            request.verified_evidence_reference,
        ):
            if ref is not None and ref not in verified:
                raise Blocked(
                    "Acquisition decision references unverified authorization evidence"
                )
        if (
            request.cause is DecisionCause.OPERATOR_REQUEST
            or request.disposition is FetchDisposition.OPERATOR_EXCLUDED
        ):
            approved = authority["configuration"].get("authorizations", [])
            if not any(
                ref["uri"] == request.operator_authorization_reference
                and ref in spec["evidence"]
                for ref in approved
            ):
                raise Blocked(
                    "Operator request requires an authorization pinned in approved Rules"
                )
            authorization = next(
                ref
                for ref in approved
                if ref["uri"] == request.operator_authorization_reference
            )
            expected = {
                "source": spec["source"],
                "feed": spec["feed"],
                "scope": spec["scope"],
                "candidate_id": request.candidate_id,
                "request_digest": digest(
                    {
                        k: v
                        for k, v in spec["request"].items()
                        if k != "operator_authorization_reference"
                    }
                ),
            }
            if book.artifacts.json(authorization) != expected:
                raise Blocked(
                    "Operator authorization names a different original request"
                )
        if definition["capabilities"]["fetch"] not in fetchers:
            raise Blocked("No registered fetch capability")
        prior = None
        if spec["prior"] is not None:
            prior = book.artifacts.json(spec["prior"])
            if (prior.get("source"), prior.get("feed"), prior.get("scope")) != (
                spec["source"],
                spec["feed"],
                spec["scope"],
            ):
                raise Blocked("Prior capture belongs to different source scope")
            if prior.get("outcome") not in {"captured", "unchanged"}:
                raise Blocked("Conditional request requires a verified prior capture")
            data = book.artifacts.verified(prior["artifact"])
            if not complete(data, definition["completeness"]):
                raise Blocked("Prior evidence fails current completeness")
        if request.disposition is FetchDisposition.ALREADY_CAPTURED_VERIFIED and (
            prior is None or request.verified_evidence_reference != spec["prior"]["uri"]
        ):
            raise Blocked(
                "Verified unchanged decision requires its exact verified prior capture"
            )
        return spec, request, definition, prior

    def outcome(book, item, body):
        ref = book.artifacts.put_bytes(item["unit"]["output"], canonical(body).encode())
        return {**ref, "evidence": ref}

    def execute(book, item, authority):
        spec, request, definition, prior = command(book, item)
        if request.disposition is not FetchDisposition.FETCH_AUTHORIZED:
            # Terminal decisions retain their authorization and evidence, with
            # no new provider request or invented successful zero capture.
            return outcome(
                book,
                item,
                {
                    "version": 1,
                    "source": spec["source"],
                    "feed": spec["feed"],
                    "scope": spec["scope"],
                    "decision": item["unit"]["input"],
                    "outcome": request.disposition.value,
                    "evidence": spec["evidence"],
                },
            )
        identity = os.environ["EDGAR_IDENTITY"]
        if "@" not in identity:
            raise Blocked("Provider identity requires an email address")

        def authorize():
            updated = book.authorize_request(authority.current(), journal)
            with authority.lock:
                authority.claim = updated

        result = fetchers[definition["capabilities"]["fetch"]](
            request.source_url,
            identity,
            etag=prior.get("etag") if prior else None,
            last_modified=prior.get("last_modified") if prior else None,
            before_request=authorize,
            definition=definition,
        )
        if result.not_modified:
            if prior is None or result.content:
                raise Blocked("304 has no verified prior source artifact")
            artifact = prior["artifact"]
            state = "unchanged"
        else:
            if not complete(result.content, definition["completeness"]):
                raise Blocked("Provider payload is incomplete")
            sha = hashlib.sha256(result.content).hexdigest()
            artifact = book.artifacts.put_bytes(
                item["unit"]["output"] + f".raw/{sha}", result.content
            )
            state = "captured"
        return outcome(
            book,
            item,
            {
                "version": 1,
                "source": spec["source"],
                "feed": spec["feed"],
                "scope": spec["scope"],
                "decision": item["unit"]["input"],
                "outcome": state,
                "artifact": artifact,
                "etag": result.etag,
                "last_modified": result.last_modified,
            },
        )

    def verify(book, item, receipt):
        if not receipt or receipt.get("uri") != item["unit"]["output"]:
            return False
        output = {"uri": receipt["uri"], "sha256": receipt["sha256"]}
        if receipt.get("evidence") != output:
            return False
        book.artifacts.verified(output)
        spec, request, definition, prior = command(book, item)
        body = book.artifacts.json(receipt["evidence"])
        if (
            body.get("decision") != item["unit"]["input"]
            or body.get("source") != spec["source"]
            or body.get("feed") != spec["feed"]
            or body.get("scope") != spec["scope"]
        ):
            return False
        if request.disposition is not FetchDisposition.FETCH_AUTHORIZED:
            return (
                body.get("outcome") == request.disposition.value
                and body.get("evidence") == spec["evidence"]
            )
        if body.get("outcome") not in {"captured", "unchanged"}:
            return False
        receipt = journal.get("acquisition", request.candidate_id)
        if (
            receipt is None
            or receipt["event"]["run_id"] != str(item["run_id"])
            or item["unit"]["input"] not in receipt["event"]["evidence"]
        ):
            raise Blocked("Capture lacks its original verified journal authorization")
        journal.verify(receipt)
        if body["outcome"] == "unchanged" and (
            prior is None or body.get("artifact") != prior["artifact"]
        ):
            return False
        if (
            body["outcome"] == "captured"
            and body["artifact"]["uri"]
            != item["unit"]["output"] + ".raw/" + body["artifact"]["sha256"]
        ):
            return False
        return complete(
            book.artifacts.verified(body["artifact"]), definition["completeness"]
        )

    def reconcile(book, item, authority):
        # Exact frozen outcome URI only; never list storage or infer completion
        # from unreferenced raw objects left by an interrupted capture.
        try:
            data = book.artifacts.read(item["unit"]["output"])
        except Blocked:
            return None
        ref = {
            "uri": item["unit"]["output"],
            "sha256": hashlib.sha256(data).hexdigest(),
        }
        receipt = {**ref, "evidence": ref}
        if not verify(book, item, receipt):
            raise Blocked("Committed capture outcome failed reconciliation")
        return receipt

    registry.operation(
        "provider.capture", Capability("source-outcome-v1", execute, reconcile, verify)
    )
