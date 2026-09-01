//! 一键迁移：把用户在 Claude Code / Codex / OpenCode / Cursor 等工具里已有的技能（SKILL.md 目录）
//! 和全局说明（AGENTS.md / CLAUDE.md）搬进 BioDSH。只复制，不动原文件。
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct Source {
    pub id: String,
    pub name: String,
    pub path: String,
    pub skills: Vec<String>,
    pub instructions: Option<String>,
    pub mcp_servers: Vec<String>,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ImportRequest { pub id: String }

#[derive(Serialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct ImportResult { pub skills: u32, pub instructions: u32, pub skipped: Vec<String> }

const SOURCES: &[(&str, &str, &[&str], &[&str], &[&str])] = &[
    // id, 显示名, 技能目录(相对 home), 全局说明文件, MCP 配置 json
    ("claude-code", "Claude Code", &[".claude/skills"], &[".claude/CLAUDE.md"], &[".claude.json", ".claude/settings.json"]),
    ("codex", "Codex", &[".codex/skills"], &[".codex/AGENTS.md"], &[]),
    ("opencode", "OpenCode", &[".config/opencode/skill", ".opencode/skill", ".config/opencode/skills"], &[".config/opencode/AGENTS.md"], &[".config/opencode/opencode.json"]),
    ("cursor", "Cursor", &[".cursor/skills"], &[], &[".cursor/mcp.json"]),
    ("agents", "通用 .agents 目录", &[".agents/skills"], &[".agents/AGENTS.md"], &[]),
];

fn skill_dirs(root: &Path) -> Vec<PathBuf> {
    let mut out = Vec::new();
    if let Ok(rd) = fs::read_dir(root) {
        for e in rd.flatten() {
            let p = e.path();
            if p.is_dir() && p.join("SKILL.md").is_file() { out.push(p); }
            else if p.is_file() && p.extension().map(|x| x == "md").unwrap_or(false) && p.file_name().map(|n| n != "SKILL.md").unwrap_or(false) { out.push(p); }
        }
    }
    out
}

fn mcp_names(file: &Path) -> Vec<String> {
    let Ok(t) = fs::read_to_string(file) else { return vec![] };
    let Ok(v) = serde_json::from_str::<serde_json::Value>(&t) else { return vec![] };
    v.get("mcpServers").or_else(|| v.get("mcp")).and_then(|m| m.as_object()).map(|m| m.keys().cloned().collect()).unwrap_or_default()
}

pub fn scan(home: &Path) -> Vec<Source> {
    let mut out = Vec::new();
    for (id, name, dirs, instr, mcps) in SOURCES {
        let mut skills = Vec::new();
        let mut path = String::new();
        for d in dirs.iter() {
            let p = home.join(d);
            let found = skill_dirs(&p);
            if !found.is_empty() { path = p.to_string_lossy().into(); skills.extend(found.iter().map(|x| x.file_name().unwrap().to_string_lossy().to_string())); }
        }
        let instructions = instr.iter().map(|f| home.join(f)).find(|p| p.is_file()).map(|p| p.to_string_lossy().to_string());
        let mut mcp = Vec::new();
        for f in mcps.iter() { mcp.extend(mcp_names(&home.join(f))); }
        if skills.is_empty() && instructions.is_none() && mcp.is_empty() { continue; }
        out.push(Source { id: id.to_string(), name: name.to_string(), path, skills, instructions, mcp_servers: mcp });
    }
    out
}

fn kebab(s: &str) -> String {
    let mut out = String::new();
    for c in s.chars() { if c.is_ascii_alphanumeric() { out.push(c.to_ascii_lowercase()); } else if !out.ends_with('-') && !out.is_empty() { out.push('-'); } }
    out.trim_matches('-').chars().take(48).collect()
}

fn copy_dir(src: &Path, dst: &Path) -> std::io::Result<()> {
    fs::create_dir_all(dst)?;
    for e in fs::read_dir(src)? {
        let e = e?; let t = dst.join(e.file_name());
        if e.file_type()?.is_dir() { copy_dir(&e.path(), &t)?; } else { fs::copy(e.path(), t)?; }
    }
    Ok(())
}

/// 把一个来源的技能与说明导入 BioDSH（技能 → $DSH_HOME/skills，说明 → 工作区 AGENTS.md）
pub fn import(home: &Path, skills_root: &Path, workspace: &Path, source_id: &str) -> ImportResult {
    let mut r = ImportResult::default();
    let Some(src) = scan(home).into_iter().find(|s| s.id == source_id) else { r.skipped.push("来源不存在".into()); return r; };
    if !src.path.is_empty() {
        for item in skill_dirs(Path::new(&src.path)) {
            let base = kebab(&item.file_stem().unwrap_or_default().to_string_lossy());
            if base.is_empty() { continue; }
            let mut id = base.clone(); let mut n = 2;
            while skills_root.join(&id).exists() { id = format!("{base}-{n}"); n += 1; }
            let dst = skills_root.join(&id);
            let ok = if item.is_dir() { copy_dir(&item, &dst).is_ok() } else { fs::create_dir_all(&dst).is_ok() && fs::copy(&item, dst.join("SKILL.md")).is_ok() };
            if ok {
                // 保证 frontmatter 的 name 与目录名一致（dsh 要求）
                let md = dst.join("SKILL.md");
                if let Ok(t) = fs::read_to_string(&md) {
                    let body = if t.starts_with("---") { t.splitn(3, "---").nth(2).unwrap_or("").to_string() } else { t.clone() };
                    let desc = t.lines().find(|l| l.trim_start().starts_with("description:")).map(|l| l.trim_start()[12..].trim().trim_matches('"').to_string()).unwrap_or_else(|| format!("Imported from {}", src.name));
                    let _ = fs::write(&md, format!("---\nname: {id}\ndescription: \"{}\"\n---\n{}", desc.replace('"', "'"), body.trim_start()));
                }
                let _ = fs::write(dst.join(".biodsh-version"), "imported\n");
                r.skills += 1;
            } else { r.skipped.push(base); }
        }
    }
    if let Some(f) = &src.instructions {
        if let Ok(t) = fs::read_to_string(f) {
            let target = workspace.join("AGENTS.md");
            let existing = fs::read_to_string(&target).unwrap_or_default();
            if !existing.contains(t.trim()) {
                let merged = if existing.trim().is_empty() { t } else { format!("{}\n\n<!-- imported from {} -->\n{}", existing.trim_end(), f, t) };
                if fs::write(&target, merged).is_ok() { r.instructions += 1; }
            }
        }
    }
    r
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn scan_and_import_roundtrip() {
        let tmp = std::env::temp_dir().join(format!("biodsh-migrate-{}", std::process::id()));
        let _ = fs::remove_dir_all(&tmp);
        let home = tmp.join("home"); let skills = tmp.join("skills"); let ws = tmp.join("ws");
        fs::create_dir_all(home.join(".claude/skills/My Skill")).unwrap();
        fs::write(home.join(".claude/skills/My Skill/SKILL.md"), "---\nname: whatever\ndescription: \"does x\"\n---\n# body\n").unwrap();
        fs::write(home.join(".claude/CLAUDE.md"), "always be nice").unwrap();
        fs::create_dir_all(&skills).unwrap(); fs::create_dir_all(&ws).unwrap();
        let found = scan(&home);
        assert_eq!(found.len(), 1); assert_eq!(found[0].id, "claude-code"); assert_eq!(found[0].skills, vec!["My Skill".to_string()]);
        let r = import(&home, &skills, &ws, "claude-code");
        assert_eq!(r.skills, 1); assert_eq!(r.instructions, 1);
        let md = fs::read_to_string(skills.join("my-skill/SKILL.md")).unwrap();
        assert!(md.starts_with("---\nname: my-skill\ndescription: \"does x\""));
        assert!(fs::read_to_string(ws.join("AGENTS.md")).unwrap().contains("always be nice"));
        // 再导一次：目录名加后缀，不覆盖
        let r2 = import(&home, &skills, &ws, "claude-code");
        assert_eq!(r2.skills, 1); assert!(skills.join("my-skill-2").exists());
        let _ = fs::remove_dir_all(&tmp);
    }
}
