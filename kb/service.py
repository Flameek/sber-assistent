"""Local TF-IDF and extractive answers; no model downloads, API or Internet."""
from collections import Counter
import math
import re
from .corpus import ROLES

STOP=set('как где куда какой какая какие какому по за на и или у я кто мне для мои моя мою надо нужно нужен мне за бы уже реестр инцидент стажер учебный учебного пожалуйста'.split())
# Normalize a few common terms of the synthetic handbook, independently of a user's role.
FORMS=[
 (r"инцидент.*|реестр.*|учебн.*|стаж[её]р.*",None),
 (r"статус.*|состоян.*","статус"),(r"регистрир.*|зарегистр.*|созда.*|регистрац.*","регистрация"),
 (r"прав[ао]?|доступ.*","доступ"),(r"эскалац.*|эскалир.*","эскалация"),
 (r"классифи.*|категор.*","категория"),(r"заявк.*|заявок","заявка"),
 (r"карточк.*","карточка"),(r"влиян.*","влияние"),(r"критическ.*","критический"),
 (r"чтени.*","чтение"),(r"провер.*|посмотр.*|узна.*","проверить")]
def terms(text):
    out=[]
    for term in re.findall(r"[a-zа-я0-9-]+",text.casefold().replace("ё","е")):
        if term in STOP or len(term)<3: continue
        for pat,value in FORMS:
            if re.fullmatch(pat,term):
                term=value
                break
        if term:out.append(term)
    return out

def rank(rows,question):
    if not rows:return []
    documents=[Counter(terms(x["title"]+" "+x["title"]+" "+x["text"])) for x in rows]
    q=Counter(terms(question))
    if not q:return []
    df=Counter(t for d in documents for t in d)
    def weight(t):return 1+math.log((1+len(rows))/(1+df[t]))
    def vector(d):return {t:(1+math.log(n))*weight(t) for t,n in d.items()}
    def mag(v):return math.sqrt(sum(x*x for x in v.values())) or 1
    vq=vector(q);out=[]
    for r,d in zip(rows,documents):
        vd=vector(d); common=set(q)&set(d)
        score=sum(vq[t]*vd[t] for t in common)/(mag(vq)*mag(vd))
        if score>0:out.append((score,r))
    return sorted(out,key=lambda pair:(-pair[0],pair[1]['ref']))

class Service:
    def __init__(self, rows, engine):
        self.rows=rows;self.engine=engine
    def visible(self,role):
        return self.engine.candidates(self.rows,role,"реестр")
    def source(self,role,ref):
        return next((r for r in self.visible(role) if r["ref"]==ref),None)
    def ask(self,role,q):
        rows=self.visible(role); ranked=rank(rows,q)
        refs=[r["ref"] for _,r in ranked]
        missing={"kind":"missing","text":"В доступных инструкциях нет подтверждённого ответа. Обратитесь в службу сопровождения учебного реестра.","source":None,"ranked":refs}
        if not ranked or ranked[0][0]<0.13:return missing
        best=ranked[0][1]; match=set(terms(q))&set(terms(best["title"]+" "+best["text"]))
        if not match or (len(match)==1 and not match & set(terms(best["title"]))):return missing
        peers=[r for r in rows if r["rule"]==best["rule"]]
        highest=max(r["priority"] for r in peers)
        winners=[r for r in peers if r["priority"]==highest]
        # Multiple sections in one instruction are not conflicting instructions.
        by_doc={}
        for r in winners:by_doc.setdefault(r["id"],[]).append(r["text"])
        if len({tuple(txts) for txts in by_doc.values()})>1:
            return {"kind":"conflict","text":"Доступные инструкции одинакового приоритета расходятся. Передайте вопрос тимлиду ИБ.","source":None,"ranked":refs}
        ordered=rank(winners,q)
        if not ordered:return missing
        row=ordered[0][1]
        return {"kind":"answer","text":row["text"],"source":row["ref"],"ranked":refs}
