"""The existing control transition protocol, compiled for its storage engine."""
from sqlalchemy import text

from .config import Blocked

POSTGRES = {
    "start_run": "SELECT bookkeeping.start_run(CAST(:r AS uuid),CAST(:s AS jsonb),:h,CAST(:i AS jsonb))",
    "block_run": "SELECT bookkeeping.block_run(CAST(:r AS uuid),:m)",
    "claim": "SELECT bookkeeping.claim(CAST(:r AS uuid),:s,:k,CAST(:a AS uuid),:d,CAST(:p AS jsonb))",
    "heartbeat": "SELECT bookkeeping.heartbeat(CAST(:r AS uuid),:s,:k,CAST(:a AS uuid),CAST(:p AS jsonb),:d)",
    "wait_work": "SELECT bookkeeping.wait_work(CAST(:r AS uuid),:s,:k,:m,CAST(:a AS uuid),CAST(:p AS jsonb))",
    "report": "SELECT bookkeeping.report(CAST(:r AS uuid),:s,:k,CAST(:a AS uuid),CAST(:p AS jsonb),CAST(:c AS jsonb),:f,:t)",
    "verify_claim": "SELECT bookkeeping.verify_claim(CAST(:r AS uuid),:s,:k,CAST(:a AS uuid),:d)",
    "pin_verifier": "SELECT bookkeeping.pin_verifier(CAST(:r AS uuid),:s,:t)",
    "finish": "SELECT bookkeeping.finish(CAST(:r AS uuid),:s,:k,CAST(:a AS uuid),CAST(:p AS jsonb),CAST(:v AS jsonb),CAST(:c AS jsonb),CAST(:e AS uuid))",
    "finish_resource": "SELECT bookkeeping.finish_resource(CAST(:r AS uuid),:s,:k,CAST(:a AS uuid),CAST(:p AS jsonb),CAST(:v AS jsonb),CAST(:c AS jsonb),CAST(:e AS uuid),:resource,:revision,:position)",
    "finish_expand": "SELECT bookkeeping.finish_expand(CAST(:r AS uuid),:s,:k,CAST(:a AS uuid),CAST(:p AS jsonb),CAST(:v AS jsonb),CAST(:c AS jsonb),CAST(:e AS uuid),CAST(:children AS jsonb),:child_step)",
    "delivery": "SELECT bookkeeping.delivery(CAST(:e AS uuid),:m)",
}


def call(engine, operation, params):
    if engine.dialect.name == "mysql":
        from .mysql import call as selected_call
        return selected_call(engine, operation, params)
    if engine.dialect.name != "postgresql" or operation not in POSTGRES:
        raise Blocked("Unsupported control storage capability")
    with engine.begin() as conn:
        return conn.scalar(text(POSTGRES[operation]), {"a": None, "p": "[]", "m": None, **params})


def complete(engine, operation, params, runtime):
    if engine.dialect.name == "mysql":
        from .mysql import call as selected_call
        return selected_call(engine, operation, {**params, "t": runtime})
    if engine.dialect.name != "postgresql" or operation not in {"finish", "finish_resource", "finish_expand"}:
        raise Blocked("Unsupported control completion capability")
    with engine.begin() as conn:
        conn.execute(text(POSTGRES["pin_verifier"]), {"r": params["r"], "s": params["s"], "t": runtime})
        conn.execute(text(POSTGRES[operation]), params)


def contention(engine, error):
    if engine.dialect.name == "postgresql":
        return getattr(error.orig, "pgcode", None) == "55P03"
    return engine.dialect.name == "mysql" and error.orig.args[0] in {1205, 1213, 3572}
