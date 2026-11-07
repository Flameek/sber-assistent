"""For this small prototype, Elasticsearch filters one handbook area before TF-IDF ranking."""
import json
import os
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from .corpus import ROLES, digest

class Local:
    def candidates(self, rows, role, area):
        return [r for r in rows if role in ROLES and role in r['roles'] and r['area']==area]

class Elastic:
    def __init__(self, url=None):
        self.url=(url or os.getenv("ES_URL","http://127.0.0.1:9200")).rstrip("/")
        self.ready=set()

    def call(self, path, method="GET", body=None, ndjson=False):
        data=(body if ndjson else json.dumps(body,ensure_ascii=False)).encode() if body is not None else None
        req=Request(self.url+path,data=data,method=method,headers={"Content-Type":"application/x-ndjson" if ndjson else "application/json"})
        with urlopen(req, timeout=12) as response:
            return json.load(response)

    def ensure(self, rows):
        if not rows or len(rows)>1000:
            raise ValueError("База демонстрации должна содержать от 1 до 1000 фрагментов")
        idx="kb-demo-"+digest(rows)
        if idx in self.ready: return idx
        try:
            self.call("/"+idx+"/_count")
        except HTTPError as e:
            if e.code!=404: raise
            try:
                self.call("/"+idx,"PUT",{"settings":{"number_of_shards":1,"number_of_replicas":0},
                    "mappings":{"properties":{k:{"type":"keyword"} for k in ("roles","area","ref","rule")}}})
            except HTTPError as conflict:
                if conflict.code!=400 or b"resource_already_exists_exception" not in conflict.read(): raise
        if self.call("/"+idx+"/_count")["count"]!=len(rows):
            payload=""
            for row in rows:
                payload+=json.dumps({"index":{"_id": row["ref"]}})+"\n"+json.dumps(row,ensure_ascii=False)+"\n"
            stored=self.call("/"+idx+"/_bulk?refresh=true","POST",payload,True)
            if stored["errors"]: raise RuntimeError("Ошибка индексации учебной базы")
        self.ready.add(idx)
        return idx

    def candidates(self, rows, role, area):
        if role not in ROLES:return []
        idx=self.ensure(rows)
        q={"size":1000,"query":{"bool":{"filter":[{"term":{"roles":role}},{"term":{"area":area}}]}}}
        hits=self.call("/"+idx+"/_search","POST",q)["hits"]["hits"]
        return sorted([h["_source"] for h in hits],key=lambda x:x["ref"])

def backend():
    value=os.getenv("KB_BACKEND","elastic")
    if value not in ("local","elastic"): raise ValueError("Неизвестный KB_BACKEND")
    return Elastic() if value=="elastic" else Local()
