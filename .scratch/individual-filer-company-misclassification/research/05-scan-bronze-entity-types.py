"""Summarise every CIK's latest bronze submissions file. Zero SEC requests: reads S3 bronze only."""
import boto3, json, sys, threading
from concurrent.futures import ThreadPoolExecutor
from botocore.config import Config
B="edgartools-prod-bronze-690839588395"; P="warehouse/bronze/submissions/sec/"
s3=boto3.client("s3",region_name="us-east-1",config=Config(max_pool_connections=64,retries={"max_attempts":8}))
out=open(sys.argv[1],"w"); lock=threading.Lock()
def ciks():
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=B,Prefix=P,Delimiter="/"):
        for c in page.get("CommonPrefixes",[]): yield c["Prefix"]
def one(prefix):
    try:
        keys=[]
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=B,Prefix=prefix+"main/"):
            keys+= [o["Key"] for o in page.get("Contents",[])]
        if not keys: rec={"prefix":prefix,"missing_main":True}
        else:
            key=max(keys)  # main/YYYY/MM/DD/ sorts by date
            d=json.loads(s3.get_object(Bucket=B,Key=key)["Body"].read())
            forms=(d.get("filings",{}).get("recent",{}) or {}).get("form",[]) or []
            counts={}
            for f in forms: counts[f]=counts.get(f,0)+1
            rec={"cik":d.get("cik"),"key":key,"entityType":d.get("entityType"),"name":d.get("name"),
                 "sic":d.get("sic"),"tickers":d.get("tickers"),"exchanges":d.get("exchanges"),
                 "stateOfIncorporation":d.get("stateOfIncorporation"),"category":d.get("category"),
                 "forms":counts,"latest":(d.get("filings",{}).get("recent",{}).get("filingDate") or [None])[0]}
    except Exception as e:
        rec={"prefix":prefix,"error":repr(e)[:200]}
    with lock: out.write(json.dumps(rec)+"\n"); out.flush()
with ThreadPoolExecutor(48) as ex: list(ex.map(one, ciks()))
print("done")
