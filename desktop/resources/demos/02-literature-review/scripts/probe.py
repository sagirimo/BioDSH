# -*- coding: utf-8 -*-
import json
import sys

import requests

h = {"User-Agent": "BioDSH-literature-review/1.0"}
E = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def q(query, page=1, ps=5):
    r = requests.get(E, params={"query": query, "format": "json", "resultType": "core",
                                "page": page, "pageSize": ps}, headers=h, timeout=60)
    return r.json()


# 1) 看一条已知 DOI 的完整记录结构
d = q('DOI:"10.1038/s41577-020-0306-5"')
for rec in d.get("resultList", {}).get("result", [])[:1]:
    print("KEYS:", sorted(rec.keys()))
    print("journalInfo:", json.dumps(rec.get("journalInfo"), ensure_ascii=False)[:400])
    print("journalTitle:", repr(rec.get("journalTitle")))
    print("authorString:", rec.get("authorString", "")[:60])

print("----- Wu TD paper -----")
d2 = q('TITLE:"Peripheral T cell expansion predicts tumour infiltration and clinical response"')
for rec in d2.get("resultList", {}).get("result", [])[:5]:
    print(rec.get("doi"), "|", rec.get("pubYear"), "|", rec.get("authorString", "")[:50],
          "|", rec.get("title", "")[:90], "|", rec.get("journalTitle"), "| cites:", rec.get("citedByCount"))
