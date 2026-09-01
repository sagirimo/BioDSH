//! 技能商店：目录在 resources/skills/catalog.json；安装 = 复制到 $DSH_HOME/skills/<id>。
use crate::paths::{resource, AppPaths};
use serde::Serialize;
use serde_json::Value;
use std::fs;
use std::path::Path;
use tauri::AppHandle;

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SkillStatus {
    pub id: String,
    pub state: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub installed_version: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
}

pub fn catalog(app: &AppHandle) -> Vec<Value> {
    let f = resource(app, "skills").join("catalog.json");
    fs::read_to_string(f).ok()
        .and_then(|t| serde_json::from_str::<Value>(&t).ok())
        .and_then(|v| v.get("skills").and_then(|s| s.as_array().cloned()))
        .unwrap_or_default()
}

fn find(app: &AppHandle, id: &str) -> Option<Value> {
    catalog(app).into_iter().find(|s| s.get("id").and_then(|x| x.as_str()) == Some(id))
}

pub fn statuses(app: &AppHandle, p: &AppPaths) -> Vec<SkillStatus> {
    catalog(app).iter().map(|s| {
        let id = s["id"].as_str().unwrap_or_default().to_string();
        let dir = p.skills.join(&id);
        if !dir.join("SKILL.md").exists() {
            return SkillStatus { id, state: "not_installed".into(), installed_version: None, error: None };
        }
        let installed = fs::read_to_string(dir.join(".biodsh-version")).ok().map(|v| v.trim().to_string());
        let latest = s["version"].as_str().unwrap_or_default();
        let state = match &installed { Some(v) if v != latest => "update_available", _ => "installed" };
        SkillStatus { id, state: state.into(), installed_version: installed, error: None }
    }).collect()
}

fn copy_dir(src: &Path, dst: &Path) -> std::io::Result<()> {
    fs::create_dir_all(dst)?;
    for e in fs::read_dir(src)? {
        let e = e?;
        let name = e.file_name();
        let n = name.to_string_lossy();
        if n == "__pycache__" || n.ends_with(".pyc") { continue; }
        let t = dst.join(&name);
        if e.file_type()?.is_dir() { copy_dir(&e.path(), &t)?; } else { fs::copy(e.path(), t)?; }
    }
    Ok(())
}

pub fn install(app: &AppHandle, p: &AppPaths, id: &str) -> SkillStatus {
    let Some(skill) = find(app, id) else {
        return SkillStatus { id: id.into(), state: "error".into(), installed_version: None, error: Some("目录中没有这个技能".into()) };
    };
    let bundle = skill["bundle"].as_str().unwrap_or("skills");
    let src = resource(app, bundle).join(id);
    let dst = p.skills.join(id);
    let _ = fs::remove_dir_all(&dst);
    if let Err(e) = copy_dir(&src, &dst) {
        return SkillStatus { id: id.into(), state: "error".into(), installed_version: None, error: Some(e.to_string()) };
    }
    let md = dst.join("SKILL.md");
    let dst_s = dst.to_string_lossy().replace('\\', "/");
    let note = if skill["tier"].as_str() == Some("community") {
        let repo = skill["origin"]["repo"].as_str().unwrap_or("a community repository");
        let lic = skill["origin"]["license"].as_str().unwrap_or("see repo license");
        format!("\n\n## Running in BioDSH Desktop\n\nThis skill was collected from {repo} ({lic}). The BioDSH Python environment (scanpy, anndata, pandas, …) is first on PATH, so `python` resolves to it; install any extra package the skill needs with `uv pip install <pkg>` (uv is on PATH) or `python -m pip install <pkg>`. Scripts referenced by this skill live in `{dst_s}`. Explain results to the user in plain language.\n")
    } else {
        let outputs: Vec<String> = skill["outputs"].as_array().map(|a| a.iter().filter_map(|x| x.as_str().map(String::from)).collect()).unwrap_or_default();
{
        let script = skill["entry"]["script"].as_str().unwrap_or("run.py");
        if script == "run.py" {
            format!("\n\n## Running in BioDSH Desktop\n\nThe BioDSH Python environment (scanpy, anndata, …) is already first on PATH; `python` resolves to it. Run this skill's script directly:\n\n```bash\npython \"{dst_s}/run.py\" --input <input file> --outdir <output directory> --seed 0\n```\n\nWrite outputs into a fresh directory under the current workspace, then summarize the generated files ({}) for the user in plain language.\n", outputs.join(", "))
        } else {
            format!("\n\n## Running in BioDSH Desktop\n\nThis skill is installed at `{dst_s}`; its script is `{dst_s}/{script}` (run it with `python`, which resolves to the BioDSH analysis environment — see the command lines above). Write any outputs into a new subfolder of the current workspace and report their paths to the user in plain language.\n")
        }
    }
    };
    if let Ok(t) = fs::read_to_string(&md) { let _ = fs::write(&md, t.trim_end().to_string() + &note); }
    let version = skill["version"].as_str().unwrap_or("1.0.0").to_string();
    let _ = fs::write(dst.join(".biodsh-version"), format!("{version}\n"));
    SkillStatus { id: id.into(), state: "installed".into(), installed_version: Some(version), error: None }
}

pub fn uninstall(p: &AppPaths, id: &str) -> SkillStatus {
    let _ = fs::remove_dir_all(p.skills.join(id));
    SkillStatus { id: id.into(), state: "not_installed".into(), installed_version: None, error: None }
}

pub fn readme(app: &AppHandle, id: &str) -> String {
    let bundle = find(app, id).and_then(|s| s["bundle"].as_str().map(String::from)).unwrap_or("skills".into());
    let f = resource(app, &bundle).join(id).join("SKILL.md");
    let t = fs::read_to_string(f).unwrap_or_default();
    // 去掉 frontmatter
    if let Some(rest) = t.strip_prefix("---") {
        if let Some(i) = rest.find("\n---") { return rest[i + 4..].trim_start().to_string(); }
    }
    t
}

/// 官方技能开箱即装：每个应用版本首次启动时把 catalog 里 tier=official 的技能装进 skills 目录（已装的按版本刷新）。
/// 社区技能不预装：dsh 会把每个已装技能的名字和说明塞进每次请求的上下文，2,000 多个一起装既慢又贵，模型也挑不准。
pub fn seed_official(app: &AppHandle, p: &AppPaths) -> usize {
    let version = app.package_info().version.to_string();
    let stamp = p.root.join(".official-skills-seeded");
    if fs::read_to_string(&stamp).map(|v| v.trim() == version).unwrap_or(false) { return 0; }
    let mut n = 0;
    for sk in catalog(app) {
        if sk["tier"].as_str() != Some("official") { continue; }
        let Some(id) = sk["id"].as_str() else { continue };
        let installed = fs::read_to_string(p.skills.join(id).join(".biodsh-version")).ok().map(|v| v.trim().to_string());
        let want = sk["version"].as_str().unwrap_or("0").to_string();
        if installed.as_deref() == Some(want.as_str()) { continue; }
        let _ = fs::create_dir_all(&p.skills);
        install(app, p, id);
        n += 1;
    }
    let _ = fs::write(&stamp, version);
    n
}
