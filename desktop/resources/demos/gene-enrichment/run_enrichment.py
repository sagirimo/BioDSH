# -*- coding: utf-8 -*-
"""
Immune-gene list functional enrichment (GO Biological Process + KEGG pathway).

ORA = one-sided hypergeometric test per term (equivalent to a one-sided
Fisher exact test on the 2x2 table), BH multiple-testing correction.
Method follows clusterProfiler enrichGO / enrichKEGG semantics
(Yu et al. 2012; Wu et al. 2021).

Gene-set sources (Enrichr snapshots, downloaded once and cached locally):
  - GO Biological Process 2023 : curated GO:BP -> human gene symbols (GOA-based)
  - KEGG 2021 Human           : KEGG pathway -> human gene symbols
Note: KEGG_2021_Human is the newest human KEGG library Enrichr distributes.

Background: the input is a hand-curated signature list with no assay
(universe of measured genes), so per Enrichr/DAVID convention the background
is all annotated genes in each library. This is stated explicitly in the report.

Original input (genes.txt) is never modified; all outputs go to ./outputs/.
"""
import math
import os
import ssl
import urllib.request

import numpy as np
import pandas as pd
from scipy.stats import hypergeom

# ---------------- settings ----------------
WORKSPACE = os.path.dirname(os.path.abspath(__file__))
GENES_FILE = os.path.join(WORKSPACE, "genes.txt")
OUT_DIR = os.path.join(WORKSPACE, "outputs")
LIB_DIR = os.path.join(OUT_DIR, "gene_set_libraries")
os.makedirs(LIB_DIR, exist_ok=True)

LIBS = {
    "GO_BP": {
        "url": "https://maayanlab.cloud/Enrichr/geneSetLibrary?mode=text&libraryName=GO_Biological_Process_2023",
        "file": os.path.join(LIB_DIR, "GO_Biological_Process_2023.gmt"),
        "label": "GO 生物过程 (GO Biological Process, 2023 快照)",
    },
    "KEGG": {
        "url": "https://maayanlab.cloud/Enrichr/geneSetLibrary?mode=text&libraryName=KEGG_2021_Human",
        "file": os.path.join(LIB_DIR, "KEGG_2021_Human.gmt"),
        "label": "KEGG 通路 (KEGG_2021_Human 快照)",
    },
}

MIN_GS = 10      # min gene-set size tested
MAX_GS = 1000    # max gene-set size tested (drop ultra-broad GO terms)
ALPHA = 0.05     # significance on adjusted p


def download(url, path):
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return False
    ctx = ssl._create_unverified_context()  # local proxy MITM certificate
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, context=ctx, timeout=120) as r, open(path, "wb") as f:
        f.write(r.read())
    return True


def parse_gmt(path):
    """GMT: term<TAB>description(usually empty)<TAB>gene1<TAB>gene2 ..."""
    sets = {}
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            name = parts[0].strip()
            genes = [g for g in parts[2:] if g.strip()]
            if name and genes:
                sets[name] = sorted(set(genes))
    return sets


def bh_adjust(pvals):
    p = np.asarray(pvals, dtype=float)
    n = p.size
    order = np.argsort(p)
    ranked = p[order]
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]  # step-down
    q = np.full(n, np.nan)
    q[order] = ranked * n / np.arange(1, n + 1)
    return np.minimum(q, 1.0)


def ora(foreground, term_sets, min_gs=MIN_GS, max_gs=MAX_GS):
    """ORA over retained term sets; returns a DataFrame."""
    # restrict to terms within size window
    kept = {t: gs for t, gs in term_sets.items() if min_gs <= len(gs) <= max_gs}
    universe = sorted({g for gs in kept.values() for g in gs})   # annotated background
    fg = sorted(set(foreground) & set(universe))                 # annotated foreground
    N = len(universe)
    n = len(fg)
    fg_set = set(fg)

    rows = []
    for term, gs in kept.items():
        gs_set = set(gs) & set(universe)
        m = len(gs_set)
        k = len(fg_set & gs_set)
        if k == 0:
            continue
        # P(X >= k) upper tail of hypergeometric == one-sided Fisher exact test
        p = hypergeom.sf(k - 1, N, m, n)
        genes = sorted(fg_set & gs_set)
        rows.append({
            "term": term,
            "gene_set_size": m,          # genes of the term that are annotated (M)
            "background_size": N,        # annotated background (N)
            "overlap_count": k,          # foreground genes in term (k)
            "foreground_annotated": n,   # foreground genes annotated (n)
            "overlap_genes": ";".join(genes),
            "fold_enrichment": ((k / n) / (m / N)) if m else np.nan,
            "pvalue": float(p),
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.sort_values("pvalue").reset_index(drop=True)
    df["p_adjust"] = bh_adjust(df["pvalue"].values)
    df["neglog10p"] = -np.log10(df["pvalue"].clip(lower=1e-320))
    df["neglog10padj"] = -np.log10(df["p_adjust"].clip(lower=1e-320))
    df = df.sort_values(["p_adjust", "pvalue"]).reset_index(drop=True)
    return df


def clean_name(term):
    """'negative regulation of T cell activation (GO:0042110)' -> 'negative regulation of T cell activation'"""
    return term.split(" (GO:")[0] if term.endswith(")") else term


def fmt(v):
    if isinstance(v, float):
        if v < 1e-300:
            return "<1e-300"
        if v < 0.001:
            return f"{v:.2e}"
        return f"{v:.4f}"
    return str(v)


def main():
    # 1) foreground genes
    with open(GENES_FILE, "r", encoding="utf-8") as fh:
        foreground = [ln.strip() for ln in fh if ln.strip()]
    print(f"input genes: {len(foreground)}")

    results = {}
    for key, cfg in LIBS.items():
        dl = download(cfg["url"], cfg["file"])
        sets = parse_gmt(cfg["file"])
        print(f"[{key}] downloaded={dl} terms(parsed)={len(sets)} file={cfg['file']}")
        df = ora(foreground, sets)
        results[key] = df
        sig = df[df["p_adjust"] < ALPHA] if not df.empty else df
        print(f"  [{key}] tested={len(df)} significant(p_adjust<0.05)={len(sig)}")

    # 2) full tables
    full_paths = {}
    for key, df in results.items():
        path = os.path.join(OUT_DIR, f"{key}_full_results.tsv")
        df.to_csv(path, sep="\t", index=False, encoding="utf-8")
        full_paths[key] = path
        print("wrote", path)

    # 3) top tables: significant terms per DB (fall back to raw-p ranking if no FDR hits)
    top = {}
    for key in results:
        df = results[key]
        if df.empty:
            top[key] = df
            continue
        sig = df[df["p_adjust"] < ALPHA]
        src = sig if len(sig) >= 1 else df.head(10)   # no FDR hits -> show raw-p top as indicative
        top[key] = src.head(10).reset_index(drop=True)

    for key, df in top.items():
        if not df.empty:
            df.to_csv(os.path.join(OUT_DIR, f"{key}_top_results.tsv"),
                      sep="\t", index=False, encoding="utf-8")
            df.to_csv(os.path.join(OUT_DIR, f"{key}_top_results.csv"),
                      index=False, encoding="utf-8-sig")

    # 4) figure
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    panel_rows = {k: len(v) for k, v in top.items()}
    n_go = max(panel_rows.get("GO_BP", 0), 1)
    n_kegg = max(panel_rows.get("KEGG", 0), 1)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 0.42 * (n_go + n_kegg) + 1.6))
    fig.subplots_adjust(hspace=0.55)

    pal = {"GO_BP": "#2c7fb8", "KEGG": "#e6550d"}
    xmax = 1.0
    for key, ax in (("GO_BP", ax1), ("KEGG", ax2)):
        df = top[key]
        if df.empty:
            ax.text(0.5, 0.5, "no term passed filters", ha="center", va="center")
            ax.set_title({"GO_BP": "GO Biological Process", "KEGG": "KEGG pathway (human)"}[key])
            continue
        # order by -log10 p (descending significance as requested)
        d = df.sort_values("neglog10p").reset_index(drop=True)
        labels = [clean_name(t) for t in d["term"]]
        vals = d["neglog10p"].values
        sig = (d["p_adjust"] < ALPHA).values
        cols = [pal[key] if s else "#bdbdbd" for s in sig]
        y = np.arange(len(d))
        ax.barh(y, vals, color=cols, edgecolor="none")
        for yi, v, s, r in zip(y, vals, sig, d.itertuples()):
            mark = "" if s else "  (FDR≥0.05)"
            ax.text(v + xmax * 0.015, yi, f"{v:.2f}{mark}", va="center", fontsize=8)
        ax.set_yticks(y)
        ax.set_yticklabels(labels, fontsize=8.5)
        ax.set_xlim(0, xmax * 1.35)
        ax.set_xlabel("-log10(p-value)  (bar 越长 = 越显著; 灰色条为 FDR 校正后不显著)")
        ax.set_title({"GO_BP": "GO Biological Process enrichment", "KEGG": "KEGG pathway enrichment (human)"}[key],
                     fontsize=11)
        ax.grid(axis="x", linestyle=":", alpha=0.5)
        ax.set_axisbelow(True)
        xmax = max(xmax, float(vals.max()) if len(vals) else 1.0)

    for ax in (ax1, ax2):
        ax.set_xlim(0, xmax * 1.35)

    fig_path = os.path.join(OUT_DIR, "enrichment_barplot.png")
    fig.savefig(fig_path, dpi=200, bbox_inches="tight")
    print("wrote", fig_path)

    # 5) merged top table + report stub numbers
    parts = []
    for key, df in top.items():
        if df.empty:
            continue
        d = df.copy()
        d.insert(0, "database", key)
        d["term"] = d["term"].map(clean_name)
        parts.append(d)
    merged = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    if not merged.empty:
        merged.to_csv(os.path.join(OUT_DIR, "top_enrichment_results.tsv"),
                      sep="\t", index=False, encoding="utf-8")
        merged.to_csv(os.path.join(OUT_DIR, "top_enrichment_results.csv"),
                      index=False, encoding="utf-8-sig")

    # 6) short machine-readable summary for the caller
    summary = {"gene_list": foreground}
    for key, df in results.items():
        summary[key] = {
            "tested_terms": int(len(df)),
            "significant_fdr005": int((df["p_adjust"] < ALPHA).sum()) if not df.empty else 0,
            "background_annotated_genes": int(df["background_size"].iloc[0]) if not df.empty else 0,
            "annotated_foreground": int(df["foreground_annotated"].iloc[0]) if not df.empty else 0,
        }
        if not df.empty:
            t = df.iloc[0]
            summary[key]["top_hit"] = {"term": clean_name(t["term"]), "pvalue": t["pvalue"],
                                       "p_adjust": t["p_adjust"], "overlap": f"{t['overlap_count']}/{t['foreground_annotated']}",
                                       "fold": round(float(t["fold_enrichment"]), 1)}
    import json
    with open(os.path.join(OUT_DIR, "_summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1)
    print("DONE")


if __name__ == "__main__":
    main()
