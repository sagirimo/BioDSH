---
name: data-format-bridge
description: Convert analysis tables (csv/tsv/xlsx/parquet/h5ad obs-var/rds/sav/dta) into the formats clinicians and statisticians open directly — SPSS .sav, Stata .dta, R .rds with a ready-to-run .R script, GraphPad Prism .pzfx plus a Prism-ready wide CSV, and tidy Excel workbooks. Never touches the input file.
---

# Data format bridge (SPSS / R / Prism / Excel / Stata)

Use this skill whenever a result table has to leave Python: the user says "导出成 SPSS 能打开的", "给我 Prism 能画图的表", "整理成 Excel", "我想在 R 里接着分析", "Stata 文件", or an analysis skill has produced CSVs that a clinician will take to their own statistics software. Also use `inspect` to look inside files the user brings (`.sav`, `.dta`, `.rds`, `.xlsx`, `.h5ad`) before doing anything with them.

Target mapping — what the user says → what you write:

| user says | `--to` | files produced |
|---|---|---|
| SPSS | `sav` | `<name>.sav` (original column names kept as variable labels) |
| R / RStudio | `r` | `<name>.rds` + `<name>_load.R` (readRDS, str, ggplot skeleton) — `rds` alone gives only the .rds |
| GraphPad Prism | `pzfx` | `<name>.pzfx` (Column table, one column per group) **and** `<name>_prism_wide.csv` |
| Excel | `xlsx` | one sheet per table, frozen header row, auto column widths |
| Stata | `dta` | `<name>.dta` (labels kept) |
| plain / "通用" | `csv` | UTF-8-BOM CSV (Excel/Prism friendly), optional long→wide pivot |

## Commands

```bash
python "<skill dir>/convert.py" inspect --input results/de_table.csv [--sheet obs]
python "<skill dir>/convert.py" convert --input results/de_table.csv --to sav
python "<skill dir>/convert.py" convert --input results/scores.csv --to pzfx --group-col group --value-col score
python "<skill dir>/convert.py" convert --input results/scores.csv --to r [--columns patient,group,score]
python "<skill dir>/convert.py" convert --input results/book.xlsx --to xlsx --sheet Sheet2 --out exports/clean.xlsx
python "<skill dir>/convert.py" h5ad-tables --input data/adata.h5ad --out exports/adata_tables --genes CD8A,GZMB,PDCD1
```

- `inspect` prints shape, columns, dtypes, first 5 rows, missing counts (and SPSS/Stata variable labels when present). For `.h5ad` it reads only `obs`/`var` (no expression matrix); use `--sheet obs|var`.
- `convert` writes into `./exports/` under the current workspace unless `--out` is given; existing files are never overwritten (a `_1`, `_2` suffix is added and reported in `notes`). The input file is never modified, and `--out` equal to the input is refused.
- `--group-col/--value-col` pivots a long table (one row per measurement) into one column per group — this is what Prism's Column tables and t-test/ANOVA dialogs expect. Without it, `pzfx` uses every numeric column as a group and reports what it dropped.
- `h5ad-tables` writes `obs.csv`, `var.csv`, and with `--genes` an `obs_with_genes.csv` (per-cell metadata + expression of those genes, taken as stored in `X` or `--layer`). Feed that file back into `convert --to sav|pzfx|xlsx` for per-cell / per-group statistics outside Python.

## Read the JSON output and relay it

Every run reports `files`, `columns_out`, and for SPSS/Stata `renamed_columns` (SPSS names must be ≤64 bytes, letters/digits/underscore, no leading digit, no reserved words like `ALL`; Stata ≤32 chars) plus `type_changes` (bool → 0/1, categorical → string, timezone dropped). **Tell the user which columns were renamed** — the original names are preserved as variable labels so they still appear in SPSS "Variable View" / Stata `describe`.

After converting, always tell the user the absolute file path and how to open it:

- SPSS: 文件(File) → 打开(Open) → 数据(Data)，选择 `.sav`；原列名在“变量标签”中。
- Prism: File → Open 打开 `.pzfx`；如果 Prism 报错或版本较旧，新建 Column 表后 File → Import 导入 `*_prism_wide.csv`（CSV/XLSX 导入是最稳妥的路线，`.pzfx` 是按 Prism 8 的 XML 结构手写的最小文件）。
- R: 打开 `*_load.R`，逐行运行；或 `df <- readRDS("<path>")`。
- Excel: 直接双击；Stata: File → Open 或 `use "<path>", clear`。

## Environment

Reading needs only pandas. Writers are imported lazily: `pyreadstat` (sav/dta), `pyreadr` (rds/r), `openpyxl` (xlsx), `anndata` (h5ad). If a run errors with "package ... is not installed", run the `uv pip install <pkg>` command from the message and retry; the BioDSH env pack **“统计与临床”** installs `pyreadstat` and `openpyxl` (add `pyreadr` with `uv pip install pyreadr`).

## Rules

- Never overwrite or edit the input; never write outside `exports/` unless the user asked for a specific `--out`.
- Do not "fix" the data while converting (no dropping rows, no recoding) — if the table needs cleaning, do it as a separate, explained step and keep the original.
- Missing values stay missing (empty cell in Prism/Excel, system-missing in SPSS/Stata, `NA` in R); say so if the user asks about blanks.
