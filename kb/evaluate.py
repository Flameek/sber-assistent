"""Evaluate annotated, answerable held-out questions separately from conflict/refusal cases."""
import argparse,json,statistics,time
from .corpus import ROOT,chunks,seed
from .backend import Local,Elastic
from .service import Service

def evaluate(engine,split="holdout",k=3):
    service=Service(chunks(seed()),engine)
    cases=[q for q in json.loads((ROOT/"data/questions.json").read_text()) if q["split"]==split]
    rows=[];precision=[];recall=[];times=[]
    for q in cases:
        t=time.perf_counter(); r=service.ask(q["role"],q["question"]);times.append(1000*(time.perf_counter()-t))
        gold=set(q["relevant"]); found=r["ranked"][:k]
        if gold:
            hits=len(gold&set(found));precision.append(hits/k);recall.append(hits/len(gold))
        ok=r["kind"]==q["expected"] and (not gold or r["source"] in gold)
        rows.append({"id":q["id"],"expected":q["expected"],"got":r["kind"],"source":r["source"],"ranked":found,"ok":ok})
    return {"split":split,"queries":len(rows),"answerable":len(recall),"k":k,"precision_at_k":round(statistics.mean(precision),3),"recall_at_k":round(statistics.mean(recall),3),"correct":sum(x["ok"] for x in rows),"median_ms":round(statistics.median(times),2),"rows":rows}
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--backend",choices=("elastic","local"),default="local");p.add_argument("--split",choices=("dev","holdout"),default="holdout")
    args=p.parse_args(); print(json.dumps(evaluate(Elastic() if args.backend=="elastic" else Local(),args.split),indent=2,ensure_ascii=False))
