#!/usr/bin/env python3
"""data-format-bridge: move analysis tables into the tools clinicians use.

  inspect      csv/tsv/xlsx/sav/dta/rds/parquet/json/h5ad(obs,var)  -> shape, columns, dtypes, head, missing
  convert      --to sav | dta | xlsx | rds | r | csv | pzfx          (SPSS, Stata, Excel, R, GraphPad Prism)
  h5ad-tables  obs.csv + var.csv (+ selected gene expression columns joined to obs)

Prints one JSON document to stdout; on failure prints {"error": ...} and exits 1.
The input file is never modified or overwritten. Default output folder: ./exports/
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

try:
    import numpy as np
    import pandas as pd
except ImportError:  # pragma: no cover
    print(json.dumps({"error": "pandas is missing. Install it with: uv pip install pandas"}))
    sys.exit(1)


# ----------------------------------------------------------------------------- helpers
def out(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=_json_default))


def _json_default(o: Any) -> Any:
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (pd.Timestamp, _dt.datetime, _dt.date)):
        return o.isoformat()
    if isinstance(o, (np.ndarray, pd.Series, pd.Index)):
        return o.tolist()
    if o is pd.NaT:
        return None
    return str(o)


def fail(msg: str, **extra: Any) -> None:
    payload = {"error": msg}
    payload.update(extra)
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default))
    sys.exit(1)


def need(module: str, pip_name: str | None = None):
    try:
        return __import__(module)
    except ImportError:
        pkg = pip_name or module
        fail(f"Python package '{pkg}' is not installed. Install it with:  uv pip install {pkg}   "
             f"(or install the BioDSH env pack '统计与临床' which bundles pyreadstat/openpyxl), then rerun.")


def ext_of(path: str) -> str:
    return Path(path).suffix.lower().lstrip(".")


# ----------------------------------------------------------------------------- reading
def read_tables(path: str, sheet: str | None = None) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    """Return {table_name: DataFrame} and reader metadata (labels etc.)."""
    if not os.path.exists(path):
        fail(f"Input file not found: {path}")
    ext = ext_of(path)
    stem = Path(path).stem
    meta: dict[str, Any] = {"reader": None}
    if ext in ("csv", "txt", "tsv", "tab"):
        sep = "\t" if ext in ("tsv", "tab") else None
        try:
            df = pd.read_csv(path, sep=sep, engine="python" if sep is None else "c", encoding="utf-8-sig")
        except UnicodeDecodeError:
            df = pd.read_csv(path, sep=sep, engine="python" if sep is None else "c", encoding="gb18030")
            meta["encoding"] = "gb18030"
        meta["reader"] = "pandas.read_csv"
        return {stem: df}, meta
    if ext in ("xlsx", "xlsm", "xls"):
        need("openpyxl")
        sheets = pd.read_excel(path, sheet_name=sheet if sheet else None)
        meta["reader"] = "pandas.read_excel"
        if isinstance(sheets, pd.DataFrame):
            return {sheet or stem: sheets}, meta
        return {str(k): v for k, v in sheets.items()}, meta
    if ext == "sav" or ext == "zsav":
        prs = need("pyreadstat")
        df, m = prs.read_sav(path, apply_value_formats=False)
        meta.update(reader="pyreadstat.read_sav", column_labels=dict(zip(m.column_names, m.column_labels)),
                    value_labels={k: v for k, v in (m.variable_value_labels or {}).items()})
        return {stem: df}, meta
    if ext == "dta":
        prs = need("pyreadstat")
        df, m = prs.read_dta(path)
        meta.update(reader="pyreadstat.read_dta", column_labels=dict(zip(m.column_names, m.column_labels)))
        return {stem: df}, meta
    if ext in ("rds", "rdata", "rda"):
        pyreadr = need("pyreadr")
        res = pyreadr.read_r(path)
        meta["reader"] = "pyreadr.read_r"
        tables = {}
        for k, v in res.items():
            tables[k if k else stem] = v
        return tables, meta
    if ext in ("parquet", "pq"):
        df = pd.read_parquet(path)
        meta["reader"] = "pandas.read_parquet"
        return {stem: df}, meta
    if ext == "feather":
        df = pd.read_feather(path)
        meta["reader"] = "pandas.read_feather"
        return {stem: df}, meta
    if ext == "json":
        df = pd.read_json(path)
        meta["reader"] = "pandas.read_json"
        return {stem: df}, meta
    if ext == "h5ad":
        ad = need("anndata")
        a = ad.read_h5ad(path, backed="r")
        meta.update(reader="anndata.read_h5ad(backed='r')", n_obs=int(a.n_obs), n_vars=int(a.n_vars),
                    obsm=list(a.obsm.keys()), layers=list(a.layers.keys()), uns=list(a.uns.keys())[:50])
        tables = {"obs": a.obs.copy(), "var": a.var.copy()}
        for nm, t in tables.items():
            t.index.name = t.index.name or ("cell_id" if nm == "obs" else "gene")
            t.reset_index(inplace=True)
        if sheet and sheet in tables:
            return {sheet: tables[sheet]}, meta
        return tables, meta
    fail(f"Unsupported input format '.{ext}'. Supported: csv tsv xlsx sav dta rds parquet feather json h5ad")


def pick_table(tables: dict[str, pd.DataFrame], sheet: str | None) -> tuple[str, pd.DataFrame]:
    if sheet:
        if sheet not in tables:
            fail(f"Table/sheet '{sheet}' not found. Available: {list(tables)}")
        return sheet, tables[sheet]
    name = next(iter(tables))
    return name, tables[name]


# ----------------------------------------------------------------------------- column names
SPSS_RESERVED = {"ALL", "AND", "BY", "EQ", "GE", "GT", "LE", "LT", "NE", "NOT", "OR", "TO", "WITH"}
STATA_RESERVED = {"_all", "_b", "byte", "_coef", "_cons", "double", "float", "if", "in", "int", "long", "_n", "_N",
                  "_pi", "_pred", "_rc", "_skip", "strL", "using", "with", "_weight"} | {f"str{i}" for i in range(1, 2046)}


def sanitize_names(names: list[str], target: str) -> tuple[list[str], list[dict]]:
    """Make column names legal for SPSS (<=64 bytes) or Stata (<=32 chars): letters/digits/underscore, no leading digit."""
    max_len = 64 if target == "sav" else 32
    reserved = SPSS_RESERVED if target == "sav" else STATA_RESERVED
    seen: dict[str, int] = {}
    new_names, changes = [], []
    for raw in names:
        original = str(raw)
        s = re.sub(r"[^\w]", "_", original.strip(), flags=re.UNICODE)
        s = re.sub(r"_+", "_", s).strip("_")
        if not s:
            s = "var"
        if s[0].isdigit():
            s = "v_" + s
        if (s.upper() if target == "sav" else s) in reserved:
            s = s + "_"
        # length limit: bytes for SPSS, chars for Stata
        if target == "sav":
            while len(s.encode("utf-8")) > max_len:
                s = s[:-1]
        else:
            s = s[:max_len]
        base = s
        key = s.lower()
        n = seen.get(key, 0)
        while key in seen:
            n += 1
            suffix = f"_{n}"
            s = base[: max_len - len(suffix)] + suffix
            key = s.lower()
        seen[key] = n
        new_names.append(s)
        if s != original:
            changes.append({"from": original, "to": s})
    return new_names, changes


def coerce_for_stats(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """pyreadstat wants plain numeric / str / datetime columns."""
    df = df.copy()
    notes = []
    for c in df.columns:
        s = df[c]
        if isinstance(s.dtype, pd.CategoricalDtype):
            df[c] = s.astype(str).where(s.notna(), None)
            notes.append({"column": str(c), "change": "categorical -> string"})
        elif s.dtype == bool:
            df[c] = s.astype(int)
            notes.append({"column": str(c), "change": "bool -> 0/1"})
        elif s.dtype == object:
            non_null = s.dropna()
            if len(non_null) and all(isinstance(v, bool) for v in non_null):
                df[c] = s.map({True: 1, False: 0})
                notes.append({"column": str(c), "change": "bool -> 0/1"})
            else:
                df[c] = s.map(lambda v: None if (v is None or (isinstance(v, float) and np.isnan(v))) else str(v))
        elif str(s.dtype).startswith("datetime64[ns,"):
            df[c] = s.dt.tz_localize(None)
            notes.append({"column": str(c), "change": "timezone dropped"})
        elif pd.api.types.is_extension_array_dtype(s.dtype) and pd.api.types.is_numeric_dtype(s.dtype):
            df[c] = s.astype("float64")
    return df, notes


# ----------------------------------------------------------------------------- writers
def unique_out(path: Path) -> tuple[Path, bool]:
    if not path.exists():
        return path, False
    i = 1
    while True:
        cand = path.with_name(f"{path.stem}_{i}{path.suffix}")
        if not cand.exists():
            return cand, True
        i += 1


def write_xlsx(tables: dict[str, pd.DataFrame], path: Path) -> list[str]:
    need("openpyxl")
    from openpyxl.utils import get_column_letter
    used = []
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        for name, df in tables.items():
            sheet = re.sub(r"[\[\]\*\?/\\:]", "_", str(name))[:31] or "Sheet1"
            base, k = sheet, 1
            while sheet in used:
                k += 1
                sheet = f"{base[:28]}_{k}"
            used.append(sheet)
            df.to_excel(xw, sheet_name=sheet, index=False)
            ws = xw.sheets[sheet]
            ws.freeze_panes = "A2"
            for i, col in enumerate(df.columns, start=1):
                sample = df[col].head(200).map(lambda v: 0 if pd.isna(v) else len(str(v)))
                width = min(60, max(8, int(max([len(str(col))] + [int(x) for x in sample.tolist()])) + 2))
                ws.column_dimensions[get_column_letter(i)].width = width
    return used


def pivot_wide(df: pd.DataFrame, group_col: str | None, value_col: str | None) -> tuple[pd.DataFrame, dict]:
    """Prism 'Column' tables want one column per group (unequal lengths allowed)."""
    info: dict[str, Any] = {}
    if group_col:
        if group_col not in df.columns:
            fail(f"--group-col '{group_col}' not in columns {list(df.columns)}")
        if value_col is None:
            nums = [c for c in df.columns if c != group_col and pd.api.types.is_numeric_dtype(df[c])]
            if not nums:
                fail("No numeric column to use as --value-col")
            value_col = nums[0]
            info["value_col_auto"] = value_col
        if value_col not in df.columns:
            fail(f"--value-col '{value_col}' not in columns {list(df.columns)}")
        groups = {}
        for g, sub in df.groupby(group_col, sort=False, dropna=False):
            groups[str(g)] = pd.to_numeric(sub[value_col], errors="coerce").reset_index(drop=True)
        wide = pd.DataFrame({k: v for k, v in groups.items()})
        info.update(mode="long_to_wide", group_col=group_col, value_col=value_col, groups=list(wide.columns),
                    n_per_group={k: int(v.notna().sum()) for k, v in groups.items()})
        return wide, info
    nums = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    dropped = [c for c in df.columns if c not in nums]
    info.update(mode="numeric_columns_as_groups", groups=nums, dropped_non_numeric=dropped)
    return df[nums].copy(), info


def write_pzfx(wide: pd.DataFrame, path: Path, title: str) -> None:
    """Minimal GraphPad Prism XML (PrismXMLVersion 5.00) with one 'Column' data table.

    Layout follows what Prism 8/9 itself writes for a Column table: each group is a <YColumn> with a single
    <Subcolumn> of <d> values; empty cells are <d/>. Prism is tolerant of missing optional elements, but the
    wide CSV written next to this file is the guaranteed import route (File → Import)."""
    now = _dt.datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
    now = now[:-2] + ":" + now[-2:]
    cols = []
    for c in wide.columns:
        vals = []
        for v in wide[c].tolist():
            if v is None or (isinstance(v, float) and np.isnan(v)):
                vals.append("<d/>")
            else:
                vals.append(f"<d>{escape(repr(float(v)) if isinstance(v, float) else str(v))}</d>")
        cols.append(
            f'<YColumn Width="120" Decimals="3" Subcolumns="1">\n<Title>{escape(str(c))}</Title>\n'
            f'<Subcolumn>\n' + "\n".join(vals) + "\n</Subcolumn>\n</YColumn>"
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<GraphPadPrismFile PrismXMLVersion="5.00">\n'
        f'<Created>\n<OriginalVersion CreatedByProgram="GraphPad Prism" CreatedByVersion="8.4.3.686" Login="" DateTime="{now}"/>\n</Created>\n'
        '<InfoSequence>\n<Ref ID="Info0" Selected="1"/>\n</InfoSequence>\n'
        '<Info ID="Info0">\n<Title>Project info 1</Title>\n<Notes/>\n'
        '<Constant><Name>Experiment Date</Name><Value/></Constant>\n'
        '<Constant><Name>Experiment ID</Name><Value/></Constant>\n'
        '<Constant><Name>Notebook ID</Name><Value/></Constant>\n'
        '<Constant><Name>Project</Name><Value/></Constant>\n'
        '<Constant><Name>Experimenter</Name><Value/></Constant>\n'
        '<Constant><Name>Protocol</Name><Value/></Constant>\n'
        '</Info>\n'
        '<TableSequence>\n<Ref ID="Table0" Selected="1"/>\n</TableSequence>\n'
        '<Table ID="Table0" XFormat="none" YFormat="replicates" Replicates="1" TableType="OneWay" EVFormat="AsteriskAfterNumber">\n'
        f'<Title>{escape(title)}</Title>\n' + "\n".join(cols) + "\n</Table>\n"
        '</GraphPadPrismFile>\n'
    )
    path.write_text(xml, encoding="utf-8")


def r_snippet(rds_path: Path, df: pd.DataFrame, group_col: str | None, value_col: str | None) -> str:
    nums = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and df[c].nunique(dropna=True) > 2]
    cats = [c for c in df.columns if not pd.api.types.is_numeric_dtype(df[c]) and 2 <= df[c].nunique(dropna=True) <= 20]
    g = group_col or (cats[0] if cats else None)
    y = value_col or (nums[0] if nums else None)
    rds = str(rds_path.resolve()).replace("\\", "/")
    lines = [
        "# Auto-generated by BioDSH data-format-bridge — open in RStudio and run line by line.",
        "# install.packages(c('ggplot2','dplyr'))  # once, if missing",
        f'df <- readRDS("{rds}")',
        "str(df)",
        "summary(df)",
        "",
        "library(ggplot2)",
        "library(dplyr)",
    ]
    if g and y:
        lines += [
            f"df %>% group_by(`{g}`) %>% summarise(n = n(), mean = mean(`{y}`, na.rm = TRUE), sd = sd(`{y}`, na.rm = TRUE))",
            "",
            f"p <- ggplot(df, aes(x = factor(`{g}`), y = `{y}`, fill = factor(`{g}`))) +",
            "  geom_boxplot(outlier.shape = NA, alpha = 0.7) +",
            "  geom_jitter(width = 0.15, size = 1, alpha = 0.6) +",
            f'  labs(x = "{g}", y = "{y}") +',
            "  theme_classic() + theme(legend.position = 'none')",
            "print(p)",
            "# ggsave('figure.pdf', p, width = 4, height = 4)",
            "",
            f"# Statistics: kruskal.test(`{y}` ~ factor(`{g}`), data = df)  or  pairwise.wilcox.test(df$`{y}`, df$`{g}`)",
        ]
    elif y:
        lines += [f"p <- ggplot(df, aes(x = `{y}`)) + geom_histogram(bins = 30) + theme_classic()", "print(p)"]
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------- commands
def cmd_inspect(args: argparse.Namespace) -> None:
    tables, meta = read_tables(args.input, args.sheet)
    report = {"input": os.path.abspath(args.input), "format": ext_of(args.input), "reader": meta.get("reader"),
              "tables": {}}
    for k in ("n_obs", "n_vars", "obsm", "layers", "uns", "encoding"):
        if k in meta:
            report[k] = meta[k]
    for name, df in tables.items():
        head = df.head(5).replace({np.nan: None})
        info = {
            "shape": [int(df.shape[0]), int(df.shape[1])],
            "columns": [str(c) for c in df.columns],
            "dtypes": {str(c): str(t) for c, t in df.dtypes.items()},
            "missing": {str(c): int(v) for c, v in df.isna().sum().items()},
            "head": json.loads(head.to_json(orient="records", force_ascii=False, date_format="iso")),
        }
        cats = {str(c): df[c].nunique(dropna=True) for c in df.columns if df[c].nunique(dropna=True) <= 20 and df.shape[0] > 0}
        info["low_cardinality_columns"] = {c: df[c].dropna().unique()[:20].tolist() for c in cats}
        if meta.get("column_labels"):
            info["column_labels"] = {k: v for k, v in meta["column_labels"].items() if v}
        if meta.get("value_labels"):
            info["value_labels"] = meta["value_labels"]
        report["tables"][name] = info
    out(report)


def cmd_convert(args: argparse.Namespace) -> None:
    src = Path(args.input).resolve()
    tables, meta = read_tables(args.input, args.sheet)
    name, df = pick_table(tables, args.sheet)
    result: dict[str, Any] = {"input": str(src), "table": name, "to": args.to, "rows": int(df.shape[0]),
                              "columns_in": [str(c) for c in df.columns], "notes": []}
    if args.columns:
        want = [c.strip() for c in args.columns.split(",") if c.strip()]
        missing = [c for c in want if c not in df.columns]
        if missing:
            fail(f"Columns not found: {missing}", available=[str(c) for c in df.columns])
        df = df[want]
        tables = {name: df}
        result["columns_selected"] = want
    df.columns = [str(c) for c in df.columns]

    ext = {"sav": "sav", "dta": "dta", "xlsx": "xlsx", "rds": "rds", "r": "rds", "csv": "csv", "pzfx": "pzfx"}[args.to]
    out_path = Path(args.out) if args.out else Path("exports") / f"{src.stem}.{ext}"
    out_path = out_path.resolve()
    if out_path == src:
        fail("Refusing to overwrite the input file. Choose a different --out (default is ./exports/).")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path, renamed = unique_out(out_path)
    if renamed:
        result["notes"].append(f"output existed, wrote {out_path.name} instead")
    files = [str(out_path)]

    if args.to in ("sav", "dta"):
        prs = need("pyreadstat")
        new_names, changes = sanitize_names(list(df.columns), args.to)
        labels = [str(c)[:256] for c in df.columns]
        df2, coerce_notes = coerce_for_stats(df)
        df2.columns = new_names
        # pyreadstat cannot write object columns of all-None -> make them strings
        for c in df2.columns:
            if df2[c].dtype == object and df2[c].notna().sum() == 0:
                df2[c] = df2[c].astype("string")
        if args.to == "sav":
            prs.write_sav(df2, str(out_path), column_labels=labels)
        else:
            prs.write_dta(df2, str(out_path), column_labels=labels)
        result.update(renamed_columns=changes, type_changes=coerce_notes,
                      columns_out=new_names,
                      note="Original column names are kept as variable labels.")
    elif args.to == "xlsx":
        sheets = write_xlsx(tables, out_path)
        result.update(sheets=sheets, columns_out=list(df.columns))
    elif args.to == "csv":
        wide_info = None
        if args.group_col:
            df, wide_info = pivot_wide(df, args.group_col, args.value_col)
        df.to_csv(out_path, index=False, encoding="utf-8-sig")
        result.update(columns_out=list(df.columns), pivot=wide_info,
                      note="UTF-8 with BOM so Excel/Prism on Windows show non-ASCII text correctly.")
    elif args.to in ("rds", "r"):
        pyreadr = need("pyreadr")
        df2 = df.copy()
        for c in df2.columns:
            if isinstance(df2[c].dtype, pd.CategoricalDtype):
                df2[c] = df2[c].astype(str).where(df2[c].notna(), None)
        pyreadr.write_rds(str(out_path), df2)
        result["columns_out"] = list(df2.columns)
        if args.to == "r":
            r_path = out_path.with_name(out_path.stem + "_load.R")
            r_path.write_text(r_snippet(out_path, df2, args.group_col, args.value_col), encoding="utf-8")
            files.append(str(r_path))
            result["r_script"] = str(r_path)
    elif args.to == "pzfx":
        wide, wide_info = pivot_wide(df, args.group_col, args.value_col)
        if wide.shape[1] == 0:
            fail("Nothing numeric to put in a Prism column table; pass --group-col/--value-col.")
        write_pzfx(wide, out_path, title=src.stem)
        csv_path = out_path.with_name(out_path.stem + "_prism_wide.csv")
        wide.to_csv(csv_path, index=False, encoding="utf-8-sig")
        files.append(str(csv_path))
        result.update(columns_out=list(wide.columns), pivot=wide_info, prism_csv=str(csv_path),
                      note="If Prism refuses the .pzfx, import the *_prism_wide.csv instead (File → Import, or paste into a Column table).")
    result["files"] = files
    result["output"] = str(out_path)
    result["open_hint"] = {
        "sav": "SPSS: 文件(File) → 打开(Open) → 数据(Data)，选择该 .sav 文件；原列名在“变量标签”里。",
        "dta": "Stata: File → Open，或命令 use \"<path>\", clear",
        "xlsx": "Excel: 直接双击打开；每个表一个工作表，首行已冻结。",
        "csv": "Excel/Prism: 直接打开或 File → Import。",
        "rds": "R/RStudio: df <- readRDS(\"<path>\")",
        "r": "RStudio: 打开 *_load.R，逐行运行（readRDS + str + ggplot 骨架）。",
        "pzfx": "GraphPad Prism: File → Open 打开 .pzfx；或新建 Column 表后 File → Import 导入 *_prism_wide.csv。",
    }[args.to]
    out(result)


def cmd_h5ad_tables(args: argparse.Namespace) -> None:
    ad = need("anndata")
    src = Path(args.input).resolve()
    out_dir = Path(args.out).resolve() if args.out else Path("exports") / (src.stem + "_tables")
    if out_dir == src:
        fail("Refusing to write over the input")
    out_dir.mkdir(parents=True, exist_ok=True)
    a = ad.read_h5ad(str(src), backed="r")
    obs = a.obs.copy()
    obs.index.name = obs.index.name or "cell_id"
    var = a.var.copy()
    var.index.name = var.index.name or "gene"
    files: dict[str, str] = {}
    obs_p, var_p = out_dir / "obs.csv", out_dir / "var.csv"
    obs.to_csv(obs_p, encoding="utf-8-sig")
    var.to_csv(var_p, encoding="utf-8-sig")
    files["obs"], files["var"] = str(obs_p), str(var_p)
    result: dict[str, Any] = {"input": str(src), "n_obs": int(a.n_obs), "n_vars": int(a.n_vars),
                              "obs_columns": [str(c) for c in obs.columns], "files": files}
    if args.genes:
        genes = [g.strip() for g in args.genes.split(",") if g.strip()]
        names = list(a.var_names)
        lower = {n.lower(): n for n in names}
        found, missing = [], []
        for g in genes:
            if g in names:
                found.append(g)
            elif g.lower() in lower:
                found.append(lower[g.lower()])
            else:
                missing.append(g)
        if not found:
            fail(f"None of the genes were found in var_names: {genes}", example_var_names=names[:10])
        layer = args.layer
        sub = a[:, found].to_memory()
        X = sub.layers[layer] if layer else sub.X
        if hasattr(X, "toarray"):
            X = X.toarray()
        expr = pd.DataFrame(np.asarray(X, dtype=float), index=obs.index, columns=[f"{g}" for g in found])
        joined = obs.join(expr)
        j_p = out_dir / "obs_with_genes.csv"
        joined.to_csv(j_p, encoding="utf-8-sig")
        files["obs_with_genes"] = str(j_p)
        result.update(genes_found=found, genes_missing=missing, expression_source=layer or "X",
                      note="Expression values are taken as stored (check whether X is raw counts or normalized/log values before running stats).")
    result["open_hint"] = "These CSVs can be converted further: convert --input obs_with_genes.csv --to sav|pzfx|xlsx"
    out(result)


# ----------------------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)

    s = sp.add_parser("inspect", help="describe a table file")
    s.add_argument("--input", required=True)
    s.add_argument("--sheet", help="sheet/table name (xlsx sheet, h5ad 'obs'/'var', rds object)")
    s.set_defaults(fn=cmd_inspect)

    s = sp.add_parser("convert", help="convert a table to sav/dta/xlsx/rds/r/csv/pzfx")
    s.add_argument("--input", required=True)
    s.add_argument("--to", required=True, choices=["sav", "dta", "xlsx", "rds", "r", "csv", "pzfx"])
    s.add_argument("--out", help="output file (default exports/<input stem>.<ext>)")
    s.add_argument("--sheet", help="which sheet/table to convert (xlsx / h5ad obs|var / rds object)")
    s.add_argument("--columns", help="comma-separated subset of columns to keep")
    s.add_argument("--group-col", help="long→wide pivot: grouping column (Prism column tables, csv)")
    s.add_argument("--value-col", help="long→wide pivot: value column")
    s.set_defaults(fn=cmd_convert)

    s = sp.add_parser("h5ad-tables", help="dump obs.csv / var.csv (+ gene expression columns) from an h5ad")
    s.add_argument("--input", required=True)
    s.add_argument("--out", help="output directory (default exports/<stem>_tables)")
    s.add_argument("--genes", help="comma-separated gene names to append to obs as columns")
    s.add_argument("--layer", help="use this layer instead of X")
    s.set_defaults(fn=cmd_h5ad_tables)

    args = p.parse_args(argv)
    try:
        args.fn(args)
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        fail(f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
