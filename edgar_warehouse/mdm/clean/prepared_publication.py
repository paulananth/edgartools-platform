"""Read and deliver original selected-store publication bytes."""
import json

from .prepared import authority, _refusals
from .prepared_registry import installed
from .store import Conflict, canonical


def adapter(store):
    with store.engine.connect() as conn:
        api = installed(conn)
    if api is None or api.protocol < 6:
        raise Conflict("Worker publication requires the protocol-6 owner migration")
    return api


def retained(store, batch, consumer, *, connection=None):
    if connection is None:
        with store.engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
            return retained(store, batch, consumer, connection=conn)
    api = installed(connection)
    if api is None or api.protocol < 6:
        raise Conflict("Worker publication requires the protocol-6 owner migration")
    rows = api.read_batches([batch], connection=connection)
    if len(rows) != 1:
        raise Conflict("Unknown publication batch")
    command = rows[0]
    intent = json.loads(bytes(command["intent"]))
    consumers = {bytes.fromhex(item["consumer"]).decode() for item in intent["consumers"]}
    if consumer not in consumers:
        raise Conflict("Consumer differs from the frozen publication contract")
    publications = api.read_batches([batch], outboxes=True, connection=connection)
    selected = [row for row in publications if bytes(row["consumer_bytes"]).decode() == consumer]
    if not selected:
        if publications:
            raise Conflict("A required consumer publication is missing")
        return command, None
    if len(selected) != 1:
        raise Conflict("Ambiguous consumer publication")
    return command, selected[0]


def receipt(store, batch, consumer):
    _, row = retained(store, batch, consumer)
    if row is None:
        body = {"version":1, "batch_id":batch, "consumer":consumer, "unchanged":True}
    else:
        if not row["verified"]:
            raise ValueError("The consumer publication is not delivered yet")
        body = {"version":1, "batch_id":batch, "consumer":consumer, "payload_hash":row["payload_hash"]}
    return canonical(body).encode()


def deliver(store, consumer, worker, publisher, *, lease_seconds=300, batch_id=None):
    api = adapter(store)
    if batch_id is None:
        batch_id = api.next_publication(consumer)
        if batch_id is None:
            return False
    _, row = retained(store, batch_id, consumer)
    if row is None:
        # A no-work worker must also prove current authority at the destination.
        _refusals(lambda: api.retain_metadata("publication_observation", canonical([batch_id,consumer,worker]),
            {"batch_id":batch_id,"consumer":consumer,"unchanged":True},
            immutable=True, authority=authority(store)))
        return False
    claim = _refusals(lambda: api.claim_outbox(batch_id, consumer, worker,
        seconds=lease_seconds, authority=authority(store)))
    if claim is None:
        return False
    key, payload = consumer+"/"+batch_id, json.loads(claim["payload"])
    try:
        publisher.publish(key, payload, claim["payload_hash"])
        verified = publisher.verify(key, payload, claim["payload_hash"])
    except Exception as error:
        try:
            _refusals(lambda: api.release_outbox(batch_id, consumer, worker,
                claim["fence"], authority=authority(store)))
        except Exception as release_error:
            raise error from release_error
        raise
    _refusals(lambda: api.ack_outbox(batch_id, consumer, worker,
        claim["fence"], verified, authority=authority(store)))
    return True
