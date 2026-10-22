//! 启动 / 停止 dsh web：用自带的官方 Node（--expose-internals）跑 dsh/bin.js，从输出里抓 URL。
use crate::paths::{dsh_bin, node_binary, uv_binary, venv_bin_dir, venv_python, AppPaths};
use serde::Serialize;
use std::fs;
use std::io::{BufRead, BufReader, Write};
#[allow(unused_imports)]
use std::path::PathBuf;
use std::path::Path;
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use tauri::{AppHandle, Emitter};

#[derive(Clone, Serialize, Default)]
pub struct DshStatus {
    pub state: String, // stopped | starting | running | error
    #[serde(skip_serializing_if = "Option::is_none")]
    pub url: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
    pub log: Vec<String>,
}

/// 把我们的外观选择同步给 dsh（settings.yaml 里的 ui-theme.preference：light / dark / system）
pub fn set_theme(paths: &AppPaths, theme: &str) {
    let f = paths.dsh_home.join("settings.yaml");
    let txt = fs::read_to_string(&f).unwrap_or_default();
    let mut out: Vec<String> = Vec::new();
    let mut skip = false;
    for line in txt.lines() {
        if line.starts_with("ui-theme:") { skip = true; continue; }
        if skip { if line.starts_with(' ') || line.starts_with('\t') || line.trim().is_empty() { continue; } skip = false; }
        out.push(line.to_string());
    }
    out.push("ui-theme:".into());
    out.push(format!("  preference: {theme}"));
    let _ = fs::write(&f, out.join("\n") + "\n");
}

/// 同步界面语言给 dsh（settings.yaml 的 locale.preference：zh / en；system 则按系统语言）
pub fn set_locale(paths: &AppPaths, language: &str) {
    let lang = match language { "en" => "en", "zh" => "zh", _ => if sys_locale_is_zh() { "zh" } else { "en" } };
    let f = paths.dsh_home.join("settings.yaml");
    let txt = fs::read_to_string(&f).unwrap_or_default();
    let mut out: Vec<String> = Vec::new();
    let mut skip = false;
    for line in txt.lines() {
        if line.starts_with("locale:") { skip = true; continue; }
        if skip { if line.starts_with(' ') || line.starts_with('\t') || line.trim().is_empty() { continue; } skip = false; }
        out.push(line.to_string());
    }
    out.push("locale:".into());
    out.push(format!("  preference: {lang}"));
    let _ = fs::write(&f, out.join("\n") + "\n");
}

fn sys_locale_is_zh() -> bool {
    for k in ["LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"] { if let Ok(v) = std::env::var(k) { if !v.is_empty() { return v.to_lowercase().starts_with("zh"); } } }
    #[cfg(windows)]
    {
        // 读 Windows 用户界面语言（HKCU\Control Panel\International\LocaleName）
        if let Ok(out) = { use std::os::windows::process::CommandExt; std::process::Command::new("reg").args(["query", "HKCU\\Control Panel\\International", "/v", "LocaleName"]).creation_flags(0x0800_0000).output() } {
            let s = String::from_utf8_lossy(&out.stdout).to_lowercase();
            return s.contains("zh-");
        }
    }
    true
}

/// 离线模式的 pi-ai 路由名(settings.yaml 的 llm-pi-ai.providers 键,也是 agent-default-model.provider)。
pub const OFFLINE_PROVIDER: &str = "biodsh-offline";

/// 1.0 起模型路由(离线路由、用户自己添加的模型来源)都通过 dsh 官方 settings API 在启动后写入(见 lib.rs sync_offline_route),
/// 不再经 settings.yaml 整段覆盖 llm-pi-ai(那样会把用户存的其他来源一起冲掉)。这里只清理旧版本写进 settings.yaml 的
/// llm-deepseek / llm-pi-ai / 离线 agent-default-model 段，防止它们在下次导入时覆盖用户设置。
pub fn set_llm_override(paths: &AppPaths) {
    let f = paths.dsh_home.join("settings.yaml");
    let Ok(txt) = fs::read_to_string(&f) else { return };
    let mut out: Vec<String> = Vec::new();
    let (mut section, mut buf): (String, Vec<String>) = (String::new(), Vec::new());
    let flush = |section: &str, buf: &mut Vec<String>, out: &mut Vec<String>| {
        let drop = section == "llm-deepseek" || section == "llm-pi-ai"
            || (section == "agent-default-model" && buf.iter().any(|l| l.trim() == format!("provider: {OFFLINE_PROVIDER}")));
        if !drop { out.append(buf); } else { buf.clear(); }
    };
    for line in txt.lines() {
        let top = !line.starts_with(' ') && !line.starts_with('\t') && !line.trim().is_empty();
        if top { flush(&section, &mut buf, &mut out); section = line.split(':').next().unwrap_or("").trim().to_string(); }
        buf.push(line.to_string());
    }
    flush(&section, &mut buf, &mut out);
    let _ = fs::write(&f, out.join("\n") + "\n");
}

/// 在线默认模型:DeepSeek-V4.1-Flash(接口 id deepseek-flash),当前 DeepSeek 最新主力,强于 V4-Pro 且更便宜。
pub const DEFAULT_ONLINE_MODEL: &str = "deepseek-flash";

/// 把随包的 dsh-biodsh(不含技能,几十 KB)复制进 profile 的 node_modules,并在 profile 的 bundles 列表里启用,
/// 布局与官方插件管理器(pnpm)安装后相同,预设里的 `dsh-biodsh/...` 模块名按 profile 解析。
fn install_bundle(home: &Path, template: &Path) {
    let profile = home.join("profiles").join("web");
    let dst = profile.join("node_modules").join("dsh-biodsh");
    if template.join("package.json").exists() {
        let _ = fs::remove_dir_all(&dst);
        let _ = copy_dir(template, &dst);
    }
    let pj = profile.join("package.json");
    let mut v: serde_json::Value = fs::read_to_string(&pj).ok().and_then(|t| serde_json::from_str(&t).ok())
        .unwrap_or_else(|| serde_json::json!({ "name": "dsh-profile-web", "private": true, "dependencies": {},
            "dsh": { "profile": { "bundles": ["@deepseek-ai/dsh-base", "@deepseek-ai/dsh-web-app"] } } }));
    let bundles = v.pointer_mut("/dsh/profile/bundles").and_then(|b| b.as_array_mut());
    match bundles {
        Some(list) => { if !list.iter().any(|b| b == "dsh-biodsh") { list.push(serde_json::json!("dsh-biodsh")); } }
        None => { v["dsh"] = serde_json::json!({ "profile": { "bundles": ["@deepseek-ai/dsh-base", "@deepseek-ai/dsh-web-app", "dsh-biodsh"] } }); }
    }
    let _ = fs::create_dir_all(&profile);
    let _ = fs::write(&pj, serde_json::to_string_pretty(&v).unwrap_or_default() + "\n");
}

fn copy_dir(src: &Path, dst: &Path) -> std::io::Result<()> {
    fs::create_dir_all(dst)?;
    for e in fs::read_dir(src)? {
        let e = e?;
        let to = dst.join(e.file_name());
        if e.file_type()?.is_dir() { copy_dir(&e.path(), &to)?; } else { fs::copy(e.path(), to)?; }
    }
    Ok(())
}

/// YAML 单引号字符串（单引号翻倍转义）
fn yaml_str(v: &str) -> String { format!("'{}'", v.replace('\'', "''")) }

/// dsh 的沙盒只允许写工作区和会话私有的临时目录；numba / matplotlib 默认往用户目录写缓存，
/// 写不进去就会反复重编译（示范项目里 pbmc3k 预处理因此跑了 40 分钟）。sitecustomize 在每个 Python 进程
/// 启动时把这些缓存指到系统临时目录（沙盒对它有写权限）。
pub fn ensure_sitecustomize(bioenv: &Path) {
    let sp = if cfg!(windows) { bioenv.join(".venv").join("Lib").join("site-packages") } else {
        let lib = bioenv.join(".venv").join("lib");
        match fs::read_dir(&lib).ok().and_then(|rd| rd.flatten().find(|e| e.file_name().to_string_lossy().starts_with("python"))) { Some(e) => e.path().join("site-packages"), None => return }
    };
    if !sp.exists() { return; }
    let f = sp.join("sitecustomize.py");
    let body = "# biodsh-sitecustomize v1 — generated by BioDSH desktop (rewritten on every start)\nimport os, tempfile\ndef _d(name):\n    p = os.path.join(tempfile.gettempdir(), 'biodsh-' + name)\n    try:\n        os.makedirs(p, exist_ok=True)\n        return p\n    except Exception:\n        return None\nfor var, name in (('NUMBA_CACHE_DIR', 'numba'), ('MPLCONFIGDIR', 'matplotlib'), ('XDG_CACHE_HOME', 'cache')):\n    if not os.environ.get(var):\n        p = _d(name)\n        if p: os.environ[var] = p\n";
    if fs::read_to_string(&f).map(|t| t == body).unwrap_or(false) { return; }
    let _ = fs::write(&f, body);
}

pub struct DshManager {
    pub status: Mutex<DshStatus>,
    child: Mutex<Option<Child>>,
}

// 桌面版专属说明,作为 dsh-biodsh 的 `appContext` 设置注入(人设本身在 bundle 里,dsh 用户和桌面版共用一份)。
// 不用 {{…}} 模板变量:该段按字面注入。
const APP_CONTEXT: &str = "You are running inside the BioDSH desktop app. Your users see these pages and you can explain them:\n- 「项目」: left tree of projects (each a data folder) and their tasks (conversations). Below it, the project's files split into 数据 and 结果. The task title bar has 审阅结论 (an independent review of your conclusions) and 存为工作流 (turn this task into a reproducible workflow).\n- 「技能」: every BioDSH and community skill with its details; all are enabled, and fitting ones are picked for each message automatically.\n- 「工作流」: saved reproducible workflows (pipelines/<id>/pipeline.json) with steps, parameters, validation checks and run history; 学习已有流程 copies a script/notebook/methods file into pipelines/_sources/ for you to learn from.\n- 「数据库」: public databases with a 让智能体抓取 button, and local reference packs (MSigDB, GO, NCBI gene_info, STRING) in the folder named by env BIODSH_REFDATA — prefer these local files for enrichment and ID mapping when present.\n- 「设置」: model API key and model sources, online / offline (local or intranet model) mode, MCP servers, image generation, language, theme. The analysis environment installs itself on first start.\n`python` on PATH is the BioDSH analysis environment (scanpy, anndata, pandas, statsmodels, matplotlib); `uv pip install <pkg>` adds packages.\nWhenever you produce or mention an image file (png/jpg/svg), also show it inline: env var BIODSH_FILES_URL (read with `$env:BIODSH_FILES_URL` in pwsh or `echo $BIODSH_FILES_URL`) is a local read-only image server; write `![说明](<BIODSH_FILES_URL>/<absolute path, forward slashes, spaces as %20>)` after the file name, one per figure. If the variable is empty, just name the file.\nIf you are unsure about an app detail, say so and point to the closest page instead of inventing UI.";

// 1.0:只关掉被 BioDSH 外壳替代或面向开发者的面板(dsh 自带侧栏、品牌、插件/预设编辑、cordis 检查器等);
// 交付文件、计划、后台任务、目标、子智能体、工作流与执行轨迹这些对科研有用的面板保留。
const MINIMAL_PLUGINS: &[&str] = &[
    "ui-settings-plugin-inventory", "ui-settings-plugins", "ui-cordis", "ui-brand-official", "ui-message-feedback",
    "ui-reference", "ui-agent-preset", "ui-sidebar",
];

impl DshManager {
    pub fn new() -> Self {
        DshManager { status: Mutex::new(DshStatus { state: "stopped".into(), ..Default::default() }), child: Mutex::new(None) }
    }

    fn emit(&self, app: &AppHandle) {
        let s = self.status.lock().unwrap().clone();
        let _ = app.emit("event", serde_json::json!({ "type": "dsh", "status": s }));
    }

    fn push(&self, app: &AppHandle, paths: &AppPaths, line: &str) {
        if let Ok(mut f) = fs::OpenOptions::new().create(true).append(true).open(paths.logs.join("dsh.log")) {
            let _ = writeln!(f, "{line}");
        }
        let mut s = self.status.lock().unwrap();
        s.log.push(line.to_string());
        if s.log.len() > 400 { let n = s.log.len() - 400; s.log.drain(0..n); }
        drop(s);
        self.emit(app);
    }

    /// 每次启动重建 BioDSH 对 dsh 的全部配置(都归应用所有,确定性生成):
    /// ① profile 里启用 dsh-biodsh bundle(BioDSH 预设 + `biodsh` 设置行,与官方 dsh 用户安装的是同一个包);
    /// ② home 补丁:精简界面、默认预设 biodsh-ptc、`biodsh` 设置(技能目录指向安装包资源、桌面说明)、自动审查、MCP。
    /// 不再覆盖 standard 预设,也不再挂散装插件。删除 cordis.patch.yml 与 profiles/web/node_modules/dsh-biodsh 后重启即恢复。
    fn ensure_home(paths: &AppPaths, official_skills: &Path, library_skills: &Path, bundle_template: &Path, mcp: &[crate::settings::McpServer]) {
        let home = &paths.dsh_home;
        let _ = fs::remove_dir_all(home.join(".agent-presets").join("biodsh")); // 0.1.2 遗留
        install_bundle(home, bundle_template);

        let mut body: Vec<String> = MINIMAL_PLUGINS.iter().map(|id| format!("- id: {id}\n  disabled: true")).collect();
        // 补丁对已有条目的 config 是整体替换:agent-preset-registry 只有 default 一个必填字段;biodsh 行是我们自己的。
        // 默认用 PTC 版(程序化工具调用,同 dsh 自带 ptc 预设):开发循环 15 题步数中位 23→16、耗时 129→97 s,正确率不变。
        body.push("- id: agent-preset-registry\n  config:\n    default: biodsh-ptc".into());
        let json = |v: &str| serde_json::to_string(v).unwrap_or_else(|_| "\"\"".into());
        body.push(format!("- id: biodsh\n  config:\n    officialSkillsDir: {}\n    librarySkillsDir: {}\n    appContext: {}",
            json(&official_skills.to_string_lossy()), json(&library_skills.to_string_lossy()), json(APP_CONTEXT)));
        let mut inserts: Vec<String> = Vec::new();
        // 官方「自动审查」(dsh 随附、默认关):权限菜单多一个选项,每次工具调用前由当前模型评估风险,
        // 项目内普通操作直接放行,删除既有文件/对外写入等仍请用户确认。官方设计不允许设为默认,需用户在会话里选择。
        inserts.push("    - id: auto-review\n      name: '@deepseek-ai/dsh-experimental-auto-review'".into());
        // 每个 MCP 服务一个 dsh-mcp-client 实例(工具名 mcp__<name>__<tool>);字段按 insert 的两层缩进(6/8 空格)。
        for m in mcp.iter().filter(|m| m.enabled != Some(false)) {
            let name: String = m.name.chars().filter(|c| c.is_ascii_alphanumeric() || *c == '_' || *c == '-').take(32).collect();
            if name.is_empty() { continue; }
            let mut y = format!("    - id: mcp-{name}\n      name: '@deepseek-ai/dsh-mcp-client'\n      config:\n        serverName: {name}\n");
            if m.transport == "streamable-http" {
                if m.url.trim().is_empty() { continue; }
                y.push_str(&format!("        transport: streamable-http\n        url: {}\n", yaml_str(m.url.trim())));
            } else {
                if m.command.trim().is_empty() { continue; }
                y.push_str(&format!("        transport: stdio\n        command: {}\n", yaml_str(m.command.trim())));
                if !m.args.is_empty() { y.push_str(&format!("        args: [{}]\n", m.args.iter().map(|a| yaml_str(a)).collect::<Vec<_>>().join(", "))); }
                if !m.env.is_empty() { y.push_str("        env:\n"); for (k, v) in &m.env { y.push_str(&format!("          {k}: {}\n", yaml_str(v))); } }
            }
            y.push_str("        failOnStartupError: false");
            inserts.push(y.trim_end().to_string());
        }
        body.push(format!("- insert:\n{}", inserts.join("\n")));
        let _ = fs::write(home.join("cordis.patch.yml"), format!("# biodsh-minimal v13 — 由 BioDSH 每次启动重新生成:精简界面 + dsh-biodsh PTC 预设设为默认 + biodsh 设置 + 自动审查 + MCP\n{}\n", body.join("\n")));

        let settings = home.join("settings.yaml");
        // 首次启动才写默认值。dsh 0.2 每次启动会把 settings.yaml 改名为 .imported,所以有 .imported 也说明不是首次。
        if !settings.exists() && !home.join("settings.yaml.imported").exists() {
            let _ = fs::write(&settings, format!("ui-onboarding:\n  welcomeNoticeVersion: 2026-08-13.1\nlocale:\n  preference: zh\nui-theme:\n  preference: system\nagent-default-model:\n  provider: deepseek-official\n  model: {DEFAULT_ONLINE_MODEL}\n  reasoningEffort: high\n"));
        }
    }

    pub fn start(self: &Arc<Self>, app: &AppHandle, paths: &AppPaths, workspace: &str) -> DshStatus { self.start_with(app, paths, workspace, None, Vec::new(), &[]) }

    /// `extra_env`：额外注入给 dsh 子进程的环境变量（图像生成接口等）；`mcp`：写进 patch 的 MCP 服务。
    pub fn start_with(self: &Arc<Self>, app: &AppHandle, paths: &AppPaths, workspace: &str, offline_key: Option<String>, extra_env: Vec<(String, String)>, mcp: &[crate::settings::McpServer]) -> DshStatus {
        if self.child.lock().unwrap().is_some() { return self.status.lock().unwrap().clone(); }
        Self::ensure_home(paths, &crate::paths::resource(app, "skills"), &crate::paths::resource(app, "community-skills"), &crate::paths::resource(app, "dsh/node_modules").join("@biodsh").join("dsh-biodsh"), mcp);
        crate::settings::migrate_credentials(paths);
        ensure_sitecustomize(&paths.bioenv);
        *self.status.lock().unwrap() = DshStatus { state: "starting".into(), ..Default::default() };
        self.emit(app);
        let node = node_binary(app);
        let bin = dsh_bin(app);
        if !node.exists() {
            *self.status.lock().unwrap() = DshStatus { state: "error".into(), error: Some(format!("找不到自带的 Node 运行时：{}", node.display())), ..Default::default() };
            self.push(app, paths, &format!("[error] node not found at {}", node.display()));
            return self.status.lock().unwrap().clone();
        }
        let bin_dir = venv_bin_dir(&paths.bioenv);
        let uv_dir = uv_binary(app).parent().map(Path::to_path_buf).unwrap_or_default();
        let sep = if cfg!(windows) { ";" } else { ":" };
        let node_dir = node.parent().map(Path::to_path_buf).unwrap_or_default();
        let path_env = format!("{}{sep}{}{sep}{}{sep}{}", bin_dir.display(), uv_dir.display(), node_dir.display(), std::env::var("PATH").unwrap_or_default());
        let _ = fs::create_dir_all(workspace);
        self.push(app, paths, &format!("[spawn] {} --expose-internals {} web (cwd {workspace})", node.display(), bin.display()));
        let mut cmd = Command::new(&node);
        cmd.arg("--expose-internals").arg(&bin).args(["web", "--port", "0", "--no-open"])
            .current_dir(workspace)
            .env("DSH_HOME", &paths.dsh_home)
            .env("BIODSH_HOME", &paths.root)
            .env("BIODSH_PYTHON", venv_python(&paths.bioenv))
            .env("UV_PROJECT_ENVIRONMENT", paths.bioenv.join(".venv"))
            .env("VIRTUAL_ENV", paths.bioenv.join(".venv"))
            .env("PATH", path_env)
            .env("DSH_TELEMETRY_DISABLED", "1")
            // 技能、技能精选与收敛护栏都由 dsh-biodsh bundle 提供并通过 `biodsh` 设置配置(见 ensure_home);不要再设
            // DSH_BUNDLED_SKILL_DIR,否则 2000+ 社区技能会经 skill-filesystem 进入会话目录。
            .env_remove("NODE_OPTIONS");
        if let Some(k) = offline_key { if !k.is_empty() { cmd.env("BIODSH_OFFLINE_KEY", k); } else { cmd.env("BIODSH_OFFLINE_KEY", "local"); } }
        for (k, v) in extra_env { if !v.is_empty() { cmd.env(k, v); } }
        cmd
            .stdin(Stdio::null()).stdout(Stdio::piped()).stderr(Stdio::piped());
        #[cfg(windows)]
        { use std::os::windows::process::CommandExt; cmd.creation_flags(0x0800_0000); } // CREATE_NO_WINDOW
        let mut child = match cmd.spawn() {
            Ok(c) => c,
            Err(e) => {
                *self.status.lock().unwrap() = DshStatus { state: "error".into(), error: Some(e.to_string()), ..Default::default() };
                self.emit(app);
                return self.status.lock().unwrap().clone();
            }
        };
        let stdout = child.stdout.take();
        let stderr = child.stderr.take();
        *self.child.lock().unwrap() = Some(child);
        for stream in [stdout.map(|s| Box::new(s) as Box<dyn std::io::Read + Send>), stderr.map(|s| Box::new(s) as Box<dyn std::io::Read + Send>)].into_iter().flatten() {
            let me = Arc::clone(self);
            let app = app.clone();
            let paths = paths.clone();
            std::thread::spawn(move || {
                for line in BufReader::new(stream).lines().map_while(Result::ok) {
                    if line.trim().is_empty() { continue; }
                    if let Some(i) = line.find("http://127.0.0.1:") {
                        // 稳健解析：host + 数字端口 + 可选 /path?query(含 0.1.2 的 ?token=)，遇空白即止；
                        // 两条 URL 粘在一行(快速重启时 stdout 交错)也只取到干净的一条，绝不把 "4307dsh" 当 URL 送进 webview。
                        let rest = &line[i..];
                        let b = rest.as_bytes();
                        let mut end = "http://127.0.0.1:".len();
                        while end < b.len() && b[end].is_ascii_digit() { end += 1; }
                        if end < b.len() && b[end] == b'/' { while end < b.len() && !b[end].is_ascii_whitespace() { end += 1; } }
                        let url = rest[..end].to_string();
                        let mut s = me.status.lock().unwrap();
                        if s.state == "starting" && end > "http://127.0.0.1:".len() { s.state = "running".into(); s.url = Some(url); }
                    }
                    // 原生模块损坏(常见于升级没替换干净):给出可操作的中文提示,而不是让用户看天书。
                    if line.contains("Mismatched native Koffi") || line.contains("native module") && line.contains("koffi") {
                        let mut s = me.status.lock().unwrap();
                        s.error = Some("运行时文件损坏（多半是升级没替换干净）。请到「更多 → 检查更新」重装,或重新下载安装包覆盖安装；你的项目和历史不会丢。".into());
                    }
                    me.push(&app, &paths, &line);
                }
            });
        }
        // 监视退出
        {
            let me = Arc::clone(self);
            let app = app.clone();
            let paths = paths.clone();
            std::thread::spawn(move || loop {
                std::thread::sleep(std::time::Duration::from_millis(500));
                let mut guard = me.child.lock().unwrap();
                let Some(child) = guard.as_mut() else { break };
                match child.try_wait() {
                    Ok(Some(code)) => {
                        *guard = None;
                        drop(guard);
                        let ok = code.success();
                        { let mut s = me.status.lock().unwrap(); s.state = if ok { "stopped".into() } else { "error".into() }; if !ok && s.error.is_none() { s.error = Some(format!("dsh 退出，代码 {code}")); } }
                        me.push(&app, &paths, &format!("[dsh exited with {code}]"));
                        break;
                    }
                    Ok(None) => {}
                    Err(_) => break,
                }
            });
        }
        // 最多等 60 秒拿到 URL
        for _ in 0..300 {
            std::thread::sleep(std::time::Duration::from_millis(200));
            let st = self.status.lock().unwrap().state.clone();
            if st != "starting" { break; }
        }
        if self.status.lock().unwrap().state == "starting" {
            let mut s = self.status.lock().unwrap();
            s.state = "error".into();
            s.error = Some("dsh 启动超时（60 秒内未就绪）".into());
        }
        self.emit(app);
        self.status.lock().unwrap().clone()
    }

    pub fn stop(&self, app: &AppHandle) {
        let child = self.child.lock().unwrap().take();
        if let Some(mut c) = child {
            #[cfg(windows)]
            { use std::os::windows::process::CommandExt; let _ = Command::new("taskkill").args(["/pid", &c.id().to_string(), "/T", "/F"]).creation_flags(0x0800_0000).stdout(Stdio::null()).stderr(Stdio::null()).status(); }
            let _ = c.kill();
            let _ = c.wait();
        }
        let mut s = self.status.lock().unwrap();
        s.state = "stopped".into();
        s.url = None;
        drop(s);
        self.emit(app);
    }
}

fn chrono_now() -> String {
    // 不引入 chrono：ISO 8601 近似（秒级）
    let secs = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0);
    let days = secs / 86400; let rem = secs % 86400;
    let (h, m, s) = (rem / 3600, (rem % 3600) / 60, rem % 60);
    // 民用历转换（Howard Hinnant 算法）
    let z = days as i64 + 719468; let era = z.div_euclid(146097); let doe = z - era * 146097;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365; let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100); let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1; let mo = if mp < 10 { mp + 3 } else { mp - 9 }; let y = if mo <= 2 { y + 1 } else { y };
    format!("{y:04}-{mo:02}-{d:02}T{h:02}:{m:02}:{s:02}.000Z")
}
