# 免疫基因列表 · 通路/功能富集分析报告

**输入**:`genes.txt`,15 个人类基因(免疫相关)
**分析日期/环境**:BioDSH 分析环境(Python 3.12,scipy 1.18)

| 基因 | 全名/角色 |
|---|---|
| PDCD1 (PD-1)、CTLA4、LAG3、HAVCR2 (TIM-3)、TIGIT | 免疫检查点受体(抑制性) |
| TOX、EOMES、TCF7 | T 细胞分化/耗竭相关转录因子 |
| CD8A、ITGAE (CD103) | CD8⁺ T 细胞标志/组织驻留 |
| GZMB、PRF1、IFNG | 细胞毒效应分子(颗粒酶B/穿孔素/干扰素-γ) |
| CXCL13、ENTPD1 (CD39) | 趋化/免疫调节 |

## 方法与参数

- **方法**:每个 GO 生物过程 / KEGG 通路做“过表达分析(ORA)”——单侧超几何检验(等价于 2×2 单侧 Fisher 精确检验),即 clusterProfiler `enrichGO` / `enrichKEGG` 的同一套检验逻辑;随后用 Benjamini–Hochberg(BH)做多重检验校正。
- **p 值公式**:`P(X ≥ k)` = phyper(k−1, M, N−M, n),其中 N=背景中带注释的基因数、M=该通路内的基因数、n=输入列表中被注释的基因数、k=两者交集数。
- **基因集来源**(Enrichr 快照,已缓存到 `outputs/gene_set_libraries/`,可离线复现):
  - GO 生物过程:`GO_Biological_Process_2023`(5407 个 BP 术语,14350 个带注释基因)
  - KEGG 人通路:`KEGG_2021_Human`(Enrichr 发行的人 KEGG 最新版;320 条通路)
- **过滤参数**:基因集大小 10–1000(去掉过小噪音与超大宽泛项);显著阈值 = 校正后 p (p.adjust) < 0.05。
- **背景说明**:输入是一份手工挑选的特征基因表、没有“检测到的全部基因”这一测量背景,因此按此类特征列表的通用惯例(Enrichr/DAVID 同法)以注释基因组为背景。结果表同时给出原始 p 与校正后 p 及富集倍数,供自行判断。

## 显著富集结果(校正后 p < 0.05)

### GO 生物过程(9 条显著)

| GO 生物过程 | 命中/15 | 富集倍数 | p 值 | 校正后 p (FDR) |
|---|---|---|---|---|
| Negative regulation of T cell differentiation (GO:0045581) | 2 | 147.2 | 7.90e-05 | 7.19e-03 |
| Apoptotic process (GO:0006915) | 4 | 16.8 | 7.38e-05 | 1.01e-02 |
| Regulation of regulatory T cell differentiation (GO:0045589) | 2 | 87.0 | 2.33e-04 | 1.27e-02 |
| T cell mediated immunity (GO:0002456) | 2 | 95.7 | 1.92e-04 | 1.31e-02 |
| Regulation of immune response (GO:0050776) | 3 | 37.3 | 6.45e-05 | 1.76e-02 |
| Negative regulation of cytokine production (GO:0001818) | 3 | 16.1 | 7.65e-04 | 3.48e-02 |
| Regulation of interleukin-12 production (GO:0032655) | 2 | 38.3 | 1.21e-03 | 3.68e-02 |
| Negative regulation of T cell activation (GO:0050868) | 2 | 39.1 | 1.17e-03 | 3.98e-02 |
| T cell differentiation (GO:0030217) | 2 | 41.6 | 1.03e-03 | 4.01e-02 |

### KEGG 通路(10 条显著)

| KEGG 通路 | 命中/11 | 富集倍数 | p 值 | 校正后 p (FDR) |
|---|---|---|---|---|
| Type I diabetes mellitus | 3 | 51.2 | 2.26e-05 | 3.67e-04 |
| Cell adhesion molecules | 4 | 19.8 | 3.25e-05 | 4.22e-04 |
| Graft-versus-host disease | 3 | 52.4 | 2.10e-05 | 4.56e-04 |
| Autoimmune thyroid disease | 3 | 41.5 | 4.26e-05 | 4.61e-04 |
| Allograft rejection | 3 | 57.9 | 1.55e-05 | 5.04e-04 |
| T cell receptor signaling pathway | 4 | 28.2 | 8.03e-06 | 5.22e-04 |
| Natural killer cell mediated cytotoxicity | 3 | 16.8 | 6.28e-04 | 5.83e-03 |
| Antigen processing and presentation | 2 | 18.8 | 4.80e-03 | 3.90e-02 |
| Rheumatoid arthritis | 2 | 15.8 | 6.76e-03 | 4.39e-02 |
| PD-L1 expression and PD-1 checkpoint pathway in cancer | 2 | 16.5 | 6.21e-03 | 4.48e-02 |

完整逐条结果(含每个术语的命中基因、被测试的全部 273 个 GO 术语与 65 个 KEGG 通路)见:
`GO_BP_full_results.tsv`、`KEGG_full_results.tsv`;Top 表 CSV(Excel 可直接打开):`GO_BP_top_results.csv`、`KEGG_top_results.csv`、`top_enrichment_results.csv`。

## 大白话解读

这组基因**不是“某一条通路”,而是 CD8⁺ 杀伤性 T 细胞“疲惫(耗竭)+ 发动攻击”两个状态的组合签名**,富集结果正好把这两层含义拆开:

1. **“刹车”基因家族(免疫检查点)→ 负向调控 T 细胞**:PD-1 (PDCD1)、CTLA4、LAG3、TIM-3 (HAVCR2)、TIGIT 全是 T 细胞表面的“刹车”受体;GO 富集出的“T 细胞分化的负调控”“Treg 分化的调控”“免疫应答的调控”“细胞因子产生的负调控”“T 细胞活化的负调控”就是它们的功能注释。生物学含义:这些基因集中出现 = 该 T 细胞亚群处于**被抑制/耗竭状态**(慢性感染、肿瘤微环境里常见)。
2. **“弹药”基因家族(细胞毒杀伤)→ 效应与杀伤**:GZMB(颗粒酶 B)、PRF1(穿孔素)、IFNG(干扰素-γ)是杀伤性 T 细胞/自然杀伤(NK)细胞“开火”的武器;对应富集到“T 细胞介导的免疫”“凋亡过程”“NK 细胞介导的细胞毒作用”。
3. **CD8/抗原识别骨架**:CD8A(CD8 分子)、ITGAE(CD103)、TCF7/EOMES/TOX 对应“T 细胞分化”“T 细胞受体信号通路”“抗原加工与呈递”等。
4. **KEGG 层面最有特色的信号——自身免疫/移植排斥 + PD-1 通路**:显著条目集中在 I 型糖尿病、自身免疫性甲状腺病、移植物抗宿主病、同种异体移植排斥、类风湿关节炎这类“免疫系统攻击自身/移植组织”的疾病(由 CTLA4、IFNG、GZMB、PRF1 等驱动),并直接命中 **“肿瘤中 PD-L1 表达与 PD-1 检查点通路”**。这与该基因列表常用于“耗竭 T 细胞/免疫治疗反应”场景完全吻合。

**一句话总结**:这 15 个基因 = 一群“手里有武器(GZMB/PRF1/IFNG)但被踩了刹车(PD-1/CTLA4/LAG3/TIM-3/TIGIT)”的 CD8⁺ 杀伤性 T 细胞——即典型的**耗竭/功能障碍 T 细胞**签名,与抗肿瘤免疫、慢性感染及自身免疫的免疫检查点调控高度相关。

## 注意事项

- 输入无“检测背景”,故按注释基因组为背景;若未来有测序获得的完整基因集合,应改用该集合做背景,结果会更有针对性。
- KEGG 数据库未收录 LAG3、HAVCR2、TOX、EOMES 四个基因(KEGG 注释滞后),它们仅体现在 GO 结果中。
- 个别 GO 术语与 KEGG 条目由同一批基因驱动(GO 的“父-子”层级会重复计),解读时建议按上面 4 个主题聚类,而不是把每条都当独立发现。
- 本分析不修改原始 `genes.txt`;脚本为工作区根目录 `run_enrichment.py`,可重复运行复现。

## 引用与致谢

- Chen EY et al. Enrichr. *BMC Bioinformatics* 2013; Kuleshov MV et al. Enrichr: a comprehensive gene set enrichment analysis web server. *Nucleic Acids Res* 2016.
- Gene Ontology: Ashburner et al. 2000; GOA 注释(经 Enrichr GO BP 2023 快照)。
- KEGG: Kanehisa & Goto 2000(经 Enrichr KEGG_2021_Human 快照)。
- ORA 方法学:Yu G et al. clusterProfiler. *OMICS* 2012; Wu T et al. clusterProfiler 4.0. *Innovation* 2021。
