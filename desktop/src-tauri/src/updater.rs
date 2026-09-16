// 轻量差量更新器:只下这次真正变化的预编译文件(多数时候就 ~10MB 的 biodsh-desktop.exe),
// 不下 270MB 整包。delta.json 由 build-delta.mjs 生成、发布脚本用 minisign 私钥签名(delta.json.sig);
// 这里用与 tauri updater 同一把公钥验签,再逐文件校验 sha256,才落地。跨大版本(fullRequired)或任何
// 校验失败 → 调用方回退 tauri 整包安装器。Windows 运行中的 exe 被锁,靠退出后小助手替换再拉起。
use std::path::{Path, PathBuf};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

// = tauri.conf.json plugins.updater.pubkey 解码后的 minisign 公钥行(与 0.2.0~0.2.5 一致)。
const UPDATER_PUBKEY: &str = "RWQArKBKITbwOFUZX9KuaooKgw+NjCpk+Djsc7pJ6UOaMkVGqyliaWsx";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeltaFile { pub target: String, pub url: String, pub sha256: String, pub size: u64 }
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Delta {
    pub version: String,
    #[serde(default, rename = "minFromVersion")] pub min_from_version: String,
    #[serde(default, rename = "fullRequired")] pub full_required: bool,
    #[serde(default, rename = "fullInstallerUrl")] pub full_installer_url: String,
    #[serde(default)] pub files: Vec<DeltaFile>,
}

fn ver_tuple(v: &str) -> Vec<u64> {
    v.split(['.', '-']).filter_map(|s| s.chars().take_while(|c| c.is_ascii_digit()).collect::<String>().parse().ok()).collect()
}
fn ver_gt(a: &str, b: &str) -> bool {
    let (x, y) = (ver_tuple(a), ver_tuple(b));
    for i in 0..x.len().max(y.len()) {
        let (xi, yi) = (*x.get(i).unwrap_or(&0), *y.get(i).unwrap_or(&0));
        if xi != yi { return xi > yi; }
    }
    false
}

fn http_get_string(url: &str) -> Result<String, String> {
    ureq::get(url).timeout(std::time::Duration::from_secs(20)).call()
        .map_err(|e| e.to_string())?.into_string().map_err(|e| e.to_string())
}

/// 验 delta.json 的 minisign 签名(同一把公钥)。
/// `tauri signer sign` 产出的 .sig 是「整个 minisign 签名文本」再 base64 一层(tauri updater 自己也先 base64 解码
/// 再解析);而裸 minisign 工具产出的就是多行文本。这里两种都吃:先尝试 base64 解一层,解出的内容像 minisign
/// 文本(含 `untrusted comment`)就用它,否则回退当作已经是原始文本。这样无论发布脚本按哪种方式落地 .sig 都能验。
fn verify_sig(data: &[u8], sig_text: &str) -> Result<(), String> {
    use minisign_verify::{PublicKey, Signature};
    use base64::Engine;
    let pk = PublicKey::from_base64(UPDATER_PUBKEY).map_err(|e| format!("公钥无效: {e}"))?;
    let trimmed = sig_text.trim();
    let text: String = match base64::engine::general_purpose::STANDARD.decode(trimmed) {
        Ok(bytes) => match String::from_utf8(bytes) {
            Ok(s) if s.contains("untrusted comment") => s,
            _ => trimmed.to_string(),
        },
        Err(_) => trimmed.to_string(),
    };
    let sig = Signature::decode(&text).map_err(|e| format!("签名解析失败: {e}"))?;
    pk.verify(data, &sig, false).map_err(|_| "delta 签名验证失败(可能被篡改)".to_string())
}

/// 查更新:拉 delta.json + delta.json.sig,验签,比版本。返回 Some(delta) 表示有可用的更新。
pub fn check(delta_url: &str, current_version: &str) -> Result<Option<Delta>, String> {
    let body = http_get_string(delta_url)?;
    let sig = http_get_string(&format!("{delta_url}.sig"))?;
    verify_sig(body.as_bytes(), &sig)?;
    let delta: Delta = serde_json::from_str(&body).map_err(|e| format!("delta.json 解析失败: {e}"))?;
    if !ver_gt(&delta.version, current_version) { return Ok(None); }
    // 低于 minFromVersion 的老版本没有轻量更新器 → 交给整包(理论上到不了这,老版本压根不调本函数)
    if ver_gt(&delta.min_from_version, current_version) { return Ok(Some(delta)); }
    Ok(Some(delta))
}

fn sha256_file(p: &Path) -> Result<String, String> {
    let mut f = std::fs::File::open(p).map_err(|e| e.to_string())?;
    let mut hasher = Sha256::new();
    std::io::copy(&mut f, &mut hasher).map_err(|e| e.to_string())?;
    Ok(format!("{:x}", hasher.finalize()))
}

/// 下载单个文件到 <install>/<target>.new,校验 sha256。返回落地的 .new 路径。
fn download_verify(install_dir: &Path, f: &DeltaFile) -> Result<PathBuf, String> {
    let dst = install_dir.join(&f.target);
    let tmp = dst.with_extension(format!("{}.new", dst.extension().and_then(|e| e.to_str()).unwrap_or("")));
    if let Some(parent) = tmp.parent() { let _ = std::fs::create_dir_all(parent); }
    let resp = ureq::get(&f.url).timeout(std::time::Duration::from_secs(600)).call().map_err(|e| e.to_string())?;
    let mut reader = resp.into_reader();
    let mut out = std::fs::File::create(&tmp).map_err(|e| e.to_string())?;
    std::io::copy(&mut reader, &mut out).map_err(|e| e.to_string())?;
    drop(out);
    let got = sha256_file(&tmp)?;
    if got != f.sha256.to_lowercase() {
        let _ = std::fs::remove_file(&tmp);
        let want = f.sha256.get(..12).unwrap_or(f.sha256.as_str());
        let have = got.get(..12).unwrap_or(got.as_str());
        return Err(format!("{} 校验失败:期望 {} 实得 {}", f.target, want, have));
    }
    Ok(tmp)
}

/// 下载并校验 delta 里的全部文件(落地为 .new,先不替换)。全部成功才返回,任何一个失败即整体失败。
pub fn stage(install_dir: &Path, delta: &Delta) -> Result<Vec<(PathBuf, PathBuf)>, String> {
    let mut staged = vec![]; // (new_path, final_path)
    for f in &delta.files {
        let newp = download_verify(install_dir, f)?;
        staged.push((newp, install_dir.join(&f.target)));
    }
    Ok(staged)
}

/// 生成"退出后替换 + 拉起"的 Windows 助手脚本并分离启动。app 随后自己退出,助手等进程结束→替换→重启。
#[cfg(windows)]
pub fn swap_and_relaunch(staged: &[(PathBuf, PathBuf)], exe_to_launch: &Path, tmp_dir: &Path) -> Result<(), String> {
    use std::io::Write;
    let pid = std::process::id();
    let bat = tmp_dir.join("biodsh-apply-update.bat");
    let mut s = String::new();
    s.push_str("@echo off\r\n");
    // 等本进程退出(最多 ~30s)
    s.push_str(&format!(":wait\r\ntasklist /FI \"PID eq {pid}\" 2>nul | find \"{pid}\" >nul\r\nif not errorlevel 1 (\r\n  timeout /t 1 /nobreak >nul\r\n  goto wait\r\n)\r\n"));
    for (newp, finalp) in staged {
        // 备份旧文件后用 .new 覆盖(move 是原子的)
        s.push_str(&format!("move /y \"{}\" \"{}.bak\" >nul 2>&1\r\n", finalp.display(), finalp.display()));
        s.push_str(&format!("move /y \"{}\" \"{}\" >nul\r\n", newp.display(), finalp.display()));
        // 覆盖成功后清掉备份,别每次更新都在安装目录留一个 .bak(旧 exe 已不再被占用)
        s.push_str(&format!("del /q \"{}.bak\" >nul 2>&1\r\n", finalp.display()));
    }
    // 拉起新版本
    s.push_str(&format!("start \"\" \"{}\"\r\n", exe_to_launch.display()));
    // 自删
    s.push_str("del \"%~f0\"\r\n");
    std::fs::File::create(&bat).and_then(|mut f| f.write_all(s.as_bytes())).map_err(|e| e.to_string())?;
    use std::os::windows::process::CommandExt;
    std::process::Command::new("cmd").args(["/c", &bat.to_string_lossy()])
        .creation_flags(0x0800_0008) // CREATE_NO_WINDOW | DETACHED_PROCESS
        .spawn().map_err(|e| e.to_string())?;
    Ok(())
}

#[cfg(not(windows))]
pub fn swap_and_relaunch(_staged: &[(PathBuf, PathBuf)], _exe: &Path, _tmp: &Path) -> Result<(), String> {
    Err("轻量更新器目前仅 Windows".into())
}
