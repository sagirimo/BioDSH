//! 本地参考数据包：常用注释/基因集文件一键下载到 ~/BioDSH/refdata，离线也能做富集、ID 转换。
use crate::paths::AppPaths;
use serde::Serialize;
use std::fs;
use std::io::{Read, Write};
use tauri::{AppHandle, Emitter};

pub struct Pack { pub id: &'static str, pub name: &'static str, pub desc: &'static str, pub group: &'static str, pub url: &'static str, pub file: &'static str, pub size_mb: f32 }

pub const PACKS: &[Pack] = &[
    Pack { id: "msigdb-hallmark", name: "MSigDB Hallmark 基因集", desc: "50 个 Hallmark 通路（人），GSEA/富集分析最常用的一套。", group: "通路与基因集", url: "https://data.broadinstitute.org/gsea-msigdb/msigdb/release/2024.1.Hs/h.all.v2024.1.Hs.symbols.gmt", file: "h.all.v2024.1.Hs.symbols.gmt", size_mb: 0.05 },
    Pack { id: "msigdb-kegg", name: "MSigDB KEGG MEDICUS 通路", desc: "KEGG 通路基因集（人，MSigDB 整理版），做通路富集。", group: "通路与基因集", url: "https://data.broadinstitute.org/gsea-msigdb/msigdb/release/2024.1.Hs/c2.cp.kegg_medicus.v2024.1.Hs.symbols.gmt", file: "c2.cp.kegg_medicus.v2024.1.Hs.symbols.gmt", size_mb: 0.2 },
    Pack { id: "msigdb-gobp", name: "MSigDB GO 生物过程基因集", desc: "GO Biological Process 基因集（人），做 GO 富集。", group: "通路与基因集", url: "https://data.broadinstitute.org/gsea-msigdb/msigdb/release/2024.1.Hs/c5.go.bp.v2024.1.Hs.symbols.gmt", file: "c5.go.bp.v2024.1.Hs.symbols.gmt", size_mb: 8.0 },
    Pack { id: "go-basic", name: "Gene Ontology 本体", desc: "GO 术语树（go-basic.obo），解释 GO 编号、找父子关系。", group: "通路与基因集", url: "https://purl.obolibrary.org/obo/go/go-basic.obo", file: "go-basic.obo", size_mb: 32.0 },
    Pack { id: "ncbi-gene-human", name: "NCBI 人类基因注释", desc: "Homo_sapiens.gene_info：基因符号、别名、Entrez ID、描述，用于 ID 转换。", group: "基因注释", url: "https://ftp.ncbi.nlm.nih.gov/gene/DATA/GENE_INFO/Mammalia/Homo_sapiens.gene_info.gz", file: "Homo_sapiens.gene_info.gz", size_mb: 5.0 },
    Pack { id: "ncbi-gene-mouse", name: "NCBI 小鼠基因注释", desc: "Mus_musculus.gene_info：小鼠基因符号/别名/Entrez ID。", group: "基因注释", url: "https://ftp.ncbi.nlm.nih.gov/gene/DATA/GENE_INFO/Mammalia/Mus_musculus.gene_info.gz", file: "Mus_musculus.gene_info.gz", size_mb: 3.7 },
    Pack { id: "string-human", name: "STRING 人类蛋白互作网络", desc: "STRING v12 全部人类蛋白互作边（含置信度），离线构建互作网络。", group: "互作网络", url: "https://stringdb-downloads.org/download/protein.links.v12.0/9606.protein.links.v12.0.txt.gz", file: "9606.protein.links.v12.0.txt.gz", size_mb: 79.0 },
    Pack { id: "string-human-info", name: "STRING 人类蛋白名称表", desc: "STRING 蛋白 ID ↔ 基因名对照，配合互作网络使用。", group: "互作网络", url: "https://stringdb-downloads.org/download/protein.info.v12.0/9606.protein.info.v12.0.txt.gz", file: "9606.protein.info.v12.0.txt.gz", size_mb: 1.9 },
];

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PackStatus { pub id: String, pub name: String, pub desc: String, pub group: String, pub size_mb: f32, pub installed: bool, pub path: String }

pub fn dir(p: &AppPaths) -> std::path::PathBuf { p.root.join("refdata") }

pub fn list(p: &AppPaths) -> Vec<PackStatus> {
    let d = dir(p);
    PACKS.iter().map(|k| {
        let f = d.join(k.file);
        PackStatus { id: k.id.into(), name: k.name.into(), desc: k.desc.into(), group: k.group.into(), size_mb: k.size_mb, installed: f.exists(), path: f.to_string_lossy().into() }
    }).collect()
}

/// 下载到 refdata/<file>.part 再改名；每 512KB 发一次进度事件。
pub fn install(app: &AppHandle, p: &AppPaths, id: &str) -> Result<PackStatus, String> {
    let k = PACKS.iter().find(|k| k.id == id).ok_or("unknown pack")?;
    let d = dir(p);
    fs::create_dir_all(&d).map_err(|e| e.to_string())?;
    let target = d.join(k.file);
    if !target.exists() {
        let part = d.join(format!("{}.part", k.file));
        let resp = ureq::get(k.url).timeout(std::time::Duration::from_secs(1800)).call().map_err(|e| e.to_string())?;
        let total: u64 = resp.header("Content-Length").and_then(|v| v.parse().ok()).unwrap_or(0);
        let mut reader = resp.into_reader();
        let mut out = fs::File::create(&part).map_err(|e| e.to_string())?;
        let mut buf = vec![0u8; 64 * 1024];
        let (mut received, mut last) = (0u64, 0u64);
        loop {
            let n = reader.read(&mut buf).map_err(|e| e.to_string())?;
            if n == 0 { break; }
            out.write_all(&buf[..n]).map_err(|e| e.to_string())?;
            received += n as u64;
            if received - last > 512 * 1024 { last = received; let _ = app.emit("event", serde_json::json!({ "type": "refdata", "id": id, "received": received, "total": total })); }
        }
        drop(out);
        fs::rename(&part, &target).map_err(|e| e.to_string())?;
        let _ = app.emit("event", serde_json::json!({ "type": "refdata", "id": id, "received": received, "total": received, "done": true }));
    }
    write_index(p);
    Ok(list(p).into_iter().find(|s| s.id == id).unwrap())
}

pub fn remove(p: &AppPaths, id: &str) -> Vec<PackStatus> {
    if let Some(k) = PACKS.iter().find(|k| k.id == id) { let _ = fs::remove_file(dir(p).join(k.file)); }
    write_index(p);
    list(p)
}

/// refdata/README.md：告诉智能体这里有什么、怎么用（人设里指向这个文件）。
fn write_index(p: &AppPaths) {
    let d = dir(p);
    let mut md = String::from("# BioDSH 本地参考数据（refdata）\n\nThese files were downloaded by the BioDSH app (数据库 → 本地参考包). Use them for offline enrichment / ID mapping instead of fetching from the internet.\n\n");
    for s in list(p) { if s.installed { md.push_str(&format!("- `{}` — {}: {}\n", s.path, s.name, s.desc)); } }
    md.push_str("\nGMT files: one gene set per line (`name<TAB>url<TAB>gene1<TAB>gene2…`); gseapy accepts a .gmt path directly (`gseapy.enrichr(gene_list, gene_sets='<path>.gmt')`). gene_info.gz: tab-separated, columns include GeneID, Symbol, Synonyms, description. STRING links: `protein1 protein2 combined_score` (score ≥ 700 = high confidence).\n");
    let _ = fs::create_dir_all(&d);
    let _ = fs::write(d.join("README.md"), md);
}
