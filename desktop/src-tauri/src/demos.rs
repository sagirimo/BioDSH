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
        // 0.2.6 起范例为现场运行式:只恢复数据 + 成品图表 + 可读对话记录(示范对话.md)并注册工作区,
        // 不再导入旧预录对话(那批在 dsh 0.1.2 下显示坏)。用户在分析页点推荐分析即可现场跑。
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

/// 恢复随包附带的范例对话:把 resources/demos/*/.session/*.jsonl.zstd 改写工作区路径后写进 dsh-home,
/// 并在 workspace.json 里把这些会话挂到对应范例项目下。这些是在 dsh 0.1.2 上真跑出来的记录(带步数/图),
/// 格式与用户真实会话一致,能正常渲染。必须在 dsh 启动前做(dsh 把 storages/*.json 读进内存,启动后改会被覆盖)。
/// 只导入、绝不删除:用户可能在范例项目里开过自己的对话、放过自己的文件(0.3.0 升级时曾因“清理旧范例”误删用户对话)。
/// 旧范例项目、残留会话一律原样保留,由用户自己在侧栏删除。
pub fn restore_demo_sessions(res_root: &Path, paths: &AppPaths, node: &Path, script: &Path) -> usize {
    let marker = paths.dsh_home.join(".demo-content-v4");
    if marker.exists() { return 0; }
    let _ = fs::remove_file(paths.dsh_home.join(".demo-content-v3"));
    let Ok(rd) = fs::read_dir(res_root) else { return 0 };
    let mut imported = 0;
    for e in rd.flatten().filter(|e| e.path().is_dir()) {
        let id = e.file_name().to_string_lossy().to_string();
        let meta: serde_json::Value = match fs::read_to_string(e.path().join("demo.json")).ok().and_then(|t| serde_json::from_str(&t).ok()) { Some(v) => v, None => continue };
        let list: Vec<serde_json::Value> = match meta.get("sessions").and_then(|v| v.as_array()) { Some(arr) => arr.clone(), None => meta.get("session").cloned().into_iter().collect() };
        let title = meta["title"].as_str().unwrap_or(&id).to_string();
        let dst = paths.root.join("demos").join(&id);
        // 确保范例数据/产出已就位(幂等:已存在的文件不覆盖),再挂对话——否则工作区路径指向空目录。
        let _ = copy_dir(&e.path(), &dst);
        let dst_cwd = crate::paths::strip_unc(dst).to_string_lossy().to_string();
        let key = project_key(&dst_cwd);
        // 按列表倒序导入:侧栏按最近更新排序,最后导入的排最上面 → 第一段对话在最上面。
        for sess in list.iter().rev() {
            let (Some(sid), Some(src_cwd), Some(file)) = (sess["id"].as_str(), sess["sourceCwd"].as_str(), sess["file"].as_str()) else { continue };
            let src = e.path().join(file);
            if !src.exists() || !node.exists() || !script.exists() { continue; }
            let out = paths.dsh_home.join("sessions").join(&key).join(sid).join("session.jsonl.zstd");
            // 已存在就不覆盖:用户可能在这段范例对话里接着聊过。
            if out.exists() { attach_session(paths, &dst_cwd, &title, sid); continue; }
            let _ = fs::create_dir_all(out.parent().unwrap());
            let mut cmd = std::process::Command::new(node);
            cmd.arg(script).arg(&src).arg(&out).arg(src_cwd).arg(&dst_cwd).env_remove("NODE_OPTIONS");
            #[cfg(windows)]
            { use std::os::windows::process::CommandExt; cmd.creation_flags(0x0800_0000); }
            let ok = cmd.output().map(|o| o.status.success()).unwrap_or(false);
            if !ok { let _ = fs::remove_file(&out); continue; }
            attach_session(paths, &dst_cwd, &title, sid);
            imported += 1;
        }
    }
    let _ = fs::write(&marker, "1");
    imported
}

/// 在 storages/workspace.json 里保证有该路径的工作区，并把会话挂进去（文件不存在就按 dsh 的 v2 格式新建）。
fn attach_session(paths: &AppPaths, cwd: &str, title: &str, sid: &str) {
    let f = paths.dsh_home.join("storages").join("workspace.json");
    let _ = fs::create_dir_all(f.parent().unwrap());
    // 关键：文件已存在但解析失败时，绝不用空文档覆盖它（否则会抹掉用户已有的全部会话注册）。
    // 只有文件确实不存在时才新建；存在却读/解析失败就放弃本次挂载，保住原数据。
    let mut doc: serde_json::Value = match fs::read_to_string(&f) {
        Ok(t) => match serde_json::from_str(&t) {
            Ok(v) => v,
            Err(e) => { eprintln!("[biodsh] workspace.json 解析失败，跳过挂载以免覆盖历史: {e}"); return; }
        },
        Err(_) => serde_json::json!({
            "unit": { "name": "workspace", "version": 2 },
            "global": { "initialized": true, "workspaceIds": [], "archivedSessionIds": [] },
            "tables": { "workspaces": {} }
        }),
    };
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
