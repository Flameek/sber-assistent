"""Local TF-IDF and extractive answers; no model downloads, API or Internet."""
from collections import Counter
from functools import lru_cache
import math
import re

import pymorphy3


MORPH = pymorphy3.MorphAnalyzer()

# Служебные слова (в начальной форме): не несут смысла для поиска.
STOP = set("как где куда какой по за на и или у я кто для мой надо нужно нужный бы уже пожалуйста".split())
# Слова, которые есть почти во всех инструкциях этой базы и не помогают отличить один раздел от другого.
DOMAIN_STOP = {"реестр", "инцидент", "стажер", "учебный"}
# Небольшой словарь предметных синонимов. Формы слов теперь приводит к начальной форме pymorphy3,
# поэтому здесь только разные слова с одним смыслом.
SYNONYMS = {
    "состояние": "статус",
    "право": "доступ",
    "регистрировать": "регистрация", "зарегистрировать": "регистрация", "создать": "регистрация", "создание": "регистрация",
    "эскалировать": "эскалация",
    "классифицировать": "категория", "классификация": "категория",
    "проверка": "проверить", "посмотреть": "проверить", "узнать": "проверить",
}


@lru_cache(maxsize=None)
def lemma(word):
    """Начальная форма слова: «заявку» -> «заявка», «открыли» -> «открыть»."""
    return MORPH.parse(word)[0].normal_form.replace("ё", "е")


def terms(text):
    out = []
    for word in re.findall(r"[a-zа-яё0-9-]+", text.casefold()):
        base = lemma(word)
        base = SYNONYMS.get(base, base)
        if len(base) < 3 or base in STOP or base in DOMAIN_STOP:
            continue
        out.append(base)
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
