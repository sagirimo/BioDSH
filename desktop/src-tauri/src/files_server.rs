//! 本地只读图片服务：把工作区里的图片变成 http 地址，让 dsh 的 Markdown 能内嵌显示。
//! 只服务白名单根目录（~/BioDSH 及已注册工作区）下的图片文件；只绑定 127.0.0.1；带随机 token。
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

pub struct FilesServer { pub port: u16, pub token: String, roots: Arc<Mutex<Vec<PathBuf>>> }

impl FilesServer {
    pub fn start(initial_roots: Vec<PathBuf>) -> Option<Arc<FilesServer>> {
        let listener = TcpListener::bind("127.0.0.1:0").ok()?;
        let port = listener.local_addr().ok()?.port();
        let token = uuid::Uuid::new_v4().simple().to_string();
        let roots = Arc::new(Mutex::new(initial_roots));
        let srv = Arc::new(FilesServer { port, token: token.clone(), roots: roots.clone() });
        std::thread::spawn(move || {
            for stream in listener.incoming().flatten() {
                let (roots, token) = (roots.clone(), token.clone());
                std::thread::spawn(move || { let _ = handle(stream, &roots, &token); });
            }
        });
        Some(srv)
    }
    pub fn add_root(&self, p: PathBuf) { let mut r = self.roots.lock().unwrap(); if !r.iter().any(|x| x == &p) { r.push(p); } }
    /// 智能体/页面用的基址，例如 http://127.0.0.1:12345/f/<token>
    pub fn base_url(&self) -> String { format!("http://127.0.0.1:{}/f/{}", self.port, self.token) }
}

/// 在 dir 下递归找同名文件（深度 ≤ 5、最多看 4000 个条目；跳过 .venv/node_modules 等大目录）
fn find_by_name(dir: &Path, name: &std::ffi::OsStr, depth: u32, seen: &mut u32) -> Option<PathBuf> {
    if depth > 5 || *seen > 4000 { return None; }
    let rd = std::fs::read_dir(dir).ok()?;
    let mut subdirs = Vec::new();
    for e in rd.flatten() {
        *seen += 1;
        let p = e.path();
        if p.is_file() && p.file_name() == Some(name) { return std::fs::canonicalize(&p).ok(); }
        if p.is_dir() {
            let dn = e.file_name().to_string_lossy().to_string();
            if dn.starts_with('.') || matches!(dn.as_str(), "node_modules" | "__pycache__" | "gtex_cache" | "fetch_cache" | "bioenv" | "uv" | "node" | "dsh-home" | "community-skills" | "skills" | "logs" | "target-bundle" | "site-packages") { continue; }
            subdirs.push(p);
        }
    }
    for d in subdirs { if let Some(f) = find_by_name(&d, name, depth + 1, seen) { return Some(f); } }
    None
}

fn mime(p: &Path) -> Option<&'static str> {
    match p.extension().and_then(|e| e.to_str()).map(|e| e.to_ascii_lowercase()).as_deref() {
        Some("png") => Some("image/png"), Some("jpg") | Some("jpeg") => Some("image/jpeg"), Some("gif") => Some("image/gif"),
        Some("webp") => Some("image/webp"), Some("svg") => Some("image/svg+xml"), Some("bmp") => Some("image/bmp"), Some("pdf") => Some("application/pdf"),
        _ => None,
    }
}

fn percent_decode(s: &str) -> String {
    let b = s.as_bytes(); let mut out = Vec::with_capacity(b.len()); let mut i = 0;
    while i < b.len() {
        if b[i] == b'%' && i + 2 < b.len() { if let Ok(v) = u8::from_str_radix(&s[i + 1..i + 3], 16) { out.push(v); i += 3; continue; } }
        out.push(if b[i] == b'+' { b' ' } else { b[i] }); i += 1;
    }
    String::from_utf8_lossy(&out).into_owned()
}

fn respond(mut s: TcpStream, code: u16, ctype: &str, body: &[u8]) -> std::io::Result<()> {
    let head = format!("HTTP/1.1 {} {}\r\nContent-Type: {}\r\nContent-Length: {}\r\nAccess-Control-Allow-Origin: *\r\nCache-Control: no-cache\r\nConnection: close\r\n\r\n", code, if code == 200 { "OK" } else { "Error" }, ctype, body.len());
    s.write_all(head.as_bytes())?; s.write_all(body)?; s.flush()
}

fn handle(mut stream: TcpStream, roots: &Mutex<Vec<PathBuf>>, token: &str) -> std::io::Result<()> {
    let mut buf = [0u8; 8192];
    let n = stream.read(&mut buf)?;
    let req = String::from_utf8_lossy(&buf[..n]);
    let line = req.lines().next().unwrap_or("");
    let mut parts = line.split_whitespace();
    let (method, target) = (parts.next().unwrap_or(""), parts.next().unwrap_or(""));
    if method != "GET" { return respond(stream, 405, "text/plain", b"method"); }
    // /f/<token>/<percent-encoded absolute path>   或   /f/<token>?p=<path>
    let prefix = format!("/f/{token}");
    let Some(rest) = target.strip_prefix(&prefix) else { return respond(stream, 404, "text/plain", b"not found") };
    let raw = if let Some(q) = rest.strip_prefix("?p=") { q.to_string() } else { rest.trim_start_matches('/').to_string() };
    let raw = raw.split('&').next().unwrap_or("").to_string();
    let path = PathBuf::from(percent_decode(&raw).replace('/', std::path::MAIN_SEPARATOR_STR));
    let canon = match std::fs::canonicalize(&path) {
        Ok(c) => c,
        Err(_) => {
            // 正文里常常只写文件名（图其实在某个子文件夹里）：在最近的存在的祖先目录下按文件名找一次
            let name = path.file_name().map(|n| n.to_os_string());
            let mut base = path.parent().map(Path::to_path_buf);
            while let Some(b) = base.clone() { if !b.as_os_str().is_empty() && b.exists() { break; } base = b.parent().map(Path::to_path_buf); }
            let mut found = None;
            if let (Some(b), Some(n)) = (base, name.clone()) { if !b.as_os_str().is_empty() { found = find_by_name(&b, &n, 0, &mut 0); } }
            if found.is_none() { if let Some(n) = name { // 正文常只写文件名：在已注册工作区里按名字找；先找最具体的（路径最长）根，避免在 ~/BioDSH 这种大目录上耗尽预算
                let mut rs: Vec<PathBuf> = roots.lock().unwrap().clone();
                rs.sort_by_key(|r| std::cmp::Reverse(r.as_os_str().len()));
                for r in rs.iter() { let mut seen = 0u32; if let Some(f) = find_by_name(r, &n, 0, &mut seen) { found = Some(f); break; } }
            } }
            match found { Some(f) => f, None => return respond(stream, 404, "text/plain", b"no such file") }
        }
    };
    let allowed = roots.lock().unwrap().iter().any(|r| std::fs::canonicalize(r).map(|rc| canon.starts_with(&rc)).unwrap_or(false));
    if !allowed { return respond(stream, 403, "text/plain", b"outside workspace"); }
    let Some(ct) = mime(&canon) else { return respond(stream, 415, "text/plain", b"not an image") };
    match std::fs::read(&canon) { Ok(data) => respond(stream, 200, ct, &data), Err(_) => respond(stream, 404, "text/plain", b"unreadable") }
}
