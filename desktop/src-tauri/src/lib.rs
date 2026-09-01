//! BioDSH Desktop（Tauri 版）主进程：一个无边框窗口里放两个 WebView —— "ui"（我们的 React 壳子）
//! 和 "dsh"（dsh web 原版界面，作为子视图贴在对话页的内容区）。
mod dsh;
mod files_server;
mod refdata;
mod demos;
mod files;
mod git;
mod migrate;
mod paths;
mod pyenv;
mod settings;
mod skills;

use dsh::DshManager;
use paths::AppPaths;
use pyenv::PyEnvManager;
use serde::Deserialize;
use settings::{read_credential, write_credential, AppSettings, CredentialStatus};
use std::sync::{Arc, Mutex};
use tauri::{AppHandle, Emitter, LogicalPosition, LogicalSize, Manager, State, WebviewUrl, Window};
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_opener::OpenerExt;

#[derive(Clone, Copy, Deserialize, Default)]
pub struct Rect { x: f64, y: f64, width: f64, height: f64 }

pub struct AppState {
    paths: AppPaths,
    settings: Mutex<AppSettings>,
    dsh: Arc<DshManager>,
    pyenv: Arc<PyEnvManager>,
    dsh_bounds: Mutex<(Rect, bool)>,
    files: Option<Arc<files_server::FilesServer>>,
}

const DSH_INIT_SCRIPT: &str = r#"(() => {
  const css = `    [class*="_sidebarCol"] { visibility: hidden !important; overflow: hidden !important; min-width: 0 !important; }
    [class*="_handle"][data-side="left"] { display: none !important; }
    [class*="_headline"], [class*="_heroGlow"] { display: none !important; }

    [data-biodsh-hidden="1"] { display: none !important; }
    .biodsh-sum { margin: 6px 0 10px; display: flex; align-items: center; gap: 8px; padding: 6px 10px; border-radius: 10px; background: rgba(120,120,128,.09); color: #6e6e73; font-size: 12.5px; cursor: pointer; user-select: none; line-height: 1.4; }
    .biodsh-sum:hover { background: rgba(120,120,128,.16); }
    .biodsh-sum .biodsh-chev { display: inline-block; font-size: 10px; transition: transform .15s; opacity: .8; }
    .biodsh-sum[data-open="1"] .biodsh-chev { transform: rotate(90deg); }
    .biodsh-sum .biodsh-n { margin-left: auto; opacity: .7; font-variant-numeric: tabular-nums; }
    .biodsh-sum[data-live="1"] .biodsh-txt { font-weight: 600; background: linear-gradient(90deg, #6e6e73 0%, #1d1d1f 35%, #b8b8bd 50%, #1d1d1f 65%, #6e6e73 100%); background-size: 200% 100%; -webkit-background-clip: text; background-clip: text; color: transparent; animation: biodsh-shimmer 1.6s linear infinite; }
    body[data-ds-dark-theme] .biodsh-sum { background: rgba(255,255,255,.07); color: #98989d; }
    body[data-ds-dark-theme] .biodsh-sum[data-live="1"] .biodsh-txt { background: linear-gradient(90deg, #8e8e93 0%, #f5f5f7 35%, #5a5a5f 50%, #f5f5f7 65%, #8e8e93 100%); background-size: 200% 100%; -webkit-background-clip: text; background-clip: text; }
    @keyframes biodsh-shimmer { from { background-position: 200% 0 } to { background-position: -200% 0 } }
    /* 展开后的中间步骤：缩进一点，和正文区分 */
    [data-biodsh-mid="1"] { margin-left: 10px !important; border-left: 2px solid rgba(120,120,128,.18); padding-left: 8px; }
    /* 最终回答里的思考行：收起时隐藏 */
    [data-biodsh-final="1"][data-biodsh-open="0"] [data-variant="think"] { display: none !important; }
    /* 正文里提到的图片文件 → 自动缩略图 */
    .biodsh-fig { display: block; max-width: min(100%, 720px); margin: 8px 0 12px; border-radius: 10px; border: 1px solid rgba(120,120,128,.18); cursor: zoom-in; background: #fff; }
    .biodsh-fig[data-zoom="1"] { max-width: 100%; cursor: zoom-out; }
    /* dsh 自己的运行状态行也用跑马灯 */
    [class*="_turnStatus"] { display: none !important; }
  `;
  const apply = () => {
    const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);
    const fix = () => { const f = document.querySelector('[class*="_frame"]'); if (!f) return; const v = f.style.gridTemplateColumns; if (v && !v.startsWith('0px')) f.style.gridTemplateColumns = v.replace(/^\S+/, '0px'); };
    const mo = new MutationObserver(fix);
    const start = () => { const f = document.querySelector('[class*="_frame"]'); if (!f) { setTimeout(start, 200); return; } mo.observe(f, { attributes: true, attributeFilter: ['style'] }); fix(); };
    start();
    // ---- 收纳中间过程：每一轮里的上下文注入 / 思考 / 工具调用折成一行，点开才逐级展开；最终回答保持可见
  const KIND = (el) => el.getAttribute('data-chat-flow-kind') || '';
  const open = new Set(); // 展开的组（以该轮 user 的 flow-key 记）
  const titleOf = (el) => {
    const t = el.querySelector('[class*="_title"]'); const s = el.querySelector('[class*="_summary"]');
    const a = (t?.textContent || '').trim(), b = (s?.textContent || '').trim();
    return (b || a).slice(0, 60);
  };
  const isThink = (el) => !!el.querySelector('[data-variant="think"]');
  const hasMd = (el) => !!el.querySelector('[class*="_markdown_"]');
  const regroup = () => {
    const col = document.querySelector('[class*="_column"]'); if (!col) return;
    const items = Array.from(col.children).filter((c) => c.hasAttribute('data-chat-flow-kind'));
    const running = !!document.querySelector('[data-streaming="true"], [data-state="running"]');
    let turnKey = null, run = [];
    const flush = (ended, i) => {
      if (!turnKey) return;
      let final = null;
      if (ended && run.length && KIND(run[run.length - 1]) === 'assistant-step' && hasMd(run[run.length - 1])) final = run.pop();
      const mid = run;
      const anchor = final || (mid.length ? mid[mid.length - 1].nextElementSibling : null);
      // 清理旧的摘要（同一轮）
      const isOpen = open.has(turnKey);
      let sum = col.querySelector(`.biodsh-sum[data-turn="${CSS.escape(turnKey)}"]`);
      if (mid.length === 0) { if (sum) sum.remove(); }
      else {
        if (!sum) {
          const key = turnKey; // 必须固定住：turnKey 是循环变量，闭包里直接用会拿到最后一轮的值（之前点不开的原因）
          sum = document.createElement('div'); sum.className = 'biodsh-sum'; sum.setAttribute('data-turn', key);
          sum.innerHTML = '<span class="biodsh-chev">▶</span><span class="biodsh-txt"></span><span class="biodsh-n"></span>';
          sum.addEventListener('click', (ev) => { ev.stopPropagation(); if (open.has(key)) open.delete(key); else open.add(key); regroup(); });
        }
        if (sum.nextElementSibling !== mid[0]) col.insertBefore(sum, mid[0]);
        const thinks = mid.filter((e) => KIND(e) === 'assistant-step').length;
        const tools = mid.filter((e) => KIND(e) === 'tool-call').length;
        const live = !ended && running;
        sum.setAttribute('data-open', isOpen ? '1' : '0'); sum.setAttribute('data-live', live ? '1' : '0');
        const last = mid[mid.length - 1];
        const lastTitle = KIND(last) === 'tool-call' ? titleOf(last) : '思考';
        sum.querySelector('.biodsh-txt').textContent = live ? `BioDSH 正在：${lastTitle}…` : `BioDSH 完成了 ${mid.length} 步（思考 ${thinks} · 操作 ${tools}）· 点开查看过程`;
        sum.querySelector('.biodsh-n').textContent = live ? `${mid.length} 步` : '';
        for (const e of mid) { e.setAttribute('data-biodsh-hidden', isOpen ? '0' : '1'); e.setAttribute('data-biodsh-mid', '1'); }
      }
      if (final) { final.setAttribute('data-biodsh-final', '1'); final.setAttribute('data-biodsh-open', isOpen ? '1' : '0'); final.removeAttribute('data-biodsh-hidden'); final.removeAttribute('data-biodsh-mid'); }
    };
    for (let i = 0; i < items.length; i++) {
      const el = items[i], k = KIND(el);
      if (k === 'user') { flush(true, i); turnKey = el.getAttribute('data-chat-flow-key') || String(i); run = []; el.removeAttribute('data-biodsh-hidden'); continue; }
      if (k === 'turn-tail') { flush(true, i); turnKey = null; run = []; continue; }
      if (k === 'context' || k === 'assistant-step' || k === 'tool-call') { if (turnKey) run.push(el); continue; }
    }
    flush(false, items.length); // 还在进行中的一轮：全部当中间过程，摘要显示“正在…”
  };
  // ---- 正文里提到的图片文件（`outputs/x.png`、C:\...\y.jpg）→ 自动插入缩略图（智能体按人设会自己用 ![]() 内嵌；这是兜底）
  const IMG_RE = /^[\w./\\:\-()（）\u4e00-\u9fa5 ]+\.(png|jpe?g|gif|webp|svg)$/i;
  const cwdOf = () => {
    const ctx = window.__biodsh || {}; const ws = ctx.ws || {};
    const crumb = document.querySelector('[class*="_crumbCurrent"]');
    const title = (crumb?.textContent || '').trim();
    return ws[title] || '';
  };
  const toUrl = (p) => {
    const ctx = window.__biodsh || {}; if (!ctx.files) return null;
    let abs = p.replace(/\\/g, '/');
    if (!/^[A-Za-z]:\//.test(abs) && !abs.startsWith('/')) { const cwd = cwdOf(); if (cwd) { abs = cwd.replace(/\\/g, '/').replace(/\/$/, '') + '/' + abs.replace(/^\.\//, ''); } else { abs = abs.split('/').pop(); } }  // 无 cwd 就只发文件名，交给服务端在工作区里搜
    return ctx.files + '/' + encodeURIComponent(abs).replace(/%2F/g, '/').replace(/%3A/g, ':');
  };
  const decorate = () => {
    document.querySelectorAll('[data-biodsh-final="1"] [class*="_markdown_"] code, [data-biodsh-final="1"] [class*="_markdown_"] a').forEach((el) => {
      if (el.dataset.biodshImg) return; el.dataset.biodshImg = '1';
      const t = (el.textContent || '').trim(); if (!IMG_RE.test(t) || t.length > 200) return;
      const url = toUrl(t); if (!url) return;
      const md = el.closest('[class*="_markdown_"]'); if (!md) return;
      if (md.querySelector(`img[data-src-key="${CSS.escape(t)}"]`)) return;
      if (md.querySelector(`img[src="${CSS.escape(url)}"]`)) return; // 智能体已经自己内嵌了
      const block = el.closest('p, li, td, th, h1, h2, h3, h4, blockquote') || el;
      const holder = block.closest('table') || block;
      const img = document.createElement('img'); img.className = 'biodsh-fig'; img.loading = 'lazy'; img.src = url; img.alt = t; img.setAttribute('data-src-key', t);
      img.addEventListener('error', () => img.remove());
      img.addEventListener('click', () => img.setAttribute('data-zoom', img.getAttribute('data-zoom') === '1' ? '0' : '1'));
      holder.insertAdjacentElement('afterend', img);
    });
  };
  let scheduled = false;
  const schedule = () => { if (scheduled) return; scheduled = true; requestAnimationFrame(() => { scheduled = false; try { regroup(); decorate(); } catch (e) { console.warn('biodsh collapse', e); } }); };
  new MutationObserver(schedule).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['data-state', 'data-streaming'] });
  schedule();
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', apply); else apply();
})();"#;

fn trace(paths: &AppPaths, line: &str) {
    use std::io::Write;
    if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(paths.logs.join("trace.log")) { let _ = writeln!(f, "{line}"); }
}

fn workspace_of(state: &AppState) -> String {
    let w = state.settings.lock().unwrap().workspace.clone();
    if w.is_empty() { state.paths.workspace.to_string_lossy().into() } else { w }
}

/// 把 dsh 子视图贴到壳子汇报的矩形上；不可见时隐藏。
fn layout_dsh(app: &AppHandle, state: &AppState) {
    let Some(view) = app.get_webview("dsh") else { return };
    let (r, visible) = *state.dsh_bounds.lock().unwrap();
    trace(&state.paths, &format!("layout_dsh visible={} rect=({},{},{},{}) pos={:?} size={:?}", visible, r.x, r.y, r.width, r.height, view.position().ok(), view.size().ok()));
    if visible && r.width > 0.0 {
        let _ = view.set_position(LogicalPosition::new(r.x, r.y));
        let _ = view.set_size(LogicalSize::new(r.width, r.height));
        let _ = view.show();
    } else {
        // Windows 上子视图 hide() 可能无效：同时把它挪出屏幕并缩为 1×1，确保不遮挡浮层
        let _ = view.hide();
        let _ = view.set_position(LogicalPosition::new(-20000.0, -20000.0));
        let _ = view.set_size(LogicalSize::new(1.0, 1.0));
    }
}

fn ensure_dsh_view(app: &AppHandle, state: &AppState, url: &str) {
    if std::env::var_os("BIODSH_NO_DSH_VIEW").is_some() { return; }
    if let Some(view) = app.get_webview("dsh") {
        let _ = view.navigate(url.parse().unwrap());
        layout_dsh(app, state);
        return;
    }
    let Some(window) = app.get_window("main") else { return };
    let opener = app.clone();
    let builder = tauri::webview::WebviewBuilder::new("dsh", WebviewUrl::External(url.parse().unwrap()))
        .initialization_script(DSH_INIT_SCRIPT)
        .on_navigation(move |u| {
            if u.host_str() == Some("127.0.0.1") || u.scheme() == "about" { return true; }
            let _ = opener.opener().open_url(u.to_string(), None::<&str>);
            false
        });
    let (r, _) = *state.dsh_bounds.lock().unwrap();
    if window.add_child(builder, LogicalPosition::new(r.x, r.y), LogicalSize::new(r.width.max(1.0), r.height.max(1.0))).is_ok() {
        layout_dsh(app, state);
    }
}

// ---------- 命令 ----------
#[tauri::command]
fn app_info(app: AppHandle, state: State<'_, AppState>) -> serde_json::Value {
    trace(&state.paths, "app_info called");
    serde_json::json!({ "version": app.package_info().version.to_string(), "dshVersion": dsh_version(&app), "platform": if cfg!(windows) { "win32" } else if cfg!(target_os = "macos") { "darwin" } else { "linux" }, "paths": state.paths, "dark": false, "runtime": "tauri" })
}
#[tauri::command]
fn settings_get(state: State<'_, AppState>) -> AppSettings { state.settings.lock().unwrap().clone() }
#[tauri::command]
fn settings_set(app: AppHandle, state: State<'_, AppState>, patch: serde_json::Value) -> AppSettings {
    let mut s = state.settings.lock().unwrap();
    if let Some(b) = patch.get("useChinaMirror").and_then(|x| x.as_bool()) { s.use_china_mirror = b; }
    if let Some(w) = patch.get("workspace").and_then(|x| x.as_str()) { s.workspace = w.into(); }
    if let Some(b) = patch.get("onboarded").and_then(|x| x.as_bool()) { s.onboarded = b; }
    for (k, setter) in [("mode", 0), ("offlineBaseUrl", 1), ("offlineModel", 2), ("offlineApiKey", 3), ("remoteDshUrl", 4)] {
        if let Some(v) = patch.get(k).and_then(|x| x.as_str()) {
            match setter { 0 => s.mode = v.into(), 1 => s.offline_base_url = v.into(), 2 => s.offline_model = v.into(), 3 => s.offline_api_key = v.into(), _ => s.remote_dsh_url = v.into() }
        }
    }
    for (k, setter) in [("imageBaseUrl", 0), ("imageModel", 1), ("imageApiKey", 2)] {
        if let Some(v) = patch.get(k).and_then(|x| x.as_str()) {
            match setter { 0 => s.image_base_url = v.trim().into(), 1 => s.image_model = v.trim().into(), _ => s.image_api_key = v.trim().into() }
        }
    }
    if let Some(arr) = patch.get("mcpServers") { if let Ok(list) = serde_json::from_value::<Vec<settings::McpServer>>(arr.clone()) { s.mcp_servers = list; } }
    if let Some(b) = patch.get("demosSeeded").and_then(|x| x.as_bool()) { s.demos_seeded = b; }
    let mut lang_changed = None;
    if let Some(l) = patch.get("language").and_then(|x| x.as_str()) { if s.language != l { lang_changed = Some(l.to_string()); } s.language = l.into(); }
    let mut theme_changed = None;
    if let Some(t) = patch.get("theme").and_then(|x| x.as_str()) { if s.theme != t { theme_changed = Some(t.to_string()); } s.theme = t.into(); }
    s.save(&state.paths);
    let out = s.clone();
    drop(s);
    if let Some(l) = lang_changed.as_deref() { dsh::set_locale(&state.paths, l); }
    if theme_changed.is_some() || lang_changed.is_some() {
        if let Some(t) = theme_changed.as_deref() { dsh::set_theme(&state.paths, t); }
        if let Some(v) = app.get_webview("dsh") { let _ = v.eval("location.reload()"); }
    }
    out
}
#[tauri::command]
fn credential_get(state: State<'_, AppState>) -> CredentialStatus { read_credential(&state.paths) }
#[tauri::command]
async fn credential_set(app: AppHandle, state: State<'_, AppState>, key: String) -> Result<CredentialStatus, String> {
    write_credential(&state.paths, &key);
    // 让新 key 立刻生效：重启 dsh（key 通过环境变量注入）
    if state.dsh.status.lock().unwrap().state != "stopped" { let _ = dsh_restart(app, state.clone()).await; }
    Ok(read_credential(&state.paths))
}

#[tauri::command]
async fn env_status(app: AppHandle, state: State<'_, AppState>) -> Result<pyenv::EnvStatus, String> {
    let (py, paths) = (Arc::clone(&state.pyenv), state.paths.clone());
    tauri::async_runtime::spawn_blocking(move || py.probe(&app, &paths)).await.map_err(|e| e.to_string())
}
#[tauri::command]
async fn env_install(app: AppHandle, state: State<'_, AppState>) -> Result<pyenv::EnvStatus, String> {
    let (py, paths, china) = (Arc::clone(&state.pyenv), state.paths.clone(), state.settings.lock().unwrap().use_china_mirror);
    tauri::async_runtime::spawn_blocking(move || py.install(&app, &paths, china)).await.map_err(|e| e.to_string())
}

#[tauri::command]
fn dsh_status(state: State<'_, AppState>) -> dsh::DshStatus { state.dsh.status.lock().unwrap().clone() }
#[tauri::command]
async fn dsh_start(app: AppHandle, state: State<'_, AppState>) -> Result<dsh::DshStatus, String> {
    let (d, paths, ws) = (Arc::clone(&state.dsh), state.paths.clone(), workspace_of(&state));
    let app2 = app.clone();
    let ws2 = ws.clone();
    let (offline, offline_key, remote) = {
        let st = state.settings.lock().unwrap();
        dsh::set_theme(&state.paths, &st.theme);
        dsh::set_locale(&state.paths, &st.language);
        let offline = st.mode == "offline";
        if offline && !st.offline_base_url.trim().is_empty() {
            dsh::set_llm_override(&state.paths, Some((st.offline_base_url.trim(), st.offline_model.trim())));
        } else {
            dsh::set_llm_override(&state.paths, None);
        }
        (offline, st.offline_api_key.clone(), st.remote_dsh_url.trim().to_string())
    };
    let (extra_env, mcp, seed_demos) = {
        let st = state.settings.lock().unwrap();
        let env = vec![
            ("BIODSH_FILES_URL".to_string(), state.files.as_ref().map(|f| f.base_url()).unwrap_or_default()),
            ("BIODSH_IMAGE_BASE_URL".to_string(), st.image_base_url.clone()),
            ("BIODSH_IMAGE_API_KEY".to_string(), st.image_api_key.clone()),
            ("BIODSH_IMAGE_MODEL".to_string(), st.image_model.clone()),
            ("BIODSH_REFDATA".to_string(), refdata::dir(&state.paths).to_string_lossy().to_string()),
        ];
        (env, st.mcp_servers.clone(), !st.demos_seeded)
    };
    // 离线模式 + 配置了远程服务器：不在本机启动，直接连服务器上的 dsh
    if offline && !remote.is_empty() {
        let mut s = state.dsh.status.lock().unwrap();
        s.state = "running".into();
        s.url = Some(remote.clone());
        s.log.push(format!("[remote] using {remote}"));
        drop(s);
        let st2 = state.inner();
        ensure_dsh_view(&app, st2, &remote);
        return Ok(state.dsh.status.lock().unwrap().clone());
    }
    let key = if offline { Some(offline_key) } else { None };
    // 示范对话：启动 dsh 之前把随包的会话日志导入并挂到示范项目下（每个会话只导一次）
    {
        let (p, res, node, script) = (state.paths.clone(), crate::paths::resource(&app, "demos"), crate::paths::node_binary(&app), crate::paths::resource(&app, "scripts").join("import-session.mjs"));
        let _ = tauri::async_runtime::spawn_blocking(move || demos::import_sessions(&res, &p, &node, &script)).await;
    }
    let st = tauri::async_runtime::spawn_blocking(move || d.start_with(&app2, &paths, &ws2, key, extra_env, &mcp)).await.map_err(|e| e.to_string())?;
    if st.state == "running" {
        if let Some(u) = &st.url {
            // 让默认工作区在 dsh 里注册（幂等：已存在则原样返回）
            let (u2, ws3) = (u.clone(), ws.clone());
            let _ = tauri::async_runtime::spawn_blocking(move || {
                if let Ok(v) = dsh_call(&u2, "workspace.create", serde_json::json!({ "path": ws3 })) {
                    if v.get("created").and_then(|x| x.as_bool()) == Some(true) {
                        if let Some(id) = v.get("workspace").and_then(|w| w.get("workspaceId")).and_then(|x| x.as_str()) {
                            let _ = dsh_call(&u2, "workspace.rename", serde_json::json!({ "workspaceId": id, "title": "我的分析" }));
                        }
                    }
                }
            }).await;
            // 把所有已注册工作区加入图片服务白名单
            if let Some(f) = state.files.clone() {
                let u5 = u.clone();
                let _ = tauri::async_runtime::spawn_blocking(move || {
                    if let Ok(v) = dsh_call(&u5, "workspace.list", serde_json::json!({})) {
                        for w in v.get("items").and_then(|x| x.as_array()).cloned().unwrap_or_default() {
                            if let Some(p) = w.get("path").and_then(|x| x.as_str()) { f.add_root(std::path::PathBuf::from(p)); }
                        }
                    }
                }).await;
            }
            // 首次启动：把示范项目复制到 ~/BioDSH/demos 并注册为工作区（只做一次；设置页可重新安装）
            if seed_demos {
                let (u4, paths4, res) = (u.clone(), state.paths.clone(), crate::paths::resource(&app, "demos"));
                let _ = tauri::async_runtime::spawn_blocking(move || demos::seed(&res, &paths4, Some(&u4), &dsh_call)).await;
                let mut s = state.settings.lock().unwrap(); s.demos_seeded = true; s.save(&state.paths);
            }
            let u = u.clone(); let st2 = state.inner(); ensure_dsh_view(&app, st2, &u);
        }
    }
    Ok(st)
}
/// 把「工作区标题 → 路径」和图片服务地址告诉 dsh 视图（对话里内嵌缩略图要靠它把相对路径拼成绝对路径）
#[tauri::command]
fn dsh_set_context(app: AppHandle, state: State<'_, AppState>, workspaces: serde_json::Value) {
    if let Some(v) = app.get_webview("dsh") {
        let files = state.files.as_ref().map(|f| f.base_url()).unwrap_or_default();
        if let Some(f) = state.files.as_ref() { for (_, p) in workspaces.as_object().cloned().unwrap_or_default() { if let Some(p) = p.as_str() { f.add_root(std::path::PathBuf::from(p)); } } }
        let js = format!("window.__biodsh = Object.assign(window.__biodsh || {{}}, {{ files: {}, ws: {} }});", serde_json::to_string(&files).unwrap_or_default(), workspaces);
        let _ = v.eval(&js);
    }
}
#[tauri::command]
fn refdata_list(state: State<'_, AppState>) -> Vec<refdata::PackStatus> { refdata::list(&state.paths) }
#[tauri::command]
async fn refdata_install(app: AppHandle, state: State<'_, AppState>, id: String) -> Result<refdata::PackStatus, String> {
    let paths = state.paths.clone();
    tauri::async_runtime::spawn_blocking(move || refdata::install(&app, &paths, &id)).await.map_err(|e| e.to_string())?
}
#[tauri::command]
fn refdata_remove(state: State<'_, AppState>, id: String) -> Vec<refdata::PackStatus> { refdata::remove(&state.paths, &id) }
/// 设置页「重新安装示范项目」：再复制一遍（不覆盖已有文件）并注册工作区。
#[tauri::command]
async fn demos_seed(app: AppHandle, state: State<'_, AppState>) -> Result<Vec<demos::Demo>, String> {
    let (paths, res) = (state.paths.clone(), crate::paths::resource(&app, "demos"));
    // 重置示范项目：清掉"对话已导入"标记，前端随后重启智能体，启动前会把附带的对话重新导入并挂回项目
    let _ = std::fs::remove_dir_all(paths.dsh_home.join(".demo-sessions"));
    let url = state.dsh.status.lock().unwrap().url.clone();
    let out = tauri::async_runtime::spawn_blocking(move || demos::seed(&res, &paths, url.as_deref(), &dsh_call)).await.map_err(|e| e.to_string())?;
    let mut s = state.settings.lock().unwrap(); s.demos_seeded = true; s.save(&state.paths);
    Ok(out)
}
#[tauri::command]
async fn dsh_restart(app: AppHandle, state: State<'_, AppState>) -> Result<dsh::DshStatus, String> {
    state.dsh.stop(&app);
    dsh_start(app, state).await
}
#[tauri::command]
fn dsh_reload(app: AppHandle) { if let Some(v) = app.get_webview("dsh") { let _ = v.eval("location.reload()"); } }
#[tauri::command]
fn dsh_bounds(app: AppHandle, state: State<'_, AppState>, rect: Rect, visible: bool) {
    trace(&state.paths, &format!("dsh_bounds x={} y={} w={} h={} visible={}", rect.x, rect.y, rect.width, rect.height, visible));
    *state.dsh_bounds.lock().unwrap() = (rect, visible);
    layout_dsh(&app, &state);
}

#[tauri::command]
fn skills_catalog(app: AppHandle) -> Vec<serde_json::Value> { skills::catalog(&app) }
#[tauri::command]
fn skills_statuses(app: AppHandle, state: State<'_, AppState>) -> Vec<skills::SkillStatus> { skills::statuses(&app, &state.paths) }
#[tauri::command]
fn skills_readme(app: AppHandle, id: String) -> String { skills::readme(&app, &id) }
#[tauri::command]
fn skills_install(app: AppHandle, state: State<'_, AppState>, id: String) -> skills::SkillStatus {
    let r = skills::install(&app, &state.paths, &id);
    let _ = app.emit("event", serde_json::json!({ "type": "skills", "statuses": skills::statuses(&app, &state.paths) }));
    r
}
#[tauri::command]
fn skills_uninstall(app: AppHandle, state: State<'_, AppState>, id: String) -> skills::SkillStatus {
    let r = skills::uninstall(&state.paths, &id);
    let _ = app.emit("event", serde_json::json!({ "type": "skills", "statuses": skills::statuses(&app, &state.paths) }));
    r
}

#[tauri::command]
fn client_log(state: State<'_, AppState>, line: String) {
    use std::io::Write;
    if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(state.paths.logs.join("ui.log")) { let _ = writeln!(f, "{line}"); }
}
/// DeepSeek 账户余额（GET https://api.deepseek.com/user/balance）
#[tauri::command]
async fn deepseek_balance(state: State<'_, AppState>) -> Result<serde_json::Value, String> {
    if state.settings.lock().unwrap().mode == "offline" { return Err("offline-mode".into()); }
    let Some(key) = settings::read_credential_value(&state.paths) else { return Err("no-key".into()) };
    tauri::async_runtime::spawn_blocking(move || {
        let resp = ureq::get("https://api.deepseek.com/user/balance").set("Authorization", &format!("Bearer {key}")).timeout(std::time::Duration::from_secs(15)).call().map_err(|e| e.to_string())?;
        resp.into_json::<serde_json::Value>().map_err(|e| e.to_string())
    }).await.map_err(|e| e.to_string())?
}
#[tauri::command]
async fn git_status(path: String) -> git::GitStatus { tauri::async_runtime::spawn_blocking(move || git::status(&path)).await.unwrap_or_default() }
#[tauri::command]
async fn git_init(path: String) -> Result<git::GitStatus, String> { tauri::async_runtime::spawn_blocking(move || git::init(&path)).await.map_err(|e| e.to_string())? }
#[tauri::command]
async fn git_commit(path: String, message: String) -> Result<git::GitStatus, String> { tauri::async_runtime::spawn_blocking(move || git::commit(&path, &message)).await.map_err(|e| e.to_string())? }
/// 调 dsh 的 HTTP RPC：POST /api/<method>，信封 {type:'client-request', rpcId, method, payload}
fn dsh_call(url: &str, method: &str, payload: serde_json::Value) -> Result<serde_json::Value, String> {
    let body = serde_json::json!({ "type": "client-request", "rpcId": uuid::Uuid::new_v4().to_string(), "method": method, "payload": payload });
    let resp = ureq::post(&format!("{}/api/{}", url.trim_end_matches('/'), method))
        .set("Content-Type", "application/json").timeout(std::time::Duration::from_secs(20))
        .send_json(body).map_err(|e| match e { ureq::Error::Status(c, r) => format!("HTTP {c}: {}", r.into_string().unwrap_or_default()), e => e.to_string() })?;
    let v: serde_json::Value = resp.into_json().map_err(|e| e.to_string())?;
    let result = v.get("result").cloned().unwrap_or(serde_json::Value::Null);
    if result.get("ok").and_then(|x| x.as_bool()) == Some(true) { Ok(result.get("value").cloned().unwrap_or(serde_json::Value::Null)) }
    else { Err(result.get("error").map(|e| e.to_string()).unwrap_or_else(|| "rpc failed".into())) }
}
fn dsh_url(state: &AppState) -> Result<String, String> { state.dsh.status.lock().unwrap().url.clone().ok_or_else(|| "dsh 未运行".into()) }

#[tauri::command]
async fn dsh_rpc(state: State<'_, AppState>, method: String, payload: serde_json::Value) -> Result<serde_json::Value, String> {
    let url = dsh_url(&state)?;
    tauri::async_runtime::spawn_blocking(move || dsh_call(&url, &method, payload)).await.map_err(|e| e.to_string())?
}
/// 切换内嵌视图到某个会话：dsh 没有 URL 路由，靠它自己记在 localStorage 的“当前会话”+ 刷新。
#[tauri::command]
fn dsh_open_session(app: AppHandle, session_id: String) {
    if let Some(v) = app.get_webview("dsh") {
        let js = format!("try {{ localStorage.setItem('dsh.sessions.current', JSON.stringify({{ sessionId: {} }})); }} catch (e) {{}} location.reload();", serde_json::to_string(&session_id).unwrap_or_default());
        let _ = v.eval(&js);
    }
}
#[tauri::command]
async fn dsh_new_session(app: AppHandle, state: State<'_, AppState>, workspace_id: String) -> Result<String, String> {
    let url = dsh_url(&state)?;
    let v = tauri::async_runtime::spawn_blocking(move || dsh_call(&url, "session.create", serde_json::json!({ "workspaceId": workspace_id }))).await.map_err(|e| e.to_string())??;
    let id = v.get("sessionId").and_then(|x| x.as_str()).ok_or("no sessionId")?.to_string();
    dsh_open_session(app, id.clone());
    Ok(id)
}
fn dsh_version(app: &AppHandle) -> String {
    let f = paths::resource(app, "dsh/node_modules").join("@deepseek-ai").join("dsh").join("package.json");
    std::fs::read_to_string(f).ok().and_then(|t| serde_json::from_str::<serde_json::Value>(&t).ok()).and_then(|v| v.get("version").and_then(|x| x.as_str()).map(String::from)).unwrap_or_else(|| "?".into())
}

/// 检查更新：dsh 内核最新版（npm registry）与本应用最新版（GitHub Releases，可选）
#[tauri::command]
async fn check_updates(app: AppHandle, state: State<'_, AppState>) -> Result<serde_json::Value, String> {
    if state.settings.lock().unwrap().mode == "offline" { return Err("offline-mode".into()); }
    let current = dsh_version(&app);
    let app_version = app.package_info().version.to_string();
    tauri::async_runtime::spawn_blocking(move || {
        let reg = ureq::get("https://registry.npmmirror.com/@deepseek-ai/dsh").timeout(std::time::Duration::from_secs(15)).call().map_err(|e| e.to_string())?;
        let v: serde_json::Value = reg.into_json().map_err(|e| e.to_string())?;
        let latest = v["dist-tags"]["latest"].as_str().unwrap_or("?").to_string();
        Ok(serde_json::json!({ "dsh": { "current": current, "latest": latest, "outdated": latest != "?" && latest != current }, "app": { "current": app_version } }))
    }).await.map_err(|e| e.to_string())?
}

/// 右键"问一下"：直接调 DeepSeek 聊天接口，非流式，回答简短。
#[tauri::command]
async fn assistant_ask(state: State<'_, AppState>, model: String, question: String, context: String) -> Result<String, String> {
    let (endpoint, key, model) = {
        let st = state.settings.lock().unwrap();
        if st.mode == "offline" {
            if st.offline_base_url.trim().is_empty() { return Err("离线模式还没配置模型接口，去「更多 → 运行模式」填一下".into()); }
            (format!("{}/chat/completions", st.offline_base_url.trim().trim_end_matches('/')), if st.offline_api_key.is_empty() { "local".into() } else { st.offline_api_key.clone() }, if st.offline_model.trim().is_empty() { model } else { st.offline_model.trim().to_string() })
        } else {
            let Some(key) = settings::read_credential_value(&state.paths) else { return Err("还没填 API Key，去「更多 → 模型 API Key」填一下".into()) };
            ("https://api.deepseek.com/chat/completions".to_string(), key, model)
        }
    };
    tauri::async_runtime::spawn_blocking(move || {
        let system = format!("你是 BioDSH 桌面软件的内置向导。用户是不懂生信和编程的医生/实验人员，请用最通俗的中文、不超过 120 字回答，必要时分 1-3 步。当前界面上下文：{context}");
        let body = serde_json::json!({ "model": model, "messages": [{ "role": "system", "content": system }, { "role": "user", "content": question }], "temperature": 0.3, "max_tokens": 400 });
        let resp = ureq::post(&endpoint).set("Authorization", &format!("Bearer {key}")).set("Content-Type", "application/json").timeout(std::time::Duration::from_secs(60)).send_json(body)
            .map_err(|e| match e { ureq::Error::Status(c, r) => format!("HTTP {c}: {}", r.into_string().unwrap_or_default().chars().take(200).collect::<String>()), e => e.to_string() })?;
        let v: serde_json::Value = resp.into_json().map_err(|e| e.to_string())?;
        v["choices"][0]["message"]["content"].as_str().map(String::from).ok_or_else(|| "没有得到回答".into())
    }).await.map_err(|e| e.to_string())?
}
/// 导出对话记录（dsh 的 session.export 是 GET 下载接口，不是 RPC）→ 让用户选保存位置
#[tauri::command]
async fn session_export(app: AppHandle, state: State<'_, AppState>, session_id: String) -> Result<Option<String>, String> {
    let url = dsh_url(&state)?;
    let (tx, rx) = std::sync::mpsc::channel();
    app.dialog().file().set_file_name(format!("biodsh-对话-{}.zip", &session_id.chars().take(12).collect::<String>())).add_filter("对话记录", &["zip"]).save_file(move |p| { let _ = tx.send(p); });
    let Some(target) = tauri::async_runtime::spawn_blocking(move || rx.recv().ok().flatten()).await.map_err(|e| e.to_string())? else { return Ok(None) };
    let target = target.to_string();
    let t2 = target.clone();
    tauri::async_runtime::spawn_blocking(move || -> Result<(), String> {
        let resp = ureq::get(&format!("{}/api/session.export?sessionId={}&includeDescendants=true", url.trim_end_matches('/'), session_id)).timeout(std::time::Duration::from_secs(120)).call().map_err(|e| e.to_string())?;
        let mut bytes = Vec::new();
        std::io::Read::read_to_end(&mut resp.into_reader(), &mut bytes).map_err(|e| e.to_string())?;
        std::fs::write(&t2, bytes).map_err(|e| e.to_string())
    }).await.map_err(|e| e.to_string())??;
    Ok(Some(target))
}
#[tauri::command]
async fn workspace_files(state: State<'_, AppState>, path: Option<String>) -> Result<Vec<files::FileEntry>, String> {
    if let (Some(f), Some(p)) = (state.files.as_ref(), path.as_ref()) { f.add_root(std::path::PathBuf::from(p)); }
    let ws = path.filter(|p| !p.trim().is_empty()).unwrap_or_else(|| workspace_of(&state));
    Ok(tauri::async_runtime::spawn_blocking(move || files::list(&ws)).await.map_err(|e| e.to_string())?)
}
#[tauri::command]
async fn read_workspace_image(state: State<'_, AppState>, rel: String, path: Option<String>) -> Result<String, String> {
    let ws = path.filter(|p| !p.trim().is_empty()).unwrap_or_else(|| workspace_of(&state));
    tauri::async_runtime::spawn_blocking(move || files::read_image(&ws, &rel)).await.map_err(|e| e.to_string())?
}
fn ratings_path(state: &AppState) -> std::path::PathBuf { state.paths.root.join("ratings.json") }
#[tauri::command]
fn ratings_get(state: State<'_, AppState>) -> serde_json::Value {
    std::fs::read_to_string(ratings_path(&state)).ok().and_then(|t| serde_json::from_str(&t).ok()).unwrap_or_else(|| serde_json::json!({}))
}
#[tauri::command]
fn ratings_set(state: State<'_, AppState>, id: String, vote: i32, comment: String) -> serde_json::Value {
    let mut all = ratings_get(state.clone());
    if vote == 0 { if let Some(o) = all.as_object_mut() { o.remove(&id); } }
    else {
        all[&id] = serde_json::json!({ "vote": vote, "comment": comment, "at": std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0) });
    }
    let _ = std::fs::write(ratings_path(&state), serde_json::to_string_pretty(&all).unwrap_or_default());
    all
}
/// 永久删除一个对话：先通过 dsh 归档（从列表消失），再删除它在 $DSH_HOME/sessions/*/ 下的记录目录
#[tauri::command]
async fn session_delete(state: State<'_, AppState>, session_id: String) -> Result<u32, String> {
    if !session_id.starts_with("session-") || session_id.contains(['/', '\\', '.']) { return Err("非法会话 id".into()); }
    if let Ok(url) = dsh_url(&state) {
        let (u, sid) = (url.clone(), session_id.clone());
        let _ = tauri::async_runtime::spawn_blocking(move || dsh_call(&u, "workspace.archiveSession", serde_json::json!({ "sessionId": sid }))).await;
    }
    let root = state.paths.dsh_home.join("sessions");
    let sid = session_id.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let mut removed = 0u32;
        if let Ok(rd) = std::fs::read_dir(&root) {
            for e in rd.flatten() {
                let p = e.path().join(&sid);
                if p.is_dir() && std::fs::remove_dir_all(&p).is_ok() { removed += 1; }
                let f = e.path().join(format!("{sid}.jsonl"));
                if f.is_file() && std::fs::remove_file(&f).is_ok() { removed += 1; }
            }
        }
        Ok(removed)
    }).await.map_err(|e| e.to_string())?
}

/// 分析环境扩展包：往 bioenv 里追加安装一组软件包（uv pip install），进度走 env 事件
#[tauri::command]
async fn env_install_extra(app: AppHandle, state: State<'_, AppState>, packages: Vec<String>) -> Result<pyenv::EnvStatus, String> {
    let (py, paths, china) = (Arc::clone(&state.pyenv), state.paths.clone(), state.settings.lock().unwrap().use_china_mirror);
    tauri::async_runtime::spawn_blocking(move || py.install_extra(&app, &paths, china, &packages)).await.map_err(|e| e.to_string())
}
#[tauri::command]
async fn migrate_scan(app: AppHandle) -> Result<Vec<migrate::Source>, String> {
    let home = app.path().home_dir().map_err(|e| e.to_string())?;
    Ok(tauri::async_runtime::spawn_blocking(move || migrate::scan(&home)).await.map_err(|e| e.to_string())?)
}
#[tauri::command]
async fn migrate_import(app: AppHandle, state: State<'_, AppState>, source_id: String) -> Result<migrate::ImportResult, String> {
    let home = app.path().home_dir().map_err(|e| e.to_string())?;
    let (skills_root, ws) = (state.paths.skills.clone(), std::path::PathBuf::from(workspace_of(&state)));
    Ok(tauri::async_runtime::spawn_blocking(move || migrate::import(&home, &skills_root, &ws, &source_id)).await.map_err(|e| e.to_string())?)
}
#[tauri::command]
fn open_path(app: AppHandle, path: String) { let _ = app.opener().open_path(path, None::<&str>); }
#[tauri::command]
fn open_external(app: AppHandle, url: String) { let _ = app.opener().open_url(url, None::<&str>); }
#[tauri::command]
async fn pick_folder(app: AppHandle) -> Option<String> {
    let (tx, rx) = std::sync::mpsc::channel();
    app.dialog().file().pick_folder(move |p| { let _ = tx.send(p); });
    tauri::async_runtime::spawn_blocking(move || rx.recv().ok().flatten().map(|p| p.to_string())).await.ok().flatten()
}
#[tauri::command]
fn window_control(app: AppHandle, action: String) {
    let Some(w) = app.get_window("main") else { return };
    match action.as_str() {
        "minimize" => { let _ = w.minimize(); }
        "maximize" => { if w.is_maximized().unwrap_or(false) { let _ = w.unmaximize(); } else { let _ = w.maximize(); } }
        "close" => { let _ = w.close(); }
        _ => {}
    }
}

fn build_main_window(app: &AppHandle) -> tauri::Result<Window> {
    let builder = tauri::window::WindowBuilder::new(app, "main")
        .title("BioDSH")
        .inner_size(1240.0, 720.0)
        .min_inner_size(960.0, 600.0)
        .center();
    #[cfg(target_os = "macos")]
    let builder = builder.title_bar_style(tauri::TitleBarStyle::Overlay).hidden_title(true);
    #[cfg(not(target_os = "macos"))]
    let builder = builder.decorations(false);
    let window = builder.build()?;
    let size = window.inner_size()?.to_logical::<f64>(window.scale_factor()?);
    window.add_child(
        tauri::webview::WebviewBuilder::new("ui", WebviewUrl::App("index.html".into())).auto_resize(),
        LogicalPosition::new(0.0, 0.0),
        LogicalSize::new(size.width, size.height),
    )?;
    Ok(window)
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .setup(|app| {
            let handle = app.handle().clone();
            let paths = AppPaths::detect(&handle);
            // 版本升级后 WebView2 可能继续用缓存里的旧页面（程序是新的、界面是旧的）。
            // 版本号变化时清掉 HTTP/代码缓存（保留 localStorage 等站点数据）。
            {
                let stamp = paths.root.join(".app-version");
                let current = handle.package_info().version.to_string();
                let prev = std::fs::read_to_string(&stamp).unwrap_or_default();
                if prev.trim() != current {
                    if let Ok(local) = handle.path().app_local_data_dir() {
                        for sub in ["EBWebView/Default/Cache", "EBWebView/Default/Code Cache", "EBWebView/Default/GPUCache"] {
                            let _ = std::fs::remove_dir_all(local.join(sub));
                        }
                    }
                    let _ = std::fs::write(&stamp, &current);
                }
            }
            // 官方技能开箱即装（每个版本首次启动刷新一次；社区技能仍按需安装）
            { let (h, p) = (handle.clone(), paths.clone()); std::thread::spawn(move || { let n = skills::seed_official(&h, &p); if n > 0 { let _ = h.emit("event", serde_json::json!({ "type": "skills", "statuses": skills::statuses(&h, &p) })); } }); }
            let settings = AppSettings::load(&paths);
            // 本地只读图片服务：让对话里能内嵌显示工作区里的图
            let files = files_server::FilesServer::start(vec![paths.root.clone(), std::path::PathBuf::from(&settings.workspace)]);
            app.manage(AppState { paths, settings: Mutex::new(settings), dsh: Arc::new(DshManager::new()), pyenv: Arc::new(PyEnvManager::new()), dsh_bounds: Mutex::new((Rect::default(), false)), files });
            build_main_window(&handle)?;
            Ok(())
        })
        .on_page_load(|webview, payload| {
            if let Some(st) = webview.app_handle().try_state::<AppState>() { trace(&st.paths, &format!("page_load {} {:?} {}", webview.label(), payload.event(), payload.url())); }
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                if window.label() == "main" { let app = window.app_handle(); if let Some(st) = app.try_state::<AppState>() { st.dsh.stop(app); } }
            }
        })
        .invoke_handler(tauri::generate_handler![
            app_info, settings_get, settings_set, credential_get, credential_set,
            env_status, env_install, dsh_status, dsh_start, dsh_restart, dsh_reload, dsh_bounds,
            skills_catalog, skills_statuses, skills_readme, skills_install, skills_uninstall,
            open_path, open_external, pick_folder, window_control, client_log, deepseek_balance, git_status, git_init, git_commit, dsh_rpc, dsh_open_session, dsh_new_session, check_updates, assistant_ask, session_export, workspace_files, read_workspace_image, ratings_get, ratings_set, session_delete, env_install_extra, migrate_scan, migrate_import, refdata_list, refdata_install, refdata_remove, demos_seed, dsh_set_context
        ])
        .run(tauri::generate_context!())
        .expect("error while running BioDSH");
}
