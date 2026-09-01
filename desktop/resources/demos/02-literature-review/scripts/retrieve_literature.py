# -*- coding: utf-8 -*-
"""
检索「肿瘤浸润 T 细胞耗竭与免疫检查点抑制剂疗效」相关文献 (2019-至今)
数据源: Europe PMC REST API + PubMed E-utilities
输出: analysis_outputs/candidates.json (排序后的候选) + analysis_outputs/search_log.json
"""
import json
import math
import os
import random
import re
import sys
import time

import requests

HEADERS = {"User-Agent": "BioDSH-literature-review/1.0 (literature review assistant)"}
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "analysis_outputs")
os.makedirs(OUT_DIR, exist_ok=True)

EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def get_json(url, params, tries=5, timeout=90):
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
            if r.status_code == 200:
                return r.json()
            last = RuntimeError("HTTP %s: %s" % (r.status_code, r.text[:200]))
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(2.0 * (i + 1) + random.random() * 1.5)
    raise RuntimeError("Request failed for %s: %s" % (url, last))


# ---------------------------------------------------------------------------
# 检索式设计（每个主题面一个检索式，用于相关性覆盖度打分）
# ---------------------------------------------------------------------------
EPMC_QUERIES = {
    "exhaustion_ici": '"T cell exhaustion" AND ("immune checkpoint inhibitor" OR "immune checkpoint blockade") AND (response OR resistance)',
    "exhaustion_pd1_tumor": '"T cell exhaustion" AND (PD-1 OR PD-L1 OR "programmed cell death") AND (tumor OR cancer OR carcinoma)',
    "scrnaseq_til": '("single-cell RNA" OR "single-cell transcriptom" OR scRNA-seq OR "single cell") AND ("tumor-infiltrating" OR TIL) AND (T cell) AND (exhaustion OR dysfunctional OR "dysfunction")',
    "anti_pd1_response": '(anti-PD-1 OR anti-PD-L1 OR pembrolizumab OR nivolumab OR atezolizumab) AND (response OR resistance OR "clinical benefit") AND ("T cell" OR CD8)',
    "progenitor_exhausted": '("progenitor exhausted" OR "stem-like" OR TCF1 OR "T cell factor 1" OR "precursor exhausted") AND (CD8 OR "T cell") AND (PD-1 OR "checkpoint" OR immunotherapy)',
    "exhaustion_biomarker": '"T cell exhaustion" AND (biomarker OR predictor OR signature OR "gene signature") AND (immunotherapy OR "checkpoint")',
}
YEAR_FILTER = "PUB_YEAR:[2019 TO 2026]"
EPMC_BASE = "({q}) AND ({yf}) AND (SRC:MED)"

# PubMed 备用检索式（同一主题面）
PUBMED_QUERIES = {
    "exhaustion_ici": '("T cell exhaustion"[Title/Abstract]) AND ("immune checkpoint inhibitor"[Title/Abstract] OR "immune checkpoint blockade"[Title/Abstract]) AND (response[Title/Abstract] OR resistance[Title/Abstract])',
    "exhaustion_pd1_tumor": '("T cell exhaustion"[Title/Abstract]) AND (PD-1[Title/Abstract] OR PD-L1[Title/Abstract]) AND (tumor[Title/Abstract] OR cancer[Title/Abstract] OR carcinoma[Title/Abstract])',
    "scrnaseq_til": '("single-cell RNA"[Title/Abstract] OR scRNA-seq[Title/Abstract]) AND ("tumor-infiltrating"[Title/Abstract]) AND ("T cell"[Title/Abstract]) AND (exhaustion[Title/Abstract] OR dysfunctional[Title/Abstract])',
    "anti_pd1_response": '(anti-PD-1[Title/Abstract] OR anti-PD-L1[Title/Abstract] OR pembrolizumab[Title/Abstract] OR nivolumab[Title/Abstract]) AND (response[Title/Abstract] OR resistance[Title/Abstract]) AND (CD8[Title/Abstract] OR "T cell"[Title/Abstract])',
    "progenitor_exhausted": '("progenitor exhausted"[Title/Abstract] OR "stem-like"[Title/Abstract] OR TCF1[Title/Abstract] OR "precursor exhausted"[Title/Abstract]) AND (CD8[Title/Abstract] OR "T cell"[Title/Abstract])',
    "exhaustion_biomarker": '("T cell exhaustion"[Title/Abstract]) AND (biomarker[Title/Abstract] OR predictor[Title/Abstract] OR signature[Title/Abstract])',
}
DATE_FILTER = 'AND ("2019/01/01"[dp] : "2026/12/31"[dp])'


def fetch_epmc(query, page_size=60, sort=None):
    params = {"query": query, "format": "json", "pageSize": page_size, "resultType": "core"}
    if sort:
        params["sort"] = sort
    data = get_json(EPMC, params)
    return data.get("resultList", {}).get("result", []), data.get("hitCount", 0)


def parse_pubtypes(rec):
    """兼容 pubTypeList 的两种结构（dict 或字符串数组）。"""
    raw = rec.get("pubTypeList") or {}
    if isinstance(raw, dict):
        pts = raw.get("pubType", []) or []
    elif isinstance(raw, list):
        pts = raw
    else:
        pts = []
    out = []
    for pt in pts:
        if isinstance(pt, dict):
            out.append(str(pt.get("type", "")))
        else:
            out.append(str(pt))
    return out


def parse_epmc(rec):
    """把 Europe PMC 记录转成统一字段。"""
    authors = rec.get("authorString", "") or ""
    first_author = authors.split(",")[0].strip() if authors else ""
    pubtypes = parse_pubtypes(rec)
    return {
        "pmid": rec.get("id") if rec.get("source") == "MED" else None,
        "doi": (rec.get("doi") or "").lower(),
        "title": rec.get("title", "") or "",
        "first_author": first_author,
        "year": rec.get("pubYear", ""),
        "journal": rec.get("journalTitle", "") or "",
        "citations": int(rec.get("citedByCount") or 0),
        "abstract": rec.get("abstractText", "") or "",
        "pubtype": pubtypes,
        "source": "europepmc",
    }


def fetch_pubmed(term, page_size=50):
    """PubMed esearch + esummary，作为第二个数据源/兜底。"""
    params = {
        "db": "pubmed", "term": term + " " + DATE_FILTER, "retmode": "json",
        "retmax": page_size, "sort": "relevance",
    }
    es = get_json(EUTILS + "/esearch.fcgi", params)
    ids = es.get("esearchresult", {}).get("idlist", [])
    if not ids:
        return [], es.get("esearchresult", {}).get("count", 0)
    out = []
    for i in range(0, len(ids), 100):
        chunk = ids[i:i + 100]
        sm = get_json(EUTILS + "/esummary.fcgi",
                      {"db": "pubmed", "id": ",".join(chunk), "retmode": "json"})
        res = sm.get("result", {})
        for pid in chunk:
            it = res.get(pid)
            if not it or "error" in it:
                continue
            doi = ""
            for aid in it.get("articleids", []):
                if aid.get("idtype") == "doi":
                    doi = (aid.get("value") or "").lower()
            authors = it.get("authors", []) or []
            first_author = authors[0]["name"] if authors else ""
            year = ""
            pd = it.get("pubdate", "") or ""
            m = re.search(r"(\d{4})", pd)
            if m:
                year = m.group(1)
            out.append({
                "pmid": pid,
                "doi": doi,
                "title": it.get("title", "") or "",
                "first_author": first_author,
                "year": year,
                "journal": it.get("fulljournalname", "") or it.get("source", "") or "",
                "citations": None,  # PubMed 不提供被引数，合并时由 Europe PMC 补
                "abstract": "",
                "pubtype": [],
                "source": "pubmed",
            })
        time.sleep(0.5)
    return out, es.get("esearchresult", {}).get("count", 0)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    records = {}   # key: pmid 或 doi
    log = {"europepmc": [], "pubmed": [], "started": time.strftime("%Y-%m-%d %H:%M:%S")}

    # ---- Europe PMC：每个检索式按相关度 + 按被引两种排序 ----
    for name, q in EPMC_QUERIES.items():
        full_q = EPMC_BASE.format(q=q, yf=YEAR_FILTER)
        for sort, tag in [(None, "relevance"), ("Cited desc", "cited")]:
            try:
                res, hits = fetch_epmc(full_q, sort=sort)
                log["europepmc"].append({"facet": name, "sort": tag, "query": full_q, "hits": hits,
                                         "returned": len(res)})
                for rec in res:
                    parsed = parse_epmc(rec)
                    key = parsed["pmid"] or parsed["doi"]
                    if not key:
                        continue
                    r = records.setdefault(key, parsed)
                    r.setdefault("facet_hits", set()).add(name)
            except Exception as e:  # noqa: BLE001
                log["europepmc"].append({"facet": name, "sort": tag, "error": str(e)})
                print("EPMC fetch failed", name, tag, e)
        time.sleep(0.4)

    # 额外：高被引地标文献池（防止遗漏被引极高但排序靠后的）
    try:
        res, hits = fetch_epmc(
            '"T cell exhaustion" AND (tumor OR cancer OR melanoma OR carcinoma) AND (immunotherapy OR "checkpoint" OR PD-1 OR PD-L1) AND (%s) AND (SRC:MED)' % YEAR_FILTER,
            page_size=80, sort="Cited desc")
        log["europepmc"].append({"facet": "landmark_cited", "sort": "cited", "hits": hits, "returned": len(res)})
        for rec in res:
            parsed = parse_epmc(rec)
            key = parsed["pmid"] or parsed["doi"]
            if not key:
                continue
            records.setdefault(key, parsed)
    except Exception as e:  # noqa: BLE001
        log["europepmc"].append({"facet": "landmark_cited", "error": str(e)})

    # ---- PubMed：备用源，补充 DOI / 摘要缺失 ----
    for name, term in PUBMED_QUERIES.items():
        try:
            res, hits = fetch_pubmed(term)
            log["pubmed"].append({"facet": name, "hits": hits, "returned": len(res)})
            for rec in res:
                key = rec["pmid"]
                if key in records:
                    # 用 PubMed 的元数据补 Europe PMC 的缺口（如 DOI）
                    old = records[key]
                    if not old.get("doi") and rec.get("doi"):
                        old["doi"] = rec["doi"]
                    if not old.get("journal") and rec.get("journal"):
                        old["journal"] = rec["journal"]
                    continue
                records[key] = rec
        except Exception as e:  # noqa: BLE001
            log["pubmed"].append({"facet": name, "error": str(e)})
            print("PubMed fetch failed", name, e)
        time.sleep(0.5)

    # -----------------------------------------------------------------------
    # 去重 + 相关性门槛 + 打分排序
    # -----------------------------------------------------------------------
    TOPIC_TITLE_KW = ["exhaust", "checkpoint", "pd-1", "pd1", "pd-l1", "immunotherap",
                      "tumor-infiltrat", "tcf1", "stem-like", "progenitor", "dysfunction"]
    OFFTOPIC_TITLE = ["covid", "coronavirus", "sars-cov", "severe acute respiratory",
                      "multimodal single-cell data", "digital cytometry", "cell type abundance"]
    scored = []
    for key, rec in records.items():
        title = (rec.get("title") or "").lower()
        abstract = (rec.get("abstract") or "").lower()
        tl = title + " " + abstract[:1500]

        # 相关性门槛：必须命中至少一个主题面，或标题含主题关键词
        facet_hits = len(rec.get("facet_hits", set()) or set())
        title_topic = any(kw in title for kw in TOPIC_TITLE_KW)
        if facet_hits == 0 and not title_topic:
            continue
        if any(ot in title for ot in OFFTOPIC_TITLE):
            continue

        s = 0.0
        # 1) 主题面覆盖度（相关性，最重要）
        s += 2.6 * min(facet_hits / 2.0, 1.0)
        if facet_hits >= 2:
            s += 0.8
        # 2) 标题关键词命中
        for kw in TOPIC_TITLE_KW:
            if kw in title:
                s += 0.3
        # 3) 被引量（对数）
        c = rec.get("citations") or 0
        s += 0.9 * math.log10(c + 1)
        # 4) 人类研究偏好（软信号）
        human = any(w in tl for w in ["patient", "human", "biopsy", "clinical", "survival", "tumor tissue"])
        mouse = bool(re.search(r"\bmouse\b|\bmice\b|murine|c57bl", tl))
        if human and not mouse:
            s += 0.7
        elif mouse and not human:
            s -= 0.5
        # 5) 综述轻微降权（开题报告以原始研究为主）
        if any("review" in (pt or "").lower() for pt in rec.get("pubtype", [])):
            s *= 0.75
        # 6) 年份新近度微奖励
        try:
            y = int(rec.get("year") or 0)
        except (TypeError, ValueError):
            y = 0
        s += max(0, y - 2018) * 0.02
        # 7) 必须有标题
        if not rec.get("title"):
            continue
        rec["score"] = round(s, 3)
        rec["facet_hits"] = facet_hits
        scored.append(rec)

    scored.sort(key=lambda r: r["score"], reverse=True)
    top = scored[:32]

    # 输出精简版供人工筛选（摘要截断）
    slim = []
    for r in top:
        slim.append({
            "rank": len(slim) + 1,
            "pmid": r.get("pmid"),
            "doi": r.get("doi") or "",
            "title": r.get("title"),
            "first_author": r.get("first_author"),
            "year": r.get("year"),
            "journal": r.get("journal"),
            "citations": r.get("citations"),
            "score": r.get("score"),
            "facet_hits": r.get("facet_hits"),
            "pubtype": r.get("pubtype"),
            "abstract_snippet": (r.get("abstract") or "")[:700],
        })

    with open(os.path.join(OUT_DIR, "candidates.json"), "w", encoding="utf-8") as f:
        json.dump({"total_unique": len(scored), "candidates": slim},
                  f, ensure_ascii=False, indent=1)
    log["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    log["total_unique"] = len(scored)
    with open(os.path.join(OUT_DIR, "search_log.json"), "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=1)

    print("total unique:", len(scored))
    print("top 10:")
    for r in slim[:10]:
        print("  %2d. [%s] (%s, %s cites) %s — %s" % (
            r["rank"], r["year"], r["journal"], r["citations"], r["first_author"], r["title"][:90]))


if __name__ == "__main__":
    main()
