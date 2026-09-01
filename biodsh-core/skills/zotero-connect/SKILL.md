---
name: zotero-connect
description: Read and extend the user's own Zotero 7 library through the local desktop app — search papers, list collections and tags, pull PDF full text for summarising, add references by DOI/PMID, and export BibTeX/RIS/CSL-JSON. Never deletes or edits existing items.
---

# Zotero connect (local library)

Use this skill when the user talks about **their own** reference library: "帮我在 Zotero 里找…", "把这篇加到 Zotero", "总结我库里关于 X 的 PDF", "导出这几篇的 BibTeX", or when a literature-review task should end with references saved into Zotero. It talks only to the Zotero desktop app on this computer (`http://127.0.0.1:23119`) — no cloud account, no API key.

Prerequisite (tell the user if `ping` fails): Zotero 7 must be **open**, and in Zotero → Settings(设置) → Advanced(高级) the option **"Allow other applications on this computer to communicate with Zotero"** (允许本机其他应用与 Zotero 通信) must be checked. Adding items uses the Zotero Connector endpoint, which is always on while Zotero runs.

## Commands

All commands print JSON to stdout; on failure they print `{"error": ...}` and exit 1.

```bash
python "<skill dir>/zotero.py" ping                                   # is Zotero running + local API enabled?
python "<skill dir>/zotero.py" search --q "PD-1 melanoma" [--limit 50] [--collection KEY] [--everything]
python "<skill dir>/zotero.py" collections                            # key, name, parent, item count
python "<skill dir>/zotero.py" tags
python "<skill dir>/zotero.py" item --key ABCD1234                    # full record + attachments with local PDF paths
python "<skill dir>/zotero.py" pdf-text --key ABCD1234 [--max-chars 20000]
python "<skill dir>/zotero.py" add --doi 10.1038/s41586-020-2649-2    # Crossref → Zotero
python "<skill dir>/zotero.py" add --pmid 32939066                    # PubMed (E-utilities) → Zotero
python "<skill dir>/zotero.py" add --json items.json [--yes]          # list of Zotero items or {"doi":..}/{"pmid":..}
python "<skill dir>/zotero.py" resolve --doi 10.xxxx/yyy              # metadata preview only, Zotero not needed
python "<skill dir>/zotero.py" export --keys K1,K2 --format bibtex|csljson|ris --out exports/refs.bib
```

`search` returns compact rows: `key, title, authors, year, journal, DOI, tags, has_pdf, date_added`. Default matching is title/creator/year; add `--everything` to also match abstracts, notes and indexed full text. `--collection KEY` restricts to one collection (get keys from `collections`).

`pdf-text` needs `pymupdf`; if the error says so, run `uv pip install pymupdf` and retry. It reads the PDF straight from the Zotero storage folder (`~/Zotero/storage/<key>/…`; override with `ZOTERO_DATA_DIR` if the user moved it).

## The loop

1. `ping` — if it errors, stop and tell the user exactly how to enable the local API (the error text already contains the settings path in English and Chinese).
2. `search` (optionally `collections` first, then `--collection`) — report the hits with their Zotero keys.
3. `item` / `pdf-text` for the papers the user picks — summarise from the extracted text, quoting the item key.
4. `add` / `export` as the task requires — report every new item key and the collection it landed in.

## Rules

- **Never delete or modify existing items.** This script has no delete/update commands; do not try to work around that with other tools.
- `add` skips DOIs already in the library (reported as `already_in_library` with the existing key). Use `--force` only if the user explicitly wants a duplicate.
- **Confirm with the user before adding more than 10 items.** The script refuses `>10` without `--yes`; ask, show the candidate list, then rerun with `--yes`.
- New items are saved into the collection currently selected in the Zotero window (or My Library). Tell the user this, and report the new item keys (`add` returns them; if it says `sent_to_zotero`, run `search --q "<title>"` a few seconds later to fetch the key).
- Always report Zotero item keys when you cite library items, so the user can find them (Zotero: search the key, or `item --key`).
- For literature-review tasks combine with web search: find candidate papers online → present title/journal/year/DOI to the user → after confirmation, `add --doi …` (or `--pmid …`) for each → finish with `export` if the user needs a bibliography.
- Metadata sources are Crossref (`api.crossref.org`) and NCBI E-utilities; both are public and need no key (`NCBI_API_KEY` / `CROSSREF_MAILTO` are optional env vars for polite rate limits). Nothing in this skill uploads the user's library anywhere.
