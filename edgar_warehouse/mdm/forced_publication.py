"""Explicit snapshot publication through the normal prepared storage boundary."""
import json
from uuid import UUID

from . import catalog
from .prepared import _refusals, authority
from .prepared_publication import adapter
from .record_reads import RecordReader
from .store import Conflict, canonical, digest, storage_adapter


def page(store, consumer, run_id, number, after, page_size):
    """Retain one immutable page; retries use its original bytes and cursor."""
    run_id = str(UUID(run_id))
    if (not isinstance(consumer,str) or not consumer or consumer == "journal"
            or type(number) is not int or number < 1
            or type(page_size) is not int or not 1 <= page_size <= 10000
            or not isinstance(after,dict) or set(after) != {"object_type","object_id"}
            or any(not isinstance(value,str) for value in after.values())):
        raise ValueError("Forced publication requires a non-Journal consumer, run and bounded page")
    catalog.assert_current()
    api, module = adapter(store), storage_adapter()
    batch = "forced:"+consumer+":"+run_id+":"+str(number)
    first_batch = "forced:"+consumer+":"+run_id+":1"
    scope = canonical(["forced",consumer,run_id])
    request = {"consumer":consumer,"run_id":run_id,"page":number,"after":after,"page_size":page_size}
    with store.engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        existing = api.read_batches([batch],connection=conn)
        if existing:
            effects = json.loads(bytes(existing[0]["assessment"]))["effects"]
            if effects["request"] != request:
                raise Conflict("Forced page differs from its original publication request")
            result = {"batch_id":batch,"generation":existing[0]["generation"],
                "records":len(effects["projections"]),"next":effects["next"],"duplicate":True}
            replay = True
        else:
            replay = False
            generation = api.generation(connection=conn)
            if not generation:
                raise Conflict("Forced publication requires a committed policy")
            origin = api.read_batches([first_batch],connection=conn)
            if number > 1:
                previous = api.read_batches(["forced:"+consumer+":"+run_id+":"+str(number-1)],connection=conn)
                if not origin or not previous:
                    raise Conflict("Forced publication requires its preceding page")
                prior = json.loads(bytes(previous[0]["assessment"]))["effects"]
                if prior["next"] != after or prior["request"]["page_size"] != page_size:
                    raise Conflict("Forced publication cursor differs from its preceding page")
            elif after != {"object_type":"","object_id":""}:
                raise Conflict("Forced publication must start at its first page")
            if not origin:
                latest = api.generation_batch(generation,connection=conn)
                if latest is None:
                    raise Conflict("Forced publication has no current committed batch")
                origin = [latest]
            original = json.loads(bytes(origin[0]["intent"]))
            pins = json.loads(bytes.fromhex(original["pins"]))
            policy = module.registered_policy(conn,pins["policy"])
            if policy is None or consumer not in policy["required_consumers"]:
                raise Conflict("Forced publication names a consumer the frozen policy does not require")
            if pins["catalog"] != digest(catalog.CATALOG):
                raise Conflict("Forced publication catalog differs from its original authority")
            cursor = None if not after["object_type"] else (after["object_type"],after["object_id"])
            records = api.snapshot_page(after=cursor,limit=page_size+1,connection=conn)
            more, selected = len(records) > page_size, records[:page_size]
            following = ({"object_type":selected[-1][0][0],"object_id":selected[-1][0][1]} if more else None)
            objects = [{"object_type":kind,"object_id":key,"body":RecordReader._body(row),"change":"snapshot"}
                       for (kind,key),row in selected]
            effects = {"forced":True,"consumer":consumer,"policy_digest":pins["policy"],
                "request":request,"next":following,"projections":objects}
            payload = {"contract_version":3,"forced":True,"generation":generation+1,
                       "policy_digest":pins["policy"],"objects":objects}
            frozen = module.PreparedBatch(batch=batch,run=run_id,scope=scope,pins=pins,
                assessment={"effects":effects},expected_generation=generation,
                expected_checkpoint=number-1,checkpoint=number,objects=(),indexes=(),
                consumers=(consumer,),payload=payload,
                payloads={consumer:module.ProducerPayload(canonical(payload).encode()[:-1]+b',"run_id":',b'}')},
                evidence=(module.Effect("publication_request",batch,request),),
                required_pins=json.loads(bytes.fromhex(original["required_pins"])),
                publish_inputs=True,governed=True,workflow=True)
    lease = _refusals(lambda: api.claim(scope,"forced-publication",authority=authority(store)))
    if replay:
        _refusals(lambda: api.replay(batch,lease,observer=run_id,authority=authority(store)))
        return result
    committed = _refusals(lambda: api.apply(frozen,lease,observer=run_id,
        proposal_body={"command":request,"outcome":"ready","effects_sha256":digest(effects)},
        authority=authority(store)))
    return {"batch_id":batch,"generation":committed["generation"],"records":len(objects),
            "next":following,"duplicate":committed["duplicate"]}
