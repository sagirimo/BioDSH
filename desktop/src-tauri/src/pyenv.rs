//! 用自带 uv 建 Python 生信环境：uv python install 3.12 → uv venv → uv sync --frozen → 验证。
use crate::paths::{resource, uv_binary, venv_python, AppPaths};
use serde::Serialize;
use std::collections::BTreeMap;
use std::fs;
use std::io::{BufRead, BufReader};
use std::process::{Command, Stdio};
use std::sync::Mutex;
use tauri::{AppHandle, Emitter};

#[derive(Clone, Serialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct EnvStatus {
    pub ready: bool,
    pub step: String,
    pub message: String,
    pub progress: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub python_path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub python_version: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub packages: Option<BTreeMap<String, String>>,
    pub log: Vec<String>,
}

pub struct PyEnvManager {
    pub status: Mutex<EnvStatus>,
    running: Mutex<bool>,
}

impl PyEnvManager {
    pub fn new() -> Self {
        PyEnvManager { status: Mutex::new(EnvStatus { step: "idle".into(), message: "尚未安装".into(), ..Default::default() }), running: Mutex::new(false) }
    }

    fn emit(&self, app: &AppHandle) {
        let s = self.status.lock().unwrap().clone();
        let _ = app.emit("event", serde_json::json!({ "type": "env", "status": s }));
    }
    fn set(&self, app: &AppHandle, f: impl FnOnce(&mut EnvStatus)) {
        { let mut s = self.status.lock().unwrap(); f(&mut s); }
        self.emit(app);
    }
    fn log(&self, app: &AppHandle, line: &str) {
        self.set(app, |s| { s.log.push(line.to_string()); if s.log.len() > 500 { let n = s.log.len() - 500; s.log.drain(0..n); } });
    }

    fn uv_env(&self, paths: &AppPaths, china: bool) -> Vec<(String, String)> {
        let mut env = vec![
            ("UV_PYTHON_INSTALL_DIR".into(), paths.root.join("uv").join("python").to_string_lossy().into()),
            ("UV_CACHE_DIR".into(), paths.root.join("uv").join("cache").to_string_lossy().into()),
            ("UV_PROJECT_ENVIRONMENT".into(), paths.bioenv.join(".venv").to_string_lossy().into()),
            ("UV_NO_PROGRESS".into(), "1".into()),
            ("UV_HTTP_TIMEOUT".into(), "120".into()),
        ];
        if china {
            env.push(("UV_PYTHON_INSTALL_MIRROR".into(), "https://registry.npmmirror.com/-/binary/python-build-standalone".into()));
            env.push(("UV_INDEX_URL".into(), "https://pypi.tuna.tsinghua.edu.cn/simple".into()));
        }
        env
    }

    fn run(&self, app: &AppHandle, paths: &AppPaths, args: &[&str], env: &[(String, String)], on_line: &mut dyn FnMut(&str)) -> Result<(), String> {
        let uv = uv_binary(app);
        self.log(app, &format!("$ uv {}", args.join(" ")));
        let mut cmd = Command::new(&uv);
        cmd.args(args).current_dir(&paths.bioenv).envs(env.iter().map(|(k, v)| (k.as_str(), v.as_str()))).stdin(Stdio::null()).stdout(Stdio::piped()).stderr(Stdio::piped());
        #[cfg(windows)]
        { use std::os::windows::process::CommandExt; cmd.creation_flags(0x0800_0000); }
        let mut child = cmd.spawn().map_err(|e| format!("无法启动 uv：{e}"))?;
        let stdout = child.stdout.take().unwrap();
        let stderr = child.stderr.take().unwrap();
        let (tx, rx) = std::sync::mpsc::channel::<String>();
        for r in [Box::new(stdout) as Box<dyn std::io::Read + Send>, Box::new(stderr) as Box<dyn std::io::Read + Send>] {
            let tx = tx.clone();
            std::thread::spawn(move || { for l in BufReader::new(r).lines().map_while(Result::ok) { let _ = tx.send(l); } });
        }
        drop(tx);
        for l in rx { if !l.trim().is_empty() { self.log(app, &l); on_line(&l); } }
        let st = child.wait().map_err(|e| e.to_string())?;
        if st.success() { Ok(()) } else { Err(format!("uv 退出代码 {st}")) }
    }

    fn python_info(py: &std::path::Path) -> Option<(String, BTreeMap<String, String>)> {
        let code = "import json,sys,importlib.metadata as m\npk={}\nfor n in ['scanpy','anndata','numpy','pandas','scipy','leidenalg','umap-learn','matplotlib','statsmodels','scikit-learn']:\n  try: pk[n]=m.version(n)\n  except Exception: pass\nprint(json.dumps({'v':sys.version.split()[0],'p':pk}))";
        let mut cmd = Command::new(py);
        cmd.arg("-c").arg(code).stdin(Stdio::null()).stdout(Stdio::piped()).stderr(Stdio::null());
        #[cfg(windows)]
        { use std::os::windows::process::CommandExt; cmd.creation_flags(0x0800_0000); }
        let out = cmd.output().ok()?;
        if !out.status.success() { return None; }
        let v: serde_json::Value = serde_json::from_slice(&out.stdout).ok()?;
        let pk: BTreeMap<String, String> = serde_json::from_value(v["p"].clone()).ok()?;
        if !pk.contains_key("scanpy") { return None; }
        Some((v["v"].as_str()?.to_string(), pk))
    }

    pub fn probe(&self, app: &AppHandle, paths: &AppPaths) -> EnvStatus {
        let py = venv_python(&paths.bioenv);
        if !py.exists() {
            self.set(app, |s| { s.ready = false; s.step = "idle".into(); s.message = "尚未安装".into(); s.progress = 0.0; });
        } else if let Some((v, pk)) = Self::python_info(&py) {
            self.set(app, |s| { s.ready = true; s.step = "ready".into(); s.message = "环境就绪".into(); s.progress = 1.0; s.python_path = Some(py.to_string_lossy().into()); s.python_version = Some(v); s.packages = Some(pk); });
        } else {
            self.set(app, |s| { s.ready = false; s.step = "error".into(); s.message = "环境损坏，请重新安装".into(); s.progress = 0.0; });
        }
        self.status.lock().unwrap().clone()
    }

    pub fn install(&self, app: &AppHandle, paths: &AppPaths, china: bool) -> EnvStatus {
        { let mut r = self.running.lock().unwrap(); if *r { return self.status.lock().unwrap().clone(); } *r = true; }
        let result = (|| -> Result<(), String> {
            if !uv_binary(app).exists() { return Err(format!("找不到 uv：{}", uv_binary(app).display())); }
            fs::create_dir_all(&paths.bioenv).map_err(|e| e.to_string())?;
            for f in ["pyproject.toml", "uv.lock"] {
                fs::copy(resource(app, "bioenv").join(f), paths.bioenv.join(f)).map_err(|e| format!("复制 {f} 失败：{e}"))?;
            }
            let env = self.uv_env(paths, china);
            self.set(app, |s| { s.ready = false; s.step = "python".into(); s.message = "正在下载 Python 3.12…".into(); s.progress = 0.05; s.log.clear(); });
            self.run(app, paths, &["python", "install", "3.12"], &env, &mut |_| {}).map_err(|_| "Python 下载失败，请检查网络后重试".to_string())?;
            self.set(app, |s| { s.step = "venv".into(); s.message = "正在创建虚拟环境…".into(); s.progress = 0.2; });
            let venv = paths.bioenv.join(".venv").to_string_lossy().to_string();
            self.run(app, paths, &["venv", "--python", "3.12", "--allow-existing", &venv], &env, &mut |_| {}).map_err(|_| "创建虚拟环境失败".to_string())?;
            self.set(app, |s| { s.step = "packages".into(); s.message = "正在安装分析软件包（scanpy 等，约需几分钟）…".into(); s.progress = 0.3; });
            let mut n: f64 = 0.0;
            let app2 = app.clone();
            let status = &self.status;
            self.run(app, paths, &["sync", "--frozen", "--python", "3.12"], &env, &mut |l| {
                if l.trim_start().starts_with(['+', '~', '-']) || l.contains("Installed") || l.contains("Prepared") || l.contains("Downloading") {
                    n += 1.0;
                    let mut s = status.lock().unwrap();
                    s.progress = (0.3 + n / 150.0).min(0.9);
                    s.message = format!("正在安装分析软件包… {}", l.trim().chars().take(60).collect::<String>());
                    let snap = s.clone(); drop(s);
                    let _ = app2.emit("event", serde_json::json!({ "type": "env", "status": snap }));
                }
            }).map_err(|_| "安装软件包失败（通常是网络问题，可重试）".to_string())?;
            self.set(app, |s| { s.step = "verify".into(); s.message = "正在验证…".into(); s.progress = 0.95; });
            let py = venv_python(&paths.bioenv);
            let (v, pk) = Self::python_info(&py).ok_or("验证失败：scanpy 无法导入")?;
            self.set(app, |s| { s.ready = true; s.step = "ready".into(); s.message = "环境就绪".into(); s.progress = 1.0; s.python_path = Some(py.to_string_lossy().into()); s.python_version = Some(v); s.packages = Some(pk); });
            Ok(())
        })();
        if let Err(e) = result { self.set(app, |s| { s.ready = false; s.step = "error".into(); s.message = e; s.progress = 0.0; }); }
        *self.running.lock().unwrap() = false;
        self.status.lock().unwrap().clone()
    }

    /// 追加安装扩展包（不重建环境）。失败时保留原环境可用状态。
    pub fn install_extra(&self, app: &AppHandle, paths: &AppPaths, china: bool, packages: &[String]) -> EnvStatus {
        { let mut r = self.running.lock().unwrap(); if *r { return self.status.lock().unwrap().clone(); } *r = true; }
        let pkgs: Vec<String> = packages.iter().filter(|p| p.chars().all(|c| c.is_ascii_alphanumeric() || "-_[]=.<>,~".contains(c))).cloned().collect();
        let result = (|| -> Result<(), String> {
            if pkgs.is_empty() { return Err("没有可安装的包".into()); }
            if !venv_python(&paths.bioenv).exists() { return Err("请先安装基础分析环境".into()); }
            let env = self.uv_env(paths, china);
            self.set(app, |s| { s.step = "packages".into(); s.message = format!("正在安装扩展包：{}…", pkgs.join(", ")); s.progress = 0.4; });
            let py = venv_python(&paths.bioenv).to_string_lossy().to_string();
            let mut args: Vec<&str> = vec!["pip", "install", "--python", &py];
            for p in &pkgs { args.push(p); }
            self.run(app, paths, &args, &env, &mut |_| {}).map_err(|_| "扩展包安装失败（通常是网络或包名问题）".to_string())?;
            Ok(())
        })();
        match result {
            Ok(()) => { self.set(app, |s| { s.message = "扩展包安装完成".into(); s.progress = 1.0; }); let _ = self.probe(app, paths); }
            Err(e) => { self.set(app, |s| { s.message = e; s.progress = if s.ready { 1.0 } else { 0.0 }; s.step = if s.ready { "ready".into() } else { "error".into() }; }); }
        }
        *self.running.lock().unwrap() = false;
        self.status.lock().unwrap().clone()
    }
}
