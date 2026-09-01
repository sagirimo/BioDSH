#!/usr/bin/env python3
"""zotero-connect: talk to the LOCAL Zotero 7 desktop app (no cloud account needed).

Two local endpoints are used, both served by the running Zotero desktop app:
  * Local API   http://127.0.0.1:23119/api/users/0/...   (read: items, collections, tags, export)
      -> must be enabled in Zotero > Settings(设置) > Advanced(高级) >
         "Allow other applications on this computer to communicate with Zotero"
  * Connector   http://127.0.0.1:23119/connector/...      (write: saveItems, ping)

Every subcommand prints one JSON document to stdout. On failure it prints
{"error": "..."} and exits with status 1. Nothing is ever deleted or modified.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from urllib.parse import quote

try:
    import requests
except ImportError:  # pragma: no cover
    print(json.dumps({"error": "The 'requests' package is missing. Install it with: uv pip install requests"}))
    sys.exit(1)

BASE = os.environ.get("ZOTERO_LOCAL_URL", "http://127.0.0.1:23119").rstrip("/")
API = f"{BASE}/api/users/0"
CONNECTOR = f"{BASE}/connector"
TIMEOUT = float(os.environ.get("ZOTERO_TIMEOUT", "15"))
USER_AGENT = "BioDSH-zotero-connect/1.0 (BioDSH desktop; https://github.com/biodsh)"

# Always emit UTF-8 JSON, even on Windows consoles that default to GBK.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# Localhost calls must never go through a system/corporate proxy.
LOCAL = requests.Session()
LOCAL.trust_env = False

NOT_RUNNING_MSG = (
    "Cannot reach Zotero at " + BASE + " . "
    "Zotero must be OPEN on this computer (Zotero 7 desktop app, 请先打开 Zotero 7 桌面版), "
    "and the local API must be enabled: Zotero → Settings(设置/首选项) → Advanced(高级) → "
    "check 'Allow other applications on this computer to communicate with Zotero' "
    "(允许本机其他应用与 Zotero 通信). Then run `ping` again."
)
API_DISABLED_MSG = (
    "Zotero is running but its local API is disabled (HTTP {code}). "
    "Enable it in Zotero → Settings(设置/首选项) → Advanced(高级) → "
    "'Allow other applications on this computer to communicate with Zotero' "
    "(允许本机其他应用与 Zotero 通信), then retry."
)


# ----------------------------------------------------------------------------- helpers
def out(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def fail(msg: str, **extra: Any) -> None:
    payload = {"error": msg}
    payload.update(extra)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    sys.exit(1)


def _request(method: str, url: str, *, params: dict | None = None, json_body: Any = None,
             headers: dict | None = None, expect_json: bool = True) -> Any:
    hdrs = {"User-Agent": USER_AGENT}
    if headers:
        hdrs.update(headers)
    try:
        r = LOCAL.request(method, url, params=params, json=json_body, headers=hdrs, timeout=TIMEOUT)
    except requests.exceptions.ConnectionError:
        fail(NOT_RUNNING_MSG, zotero_running=False)
    except requests.exceptions.Timeout:
        fail(f"Zotero did not answer within {TIMEOUT:.0f}s at {url}. Is Zotero busy or frozen?")
    if r.status_code in (403, 404) and url.startswith(API):
        fail(API_DISABLED_MSG.format(code=r.status_code), zotero_running=True, local_api=False,
             detail=r.text[:300])
    if r.status_code >= 400:
        fail(f"Zotero returned HTTP {r.status_code} for {url}", detail=r.text[:500])
    if not expect_json:
        return r
    try:
        return r.json()
    except ValueError:
        fail(f"Zotero returned non-JSON for {url}", detail=r.text[:300])


def api_get(path: str, params: dict | None = None, expect_json: bool = True) -> Any:
    return _request("GET", f"{API}{path}", params=params, expect_json=expect_json)


def api_get_all(path: str, params: dict | None = None, limit: int | None = None) -> list:
    """Follow Zotero-style pagination (start/limit, max 100 per page)."""
    params = dict(params or {})
    got: list = []
    start = 0
    while True:
        page_size = 100 if limit is None else max(1, min(100, limit - len(got)))
        params.update({"start": start, "limit": page_size})
        chunk = api_get(path, params)
        if not isinstance(chunk, list):
            break
        got.extend(chunk)
        if len(chunk) < page_size or (limit is not None and len(got) >= limit):
            break
        start += len(chunk)
    return got[:limit] if limit else got


def connector_ping() -> bool:
    try:
        r = LOCAL.get(f"{CONNECTOR}/ping", timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
        return r.status_code == 200
    except requests.exceptions.RequestException:
        return False


def year_of(date: str | None) -> str | None:
    m = re.search(r"(1[6-9]|20)\d{2}", date or "")
    return m.group(0) if m else None


def creators_short(creators: list[dict]) -> list[str]:
    names = []
    for c in creators or []:
        if c.get("creatorType") not in (None, "author", "editor"):
            continue
        if "lastName" in c or "firstName" in c:
            first = (c.get("firstName") or "").strip()
            initials = " ".join(p[0] + "." for p in first.split() if p)
            names.append((c.get("lastName") or "").strip() + (" " + initials if initials else ""))
        elif c.get("name"):
            names.append(c["name"])
    return names


def compact(item: dict) -> dict:
    d = item.get("data", {})
    links = item.get("links", {})
    att = links.get("attachment") or {}
    return {
        "key": item.get("key") or d.get("key"),
        "itemType": d.get("itemType"),
        "title": d.get("title"),
        "authors": creators_short(d.get("creators", [])),
        "year": year_of(d.get("date")),
        "journal": d.get("publicationTitle") or d.get("bookTitle") or d.get("proceedingsTitle"),
        "DOI": d.get("DOI") or None,
        "tags": [t.get("tag") for t in d.get("tags", []) if t.get("tag")],
        "has_pdf": att.get("attachmentType") == "application/pdf" or None,
        "date_added": d.get("dateAdded"),
    }


# ----------------------------------------------------------------------------- data dir
def _prefs_data_dir() -> str | None:
    """Look for extensions.zotero.dataDir in the Zotero profile prefs.js."""
    home = Path.home()
    candidates = [
        os.path.join(os.environ.get("APPDATA", ""), "Zotero", "Zotero", "Profiles", "*", "prefs.js"),
        str(home / "Library" / "Application Support" / "Zotero" / "Profiles" / "*" / "prefs.js"),
        str(home / ".zotero" / "zotero" / "*" / "prefs.js"),
    ]
    for pat in candidates:
        if not pat.strip("*/"):
            continue
        for f in glob.glob(pat):
            try:
                txt = Path(f).read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            m = re.search(r'user_pref\("extensions\.zotero\.dataDir",\s*"([^"]+)"\)', txt)
            if m:
                p = m.group(1).encode().decode("unicode_escape")
                if os.path.isdir(p):
                    return p
    return None


def zotero_data_dir() -> str | None:
    env = os.environ.get("ZOTERO_DATA_DIR")
    if env and os.path.isdir(env):
        return env
    default = Path.home() / "Zotero"
    if default.is_dir():
        return str(default)
    userprofile = os.environ.get("USERPROFILE")
    if userprofile and os.path.isdir(os.path.join(userprofile, "Zotero")):
        return os.path.join(userprofile, "Zotero")
    return _prefs_data_dir()


def attachment_path(att: dict, data_dir: str | None) -> str | None:
    d = att.get("data", {})
    href = (att.get("links", {}).get("enclosure") or {}).get("href")
    if href and href.startswith("file://"):
        from urllib.parse import unquote, urlparse
        p = unquote(urlparse(href).path)
        if re.match(r"^/[A-Za-z]:", p):
            p = p[1:]
        if os.path.exists(p):
            return p
    if d.get("linkMode") == "linked_file" and d.get("path"):
        p = d["path"]
        if p.startswith("attachments:") and data_dir:
            p = os.path.join(data_dir, p.split(":", 1)[1])
        return p
    if d.get("linkMode") in ("imported_file", "imported_url") and data_dir and d.get("filename"):
        return os.path.join(data_dir, "storage", att.get("key", d.get("key", "")), d["filename"])
    return None


# ----------------------------------------------------------------------------- commands
def cmd_ping(args: argparse.Namespace) -> None:
    running = connector_ping()
    if not running:
        fail(NOT_RUNNING_MSG, zotero_running=False, local_api=False)
    probe = api_get("/items", {"limit": 1, "format": "json"})
    out({
        "ok": True,
        "zotero_running": True,
        "local_api": True,
        "endpoint": BASE,
        "data_dir": zotero_data_dir(),
        "sample_item": compact(probe[0]) if isinstance(probe, list) and probe else None,
    })


def cmd_search(args: argparse.Namespace) -> None:
    params = {"q": args.q, "include": "data", "sort": args.sort, "direction": "desc",
              "itemType": "-attachment || -note"}
    if args.everything:
        params["qmode"] = "everything"
    path = f"/collections/{args.collection}/items" if args.collection else "/items"
    items = api_get_all(path, params, limit=args.limit)
    rows = [compact(i) for i in items if i.get("data", {}).get("itemType") not in ("attachment", "note")]
    out({"query": args.q, "collection": args.collection, "count": len(rows), "items": rows})


def cmd_collections(args: argparse.Namespace) -> None:
    cols = api_get_all("/collections")
    rows = [{
        "key": c.get("key"),
        "name": c.get("data", {}).get("name"),
        "parent": c.get("data", {}).get("parentCollection") or None,
        "num_items": (c.get("meta") or {}).get("numItems"),
    } for c in cols]
    rows.sort(key=lambda r: ((r["parent"] or ""), (r["name"] or "").lower()))
    out({"count": len(rows), "collections": rows})


def _children(key: str) -> list[dict]:
    return api_get_all(f"/items/{key}/children")


def cmd_item(args: argparse.Namespace) -> None:
    item = api_get(f"/items/{args.key}")
    data_dir = zotero_data_dir()
    kids = _children(args.key)
    attachments, notes = [], []
    for k in kids:
        d = k.get("data", {})
        if d.get("itemType") == "attachment":
            p = attachment_path(k, data_dir)
            attachments.append({
                "key": k.get("key"), "title": d.get("title"), "contentType": d.get("contentType"),
                "linkMode": d.get("linkMode"), "filename": d.get("filename"),
                "path": p, "file_exists": bool(p and os.path.exists(p)),
            })
        elif d.get("itemType") == "note":
            notes.append({"key": k.get("key"), "note": re.sub(r"<[^>]+>", " ", d.get("note", "")).strip()[:2000]})
    out({
        "key": item.get("key"),
        "summary": compact(item),
        "data": item.get("data"),
        "collections": item.get("data", {}).get("collections", []),
        "attachments": attachments,
        "notes": notes,
        "zotero_data_dir": data_dir,
    })


def _find_pdf(key: str) -> tuple[dict | None, str | None]:
    data_dir = zotero_data_dir()
    item = api_get(f"/items/{key}")
    cands = [item] if item.get("data", {}).get("itemType") == "attachment" else _children(key)
    for k in cands:
        d = k.get("data", {})
        if d.get("itemType") != "attachment":
            continue
        if d.get("contentType") != "application/pdf" and not (d.get("filename") or "").lower().endswith(".pdf"):
            continue
        p = attachment_path(k, data_dir)
        if p and os.path.exists(p):
            return k, p
    return None, None


def cmd_pdf_text(args: argparse.Namespace) -> None:
    try:
        import pymupdf as fitz
    except ImportError:
        try:
            import fitz  # older pymupdf
        except ImportError:
            fail("pymupdf is not installed. Install it with: uv pip install pymupdf  (then rerun pdf-text)")
    att, path = _find_pdf(args.key)
    if not path:
        fail(f"No PDF file found on disk for item {args.key}. Check `item --key {args.key}` for attachment paths; "
             "the PDF may not be downloaded (Zotero: right-click → 'Find Full Text') or the data dir was not resolved "
             "(set ZOTERO_DATA_DIR).")
    try:
        doc = fitz.open(path)
    except Exception as e:  # noqa: BLE001
        fail(f"Could not open PDF {path}: {e}")
    parts, total = [], 0
    pages_read = 0
    for page in doc:
        t = page.get_text()
        parts.append(t)
        total += len(t)
        pages_read += 1
        if total >= args.max_chars:
            break
    text = "\n".join(parts)
    truncated = len(text) > args.max_chars
    out({
        "key": args.key, "attachment_key": att.get("key"), "path": path,
        "pages_total": doc.page_count, "pages_read": pages_read,
        "chars": min(len(text), args.max_chars), "truncated": truncated,
        "text": text[:args.max_chars],
    })


# ----------------------------------------------------------------------------- metadata resolvers
def _strip_jats(s: str | None) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


CROSSREF_TYPES = {
    "journal-article": "journalArticle", "book-chapter": "bookSection", "book": "book",
    "monograph": "book", "proceedings-article": "conferencePaper", "posted-content": "preprint",
    "dissertation": "thesis", "report": "report", "dataset": "dataset",
}


def resolve_doi(doi: str) -> dict:
    doi = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", doi.strip(), flags=re.I)
    ua = USER_AGENT
    mailto = os.environ.get("CROSSREF_MAILTO")
    if mailto:
        ua += f" (mailto:{mailto})"
    try:
        r = requests.get(f"https://api.crossref.org/works/{quote(doi, safe='')}", headers={"User-Agent": ua}, timeout=30)
    except requests.exceptions.RequestException as e:
        fail(f"Crossref request failed for DOI {doi}: {e}")
    if r.status_code == 404:
        fail(f"DOI {doi} was not found on Crossref (check the DOI).")
    if r.status_code >= 400:
        fail(f"Crossref returned HTTP {r.status_code} for DOI {doi}", detail=r.text[:300])
    m = r.json().get("message", {})
    creators = []
    for a in m.get("author", []) or []:
        if a.get("family") or a.get("given"):
            creators.append({"firstName": a.get("given", ""), "lastName": a.get("family", ""), "creatorType": "author"})
        elif a.get("name"):
            creators.append({"name": a["name"], "creatorType": "author"})
    parts = ((m.get("issued") or m.get("published-print") or m.get("published-online") or {}).get("date-parts") or [[]])[0]
    date = "-".join(f"{p:02d}" if i else str(p) for i, p in enumerate(parts)) if parts else ""
    item = {
        "itemType": CROSSREF_TYPES.get(m.get("type"), "journalArticle"),
        "title": _strip_jats((m.get("title") or [""])[0]),
        "creators": creators,
        "date": date,
        "publicationTitle": (m.get("container-title") or [""])[0],
        "journalAbbreviation": (m.get("short-container-title") or [""])[0],
        "volume": m.get("volume", ""),
        "issue": m.get("issue", ""),
        "pages": m.get("page", ""),
        "DOI": m.get("DOI", doi),
        "url": m.get("URL", f"https://doi.org/{doi}"),
        "ISSN": ", ".join(m.get("ISSN", []) or []),
        "abstractNote": _strip_jats(m.get("abstract")),
        "language": m.get("language", ""),
        "libraryCatalog": "Crossref",
    }
    if item["itemType"] == "bookSection":
        item["bookTitle"] = item.pop("publicationTitle")
    return {k: v for k, v in item.items() if v not in ("", None)}


def resolve_pmid(pmid: str) -> dict:
    pmid = pmid.strip().replace("PMID:", "").strip()
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    params = {"db": "pubmed", "id": pmid, "retmode": "json"}
    if os.environ.get("NCBI_API_KEY"):
        params["api_key"] = os.environ["NCBI_API_KEY"]
    try:
        r = requests.get(base + "esummary.fcgi", params=params, headers={"User-Agent": USER_AGENT}, timeout=30)
        r.raise_for_status()
        summ = r.json().get("result", {}).get(pmid)
        if not summ or "error" in summ:
            fail(f"PMID {pmid} was not found in PubMed.")
        xr = requests.get(base + "efetch.fcgi", params={**params, "retmode": "xml"},
                          headers={"User-Agent": USER_AGENT}, timeout=30)
        xr.raise_for_status()
    except requests.exceptions.RequestException as e:
        fail(f"PubMed (NCBI E-utilities) request failed for PMID {pmid}: {e}")
    doi = next((a["value"] for a in summ.get("articleids", []) if a.get("idtype") == "doi"), "")
    pmc = next((a["value"] for a in summ.get("articleids", []) if a.get("idtype") == "pmc"), "")
    abstract, creators = "", []
    try:
        root = ET.fromstring(xr.content)
        art = root.find(".//Article")
        if art is not None:
            abstract = " ".join(
                (("[" + t.get("Label") + "] ") if t.get("Label") else "") + "".join(t.itertext()).strip()
                for t in art.findall(".//Abstract/AbstractText")).strip()
            for au in art.findall(".//AuthorList/Author"):
                last, fore, coll = au.findtext("LastName"), au.findtext("ForeName"), au.findtext("CollectiveName")
                if last:
                    creators.append({"firstName": fore or "", "lastName": last, "creatorType": "author"})
                elif coll:
                    creators.append({"name": coll, "creatorType": "author"})
            if not doi:
                doi = art.findtext(".//ELocationID[@EIdType='doi']") or ""
    except ET.ParseError:
        pass
    if not creators:
        for a in summ.get("authors", []):
            nm = a.get("name", "")
            last, _, first = nm.partition(" ")
            creators.append({"firstName": first, "lastName": last, "creatorType": "author"})
    item = {
        "itemType": "journalArticle",
        "title": _strip_jats(summ.get("title")),
        "creators": creators,
        "date": summ.get("pubdate") or summ.get("epubdate") or "",
        "publicationTitle": summ.get("fulljournalname") or summ.get("source", ""),
        "journalAbbreviation": summ.get("source", ""),
        "volume": summ.get("volume", ""),
        "issue": summ.get("issue", ""),
        "pages": summ.get("pages", ""),
        "DOI": doi,
        "ISSN": summ.get("issn") or summ.get("essn", ""),
        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        "abstractNote": abstract,
        "extra": f"PMID: {pmid}" + (f"\nPMCID: {pmc}" if pmc else ""),
        "libraryCatalog": "PubMed",
    }
    return {k: v for k, v in item.items() if v not in ("", None)}


# ----------------------------------------------------------------------------- add / export / tags
def _already_in_library(doi: str | None, title: str | None) -> dict | None:
    q = doi or title
    if not q:
        return None
    items = api_get_all("/items", {"q": q, "qmode": "everything", "include": "data",
                                   "itemType": "-attachment || -note"}, limit=25)
    for it in items:
        d = it.get("data", {})
        if doi and (d.get("DOI") or "").lower() == doi.lower():
            return compact(it)
        if not doi and title and (d.get("title") or "").strip().lower() == title.strip().lower():
            return compact(it)
    return None


def _save_items(items: list[dict], uri: str) -> None:
    for i, it in enumerate(items):
        it.setdefault("id", str(i + 1))
        it.setdefault("attachments", [])
        it.setdefault("creators", [])
    if not connector_ping():
        fail(NOT_RUNNING_MSG, zotero_running=False)
    _request("POST", f"{CONNECTOR}/saveItems", json_body={"items": items, "uri": uri},
             headers={"Content-Type": "application/json", "X-Zotero-Connector-API-Version": "3",
                      "X-Zotero-Version": "7.0"}, expect_json=False)


def _count_requested(args: argparse.Namespace) -> int:
    n = len([d for d in (args.doi or "").split(",") if d.strip()]) + len([p for p in (args.pmid or "").split(",") if p.strip()])
    if args.json:
        try:
            raw = json.loads(Path(args.json).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            fail(f"Cannot read {args.json}: {e}")
        if isinstance(raw, dict):
            raw = raw.get("items", [raw])
        n += len([e for e in raw if isinstance(e, dict)])
    return n


def cmd_add(args: argparse.Namespace) -> None:
    todo: list[dict] = []
    sources: list[str] = []
    n_req = _count_requested(args)
    if n_req == 0:
        fail("Nothing to add: pass --doi, --pmid and/or --json.")
    if n_req > 10 and not args.yes:
        fail(f"Refusing to add {n_req} items at once without confirmation. Ask the user first, then rerun with --yes.")
    if args.doi:
        for d in args.doi.split(","):
            todo.append(resolve_doi(d))
            sources.append(f"doi:{d.strip()}")
    if args.pmid:
        for p in args.pmid.split(","):
            todo.append(resolve_pmid(p))
            sources.append(f"pmid:{p.strip()}")
    if args.json:
        try:
            raw = json.loads(Path(args.json).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            fail(f"Cannot read {args.json}: {e}")
        if isinstance(raw, dict):
            raw = raw.get("items", [raw])
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            doi = entry.get("DOI") or entry.get("doi")
            pmid = entry.get("PMID") or entry.get("pmid")
            if entry.get("title"):
                entry.setdefault("itemType", "journalArticle")
                todo.append(entry)
                sources.append(f"json:{entry['title'][:40]}")
            elif doi:
                todo.append(resolve_doi(str(doi)))
                sources.append(f"doi:{doi}")
            elif pmid:
                todo.append(resolve_pmid(str(pmid)))
                sources.append(f"pmid:{pmid}")
    if not todo:
        fail("Nothing to add: pass --doi, --pmid and/or --json.")

    results = []
    to_save = []
    for src, it in zip(sources, todo):
        dup = None if args.force else _already_in_library(it.get("DOI"), it.get("title"))
        if dup:
            results.append({"source": src, "status": "already_in_library", "key": dup["key"], "title": dup["title"]})
        else:
            to_save.append((src, it))
    if to_save and not args.dry_run:
        _save_items([it for _, it in to_save], uri=(to_save[0][1].get("url") or "https://biodsh.local/zotero-connect"))
        time.sleep(1.5)
        for src, it in to_save:
            found = None
            for _ in range(4):
                found = _already_in_library(it.get("DOI"), it.get("title"))
                if found:
                    break
                time.sleep(1.0)
            results.append({"source": src, "status": "added" if found else "sent_to_zotero",
                            "key": found["key"] if found else None, "title": it.get("title"),
                            "DOI": it.get("DOI")})
    elif to_save:
        results.extend({"source": s, "status": "dry_run", "title": it.get("title"), "item": it} for s, it in to_save)
    out({
        "added": sum(r["status"] in ("added", "sent_to_zotero") for r in results),
        "skipped_duplicates": sum(r["status"] == "already_in_library" for r in results),
        "note": "Items are saved into the collection currently selected in the Zotero window "
                "(or 'My Library' if none). Zotero will try to fetch the PDF automatically.",
        "results": results,
    })


def cmd_export(args: argparse.Namespace) -> None:
    keys = [k.strip() for k in args.keys.split(",") if k.strip()]
    if not keys:
        fail("--keys must list at least one Zotero item key (comma separated).")
    fmt = args.format
    chunks: list[str] = []
    for i in range(0, len(keys), 50):
        r = api_get("/items", {"itemKey": ",".join(keys[i:i + 50]), "format": fmt, "limit": 100}, expect_json=False)
        chunks.append(r.text)
    if fmt == "csljson":
        merged = []
        for c in chunks:
            merged.extend(json.loads(c))
        text = json.dumps(merged, ensure_ascii=False, indent=2)
    else:
        text = "\n\n".join(c.strip() for c in chunks) + "\n"
    outp = Path(args.out) if args.out else Path("exports") / f"references.{ {'bibtex': 'bib', 'csljson': 'json', 'ris': 'ris'}[fmt] }"
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(text, encoding="utf-8")
    out({"out": str(outp.resolve()), "format": fmt, "requested": len(keys), "bytes": len(text.encode("utf-8"))})


def cmd_tags(args: argparse.Namespace) -> None:
    tags = api_get_all("/tags")
    rows = [{"tag": t.get("tag"), "num_items": (t.get("meta") or {}).get("numItems")} for t in tags]
    rows.sort(key=lambda r: (-(r["num_items"] or 0), (r["tag"] or "").lower()))
    out({"count": len(rows), "tags": rows})


def cmd_resolve(args: argparse.Namespace) -> None:
    """Resolve metadata only (no Zotero needed) — handy for checking a DOI/PMID before adding."""
    if args.doi:
        out({"source": "crossref", "item": resolve_doi(args.doi)})
    elif args.pmid:
        out({"source": "pubmed", "item": resolve_pmid(args.pmid)})
    else:
        fail("Pass --doi or --pmid.")


# ----------------------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)

    sp.add_parser("ping", help="check that Zotero is running and its local API is enabled").set_defaults(fn=cmd_ping)

    s = sp.add_parser("search", help="search the library (title/creator/year by default)")
    s.add_argument("--q", required=True)
    s.add_argument("--limit", type=int, default=50)
    s.add_argument("--collection", help="collection key to search within")
    s.add_argument("--everything", action="store_true", help="also match abstracts, notes, full text")
    s.add_argument("--sort", default="dateAdded", choices=["dateAdded", "dateModified", "title", "date", "creator"])
    s.set_defaults(fn=cmd_search)

    sp.add_parser("collections", help="list collections").set_defaults(fn=cmd_collections)

    s = sp.add_parser("item", help="full record + attachments (with local file paths)")
    s.add_argument("--key", required=True)
    s.set_defaults(fn=cmd_item)

    s = sp.add_parser("pdf-text", help="extract text from the item's PDF attachment")
    s.add_argument("--key", required=True)
    s.add_argument("--max-chars", type=int, default=20000)
    s.set_defaults(fn=cmd_pdf_text)

    s = sp.add_parser("add", help="add references by DOI / PMID / JSON file (never deletes anything)")
    s.add_argument("--doi", help="one DOI or a comma-separated list")
    s.add_argument("--pmid", help="one PMID or a comma-separated list")
    s.add_argument("--json", help="JSON file: list of Zotero items, or of {\"doi\":..}/{\"pmid\":..} entries")
    s.add_argument("--yes", action="store_true", help="confirm adding more than 10 items")
    s.add_argument("--force", action="store_true", help="add even if the DOI already exists in the library")
    s.add_argument("--dry-run", action="store_true", help="resolve metadata but do not save")
    s.set_defaults(fn=cmd_add)

    s = sp.add_parser("resolve", help="resolve DOI/PMID metadata without touching Zotero")
    s.add_argument("--doi")
    s.add_argument("--pmid")
    s.set_defaults(fn=cmd_resolve)

    s = sp.add_parser("export", help="export citations for given item keys")
    s.add_argument("--keys", required=True, help="comma-separated Zotero item keys")
    s.add_argument("--format", default="bibtex", choices=["bibtex", "csljson", "ris"])
    s.add_argument("--out", help="output file (default exports/references.<ext>)")
    s.set_defaults(fn=cmd_export)

    sp.add_parser("tags", help="list tags with item counts").set_defaults(fn=cmd_tags)

    args = p.parse_args(argv)
    try:
        args.fn(args)
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        fail(f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
