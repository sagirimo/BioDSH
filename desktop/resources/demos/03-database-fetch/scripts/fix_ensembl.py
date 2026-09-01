# -*- coding: utf-8 -*-
"""Ensembl ID 兜底: 对 xlsx 中缺失 Ensembl ID 的行, 依次尝试
Ensembl REST -> UniProt xref -> NCBI dbtag, 全部失败则保持原样"""
import os
import time
import xml.etree.ElementTree as ET

import pandas as pd
import requests

HDR = {"User-Agent": "BioDSH-demo/03 (ensembl fallback)", "Accept": "application/json"}
WORKDIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
path = os.path.join(WORKDIR, "gene_annotations.xlsx")

df = pd.read_excel(path)


def find_ensembl(sym):
    """返回 (source, ensembl_id) 或 None"""
    # 1) Ensembl REST
    for i in range(3):
        try:
            r = requests.get(f"https://rest.ensembl.org/lookup/symbol/homo_sapiens/{sym}",
                             headers=HDR, timeout=30)
            if r.status_code == 200:
                return "ensembl-rest", r.json().get("id")
            if r.status_code == 404:
                break
        except Exception:
            time.sleep(2)
    # 2) UniProt xref
    try:
        r = requests.get("https://rest.uniprot.org/uniprotkb/search",
                         params={"query": f"gene_exact:{sym} AND organism_id:9606 AND reviewed:true",
                                 "fields": "xref_ensembl", "format": "tsv", "size": 5},
                         headers=HDR, timeout=30)
        for line in r.text.splitlines()[1:]:
            for token in line.split("\t"):
                for eid in token.split(";"):
                    eid = eid.strip()
                    if eid.startswith("ENSG"):
                        return "uniprot-xref", eid
    except Exception:
        pass
    # 3) NCBI gene XML Dbtag
    try:
        term = f"{sym}[Gene Name] AND Homo sapiens[Organism]"
        s = requests.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                         params={"db": "gene", "term": term, "retmode": "json"}, headers=HDR, timeout=30)
        gid = s.json()["esearchresult"]["idlist"][0]
        time.sleep(0.4)
        e = requests.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
                         params={"db": "gene", "id": gid, "retmode": "xml"}, headers=HDR, timeout=30)
        root = ET.fromstring(e.text)
        for db in root.findall(".//Dbtag"):
            if db.findtext("Dbtag_db") == "Ensembl":
                oid = db.findtext("Dbtag_tag/Object-id/Object-id_id")
                if oid and oid.startswith("ENSG"):
                    return "ncbi-dbtag", oid
    except Exception:
        pass
    return None


changed = 0
for idx, row in df.iterrows():
    sym = str(row["基因符号"]).strip()
    cur = row.get("Ensembl ID")
    if isinstance(cur, str) and cur.strip():
        continue
    hit = find_ensembl(sym)
    if hit:
        df.at[idx, "Ensembl ID"] = hit[1]
        print("OK", sym, hit)
        changed += 1
    else:
        print("FAIL", sym)

if changed:
    df.to_excel(path, index=False)
print("updated rows:", changed)
