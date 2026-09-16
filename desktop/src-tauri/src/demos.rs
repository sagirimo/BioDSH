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
/// 同时清掉之前版本遗留的"空壳"范例会话(只有 session/end-seed、id 不在 demo.json 里的),避免出现空对话。
/// 用可升级的 marker(.demo-content-v3)控制:老机器(有 .demo-cleaned-v2 无 v3)会自愈一次,把空对话换成真对话。
pub fn restore_demo_sessions(res_root: &Path, paths: &AppPaths, node: &Path, script: &Path) -> usize {
    // v4:除了导入当前范例,还要清掉升级前遗留的旧范例(改版换了名字/删掉的,如 01-scrna-analysis、
    // 电脑控制与 Zotero 等)——否则新旧范例在侧栏并存、还带空对话。marker 升级即对老机器自愈一次。
    let marker = paths.dsh_home.join(".demo-content-v4");
    if marker.exists() { return 0; }
    // 清掉旧的一次性 marker(不再使用),避免残留
    let _ = fs::remove_dir_all(paths.dsh_home.join(".demo-sessions"));
    let _ = fs::remove_file(paths.dsh_home.join(".demo-content-v3"));
    // 本版随包的范例 id 集合(res_root 下的子目录名);不在此集合里的 demos 工作区都要清掉。
    let shipped: std::collections::HashSet<String> = fs::read_dir(res_root).ok()
        .map(|rd| rd.flatten().filter(|e| e.path().is_dir()).map(|e| e.file_name().to_string_lossy().to_string()).collect())
        .unwrap_or_default();
    remove_unshipped_demos(paths, &shipped);
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
        let canonical: std::collections::HashSet<String> = list.iter().filter_map(|s| s["id"].as_str().map(String::from)).collect();
        // 先清掉这个范例项目下的"非规范"残留会话(空壳/旧 id):删目录 + 从 workspace.json 剔除。
        remove_stale_demo_sessions(paths, &key, &canonical);
        // 按列表倒序导入:侧栏按最近更新排序,最后导入的排最上面 → 第一段对话在最上面。
        for sess in list.iter().rev() {
            let (Some(sid), Some(src_cwd), Some(file)) = (sess["id"].as_str(), sess["sourceCwd"].as_str(), sess["file"].as_str()) else { continue };
            let src = e.path().join(file);
            if !src.exists() || !node.exists() || !script.exists() { continue; }
            let out = paths.dsh_home.join("sessions").join(&key).join(sid).join("session.jsonl.zstd");
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

/// 清掉不在本版随包范例集合(`shipped`)里的旧 demos 工作区:改版换名/删掉的范例(如 01-scrna-analysis、
/// 电脑控制与 Zotero)升级后仍残留在 workspace.json + 侧栏。只动 ~/BioDSH/demos 下、且不在 shipped 里的项目;
/// 删会话目录 + 从 workspace.json(workspaceIds/workspaces/archivedSessionIds)剔除 + 删标题 + 删磁盘目录。用户自己的项目不受影响。
fn remove_unshipped_demos(paths: &AppPaths, shipped: &std::collections::HashSet<String>) {
    let demos_root = crate::paths::strip_unc(paths.root.join("demos")).to_string_lossy().to_lowercase();
    let is_unshipped = |p: &str| -> bool {
        let pl = p.replace('/', "\\").to_lowercase();
        let rl = demos_root.replace('/', "\\");
        if let Some(rest) = pl.strip_prefix(&format!("{rl}\\")) {
            let name = rest.split('\\').next().unwrap_or("");
            !name.is_empty() && !shipped.contains(name)
        } else { false }
    };
    // 1) workspace.json:找出要删的工作区 id + 它们的会话 id,再删条目
    let wsj = paths.dsh_home.join("storages").join("workspace.json");
    let mut removed_paths: Vec<String> = Vec::new();
    if let Ok(t) = fs::read_to_string(&wsj) {
        if let Ok(mut doc) = serde_json::from_str::<serde_json::Value>(&t) {
            let mut rm_ids: Vec<String> = Vec::new();
            let mut rm_sess: std::collections::HashSet<String> = std::collections::HashSet::new();
            if let Some(tbl) = doc.pointer("/tables/workspaces").and_then(|x| x.as_object()) {
                for (id, w) in tbl {
                    let p = w.get("path").and_then(|x| x.as_str()).unwrap_or("");
                    if is_unshipped(p) {
                        rm_ids.push(id.clone());
                        removed_paths.push(p.to_string());
                        if let Some(a) = w.get("sessionIds").and_then(|x| x.as_array()) {
                            for s in a { if let Some(s) = s.as_str() { rm_sess.insert(s.to_string()); } }
                        }
                    }
                }
            }
            if !rm_ids.is_empty() {
                // 删会话目录 dsh-home/sessions/<project_key(path)>
                for p in &removed_paths { let d = paths.dsh_home.join("sessions").join(project_key(p)); if d.exists() { let _ = fs::remove_dir_all(&d); } }
                if let Some(tbl) = doc.pointer_mut("/tables/workspaces").and_then(|x| x.as_object_mut()) {
                    for id in &rm_ids { tbl.remove(id); }
                }
                if let Some(a) = doc.pointer_mut("/global/workspaceIds").and_then(|x| x.as_array_mut()) { a.retain(|i| i.as_str().map(|i| !rm_ids.contains(&i.to_string())).unwrap_or(true)); }
                if let Some(a) = doc.pointer_mut("/global/archivedSessionIds").and_then(|x| x.as_array_mut()) { a.retain(|s| s.as_str().map(|s| !rm_sess.contains(s)).unwrap_or(true)); }
                let _ = fs::write(&wsj, serde_json::to_string(&doc).unwrap_or(t));
            }
        }
    }
    // 2) 标题库:删掉这些路径的标题(直接读写 biodsh-project-titles.json,避免跨模块可见性)
    let tp = paths.dsh_home.join("storages").join("biodsh-project-titles.json");
    if let Ok(t) = fs::read_to_string(&tp) {
        if let Ok(mut m) = serde_json::from_str::<serde_json::Map<String, serde_json::Value>>(&t) {
            let before = m.len();
            m.retain(|k, _| !is_unshipped(k));
            if m.len() != before { let _ = fs::write(&tp, serde_json::to_string(&m).unwrap_or(t)); }
        }
    }
    // 3) 磁盘:删掉 ~/BioDSH/demos 下不在 shipped 里的目录(即使 workspace.json 里没登记)
    if let Ok(rd) = fs::read_dir(paths.root.join("demos")) {
        for e in rd.flatten() {
            let name = e.file_name().to_string_lossy().to_string();
            if e.path().is_dir() && !shipped.contains(&name) { let _ = fs::remove_dir_all(e.path()); }
        }
    }
}

/// 删除某范例项目(project_key)下 id 不在 `keep` 集合里的会话(空壳/旧预录残留):删会话目录 + 从
/// workspace.json 的 sessionIds/archivedSessionIds 里剔除。只碰这一个项目目录,不动用户自己的会话。
fn remove_stale_demo_sessions(paths: &AppPaths, key: &str, keep: &std::collections::HashSet<String>) {
    let proj_dir = paths.dsh_home.join("sessions").join(key);
    let mut stale: std::collections::HashSet<String> = std::collections::HashSet::new();
    if let Ok(rd) = fs::read_dir(&proj_dir) {
        for s in rd.flatten() {
            let sid = s.file_name().to_string_lossy().to_string();
            if sid.starts_with("session-") && !keep.contains(&sid) {
                let _ = fs::remove_dir_all(s.path());
                stale.insert(sid);
            }
        }
    }
    if stale.is_empty() { return; }
    let wsj = paths.dsh_home.join("storages").join("workspace.json");
    if let Ok(t) = fs::read_to_string(&wsj) {
        if let Ok(mut doc) = serde_json::from_str::<serde_json::Value>(&t) {
            let strip = |arr: &mut Vec<serde_json::Value>| arr.retain(|s| s.as_str().map(|s| !stale.contains(s)).unwrap_or(true));
            if let Some(tbl) = doc.pointer_mut("/tables/workspaces").and_then(|x| x.as_object_mut()) {
                for (_, w) in tbl.iter_mut() {
                    if let Some(a) = w.get_mut("sessionIds").and_then(|x| x.as_array_mut()) { strip(a); }
                }
            }
            if let Some(a) = doc.pointer_mut("/global/archivedSessionIds").and_then(|x| x.as_array_mut()) { strip(a); }
            let _ = fs::write(&wsj, serde_json::to_string(&doc).unwrap_or(t));
        }
    }
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
