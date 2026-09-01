# -*- coding: utf-8 -*-
"""校验 review_outline.md 中的 DOI 与 literature_table.xlsx 一致。"""
import re
import sys

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

df = pd.read_excel("literature_table.xlsx", sheet_name=0)
table_dois = {str(d).strip().lower() for d in df["DOI"]}
md = open("review_outline.md", encoding="utf-8").read()
md_dois = {d.rstrip("]），;。").lower() for d in re.findall(r"DOI:\s*([0-9]{2}\.[0-9A-Za-z./_()-]+)", md)}

print("表内 DOI 数:", len(table_dois))
print("提纲引用 DOI 数:", len(md_dois))
print("提纲有而表无:", sorted(md_dois - table_dois) or "无")
print("表有而提纲无:", sorted(table_dois - md_dois) or "无")
