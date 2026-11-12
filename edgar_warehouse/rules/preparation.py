"""Configured preparation before a load derives its scope and freezes any new run.

Operations live in a registry; the loader knows neither a provider nor an identity
kind. Matching remains in the existing Merge Stage. Private, hash-bound artifacts
cache expensive input projection; retry always applies its pairs idempotently.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import tempfile
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.control_contract import canonical, digest
from edgar_warehouse.mdm import raw_capture

from . import files
from .driving import RunStopped


@contextmanager
def registered_store(policy_digest, environment):
    from edgar_warehouse.database_connections import storage_adapter
    from edgar_warehouse.mastering.store import open_store
    from edgar_warehouse.mdm.connections import engine_from_environment

    value = environment.get("MDM_DATABASE_URL")
    if not value:
        raise RunStopped("Automatic preparation needs the selected stores' worker MDM login")
    engine = engine_from_environment("MDM_DATABASE_URL", environment, restricted=True)
    store = None
    try:
        with engine.connect() as conn:
            policy = storage_adapter().registered_policy(conn, policy_digest)
        if policy is None:
            raise RunStopped("Automatic preparation requires the load's registered mastering policy")
        store = open_store(engine)
        yield store
    finally:
        if store is not None:
            store.close()
        engine.dispose()


def _runtime():
    from edgar_warehouse.mastering import merge
    from edgar_warehouse.mdm import cascade, matching, names, waterfall
    from edgar_warehouse.workers import source_read

    paths = {*source_read.runtime_files(), *(Path(m.__file__) for m in
             (merge, cascade, matching, names, waterfall)), Path(__file__)}
    hashes = []
    for path in sorted(paths):
        with path.open("rb") as stream:
            hashes.append(hashlib.file_digest(stream, "sha256").hexdigest())
    return digest(hashes)


def project_capture(artifacts, folder, name, recipe, inputs):
    """The same local worker path as a local target: one authenticated read, no second parse."""
    from edgar_warehouse.workers import source_read

    request = raw_capture.request(artifacts.put(folder.as_uri(), recipe), inputs)
    task = {"input": artifacts.put(folder.as_uri(), request),
            "output": (folder / f"{name}.reading.json").as_uri(), "checks": ["source.output"]}
    return source_read.execute(task, artifacts)


def population(filers):
    """Only facts the pass consumes; retaining its derived answer must not invalidate its own cache."""
    def plain(value):
        if isinstance(value, dict):
            return {k: plain(v) for k, v in value.items()}
        if isinstance(value, (set, frozenset)):
            return sorted((plain(v) for v in value), key=canonical)
        if isinstance(value, (list, tuple)):
            return [plain(v) for v in value]
        return value

    return sorted((plain(asdict(f)) for f in filers), key=canonical)


def _waterfall(*, options, capture, folder, facts, as_of, deadline, say, environment):
    from edgar_warehouse.mastering import merge
    from edgar_warehouse.mdm import cascade, waterfall
    from edgar_warehouse.mdm.activation import activated

    required = {"kind", "holder_source", "files", "full_filename", "completeness", "count_fact"}
    if (set(options) != required or any(not isinstance(v, str) or not v for v in options.values())
            or options["completeness"] != "full_publication"):
        raise RunStopped("Waterfall preparation requires an explicit full-publication declaration and filename")
    try:
        full_filename = re.compile(options["full_filename"])
    except re.error:
        raise RunStopped("Waterfall preparation's full-publication filename is not a valid pattern") from None
    try:
        count = facts[options["count_fact"]]
        if type(count) is not int or not 0 <= count <= waterfall.GLEIF_ROWS:
            raise ValueError()
    except (KeyError, ValueError, TypeError):
        raise RunStopped("Waterfall preparation needs its declared complete-publication count fact") from None
    policy = files.policy()
    policy_digest = digest(policy)
    kind = options["kind"]
    body = policy.get("kinds", {}).get(kind)
    if body is None:
        raise RunStopped("Waterfall preparation names no configured identity kind")
    # Prepare only the rules which may actually act; declared but inactive rules cannot expand scope.
    active = [r for r in body.get("rules", []) if activated(policy, kind, r, "bind")]
    spec = cascade.spec({"kinds": {kind: {**body, "rules": active}}}, kind)
    if not spec["passes"]:
        raise RunStopped("Waterfall preparation has no active matching pass")
    import fnmatch

    _, receipts = raw_capture.receipts(capture)
    keys = sorted(k for k in receipts if fnmatch.fnmatchcase(k, options["files"])
                  and full_filename.fullmatch(k.rsplit("/", 1)[-1]))
    if len(keys) != 1:
        raise RunStopped("Waterfall preparation requires exactly one complete Golden Copy publication")
    archive = raw_capture.document(capture, receipts, keys[0])
    artifacts = Artifacts()
    folder.mkdir(parents=True, exist_ok=True)
    with registered_store(policy_digest, environment) as store:
        records = [json.loads(b) if isinstance(b, str) else b for (b,) in
                   store.rows("select body from mastering_record where source_code=%s", [options["holder_source"]])]
        filers = waterfall.filers_from_records(records)
        recipe = files.load(waterfall.GLEIF_READING)
        inputs = {"version": 1, "archive": archive, "records": count, "options": options, "recipe": recipe,
                  "filers": population(filers), "policy": policy_digest, "runtime": _runtime()}
        cache_key = digest(inputs)
        cache = folder / f"{cache_key}.json"
        if time.monotonic() >= deadline:
            raise RunStopped("Automatic preparation reached the load deadline")
        if cache.exists():
            result = artifacts.json(json.loads(cache.read_text()))
            if result["input_digest"] != cache_key:
                raise RunStopped("Cached waterfall preparation names different inputs")
            # Reuse projection, not unchecked bytes: a receipt retained beside a damaged capture
            # must not let the cached answer reach the database. Hash compressed bytes once.
            with artifacts.verified_stream(archive, max_bytes=recipe["read"]["stream"]["max_input_bytes"]):
                pass
        else:
            wanted = sorted(waterfall.wanted_names(filers))
            lookup = artifacts.put(folder.as_uri(), {"version": 1, "input": archive, "sets": {"wanted": wanted}})
            context = artifacts.put(folder.as_uri(), {"version": 1, "input": archive,
                                                       "values": {"publication_count": count}})
            reading = project_capture(artifacts, folder, cache_key, recipe,
                [{"input": archive, "context": context, "lookups": lookup}])
            publication, pairs = waterfall.declared_pairs(filers, reading, artifacts, count,
                                                          spec["passes"], over_shared=spec["over_shared"])
            if publication["archive_sha256"] != archive["sha256"]:
                raise RunStopped("Waterfall projection names another captured archive")
            result = {"input_digest": cache_key, "publication": publication, "pairs": pairs}
            receipt = artifacts.put(folder.as_uri(), result)
            # Cache only a fully read and verified projection. Retrying after an interrupted apply still applies it.
            with tempfile.NamedTemporaryFile(mode="w", dir=folder, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(canonical(receipt))
            try:
                temporary.replace(cache)
            finally:
                temporary.unlink(missing_ok=True)
        if time.monotonic() >= deadline:
            raise RunStopped("Automatic preparation reached the load deadline before applying pairs")
        counts = merge.apply_pairs(store, merge.Settings(policy, policy_digest, kind, as_of),
                                   options["holder_source"], result["pairs"])
    say(f"Automatic waterfall preparation: {len(filers)} source records, {count} publication records, "
        f"{len(result['pairs'])} pairs; applied {counts.get('records', 0)} records")
    return {"method": "waterfall", "input_digest": cache_key, "publication": result["publication"],
            "filers": len(filers), "pairs": len(result["pairs"]), "applied": counts.get("records", 0)}


METHODS = {"waterfall": _waterfall}


def prepare_load(*, reading, target, capture, folder, facts, as_of, deadline, say, environment):
    declared = reading["bookkeeping"]["targets"][target].get("preparation", [])
    if not declared:
        return []
    # Reuse the target validator, including the preparation declaration's strict outer shape.
    from edgar_warehouse.bookkeeping.clean.config import validate
    from edgar_warehouse.mdm.target_manifest import run_arguments

    validate(reading, target)
    named, _ = run_arguments(facts, [])
    for step in declared:
        if step["method"] not in METHODS:
            raise RunStopped(f"Unknown automatic preparation method {step['method']}")
    return [METHODS[step["method"]](options=step["options"], capture=capture.resolve(),
            folder=folder.resolve() / str(i), facts=named, as_of=as_of, deadline=deadline, say=say,
            environment=environment)
            for i, step in enumerate(declared)]
