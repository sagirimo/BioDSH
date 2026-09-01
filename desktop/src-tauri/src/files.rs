//! 数据文件面板：列出工作区里的数据文件（不递归进隐藏目录/输出噪音），给 CSV 一个表头预览。
use serde::Serialize;
use std::fs;
use std::path::Path;

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct FileEntry {
    pub name: String,
    pub rel: String,
    pub size: u64,
    pub modified: u64,
    pub kind: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub preview: Option<String>,
}

fn kind_of(name: &str) -> &'static str {
    let n = name.to_lowercase();
    let ext = n.rsplit('.').next().unwrap_or("");
    match ext {
        "h5ad" => "singlecell",
        "h5" | "loom" | "rds" | "zarr" => "matrix",
        "csv" | "tsv" | "txt" | "xlsx" | "parquet" => "table",
        "png" | "jpg" | "jpeg" | "svg" | "pdf" => "figure",
        "fastq" | "fq" | "fasta" | "fa" | "bam" | "sam" | "vcf" | "bed" | "gtf" | "gff" => "seq",
        "json" | "yaml" | "yml" => "meta",
        "md" | "html" => "report",
        _ => if n.ends_with(".fastq.gz") || n.ends_with(".fq.gz") || n.ends_with(".vcf.gz") { "seq" } else { "other" },
    }
}

fn csv_preview(p: &Path) -> Option<String> {
    let f = fs::File::open(p).ok()?;
    use std::io::{BufRead, BufReader};
    let mut r = BufReader::new(f);
    let mut line = String::new();
    r.read_line(&mut line).ok()?;
    let sep = if line.contains('\t') { '\t' } else { ',' };
    let cols: Vec<&str> = line.trim_end().split(sep).take(8).collect();
    if cols.len() < 2 { return None; }
    Some(cols.join(" · ").chars().take(120).collect())
}

pub fn list(workspace: &str) -> Vec<FileEntry> {
    let mut out = Vec::new();
    let root = Path::new(workspace);
    let mut stack = vec![(root.to_path_buf(), 0usize)];
    while let Some((dir, depth)) = stack.pop() {
        let Ok(rd) = fs::read_dir(&dir) else { continue };
        for e in rd.flatten() {
            let name = e.file_name().to_string_lossy().to_string();
            if name.starts_with('.') || name == "__pycache__" || name == "node_modules" { continue; }
            let path = e.path();
            let Ok(meta) = e.metadata() else { continue };
            if meta.is_dir() {
                if depth < 2 { stack.push((path, depth + 1)); }
                continue;
            }
            let kind = kind_of(&name);
            if kind == "other" && meta.len() < 200 { continue; }
            let rel = path.strip_prefix(root).map(|r| r.to_string_lossy().replace('\\', "/")).unwrap_or(name.clone());
            let preview = if kind == "table" && meta.len() < 50_000_000 { csv_preview(&path) } else { None };
            out.push(FileEntry {
                name, rel, size: meta.len(),
                modified: meta.modified().ok().and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok()).map(|d| d.as_secs()).unwrap_or(0),
                kind: kind.into(), preview,
            });
            if out.len() >= 500 { return out; }
        }
    }
    out.sort_by(|a, b| b.modified.cmp(&a.modified));
    out
}

/// 读工作区内的一张图，返回 data URL（缩略图用）。路径必须落在工作区里，防止越权读取。
pub fn read_image(workspace: &str, rel: &str) -> Result<String, String> {
    let root = fs::canonicalize(workspace).map_err(|e| e.to_string())?;
    let p = fs::canonicalize(root.join(rel)).map_err(|e| e.to_string())?;
    if !p.starts_with(&root) { return Err("路径越界".into()); }
    let meta = fs::metadata(&p).map_err(|e| e.to_string())?;
    if meta.len() > 3_000_000 { return Err("图片太大".into()); }
    let ext = p.extension().and_then(|e| e.to_str()).unwrap_or("").to_lowercase();
    let mime = match ext.as_str() { "png" => "image/png", "jpg" | "jpeg" => "image/jpeg", "svg" => "image/svg+xml", _ => return Err("不支持的图片类型".into()) };
    let bytes = fs::read(&p).map_err(|e| e.to_string())?;
    Ok(format!("data:{mime};base64,{}", base64_encode(&bytes)))
}

fn base64_encode(data: &[u8]) -> String {
    const T: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity(data.len().div_ceil(3) * 4);
    for chunk in data.chunks(3) {
        let b = [chunk[0], *chunk.get(1).unwrap_or(&0), *chunk.get(2).unwrap_or(&0)];
        let n = ((b[0] as u32) << 16) | ((b[1] as u32) << 8) | b[2] as u32;
        out.push(T[(n >> 18) as usize & 63] as char);
        out.push(T[(n >> 12) as usize & 63] as char);
        out.push(if chunk.len() > 1 { T[(n >> 6) as usize & 63] as char } else { '=' });
        out.push(if chunk.len() > 2 { T[n as usize & 63] as char } else { '=' });
    }
    out
}
