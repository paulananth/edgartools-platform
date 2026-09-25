"""Ticket 08, step 1: how often does SEC's own record state its LEI?

Reads each CIK's latest bronze submissions file from S3. Zero SEC requests.
Writes one JSON line per CIK with the fields a SEC-to-GLEIF matching rule
could compare: name, former names, LEI, addresses, state and country of
incorporation, tickers, filer category.

Usage: python 08-scan-sec-lei-and-address.py <out.jsonl>
"""

import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import boto3
from botocore.config import Config

BUCKET = "edgartools-prod-bronze-690839588395"
PREFIX = "warehouse/bronze/submissions/sec/"
s3 = boto3.client(
    "s3",
    region_name="us-east-1",
    config=Config(max_pool_connections=64, retries={"max_attempts": 8}),
)
out = open(sys.argv[1], "w")
lock = threading.Lock()


def ciks():
    pages = s3.get_paginator("list_objects_v2").paginate(
        Bucket=BUCKET, Prefix=PREFIX, Delimiter="/"
    )
    for page in pages:
        for c in page.get("CommonPrefixes", []):
            yield c["Prefix"]


def one(prefix):
    try:
        keys = []
        pages = s3.get_paginator("list_objects_v2").paginate(
            Bucket=BUCKET, Prefix=prefix + "main/"
        )
        for page in pages:
            keys += [o["Key"] for o in page.get("Contents", [])]
        if not keys:
            rec = {"prefix": prefix, "missing_main": True}
        else:
            key = max(keys)  # main/YYYY/MM/DD/ sorts by date
            d = json.loads(s3.get_object(Bucket=BUCKET, Key=key)["Body"].read())
            forms = (d.get("filings", {}).get("recent", {}) or {}).get("form", []) or []
            rec = {
                "cik": d.get("cik"),
                "key": key,
                "has_lei_key": "lei" in d,
                "lei": d.get("lei"),
                "entityType": d.get("entityType"),
                "name": d.get("name"),
                "formerNames": d.get("formerNames"),
                "sic": d.get("sic"),
                "category": d.get("category"),
                "tickers": d.get("tickers"),
                "exchanges": d.get("exchanges"),
                "stateOfIncorporation": d.get("stateOfIncorporation"),
                "stateOfIncorporationDescription": d.get(
                    "stateOfIncorporationDescription"
                ),
                "addresses": d.get("addresses"),
                "ein": bool(d.get("ein")),
                "forms": sorted(set(forms)),
            }
    except Exception as e:  # recorded, never fatal: one bad object is one row
        rec = {"prefix": prefix, "error": repr(e)[:200]}
    with lock:
        out.write(json.dumps(rec) + "\n")
        out.flush()


with ThreadPoolExecutor(48) as ex:
    list(ex.map(one, ciks()))
print("done")
