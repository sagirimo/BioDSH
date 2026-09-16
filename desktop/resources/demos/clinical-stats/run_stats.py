# -*- coding: utf-8 -*-
"""
临床随机对照数据统计:描述统计 + 组间比较(自动选检验)+ 疗效图
输出到 outputs/ 子文件夹。原始数据 patients.csv 不会被修改。
"""
import os
import numpy as np
import pandas as pd
from scipy import stats

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")
os.makedirs(OUT, exist_ok=True)

# ---------------- 读取 ----------------
df = pd.read_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "patients.csv"))
df["improved"] = df["improved"].astype(str).str.strip().str.lower()
df["sex"] = df["sex"].astype(str).str.strip().str.upper()

T = df[df["group"] == "treatment"]
C = df[df["group"] == "control"]
print(f"总例数 n={len(df)} | 试验组 n={len(T)} | 对照组 n={len(C)}")

cont_cols = ["age", "baseline_CRP", "post_CRP", "LOS_days"]
cat_cols = ["sex", "improved"]

# ---------------- 1) 描述统计 ----------------
rows = []
for col in cont_cols:
    for gname, gdf in [("全部", df), ("试验组treatment", T), ("对照组control", C)]:
        s = gdf[col].dropna()
        rows.append({
            "变量": col, "组别": gname, "n": int(s.size),
            "均值": round(s.mean(), 2), "标准差": round(s.std(ddof=1), 2),
            "中位数": round(s.median(), 2), "IQR": round(s.quantile(0.75) - s.quantile(0.25), 2),
            "最小值": round(s.min(), 2), "最大值": round(s.max(), 2)})
desc_cont = pd.DataFrame(rows)
desc_cont.to_csv(os.path.join(OUT, "continuous_descriptives.csv"), index=False, encoding="utf-8-sig")

cat_rows = []
for col in cat_cols:
    for gname, gdf in [("全部", df), ("试验组treatment", T), ("对照组control", C)]:
        for val in sorted(gdf[col].unique()):
            nv = int((gdf[col] == val).sum())
            cat_rows.append({"变量": col, "组别": gname, "取值": val,
                             "人数": nv, "占比%": round(100.0 * nv / len(gdf), 1)})
desc_cat = pd.DataFrame(cat_rows)
desc_cat.to_csv(os.path.join(OUT, "categorical_counts.csv"), index=False, encoding="utf-8-sig")

# ---------------- 2) 检验(自动选择) ----------------
def stars(p):
    return "***" if p < 0.001 else ("**" if p < 0.01 else ("*" if p < 0.05 else "ns"))

def test_continuous(col):
    a = T[col].dropna().values
    b = C[col].dropna().values
    n1, n2 = a.size, b.size
    # 正态性(每组 Shapiro-Wilk, 双侧 p>=0.05 视为可接受正态)
    w1, p1 = stats.shapiro(a)
    w2, p2 = stats.shapiro(b)
    normal = (p1 >= 0.05) and (p2 >= 0.05)
    if normal:
        tval, pv = stats.ttest_ind(a, b, equal_var=False)  # Welch t 检验
        method = "Welch t 检验(两样本均正态)"
        stat_name = "t"
        stat_val = tval
        # Cohen's d(合并标准差)
        sp = np.sqrt(((n1 - 1) * a.std(ddof=1) ** 2 + (n2 - 1) * b.std(ddof=1) ** 2) / (n1 + n2 - 2))
        es = (a.mean() - b.mean()) / sp
        es_name = "Cohen's d(组间均值差/合并标准差)"
    else:
        uval, pv = stats.mannwhitneyu(a, b, alternative="two-sided")
        method = "Mann-Whitney U 检验(至少一组非正态)"
        stat_name = "U"
        stat_val = uval
        # rank-biserial 效应量
        n_ab = n1 * n2
        es = 1 - 2 * uval / n_ab
        es_name = "秩双列相关 r(0=无差异,越偏离0差异越大)"
    return {
        "变量": col, "检验方法": method, "正态性W/p(试验/对照)": f"{w1:.3f}/{p1:.3f} | {w2:.3f}/{p2:.3f}",
        f"{stat_name}值": round(float(stat_val), 3),
        "p值": pv, "显著性": stars(pv),
        "均值±SD(试验/对照)": f"{a.mean():.2f}±{a.std(ddof=1):.2f} / {b.mean():.2f}±{b.std(ddof=1):.2f}",
        "中位数(试验/对照)": f"{np.median(a):.2f} / {np.median(b):.2f}",
        "效应量": round(float(es), 3), "效应量说明": es_name,
    }

res_cont = [test_continuous(c) for c in ["age", "baseline_CRP", "post_CRP", "LOS_days"]]

def test_categorical(col, ref):
    a_yes = int((T[col] == ref).sum())
    b_yes = int((C[col] == ref).sum())
    a_no = len(T) - a_yes
    b_no = len(C) - b_yes
    table = np.array([[a_yes, a_no], [b_yes, b_no]])
    # 期望频数过小则 Fisher 精确检验
    if np.any(stats.contingency.expected_freq(table) < 5):
        orv, pv = stats.fisher_exact(table)
        method = "Fisher 精确检验(期望频数<5)"
        stat_name = "比值比OR"
        stat_val = orv
    else:
        chi2v, pv, dof, _ = stats.chi2_contingency(table, correction=False)
        method = "Pearson 卡方检验(2x2,不校正)"
        stat_name = "χ²"
        stat_val = chi2v
    rt, rc = a_yes / len(T), b_yes / len(C)
    rr = rt / rc if rc > 0 else np.nan
    return {
        "变量": col, "检验方法": method,
        "试验组计数": f"{a_yes}/{len(T)}({100*rt:.1f}%)", "对照组计数": f"{b_yes}/{len(C)}({100*rc:.1f}%)",
        f"{stat_name}值": round(float(stat_val), 3),
        "p值": pv, "显著性": stars(pv),
        "相对危险度RR(试验vs对照)": round(float(rr), 3) if col == "improved" else np.nan,
    }

res_cat = [test_categorical("improved", "yes"), test_categorical("sex", "F")]

tests_df = pd.DataFrame(res_cont + res_cat)
tests_df["p值"] = tests_df["p值"].map(lambda x: f"{x:.4g}")
tests_df = tests_df.replace({np.nan: ""})
tests_df.to_csv(os.path.join(OUT, "tests_summary.csv"), index=False, encoding="utf-8-sig")

# 好转率差与 NNT
a_yes = int((T["improved"] == "yes").sum()); b_yes = int((C["improved"] == "yes").sum())
rt, rc = a_yes / len(T), b_yes / len(C)
arr = rt - rc
nnt = 1.0 / arr if arr > 0 else np.nan
print(f"好转率: 试验组 {a_yes}/{len(T)}={100*rt:.1f}%  vs  对照组 {b_yes}/{len(C)}={100*rc:.1f}%  | 绝对差 {100*arr:.1f} 个百分点, NNT={nnt:.1f}")

# ---------------- 3) 疗效图 ----------------
from matplotlib import font_manager
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# 中文字体(找不到则退回英文标签)
zh_name = None
for p in [r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc",
          r"C:\Windows\Fonts\simhei.ttf", r"C:\Windows\Fonts\simsun.ttc"]:
    if os.path.exists(p):
        try:
            zh_name = font_manager.FontProperties(fname=p).get_name()
            font_manager.fontManager.addfont(p)
            break
        except Exception:
            zh_name = None
if zh_name:
    plt.rcParams["font.sans-serif"] = [zh_name, "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["font.size"] = 11

TR = "#4C72B0"; CO = "#DD8452"
LBL = {"treatment": "试验组(用药)", "control": "对照组(安慰剂/常规)"} if zh_name else {"treatment": "Treatment", "control": "Control"}
rng = np.random.default_rng(42)

def panel_box(ax, col, ylab, ptext, sub, unit_note):
    data = [T[col].dropna().values, C[col].dropna().values]
    bp = ax.boxplot(data, positions=[1, 2], widths=0.55, patch_artist=True,
                    medianprops=dict(color="black", lw=1.6),
                    flierprops=dict(marker="o", markersize=4, alpha=0.6))
    for patch, c in zip(bp["boxes"], [TR, CO]):
        patch.set_facecolor(c); patch.set_alpha(0.75)
    for i, d in enumerate(data):
        xs = rng.uniform(-0.12, 0.12, size=d.size) + (i + 1)
        ax.scatter(xs, d, s=16, color="#333333", alpha=0.45, linewidths=0)
    ymax = max(d.max() for d in data)
    ax.set_ylim(0, ymax * 1.18)
    ax.set_xticks([1, 2]); ax.set_xticklabels([LBL["treatment"], LBL["control"]])
    ax.set_ylabel(ylab)
    ax.text(1.5, ymax * 1.08, ptext, ha="center", fontsize=12, fontweight="bold")
    ax.set_title(sub, fontsize=12)

fig, axes = plt.subplots(1, 3, figsize=(15.5, 5.2))

pv_crp = res_cont[2]["p值"]; star_crp = res_cont[2]["显著性"]
pv_los = res_cont[3]["p值"]; star_los = res_cont[3]["显著性"]
m1 = res_cont[2]["检验方法"].split("(")[0]; m2 = res_cont[3]["检验方法"].split("(")[0]
fmt = lambda p: "p<0.001" if p < 0.001 else f"p={p:.4f}"

panel_box(axes[0], "post_CRP", "治疗后 CRP (mg/L)", f"{fmt(pv_crp)}  {star_crp}", "A  治疗后 CRP: 越低越好", "")
panel_box(axes[1], "LOS_days", "住院天数 (天)", f"{fmt(pv_los)}  {star_los}", "B  住院天数: 越短越好", "")

# C 好转率条形
rates = [rt, rc]
bars = axes[2].bar([1, 2], [100 * r for r in rates], width=0.55, color=[TR, CO], alpha=0.85, edgecolor="black", linewidth=0.8)
axes[2].set_xticks([1, 2]); axes[2].set_xticklabels([LBL["treatment"], LBL["control"]])
axes[2].set_ylabel("好转率 (%)")
axes[2].set_ylim(0, 105)
for i, (r, b) in enumerate(zip(rates, bars)):
    axes[2].text(b.get_x() + b.get_width() / 2, 100 * r + 2.5,
                 f"{100*r:.0f}%\n({[a_yes, b_yes][i]}/{len(T)})", ha="center", fontsize=11)
pv_chi = res_cat[0]["p值"]
axes[2].text(1.5, 96, f"{fmt(pv_chi)}  {res_cat[0]['显著性']}", ha="center", fontsize=12, fontweight="bold")
axes[2].set_title("C  好转率", fontsize=12)

fig.suptitle("主要疗效指标比较: 试验组 vs 对照组 (n=40/组)" + ("" if zh_name else "  (trial vs control)"),
             fontsize=14, fontweight="bold", y=0.99)
fig.tight_layout(rect=[0, 0, 1, 0.96])
fig.savefig(os.path.join(OUT, "efficacy_figure.png"), dpi=200)
print("图已保存:", os.path.join(OUT, "efficacy_figure.png"))

# ---------------- 汇总文本 ----------------
lines = []
lines.append("# 统计结果摘要")
lines.append("")
lines.append("## 描述统计(均值±标准差 / 分类计数)")
for _, r in desc_cont[desc_cont["组别"].isin(["试验组treatment", "对照组control"])].iterrows():
    lines.append(f"- {r['变量']} | {r['组别']}: n={r['n']}, 均值±SD = {r['均值']}±{r['标准差']}, 中位数={r['中位数']}, IQR={r['IQR']}")
lines.append("")
lines.append("## 组间比较")
lines.append("")
lines.append("| 变量 | 检验方法 | 试验组 | 对照组 | p值 | 显著性 |")
lines.append("|---|---|---|---|---|---|")
for r in res_cont + res_cat:
    if "均值±SD(试验/对照)" in r:
        m1s, m2s = r["均值±SD(试验/对照)"].split(" / ")
        g1, g2 = f"均值±SD {m1s}", f"均值±SD {m2s}"
    else:
        g1, g2 = r["试验组计数"], r["对照组计数"]
    lines.append(f"| {r['变量']} | {r['检验方法']} | {g1} | {g2} | {r['p值']:.4g} | {r['显著性']} |")
with open(os.path.join(OUT, "statistics_summary.md"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines))

print("\n==== 连续变量检验 ====")
print(pd.DataFrame(res_cont).to_string(index=False))
print("\n==== 分类变量检验 ====")
print(pd.DataFrame(res_cat).to_string(index=False))
print("\n==== 描述(连续) ====")
print(desc_cont.to_string(index=False))
print("\n==== 描述(分类) ====")
print(desc_cat.to_string(index=False))
print("\n输出文件:", os.listdir(OUT))
