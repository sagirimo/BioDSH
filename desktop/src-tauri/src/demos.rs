//! 示范项目：随软件附带的 4 个真实项目（数据 + 真实对话记录 + 产出），首次启动复制到 ~/BioDSH/demos 并注册为工作区。
use crate::paths::AppPaths;
use serde::Serialize;
use std::fs;
use std::path::Path;

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Demo { pub id: String, pub title: String, pub path: String, pub registered: bool }

fn copy_dir(src: &Path, dst: &Path) -> std::io::Result<()> {
    fs::create_dir_all(dst)?;
    for e in fs::read_dir(src)? {
        let e = e?;
        let t = dst.join(e.file_name());
        if e.file_type()?.is_dir() { copy_dir(&e.path(), &t)?; } else if !t.exists() { fs::copy(e.path(), &t)?; }
    }
    Ok(())
}

/// 复制资源里的 demos/* 到 ~/BioDSH/demos/*（已存在的文件不覆盖，用户改过的东西留着），并在 dsh 里注册为工作区。
pub fn seed(res_root: &Path, paths: &AppPaths, dsh_url: Option<&str>, call: &dyn Fn(&str, &str, serde_json::Value) -> Result<serde_json::Value, String>) -> Vec<Demo> {
    let mut out = Vec::new();
    let Ok(rd) = fs::read_dir(res_root) else { return out };
    let mut entries: Vec<_> = rd.flatten().filter(|e| e.path().is_dir()).collect();
    entries.sort_by_key(|e| e.file_name());
    for e in entries {
        let id = e.file_name().to_string_lossy().to_string();
        let meta: serde_json::Value = fs::read_to_string(e.path().join("demo.json")).ok().and_then(|t| serde_json::from_str(&t).ok()).unwrap_or_default();
        let title = meta.get("title").and_then(|x| x.as_str()).unwrap_or(&id).to_string();
        let dst = paths.root.join("demos").join(&id);
        let _ = copy_dir(&e.path(), &dst);
        let mut registered = false;
        if let Some(u) = dsh_url {
            let p = dst.to_string_lossy().to_string();
            if let Ok(v) = call(u, "workspace.create", serde_json::json!({ "path": p })) {
                registered = true;
                if v.get("created").and_then(|x| x.as_bool()) == Some(true) {
                    if let Some(wid) = v.get("workspace").and_then(|w| w.get("workspaceId")).and_then(|x| x.as_str()) {
                        let _ = call(u, "workspace.rename", serde_json::json!({ "workspaceId": wid, "title": title.clone() }));
                    }
                }
            }
        }
        // 附带的对话：把标题也告诉 dsh（日志里虽有标题事件，但列表投影要等打开才算；rename 立刻生效）
        if let Some(u) = dsh_url {
            if let Some(list) = meta.get("sessions").and_then(|v| v.as_array()) {
                for sess in list.iter().rev() {
                    if let (Some(sid), Some(t)) = (sess["id"].as_str(), sess["title"].as_str()) {
                        let _ = call(u, "session.rename", serde_json::json!({ "sessionId": sid, "title": t }));
                    }
                }
            }
        }
        out.push(Demo { id, title, path: dst.to_string_lossy().into(), registered });
    }
    out
}

// ---------------------------------------------------------------------------
// 示范对话导入：把随包附带的会话日志放进 dsh-home，并在工作区登记表里挂到对应项目下。
// 必须在 dsh 启动前做（dsh 把 storages/*.json 读进内存，运行时改文件会被覆盖）。
// ---------------------------------------------------------------------------

/// dsh-session-persistence-jsonl 的 projectKey：cwd → sessions/ 下的目录名。
pub fn project_key(cwd: &str) -> String {
    let mut readable = String::new();
    let mut sep_run = false;
    for ch in cwd.chars() {
        if ch == '/' || ch == '\\' || ch == ':' {
            if !sep_run { readable.push('-'); }
            sep_run = true;
        } else if ch != '~' && (ch.is_ascii_alphanumeric() || ch == '.' || ch == '_' || ch == '-') {
            readable.push(ch);
            sep_run = false;
        } else {
            readable.push_str(&format!("~{:04X}", ch as u32));
            sep_run = false;
        }
    }
    let trimmed = readable.trim_start_matches('-');
    let body: String = if trimmed.is_empty() { "root".into() } else { trimmed.chars().take(251).collect() };
    format!("--{body}--")
}

fn iso_now() -> String {
    let secs = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0) as i64;
    let (days, rem) = (secs.div_euclid(86400), secs.rem_euclid(86400));
    // civil-from-days (Howard Hinnant)
    let z = days + 719468; let era = z.div_euclid(146097); let doe = z - era * 146097;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365; let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100); let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1; let m = if mp < 10 { mp + 3 } else { mp - 9 }; let y = if m <= 2 { y + 1 } else { y };
    format!("{y:04}-{m:02}-{d:02}T{:02}:{:02}:{:02}.000Z", rem / 3600, (rem % 3600) / 60, rem % 60)
}

/// 返回导入了几个会话。`node` 是自带的 Node，`script` 是 resources/scripts/import-session.mjs。
pub fn import_sessions(res_root: &Path, paths: &AppPaths, node: &Path, script: &Path) -> usize {
    let Ok(rd) = fs::read_dir(res_root) else { return 0 };
    let marker_dir = paths.dsh_home.join(".demo-sessions");
    let _ = fs::create_dir_all(&marker_dir);
    let mut imported = 0;
    for e in rd.flatten().filter(|e| e.path().is_dir()) {
        let id = e.file_name().to_string_lossy().to_string();
        let meta: serde_json::Value = match fs::read_to_string(e.path().join("demo.json")).ok().and_then(|t| serde_json::from_str(&t).ok()) { Some(v) => v, None => continue };
        // demo.json 里 `sessions: [{id, sourceCwd, file}]`（多段短对话），兼容旧的单个 `session`
        let list: Vec<serde_json::Value> = match meta.get("sessions").and_then(|v| v.as_array()) { Some(arr) => arr.clone(), None => meta.get("session").cloned().into_iter().collect() };
        let title = meta["title"].as_str().unwrap_or(&id).to_string();
        let dst_cwd = crate::paths::strip_unc(paths.root.join("demos").join(&id)).to_string_lossy().to_string();
        // 按列表倒序导入：侧栏按最近更新排序，最后导入的排最上面 → 第一段对话在最上面
        for sess in list.iter().rev() {
            let (Some(sid), Some(src_cwd), Some(file)) = (sess["id"].as_str(), sess["sourceCwd"].as_str(), sess["file"].as_str()) else { continue };
            if marker_dir.join(sid).exists() { continue; }
            let src = e.path().join(file);
            if !src.exists() || !node.exists() || !script.exists() { continue; }
            let dst = paths.dsh_home.join("sessions").join(project_key(&dst_cwd)).join(sid).join("session.jsonl.zstd");
            let _ = fs::create_dir_all(dst.parent().unwrap());
            let mut cmd = std::process::Command::new(node);
            cmd.arg(script).arg(&src).arg(&dst).arg(src_cwd).arg(&dst_cwd).env_remove("NODE_OPTIONS");
            #[cfg(windows)]
            { use std::os::windows::process::CommandExt; cmd.creation_flags(0x0800_0000); }
            let ok = cmd.output().map(|o| o.status.success()).unwrap_or(false);
            if !ok { let _ = fs::remove_file(&dst); continue; }
            attach_session(paths, &dst_cwd, &title, sid);
            let _ = fs::write(marker_dir.join(sid), &dst_cwd);
            imported += 1;
        }
    }
    imported
}

/// 在 storages/workspace.json 里保证有该路径的工作区，并把会话挂进去（文件不存在就按 dsh 的 v2 格式新建）。
fn attach_session(paths: &AppPaths, cwd: &str, title: &str, sid: &str) {
    let f = paths.dsh_home.join("storages").join("workspace.json");
    let _ = fs::create_dir_all(f.parent().unwrap());
    let mut doc: serde_json::Value = fs::read_to_string(&f).ok().and_then(|t| serde_json::from_str(&t).ok()).unwrap_or_else(|| serde_json::json!({
        "unit": { "name": "workspace", "version": 2 },
        "global": { "initialized": true, "workspaceIds": [], "archivedSessionIds": [] },
        "tables": { "workspaces": {} }
    }));
    let now = iso_now();
    let norm = |p: &str| p.replace('/', "\\").trim_end_matches('\\').to_lowercase();
    let existing = doc["tables"]["workspaces"].as_object().and_then(|m| m.iter().find(|(_, w)| w["path"].as_str().map(|p| norm(p) == norm(cwd)).unwrap_or(false)).map(|(k, _)| k.clone()));
    let wid = existing.unwrap_or_else(|| {
        let id = uuid::Uuid::new_v4().to_string();
        doc["tables"]["workspaces"][&id] = serde_json::json!({ "path": cwd, "title": title, "sessionIds": [], "createdAt": now, "updatedAt": now });
        if let Some(arr) = doc["global"]["workspaceIds"].as_array_mut() { arr.push(serde_json::Value::String(id.clone())); }
        id
    });
    let w = &mut doc["tables"]["workspaces"][&wid];
    if !w["sessionIds"].is_array() { w["sessionIds"] = serde_json::json!([]); }
    let has = w["sessionIds"].as_array().map(|a| a.iter().any(|x| x.as_str() == Some(sid))).unwrap_or(false);
    if !has { w["sessionIds"].as_array_mut().unwrap().push(serde_json::Value::String(sid.into())); w["updatedAt"] = serde_json::Value::String(now); }
    let _ = fs::write(&f, serde_json::to_string(&doc).unwrap_or_default());
}

#[cfg(test)]
mod tests {
    #[test]
    fn project_key_matches_dsh() {
        assert_eq!(super::project_key(r"C:\Users\MOLIEX-DESKTOP\BioDSH\demos\01-scrna-analysis"), "--C-Users-MOLIEX-DESKTOP-BioDSH-demos-01-scrna-analysis--");
        assert_eq!(super::project_key("/home/u/项目"), "--home-u-~9879~76EE--");
    }
}
