use crate::paths::AppPaths;
use serde::{Deserialize, Serialize};
use std::fs;

#[derive(Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AppSettings {
    pub use_china_mirror: bool,
    pub workspace: String,
    pub onboarded: bool,
    pub theme: String,
    #[serde(default = "default_language")]
    pub language: String,
    #[serde(default = "default_mode")]
    pub mode: String,
    #[serde(default)]
    pub offline_base_url: String,
    #[serde(default)]
    pub offline_model: String,
    #[serde(default)]
    pub offline_api_key: String,
    #[serde(default)]
    pub remote_dsh_url: String,
    /// 图像生成（OpenAI 兼容 images 接口）：智谱 CogView / OpenAI / SiliconFlow / 通义万相
    #[serde(default)]
    pub image_base_url: String,
    #[serde(default)]
    pub image_api_key: String,
    #[serde(default)]
    pub image_model: String,
    /// 外接 MCP 服务（写进 dsh 的 cordis.patch.yml）
    #[serde(default)]
    pub mcp_servers: Vec<McpServer>,
    /// 示范项目是否已复制到 ~/BioDSH/demos 并注册为工作区
    #[serde(default)]
    pub demos_seeded: bool,
}

#[derive(Clone, Serialize, Deserialize, Default, Debug, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct McpServer {
    pub name: String,
    #[serde(default = "default_transport")]
    pub transport: String, // stdio | streamable-http
    #[serde(default)]
    pub command: String,
    #[serde(default)]
    pub args: Vec<String>,
    #[serde(default)]
    pub url: String,
    #[serde(default)]
    pub env: std::collections::BTreeMap<String, String>,
    #[serde(default)]
    pub enabled: Option<bool>,
}
fn default_transport() -> String { "stdio".into() }

fn default_language() -> String { "system".into() }
fn default_mode() -> String { "online".into() }

impl AppSettings {
    pub fn load(p: &AppPaths) -> AppSettings {
        let f = p.root.join("settings.json");
        let mut s = AppSettings { use_china_mirror: true, workspace: p.workspace.to_string_lossy().into(), onboarded: false, theme: "system".into(), language: "system".into(), mode: "online".into(), offline_base_url: String::new(), offline_model: String::new(), offline_api_key: String::new(), remote_dsh_url: String::new(), image_base_url: String::new(), image_api_key: String::new(), image_model: String::new(), mcp_servers: Vec::new(), demos_seeded: false };
        if let Ok(txt) = fs::read_to_string(&f) {
            if let Ok(v) = serde_json::from_str::<serde_json::Value>(&txt) {
                if let Some(b) = v.get("useChinaMirror").and_then(|x| x.as_bool()) { s.use_china_mirror = b; }
                if let Some(w) = v.get("workspace").and_then(|x| x.as_str()) { if !w.is_empty() { s.workspace = w.into(); } }
                if let Some(b) = v.get("onboarded").and_then(|x| x.as_bool()) { s.onboarded = b; }
                if let Some(t) = v.get("theme").and_then(|x| x.as_str()) { s.theme = t.into(); }
                if let Some(l) = v.get("language").and_then(|x| x.as_str()) { s.language = l.into(); }
                if let Some(m) = v.get("mode").and_then(|x| x.as_str()) { s.mode = m.into(); }
                for (k, field) in [("offlineBaseUrl", 0), ("offlineModel", 1), ("offlineApiKey", 2), ("remoteDshUrl", 3)] {
                    if let Some(val) = v.get(k).and_then(|x| x.as_str()) {
                        match field { 0 => s.offline_base_url = val.into(), 1 => s.offline_model = val.into(), 2 => s.offline_api_key = val.into(), _ => s.remote_dsh_url = val.into() }
                    }
                }
                for (k, field) in [("imageBaseUrl", 0), ("imageModel", 1), ("imageApiKey", 2)] {
                    if let Some(val) = v.get(k).and_then(|x| x.as_str()) {
                        match field { 0 => s.image_base_url = val.into(), 1 => s.image_model = val.into(), _ => s.image_api_key = val.into() }
                    }
                }
                if let Some(arr) = v.get("mcpServers") { if let Ok(list) = serde_json::from_value::<Vec<McpServer>>(arr.clone()) { s.mcp_servers = list; } }
                if let Some(b) = v.get("demosSeeded").and_then(|x| x.as_bool()) { s.demos_seeded = b; }
            }
        }
        s
    }
    pub fn save(&self, p: &AppPaths) {
        let _ = fs::write(p.root.join("settings.json"), serde_json::to_string_pretty(self).unwrap_or_default());
    }
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CredentialStatus {
    pub has_key: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub masked: Option<String>,
}

const CRED_KEY: &str = "DEEPSEEK_API_KEY";

/// 解析凭据文件里的 key：支持 dsh ≥0.1.1 的 `version: 1 / refs:` 布局，也认早期的扁平布局。
fn parse_key(txt: &str) -> Option<String> {
    let mut in_refs = false;
    for line in txt.lines() {
        if line.starts_with("refs:") { in_refs = true; continue; }
        if !line.starts_with(' ') && !line.starts_with('\t') { in_refs = false; }
        let t = line.trim();
        if let Some(rest) = t.strip_prefix(&format!("{CRED_KEY}:")) {
            if in_refs || !txt.contains("version:") {
                let k = rest.trim().trim_matches(|c| c == '"' || c == '\'');
                if !k.is_empty() { return Some(k.to_string()); }
            }
        }
    }
    None
}

fn render(key: Option<&str>) -> String {
    match key { Some(k) => format!("version: 1\n\nrefs:\n  {CRED_KEY}: {k}\n"), None => "version: 1\n\nrefs: {}\n".to_string() }
}

pub fn read_credential_value(p: &AppPaths) -> Option<String> {
    fs::read_to_string(p.dsh_home.join(".credentials.yaml")).ok().and_then(|t| parse_key(&t))
}

pub fn read_credential(p: &AppPaths) -> CredentialStatus {
    match read_credential_value(p) {
        Some(k) => CredentialStatus { has_key: true, masked: Some(if k.len() > 8 { format!("{}••••{}", &k[..5], &k[k.len() - 4..]) } else { "••••".into() }) },
        None => CredentialStatus { has_key: false, masked: None },
    }
}

pub fn write_credential(p: &AppPaths, key: &str) {
    let f = p.dsh_home.join(".credentials.yaml");
    let key = key.trim();
    let _ = fs::write(&f, render(if key.is_empty() { None } else { Some(key) }));
    #[cfg(unix)]
    { use std::os::unix::fs::PermissionsExt; let _ = fs::set_permissions(&f, fs::Permissions::from_mode(0o600)); }
}

/// 启动 dsh 前调用：把早期扁平格式的凭据文件迁移到版本化布局（dsh 0.1.1 起扁平格式会让整个进程启动失败）。
pub fn migrate_credentials(p: &AppPaths) {
    let f = p.dsh_home.join(".credentials.yaml");
    let Ok(txt) = fs::read_to_string(&f) else { return };
    if txt.contains("version:") || txt.trim().is_empty() { return; }
    if let Some(k) = parse_key(&txt) { let _ = fs::write(&f, render(Some(&k))); }
}
