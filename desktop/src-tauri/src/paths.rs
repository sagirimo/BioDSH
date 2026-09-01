//! 目录约定：一切状态放在 ~/BioDSH（可用 BIODSH_HOME 覆盖）；资源在应用 resources 目录。
use serde::Serialize;
use std::path::{Path, PathBuf};
use tauri::{AppHandle, Manager};

#[derive(Clone, Serialize)]
pub struct AppPaths {
    pub root: PathBuf,
    #[serde(rename = "dshHome")]
    pub dsh_home: PathBuf,
    pub bioenv: PathBuf,
    pub workspace: PathBuf,
    pub skills: PathBuf,
    pub logs: PathBuf,
}

impl AppPaths {
    pub fn detect(app: &AppHandle) -> AppPaths {
        let root = strip_unc(std::env::var_os("BIODSH_HOME")
            .map(PathBuf::from)
            .unwrap_or_else(|| app.path().home_dir().expect("home dir").join("BioDSH")));
        let dsh_home = root.join("dsh-home");
        let p = AppPaths {
            skills: dsh_home.join("skills"),
            bioenv: root.join("bioenv"),
            workspace: root.join("workspace"),
            logs: root.join("logs"),
            dsh_home,
            root,
        };
        for d in [&p.root, &p.dsh_home, &p.bioenv, &p.workspace, &p.skills, &p.logs] {
            let _ = std::fs::create_dir_all(d);
        }
        p
    }
}

/// 打包后的资源目录（resources/），开发时退回到项目 desktop/resources 与 dsh-runtime。
pub fn resource_root(app: &AppHandle) -> PathBuf {
    strip_unc(app.path().resource_dir().unwrap_or_else(|_| PathBuf::from(".")))
}

/// Windows 上 Tauri 返回 `\\?\C:\...` 形式的长路径；Node/uv 不认这个前缀，去掉。
pub fn strip_unc(p: PathBuf) -> PathBuf {
    let s = p.to_string_lossy();
    if let Some(rest) = s.strip_prefix(r"\\?\") { PathBuf::from(rest) } else { p }
}

fn dev_root() -> PathBuf {
    // src-tauri 的父目录 = desktop/
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).parent().map(Path::to_path_buf).unwrap_or_default()
}

fn platform_dir() -> &'static str {
    match (std::env::consts::OS, std::env::consts::ARCH) {
        ("windows", _) => "win32-x64",
        ("macos", "aarch64") => "darwin-arm64",
        ("macos", _) => "darwin-x64",
        _ => "linux-x64",
    }
}

pub fn resource(app: &AppHandle, rel: &str) -> PathBuf {
    let packaged = resource_root(app).join(rel);
    if packaged.exists() {
        return packaged;
    }
    match rel {
        "node" => dev_root().join("resources").join("node").join(platform_dir()),
        "bin" => dev_root().join("resources").join("bin").join(platform_dir()),
        "dsh/node_modules" => dev_root().join("dsh-runtime").join("node_modules"),
        other => dev_root().join("resources").join(other),
    }
}

pub fn node_binary(app: &AppHandle) -> PathBuf {
    let base = resource(app, "node");
    if cfg!(windows) { base.join("node.exe") } else { base.join("bin").join("node") }
}

pub fn uv_binary(app: &AppHandle) -> PathBuf {
    resource(app, "bin").join(if cfg!(windows) { "uv.exe" } else { "uv" })
}

pub fn dsh_bin(app: &AppHandle) -> PathBuf {
    resource(app, "dsh/node_modules").join("@deepseek-ai").join("dsh").join("lib").join("bin.js")
}

pub fn venv_python(bioenv: &Path) -> PathBuf {
    if cfg!(windows) { bioenv.join(".venv").join("Scripts").join("python.exe") } else { bioenv.join(".venv").join("bin").join("python") }
}

pub fn venv_bin_dir(bioenv: &Path) -> PathBuf {
    if cfg!(windows) { bioenv.join(".venv").join("Scripts") } else { bioenv.join(".venv").join("bin") }
}
