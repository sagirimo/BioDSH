//! 项目（工作区文件夹）的版本控制：查状态 / 初始化 / 提交快照。找不到 git 时返回 available=false。
use serde::Serialize;
use std::path::Path;
use std::process::{Command, Stdio};

#[derive(Serialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct GitStatus {
    pub available: bool,
    pub is_repo: bool,
    pub branch: Option<String>,
    pub dirty: usize,
    pub last_commit: Option<String>,
    pub error: Option<String>,
}

fn git(cwd: &Path, args: &[&str]) -> Result<String, String> {
    let mut cmd = Command::new("git");
    cmd.args(args).current_dir(cwd).stdin(Stdio::null()).stdout(Stdio::piped()).stderr(Stdio::piped());
    #[cfg(windows)]
    { use std::os::windows::process::CommandExt; cmd.creation_flags(0x0800_0000); }
    let out = cmd.output().map_err(|e| e.to_string())?;
    if out.status.success() { Ok(String::from_utf8_lossy(&out.stdout).trim().to_string()) } else { Err(String::from_utf8_lossy(&out.stderr).trim().to_string()) }
}

pub fn status(path: &str) -> GitStatus {
    let p = Path::new(path);
    if !p.exists() { return GitStatus { error: Some("目录不存在".into()), ..Default::default() }; }
    if git(p, &["--version"]).is_err() { return GitStatus { available: false, ..Default::default() }; }
    let inside = git(p, &["rev-parse", "--is-inside-work-tree"]).map(|s| s == "true").unwrap_or(false);
    if !inside { return GitStatus { available: true, is_repo: false, ..Default::default() }; }
    let branch = git(p, &["rev-parse", "--abbrev-ref", "HEAD"]).ok();
    let dirty = git(p, &["status", "--porcelain"]).map(|s| s.lines().filter(|l| !l.trim().is_empty()).count()).unwrap_or(0);
    let last_commit = git(p, &["log", "-1", "--format=%s (%cr)"]).ok().filter(|s| !s.is_empty());
    GitStatus { available: true, is_repo: true, branch, dirty, last_commit, error: None }
}

pub fn init(path: &str) -> Result<GitStatus, String> {
    let p = Path::new(path);
    if git(p, &["init", "-q", "-b", "main"]).is_err() { git(p, &["init", "-q"])?; }
    if !p.join(".gitignore").exists() {
        let _ = std::fs::write(p.join(".gitignore"), "# BioDSH 默认忽略大文件与中间产物\n*.h5ad\n*.h5\n*.bam\n*.fastq*\n*.fq*\n__pycache__/\n.ipynb_checkpoints/\n");
    }
    Ok(status(path))
}

pub fn commit(path: &str, message: &str) -> Result<GitStatus, String> {
    let p = Path::new(path);
    git(p, &["add", "-A"])?;
    let msg = if message.trim().is_empty() { "BioDSH 快照".to_string() } else { message.to_string() };
    // 没有 user.name 时用本地默认身份，避免首次提交失败
    let _ = git(p, &["-c", "user.name=BioDSH", "-c", "user.email=biodsh@local", "commit", "-q", "-m", &msg]);
    Ok(status(path))
}
