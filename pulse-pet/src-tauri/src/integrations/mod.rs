//! v2 M1 接入管理（V2-DESIGN §1.4，TC-INT-03/07/08/12）：外部 agent 接入
//! （opencode 插件 / Claude Code hooks）的安装 / 卸载 / doctor。
//!
//! 概念边界：本模块的 `integrations`（外部 agent 接入管理）与 v1 既有
//! `plugins.rs`（PulsePet 内置插件机制，如 todo）是两个正交概念。
//!
//! 两接入对等（§1.4.1 表）：
//! - opencode：脚本落 `~/.config/opencode/plugins/pulse-pet-hook.js`（Windows
//!   优先 `%APPDATA%\opencode`），配置 `opencode.json → .jsonc → 新建 .json`
//!   （与 v1 install.sh 完全一致），JSONC 文本外科手术（`opencode_config.rs`）；
//! - claude-code：脚本落 `~/.pulsepet/hooks/claude-code-hook.js`（Windows
//!   `%LOCALAPPDATA%\pulsepet\hooks\`），配置 `~/.claude/settings.json`
//!   严格 JSON 结构化改写（serde_json preserve_order 保键序）。
//!
//! 统一防护：备份（仅留最近 1 份）+ 原子写（`<pid>.tmp` → rename，0600）+
//! symlink 拒绝 + 解析失败不落笔。脚本单一来源：`include_str!` 仓库源文件
//! （install.sh 同源拷贝，md5 天然一致）。
//!
//! 线程与 panic 纪律（issue #9 复核面，TC-INT-08-5）：
//! - 三命令 `async fn`（tokio worker 线程），node 探测（spawn ~50-200ms）与
//!   安装文件 I/O 经 `spawn_blocking`——不放主线程（Windows 消息泵所在，
//!   阻塞即 UI 冻结）；
//! - 命令路径零 panic：全部 `Result<T,String>` 错误返回 + `plog!`，禁
//!   `unwrap()/expect()`（`command_paths_have_no_unwrap` 源码纪律测试钉住）；
//! - `AgentActivity` 等 managed state 在 lib.rs 窗口创建循环之前 manage
//!   （钉子测试在 lib.rs：`agent_activity_managed_before_window_creation`）。

pub mod opencode_config;

use crate::i18n::{self, Lang};
use crate::plog;
use serde::Serialize;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

/// App 内嵌脚本（源文件单一来源；install.sh 同源拷贝，md5 天然一致）。
pub const BUNDLED_OPENCODE_HOOK: &str = include_str!("../../../opencode-plugin/pulse-pet-hook.js");
pub const BUNDLED_CC_HOOK: &str = include_str!("../../../opencode-plugin/claude-code-hook.js");

/// CC 接入注册的 8 个事件键（§1.3.1 最小事件集；Notification/Subagent*/Compact
/// 等不注册——安装条目与脚本分类均不出现）。
pub const CC_EVENTS: [&str; 8] = [
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "PermissionRequest",
    "Stop",
    "StopFailure",
];

/// managed 标记（claude-code 走 command 数据级；opencode 走 JSONC 行内注释）。
pub const MANAGED_FLAG: &str = "--pulse-pet-managed";

/// claude-code 接入 id；opencode 接入 id。
pub const ID_CLAUDE_CODE: &str = "claude-code";
pub const ID_OPENCODE: &str = "opencode";

/// `lastEventAt` 新鲜度阈值（10 分钟，超阈显示 noEvent，§1.5 P2-3）。
pub const LAST_EVENT_FRESH_MS: u64 = 10 * 60 * 1000;

// ---------------------------------------------------------------------------
// 路径解析（真实环境；测试直接注入 tempdir 路径给内层函数）
// ---------------------------------------------------------------------------

fn home_dir() -> PathBuf {
    #[cfg(target_os = "windows")]
    {
        PathBuf::from(std::env::var("USERPROFILE").unwrap_or_else(|_| ".".to_string()))
    }
    #[cfg(not(target_os = "windows"))]
    {
        PathBuf::from(std::env::var("HOME").unwrap_or_else(|_| ".".to_string()))
    }
}

/// CC settings.json 路径（`~/.claude/settings.json`）。
pub fn claude_settings_path() -> PathBuf {
    home_dir().join(".claude").join("settings.json")
}

/// CC hook 脚本目录（`~/.pulsepet/hooks/`；Windows `%LOCALAPPDATA%\pulsepet\hooks\`，
/// 与 runtime/plugins 平级，§1.4.4）。
pub fn cc_hooks_dir() -> PathBuf {
    #[cfg(target_os = "windows")]
    {
        let base = std::env::var("LOCALAPPDATA").unwrap_or_else(|_| ".".to_string());
        PathBuf::from(base).join("pulsepet").join("hooks")
    }
    #[cfg(not(target_os = "windows"))]
    {
        home_dir().join(".pulsepet").join("hooks")
    }
}

/// opencode 配置目录（与 v1 install.sh 一致：`OPENCODE_DIR` 可覆盖；
/// Windows 优先 `%APPDATA%\opencode`，回退 `~/.config/opencode`，install.ps1 同款）。
pub fn opencode_dir() -> PathBuf {
    if let Ok(d) = std::env::var("OPENCODE_DIR") {
        if !d.is_empty() {
            return PathBuf::from(d);
        }
    }
    #[cfg(target_os = "windows")]
    {
        let appdata = std::env::var("APPDATA").unwrap_or_default();
        let ad = PathBuf::from(&appdata).join("opencode");
        if !appdata.is_empty() && ad.is_dir() {
            return ad;
        }
        home_dir().join(".config").join("opencode")
    }
    #[cfg(not(target_os = "windows"))]
    {
        home_dir().join(".config").join("opencode")
    }
}

/// opencode 配置查找顺序（install.sh find_config 同款）：`opencode.json` →
/// `.jsonc` → 新建 `.json`。
pub fn find_opencode_config(dir: &Path) -> PathBuf {
    let json = dir.join("opencode.json");
    if json.is_file() {
        return json;
    }
    let jsonc = dir.join("opencode.jsonc");
    if jsonc.is_file() {
        return jsonc;
    }
    json
}

fn opencode_plugin_file(dir: &Path) -> PathBuf {
    dir.join("plugins").join("pulse-pet-hook.js")
}

// ---------------------------------------------------------------------------
// 通用防护：symlink 拒绝 / 备份（仅留最近 1 份）/ 原子写
// ---------------------------------------------------------------------------

/// settings 路径为符号链接 → 拒绝操作（openpets assertSafeSettingsPath 同构）。
fn assert_not_symlink(path: &Path) -> Result<(), String> {
    match std::fs::symlink_metadata(path) {
        Ok(meta) if meta.file_type().is_symlink() => Err(format!(
            "{} 是符号链接，拒绝修改（请先解除链接）",
            path.display()
        )),
        Ok(_) => Ok(()),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(e) => Err(format!("stat {}: {e}", path.display())),
    }
}

/// 备份文件名后缀模式：`<配置名>.pulsepet-backup-<时间戳>.json`。
fn backup_name(file: &Path) -> String {
    let ts = chrono::Local::now().format("%Y%m%dT%H%M%S%3f");
    format!(
        "{}.pulsepet-backup-{}.json",
        file.file_name()
            .map(|n| n.to_string_lossy().to_string())
            .unwrap_or_default(),
        ts
    )
}

/// 写前备份：复制为 `<名>.pulsepet-backup-<ISO>.json`（0600）；写新备份前先清理
/// 旧 `*.pulsepet-backup-*.json`（仅保留最近 1 份，§1.4.3）。
fn backup_file(path: &Path) -> Result<(), String> {
    if !path.is_file() {
        return Ok(());
    }
    let dir = path.parent().ok_or("backup: no parent dir")?;
    let prefix = format!(
        "{}.pulsepet-backup-",
        path.file_name()
            .map(|n| n.to_string_lossy().to_string())
            .unwrap_or_default()
    );
    // 清理旧备份（时间戳文件名不会自然覆盖，显式清理保「仅留最近 1 份」）
    if let Ok(entries) = std::fs::read_dir(dir) {
        for e in entries.flatten() {
            let name = e.file_name();
            let name = name.to_string_lossy();
            if name.starts_with(&prefix) && name.ends_with(".json") {
                let _ = std::fs::remove_file(e.path());
            }
        }
    }
    let dst = dir.join(backup_name(path));
    std::fs::copy(path, &dst).map_err(|e| format!("backup: {e}"))?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let _ = std::fs::set_permissions(&dst, std::fs::Permissions::from_mode(0o600));
    }
    Ok(())
}

/// 原子写：`<名>.<pid>.tmp`（0600）→ fsync → rename（跨平台原子，§1.4.3）。
fn atomic_write(path: &Path, content: &str) -> Result<(), String> {
    let dir = path.parent().ok_or("write: no parent dir")?;
    std::fs::create_dir_all(dir).map_err(|e| format!("mkdir {}: {e}", dir.display()))?;
    let base = path
        .file_name()
        .map(|n| n.to_string_lossy().to_string())
        .unwrap_or_default();
    let tmp = dir.join(format!("{base}.{}.tmp", std::process::id()));
    {
        let mut opts = std::fs::OpenOptions::new();
        opts.write(true).create(true).truncate(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            opts.mode(0o600);
        }
        let mut f = opts.open(&tmp).map_err(|e| format!("open tmp: {e}"))?;
        f.write_all(content.as_bytes())
            .map_err(|e| format!("write tmp: {e}"))?;
        let _ = f.sync_all();
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let _ = std::fs::set_permissions(&tmp, std::fs::Permissions::from_mode(0o600));
    }
    std::fs::rename(&tmp, path).map_err(|e| format!("rename into place: {e}"))?;
    Ok(())
}

/// epoch 毫秒（AgentActivity SystemTime → u64）。
fn epoch_ms(t: SystemTime) -> u64 {
    t.duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}

// ---------------------------------------------------------------------------
// claude-code：canonical 形态 / 特征检测 / 安装 / 卸载 / 状态（§1.4.2~1.4.4）
// ---------------------------------------------------------------------------

/// canonical command（Unix shell 包装形态，§1.4.2 逐字；Windows 跨 shell 字面
/// 路径形态 + `"shell":"powershell"`，§1.4.4）。
pub fn canonical_cc_command(windows: bool, hooks_dir: &Path) -> String {
    if windows {
        let script = hooks_dir.join("claude-code-hook.js");
        format!("node \"{}\" {MANAGED_FLAG}", script.display())
    } else {
        // killswitch 前置 → hook 文件存在且 node 在 PATH 则 exec node →
        // 兜底 drain stdin + exit 0（`[ -t 0 ] || cat >/dev/null` 防 SIGPIPE）
        "if [ -f \"$HOME/.pulsepet/runtime/hooks-disabled\" ]; then [ -t 0 ] || cat >/dev/null; \
         exit 0; fi; if [ -f \"$HOME/.pulsepet/hooks/claude-code-hook.js\" ] && \
         command -v node >/dev/null 2>&1; then \
         exec node \"$HOME/.pulsepet/hooks/claude-code-hook.js\" --pulse-pet-managed; fi; \
         [ -t 0 ] || cat >/dev/null; exit 0"
            .to_string()
    }
}

/// canonical hook 条目（数组直接元素，无 matcher；§1.4.2）。
fn canonical_cc_entry(windows: bool, hooks_dir: &Path) -> serde_json::Value {
    let mut v = serde_json::json!({
        "type": "command",
        "command": canonical_cc_command(windows, hooks_dir),
        "timeout": 3,
        "async": true,
        "asyncRewake": false,
    });
    if windows {
        v["shell"] = serde_json::json!("powershell"); // 免 Git for Windows 依赖
    }
    v
}

/// 「pulse-pet 特征」= type:"command" 且 command 含 `--pulse-pet-managed` 或
/// pulsepet 路径（§1.4.3）。
fn is_feature_entry(entry: &serde_json::Value) -> bool {
    let ty = entry.get("type").and_then(|v| v.as_str());
    if ty != Some("command") {
        return false;
    }
    entry
        .get("command")
        .and_then(|v| v.as_str())
        .is_some_and(|cmd| cmd.contains(MANAGED_FLAG) || cmd.contains(".pulsepet"))
}

/// 递归移除事件数组内全部特征条目（含 matcher 组 `{"matcher":…,"hooks":[…]}`
/// 内部——与检测同口径，§1.4.3）；返回移除数。
fn remove_feature_entries(arr: &mut Vec<serde_json::Value>) -> usize {
    let mut removed = 0;
    for entry in arr.iter_mut() {
        if let Some(hooks) = entry.get_mut("hooks").and_then(|h| h.as_array_mut()) {
            removed += remove_feature_entries(hooks);
        }
    }
    let before = arr.len();
    arr.retain(|e| !is_feature_entry(e));
    removed + (before - arr.len())
}

/// 统计事件数组：`(特征条目总数（含 matcher 组内）, 与 canonical 完全一致的直接元素数)`。
fn count_key(arr: &[serde_json::Value], canonical: &str) -> (usize, usize) {
    let mut feature = 0;
    let mut canonical_direct = 0;
    for e in arr {
        if let Some(hooks) = e.get("hooks").and_then(|h| h.as_array()) {
            feature += count_key(hooks, canonical).0;
        }
        if is_feature_entry(e) {
            feature += 1;
            if e.get("command").and_then(|v| v.as_str()) == Some(canonical) {
                canonical_direct += 1;
            }
        }
    }
    (feature, canonical_direct)
}

/// 配置条目三态（P1-1 修订口径：特征条目恰 1 且与 canonical 一致 → installed；
/// 多条 / 不一致 / 部分缺失 → stale；无特征条目 → 未安装）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ConfigState {
    NotInstalled,
    Installed,
    Stale,
}

/// 读取并判定 CC settings.json 的配置三态（Err = 解析失败/结构非法 → doctor
/// error，安装时不落笔）。
pub fn cc_config_state(settings: &Path, canonical: &str) -> Result<ConfigState, String> {
    let text = match std::fs::read_to_string(settings) {
        Ok(t) => t,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            return Ok(ConfigState::NotInstalled)
        }
        Err(e) => return Err(format!("read {}: {e}", settings.display())),
    };
    let v: serde_json::Value =
        serde_json::from_str(&text).map_err(|e| format!("JSON 解析失败：{e}"))?;
    let obj = v
        .as_object()
        .ok_or_else(|| "顶层不是对象".to_string())?;
    let Some(hooks) = obj.get("hooks") else {
        return Ok(ConfigState::NotInstalled);
    };
    let hooks = hooks
        .as_object()
        .ok_or_else(|| "hooks 不是对象".to_string())?;
    let mut total = 0usize;
    let mut all_ok = true;
    for ev in CC_EVENTS {
        match hooks.get(ev) {
            None => all_ok = false,
            Some(a) => {
                let arr = a
                    .as_array()
                    .ok_or_else(|| format!("hooks.{ev} 不是数组"))?;
                let (feature, canonical_direct) = count_key(arr, canonical);
                total += feature;
                if feature != 1 || canonical_direct != 1 {
                    all_ok = false;
                }
            }
        }
    }
    // 其它事件键里的特征条目（用户复制走的）也计入总量（>8 → stale）
    for (k, val) in hooks {
        if !CC_EVENTS.contains(&k.as_str()) {
            if let Some(arr) = val.as_array() {
                total += count_key(arr, canonical).0;
            }
        }
    }
    if total == 0 {
        Ok(ConfigState::NotInstalled)
    } else if all_ok && total == CC_EVENTS.len() {
        Ok(ConfigState::Installed)
    } else {
        Ok(ConfigState::Stale)
    }
}

/// 落 CC hook 脚本（+ `{"type":"module"}` package.json，node ESM 加载兜底）。
fn write_cc_hook_files(hooks_dir: &Path) -> Result<(), String> {
    std::fs::create_dir_all(hooks_dir).map_err(|e| format!("mkdir hooks: {e}"))?;
    let script = hooks_dir.join("claude-code-hook.js");
    atomic_write(&script, BUNDLED_CC_HOOK)?;
    let pkg = hooks_dir.join("package.json");
    // 只在缺失时落（用户手改过的 package.json 不覆盖）
    if !pkg.is_file() {
        atomic_write(&pkg, "{\"type\":\"module\"}\n")?;
    }
    Ok(())
}

fn read_settings_object(settings: &Path) -> Result<Option<serde_json::Value>, String> {
    match std::fs::read_to_string(settings) {
        Ok(text) => {
            let v: serde_json::Value =
                serde_json::from_str(&text).map_err(|e| format!("JSON 解析失败：{e}"))?;
            if !v.is_object() {
                return Err("顶层不是对象".to_string());
            }
            Ok(Some(v))
        }
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(e) => Err(format!("read {}: {e}", settings.display())),
    }
}

/// 安装 claude-code 接入（§1.4.3：移除全部特征条目 → 逐事件追加 canonical →
/// 序列化写回；用户条目永不触碰）。路径注入，测试用 tempdir。
pub fn install_cc(settings: &Path, hooks_dir: &Path) -> Result<(), String> {
    assert_not_symlink(settings)?;
    // 解析失败/结构非法 → 报 error 不落笔
    let mut root = read_settings_object(settings)?.unwrap_or_else(|| serde_json::json!({}));
    {
        let obj = root
            .as_object_mut()
            .ok_or_else(|| "顶层不是对象".to_string())?;
        if let Some(h) = obj.get("hooks") {
            if !h.is_object() {
                return Err("hooks 不是对象".to_string());
            }
        }
        // 1) 移除全部特征条目（所有事件键，含 matcher 组内递归——升级即重装）
        if let Some(hooks) = obj.get_mut("hooks").and_then(|h| h.as_object_mut()) {
            for (_k, v) in hooks.iter_mut() {
                if let Some(arr) = v.as_array_mut() {
                    remove_feature_entries(arr);
                }
            }
        }
        // 2) 逐事件追加 canonical 条目（事件数组缺失则建；非数组 → 不落笔）
        let entry = canonical_cc_entry(cfg!(windows), hooks_dir);
        let obj = root
            .as_object_mut()
            .ok_or_else(|| "顶层不是对象".to_string())?;
        let hooks = obj
            .entry("hooks")
            .or_insert_with(|| serde_json::json!({}));
        let hooks_obj = hooks
            .as_object_mut()
            .ok_or_else(|| "hooks 不是对象".to_string())?;
        for ev in CC_EVENTS {
            let arr = hooks_obj
                .entry(ev)
                .or_insert_with(|| serde_json::json!([]));
            let arr = arr
                .as_array_mut()
                .ok_or_else(|| format!("hooks.{ev} 不是数组"))?;
            arr.push(entry.clone());
        }
    }
    // 3) 脚本先行（settings 写失败时至多遗留无害脚本文件，doctor 钉住重装修复）
    write_cc_hook_files(hooks_dir)?;
    // 4) 备份 + 原子写（serde_json preserve_order：用户 env 等键序不变）
    let out = format!("{}\n", serde_json::to_string_pretty(&root).map_err(|e| e.to_string())?);
    backup_file(settings)?;
    atomic_write(settings, &out)?;
    Ok(())
}

/// 卸载 claude-code 接入：移除全部特征条目（递归进 matcher 组）→ 事件数组空则
/// 删事件键 → hooks 空则删 hooks 键；删除 hook 脚本；二次卸载 no-op。
pub fn uninstall_cc(settings: &Path, hooks_dir: &Path) -> Result<(), String> {
    assert_not_symlink(settings)?;
    if let Some(mut root) = read_settings_object(settings)? {
        let mut changed = false;
        {
            let obj = root
                .as_object_mut()
                .ok_or_else(|| "顶层不是对象".to_string())?;
            if let Some(hooks) = obj.get_mut("hooks").and_then(|h| h.as_object_mut()) {
                let mut empty_keys: Vec<String> = Vec::new();
                for (k, v) in hooks.iter_mut() {
                    if let Some(arr) = v.as_array_mut() {
                        let removed = remove_feature_entries(arr);
                        if removed > 0 {
                            changed = true;
                            if arr.is_empty() {
                                empty_keys.push(k.clone());
                            }
                        }
                    }
                }
                for k in &empty_keys {
                    hooks.remove(k);
                }
                if changed && hooks.is_empty() {
                    obj.remove("hooks");
                }
            }
        }
        if changed {
            let out =
                format!("{}\n", serde_json::to_string_pretty(&root).map_err(|e| e.to_string())?);
            backup_file(settings)?;
            atomic_write(settings, &out)?;
        }
    }
    // 删除脚本 + 我们落的 package.json（内容校验，用户手改过则保留）
    let _ = std::fs::remove_file(hooks_dir.join("claude-code-hook.js"));
    let pkg = hooks_dir.join("package.json");
    if let Ok(content) = std::fs::read_to_string(&pkg) {
        if content.trim() == "{\"type\":\"module\"}" {
            let _ = std::fs::remove_file(&pkg);
        }
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// opencode 接入（§1.4.5 对等收口：JSONC 合并 + 统一备份/原子写）
// ---------------------------------------------------------------------------

const EMPTY_OPENCODE_CONFIG: &str = "{\n  \"plugin\": []\n}\n";

/// 安装 opencode 插件：脚本拷贝 + JSONC 合并（install.sh 同流程）。
/// 返回实际操作的配置文件路径（status 展示用）。
pub fn install_opencode(dir: &Path) -> Result<PathBuf, String> {
    // 1) 脚本落点（verbatim 内嵌串 → md5 与 App 内嵌天然一致）
    let plugin = opencode_plugin_file(dir);
    if let Some(parent) = plugin.parent() {
        std::fs::create_dir_all(parent).map_err(|e| format!("mkdir plugins: {e}"))?;
    }
    backup_file(&plugin)?;
    atomic_write(&plugin, BUNDLED_OPENCODE_HOOK)?;
    // 2) 配置（不存在则新建空骨架，install.sh 同款）
    let cfg = find_opencode_config(dir);
    assert_not_symlink(&cfg)?;
    if !cfg.is_file() {
        atomic_write(&cfg, EMPTY_OPENCODE_CONFIG)?;
    }
    // 3) JSONC 合并（定位失败 → 不落笔 + 报 error）
    let text = std::fs::read_to_string(&cfg).map_err(|e| format!("read {}: {e}", cfg.display()))?;
    let outcome = opencode_config::merge_plugin(&text);
    if !outcome.located {
        return Err(format!(
            "{} 结构无法定位 plugin 段，保守未修改（请检查配置格式）",
            cfg.display()
        ));
    }
    if outcome.text != text {
        backup_file(&cfg)?;
        atomic_write(&cfg, &outcome.text)?;
    }
    Ok(cfg)
}

/// 卸载 opencode 插件：移除带标记项（JSONC 文本级）+ 删脚本；未安装 no-op。
pub fn uninstall_opencode(dir: &Path) -> Result<(), String> {
    let cfg = find_opencode_config(dir);
    if cfg.is_file() {
        assert_not_symlink(&cfg)?;
        let text =
            std::fs::read_to_string(&cfg).map_err(|e| format!("read {}: {e}", cfg.display()))?;
        let outcome = opencode_config::uninstall_plugin(&text);
        if !outcome.located {
            return Err(format!(
                "{} 存在 managed 标记但无法安全定位插件项，保守未修改",
                cfg.display()
            ));
        }
        if outcome.text != text {
            backup_file(&cfg)?;
            atomic_write(&cfg, &outcome.text)?;
        }
    }
    let _ = std::fs::remove_file(opencode_plugin_file(dir));
    Ok(())
}

/// opencode 配置三态：marker 在配置 + 脚本文件与内嵌一致 → Installed；
/// 任一存在但形态不完整/过时 → Stale；均无 → NotInstalled。
pub fn opencode_config_state(dir: &Path) -> Result<(ConfigState, PathBuf), String> {
    let cfg = find_opencode_config(dir);
    let cfg_marker = match std::fs::read_to_string(&cfg) {
        Ok(text) => text.contains(opencode_config::MARKER),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => false,
        Err(e) => return Err(format!("read {}: {e}", cfg.display())),
    };
    let plugin = opencode_plugin_file(dir);
    let file_ok = match std::fs::read_to_string(&plugin) {
        Ok(content) => content == BUNDLED_OPENCODE_HOOK,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => false,
        Err(e) => return Err(format!("read {}: {e}", plugin.display())),
    };
    let file_exists = plugin.is_file();
    Ok((
        match (cfg_marker, file_exists, file_ok) {
            (false, false, _) => ConfigState::NotInstalled,
            (true, true, true) => ConfigState::Installed,
            _ => ConfigState::Stale,
        },
        cfg,
    ))
}

// ---------------------------------------------------------------------------
// 状态组装 + doctor message（i18n.rs 双语模板）
// ---------------------------------------------------------------------------

/// hook 脚本文件健康快照（md5 与 App 内嵌副本对账的等价实现：逐字节比对）。
#[derive(Debug, Clone, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct HookFileStatus {
    pub exists: bool,
    pub matches_bundled: bool,
}

/// 一条接入的健康快照（§1.4.1 IntegrationStatus）。
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct IntegrationStatus {
    pub id: String,
    pub installed: bool,
    pub stale: bool,
    pub version: String,
    pub config_path: String,
    pub hook_file: HookFileStatus,
    /// CC 接入独有（每次 doctor 现测 spawn `node --version`，不缓存）。
    pub node_available: Option<bool>,
    /// App 侧最近收到该 agent 事件的时间（epoch ms；AgentActivity 内存跟踪）。
    pub last_event_at: Option<u64>,
    /// 人类可读诊断（zh/en 走 i18n.rs）。
    pub message: String,
    /// 检测/操作失败原因（None = 检测成功；Some → UI「错误」态）。
    pub error: Option<String>,
}

/// 状态组装输入（探测结果注入，纯函数可单测）。
pub struct StatusInputs {
    pub config_state: ConfigState,
    pub hook_file: HookFileStatus,
    pub node_available: Option<bool>,
    pub last_event_at: Option<u64>,
}

fn hook_file_status(path: &Path, bundled: &str) -> Result<HookFileStatus, String> {
    match std::fs::read_to_string(path) {
        Ok(content) => Ok(HookFileStatus {
            exists: true,
            matches_bundled: content == bundled,
        }),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(HookFileStatus {
            exists: false,
            matches_bundled: false,
        }),
        Err(e) => Err(format!("read {}: {e}", path.display())),
    }
}

/// 组装 doctor message（installed/stale/notInstalled 基调 + node/活性附加段）。
fn doctor_message(
    lang: Lang,
    installed: bool,
    stale: bool,
    node: Option<bool>,
    last_event_at: Option<u64>,
    now_ms: u64,
) -> String {
    let mut parts: Vec<String> = Vec::new();
    if installed {
        parts.push(lang.intg_installed());
    } else if stale {
        parts.push(lang.intg_stale().to_string());
    } else {
        parts.push(lang.intg_not_installed().to_string());
    }
    if let Some(node_ok) = node {
        parts.push(if node_ok {
            lang.intg_node_ready().to_string()
        } else {
            lang.intg_node_missing().to_string()
        });
    }
    let fresh = last_event_at.is_some_and(|t| now_ms.saturating_sub(t) <= LAST_EVENT_FRESH_MS);
    parts.push(if fresh {
        lang.intg_last_event().to_string()
    } else {
        lang.intg_no_event().to_string()
    });
    parts.join(" · ")
}

/// 纯组装（探测已注入）：installed/stale 合成 + message。
pub fn build_status(id: &str, inputs: StatusInputs, lang: Lang, now_ms: u64) -> IntegrationStatus {
    let entries = matches!(inputs.config_state, ConfigState::Installed | ConfigState::Stale);
    let healthy = inputs.config_state == ConfigState::Installed
        && inputs.hook_file.exists
        && inputs.hook_file.matches_bundled;
    let stale = inputs.config_state == ConfigState::Stale || (entries && !healthy);
    IntegrationStatus {
        id: id.to_string(),
        installed: healthy,
        stale,
        version: env!("CARGO_PKG_VERSION").to_string(),
        config_path: String::new(), // 由命令层填充真实路径
        hook_file: inputs.hook_file,
        node_available: inputs.node_available,
        last_event_at: inputs.last_event_at,
        message: doctor_message(
            lang,
            healthy,
            stale,
            inputs.node_available,
            inputs.last_event_at,
            now_ms,
        ),
        error: None,
    }
}

/// 读取 AgentActivity 快照（epoch ms）。
fn read_activity_last_event(
    activity: &crate::http_server::AgentActivity,
    id: &str,
) -> Option<u64> {
    let act = activity.lock().unwrap_or_else(|p| p.into_inner());
    act.get(id).map(|t| epoch_ms(*t))
}

/// node 探测（每次 doctor 现测不缓存，~50-200ms；阻塞 → 只在 spawn_blocking 内调）。
fn detect_node() -> bool {
    std::process::Command::new("node")
        .arg("--version")
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

/// 真实环境探测 + 组装（阻塞 I/O：调用方须在 spawn_blocking 内）。
fn status_for(id: &str, activity_last: Option<u64>, lang: Lang) -> IntegrationStatus {
    let now_ms = epoch_ms(SystemTime::now());
    let version = env!("CARGO_PKG_VERSION").to_string();
    if id == ID_OPENCODE {
        let dir = opencode_dir();
        let (state, cfg) = match opencode_config_state(&dir) {
            Ok(x) => x,
            Err(e) => {
                return IntegrationStatus {
                    id: id.to_string(),
                    installed: false,
                    stale: false,
                    version,
                    config_path: find_opencode_config(&dir).display().to_string(),
                    hook_file: HookFileStatus {
                        exists: false,
                        matches_bundled: false,
                    },
                    node_available: None,
                    last_event_at: activity_last,
                    message: lang.intg_error(&e),
                    error: Some(e),
                };
            }
        };
        let hook = match hook_file_status(&opencode_plugin_file(&dir), BUNDLED_OPENCODE_HOOK) {
            Ok(h) => h,
            Err(e) => {
                return IntegrationStatus {
                    id: id.to_string(),
                    installed: false,
                    stale: false,
                    version,
                    config_path: cfg.display().to_string(),
                    hook_file: HookFileStatus {
                        exists: false,
                        matches_bundled: false,
                    },
                    node_available: None,
                    last_event_at: activity_last,
                    message: lang.intg_error(&e),
                    error: Some(e),
                };
            }
        };
        let mut st = build_status(
            id,
            StatusInputs {
                config_state: state,
                hook_file: hook,
                node_available: None,
                last_event_at: activity_last,
            },
            lang,
            now_ms,
        );
        st.config_path = cfg.display().to_string();
        st
    } else {
        let settings = claude_settings_path();
        let hooks_dir = cc_hooks_dir();
        let canonical = canonical_cc_command(cfg!(windows), &hooks_dir);
        let (state, hook, node) = (
            cc_config_state(&settings, &canonical),
            hook_file_status(&hooks_dir.join("claude-code-hook.js"), BUNDLED_CC_HOOK),
            detect_node(),
        );
        match (state, hook) {
            (Ok(state), Ok(hook)) => {
                let mut st = build_status(
                    id,
                    StatusInputs {
                        config_state: state,
                        hook_file: hook,
                        node_available: Some(node),
                        last_event_at: activity_last,
                    },
                    lang,
                    now_ms,
                );
                st.config_path = settings.display().to_string();
                st
            }
            (Err(e), _) | (_, Err(e)) => IntegrationStatus {
                id: id.to_string(),
                installed: false,
                stale: false,
                version,
                config_path: settings.display().to_string(),
                hook_file: HookFileStatus {
                    exists: false,
                    matches_bundled: false,
                },
                node_available: Some(node),
                last_event_at: activity_last,
                message: lang.intg_error(&e),
                error: Some(e),
            },
        }
    }
}

// ---------------------------------------------------------------------------
// Tauri 命令（async fn + spawn_blocking + Result + plog!，TC-INT-08-5）
// ---------------------------------------------------------------------------

/// 两个接入的完整状态（即 doctor）。进入设置页 / tauri://focus 时调用。
#[tauri::command]
pub async fn integrations_status(
    app: tauri::AppHandle,
) -> Result<Vec<IntegrationStatus>, String> {
    let activity = activity_of(&app);
    let lang = i18n::current();
    let blocking = tauri::async_runtime::spawn_blocking(move || {
        let last_opencode = read_activity_last_event(&activity, ID_OPENCODE);
        let last_cc = read_activity_last_event(&activity, ID_CLAUDE_CODE);
        vec![
            status_for(ID_OPENCODE, last_opencode, lang),
            status_for(ID_CLAUDE_CODE, last_cc, lang),
        ]
    })
    .await
    .map_err(|e| format!("status task join: {e}"))?;
    Ok(blocking)
}

/// 安装/重装（升级即重装：先移除全部特征条目再写 canonical）。
#[tauri::command]
pub async fn integrations_install(
    app: tauri::AppHandle,
    id: String,
) -> Result<IntegrationStatus, String> {
    if id != ID_OPENCODE && id != ID_CLAUDE_CODE {
        return Err(format!("未知接入 id：{id}"));
    }
    let lang = i18n::current();
    let activity = activity_of(&app);
    let install_id = id.clone();
    let result: Result<(), String> =
        tauri::async_runtime::spawn_blocking(move || match install_id.as_str() {
            ID_OPENCODE => install_opencode(&opencode_dir()).map(|_| ()),
            _ => install_cc(&claude_settings_path(), &cc_hooks_dir()),
        })
        .await
        .map_err(|e| format!("install task join: {e}"))?;
    match result {
        Ok(()) => plog!("[pulsepet] integrations install {id}: ok"),
        Err(ref e) => plog!("[pulsepet] integrations install {id}: failed: {e}"),
    }
    result?;
    let mut st = spawn_status(&activity, &id, lang).await?;
    if id == ID_CLAUDE_CODE {
        // §1.4.4：Windows 字面路径无逐事件自愈，卸载/重装后建议新开 CC 会话
        st.message = format!("{} · {}", st.message, lang.intg_uninstall_hint());
    }
    Ok(st)
}

/// 卸载（幂等；二次卸载 no-op）。
#[tauri::command]
pub async fn integrations_uninstall(
    app: tauri::AppHandle,
    id: String,
) -> Result<IntegrationStatus, String> {
    if id != ID_OPENCODE && id != ID_CLAUDE_CODE {
        return Err(format!("未知接入 id：{id}"));
    }
    let lang = i18n::current();
    let activity = activity_of(&app);
    let uninstall_id = id.clone();
    let result: Result<(), String> =
        tauri::async_runtime::spawn_blocking(move || match uninstall_id.as_str() {
            ID_OPENCODE => uninstall_opencode(&opencode_dir()),
            _ => uninstall_cc(&claude_settings_path(), &cc_hooks_dir()),
        })
        .await
        .map_err(|e| format!("uninstall task join: {e}"))?;
    match result {
        Ok(()) => plog!("[pulsepet] integrations uninstall {id}: ok"),
        Err(ref e) => plog!("[pulsepet] integrations uninstall {id}: failed: {e}"),
    }
    result?;
    let mut st = spawn_status(&activity, &id, lang).await?;
    if id == ID_CLAUDE_CODE {
        st.message = format!("{} · {}", st.message, lang.intg_uninstall_hint());
    }
    Ok(st)
}

/// 从 managed state 取 AgentActivity（issue #9 铁律：lib.rs 窗口创建前 manage）。
fn activity_of(app: &tauri::AppHandle) -> crate::http_server::AgentActivity {
    use tauri::Manager;
    app.state::<crate::http_server::AgentActivity>().inner().clone()
}

/// 探测 + 组装单个接入状态（阻塞 I/O → spawn_blocking）。
async fn spawn_status(
    activity: &crate::http_server::AgentActivity,
    id: &str,
    lang: Lang,
) -> Result<IntegrationStatus, String> {
    let activity = activity.clone();
    let id = id.to_string();
    tauri::async_runtime::spawn_blocking(move || {
        let last = read_activity_last_event(&activity, &id);
        status_for(&id, last, lang)
    })
    .await
    .map_err(|e| format!("status task join: {e}"))
}

// ---------------------------------------------------------------------------
// 测试（TC-INT-03 单测可测部分 + TC-INT-08 五子项；tempdir 注入）
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    fn tempdir(tag: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "pulsepet-intg-{tag}-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .map(|d| d.as_nanos())
                .unwrap_or(0)
        ));
        fs::create_dir_all(&dir).expect("tempdir");
        dir
    }

    fn read(p: &Path) -> String {
        fs::read_to_string(p).expect("read")
    }

    // ---- canonical 形态（TC-INT-03-1/2、TC-INT-13-1） ----

    #[test]
    fn canonical_unix_command_matches_design_verbatim() {
        // §1.4.2 逐字钉子（一行串，与文档字面一致——语义上等价于设计示例的
        // 换行折叠形态；分号分段与设计分解一一对应）
        let c = canonical_cc_command(false, Path::new("/x"));
        assert!(c.starts_with("if [ -f \"$HOME/.pulsepet/runtime/hooks-disabled\" ]"));
        assert!(c.contains("[ -t 0 ] || cat >/dev/null; exit 0; fi"));
        assert!(c.contains(
            "if [ -f \"$HOME/.pulsepet/hooks/claude-code-hook.js\" ] && command -v node >/dev/null 2>&1"
        ));
        assert!(c.contains("exec node \"$HOME/.pulsepet/hooks/claude-code-hook.js\" --pulse-pet-managed"));
        assert!(c.ends_with("[ -t 0 ] || cat >/dev/null; exit 0"));
        assert!(!c.contains('\n'), "command 必须是单行（JSON 字符串）");
    }

    #[test]
    fn canonical_windows_command_is_literal_path() {
        let dir = Path::new("C:\\Users\\name\\.pulsepet\\hooks");
        let c = canonical_cc_command(true, dir);
        assert!(c.starts_with("node \"C:\\Users\\name\\.pulsepet\\hooks"));
        assert!(c.ends_with("claude-code-hook.js\" --pulse-pet-managed"));
        assert!(!c.contains("if [")); // 无 POSIX 包装语法
        let entry = canonical_cc_entry(true, dir);
        assert_eq!(entry["shell"], serde_json::json!("powershell"));
        assert_eq!(entry["timeout"], serde_json::json!(3));
        assert_eq!(entry["async"], serde_json::json!(true));
        assert_eq!(entry["asyncRewake"], serde_json::json!(false));
        assert_eq!(entry["type"], serde_json::json!("command"));
        // Unix 条目无 shell 键
        let unix_entry = canonical_cc_entry(false, dir);
        assert!(unix_entry.get("shell").is_none());
    }

    // ---- 安装 / 幂等 / 卸载 / 状态（TC-INT-03、TC-INT-07、TC-INT-08-1/2） ----

    #[test]
    fn install_into_missing_settings_creates_eight_event_keys() {
        let dir = tempdir("cc-empty");
        let settings = dir.join("settings.json");
        let hooks = dir.join("hooks");
        install_cc(&settings, &hooks).expect("install");
        let v: serde_json::Value = serde_json::from_str(&read(&settings)).expect("parse");
        let hooks_obj = v["hooks"].as_object().expect("hooks object");
        assert_eq!(hooks_obj.len(), 8, "恰 8 个事件键");
        for ev in CC_EVENTS {
            let arr = hooks_obj[ev].as_array().expect("array");
            assert_eq!(arr.len(), 1, "{ev} 下恰一条 canonical 条目");
            assert_eq!(arr[0]["command"], serde_json::json!(canonical_cc_command(false, &hooks)));
        }
        // 脚本落点 + 内容与内嵌一致
        assert_eq!(read(&hooks.join("claude-code-hook.js")), BUNDLED_CC_HOOK);
        // 状态：installed
        assert_eq!(
            cc_config_state(&settings, &canonical_cc_command(false, &hooks)).expect("state"),
            ConfigState::Installed
        );
        fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn install_preserves_user_entries_and_key_order() {
        let dir = tempdir("cc-user");
        let settings = dir.join("settings.json");
        let hooks = dir.join("hooks");
        let original = r#"{
  "env": { "ANTHROPIC_BASE_URL": "http://127.0.0.1:15721" },
  "model": "deepseek-v4",
  "hooks": {
    "PreToolUse": [
      { "matcher": "Edit|Write", "hooks": [ { "type": "command", "command": "echo user-hook" } ] },
      { "type": "command", "command": "echo direct-user" }
    ],
    "Notification": [ { "type": "command", "command": "echo notify" } ]
  }
}"#;
        fs::write(&settings, original).expect("write");
        install_cc(&settings, &hooks).expect("install");
        let after = read(&settings);
        let v: serde_json::Value = serde_json::from_str(&after).expect("parse");
        // 用户条目原样保留（matcher 组 + 直接元素 + 其它事件键）
        assert_eq!(v["hooks"]["PreToolUse"][0]["matcher"], serde_json::json!("Edit|Write"));
        assert_eq!(v["hooks"]["PreToolUse"][0]["hooks"][0]["command"], serde_json::json!("echo user-hook"));
        assert_eq!(v["hooks"]["PreToolUse"][1]["command"], serde_json::json!("echo direct-user"));
        assert_eq!(v["hooks"]["Notification"][0]["command"], serde_json::json!("echo notify"));
        // 键序不变（preserve_order）：env 仍在最前
        let keys: Vec<&String> = v.as_object().expect("obj").keys().collect();
        assert_eq!(keys[0], "env");
        // canonical 追加在既有数组尾部
        let pre = v["hooks"]["PreToolUse"].as_array().expect("arr");
        assert_eq!(pre.len(), 3);
        assert!(pre[2]["command"].as_str().expect("cmd").contains(MANAGED_FLAG));
        // 用户条目 + canonical 共存 → installed（P1-1）
        assert_eq!(
            cc_config_state(&settings, &canonical_cc_command(false, &hooks)).expect("state"),
            ConfigState::Installed
        );
        fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn install_is_idempotent_and_upgrades_stale_entries() {
        let dir = tempdir("cc-idem");
        let settings = dir.join("settings.json");
        let hooks = dir.join("hooks");
        install_cc(&settings, &hooks).expect("install 1");
        let once = read(&settings);
        install_cc(&settings, &hooks).expect("install 2");
        assert_eq!(read(&settings), once, "重装幂等（字节级一致）");
        // 手改一条 command（经 JSON 改写——文件内 command 带转义引号，文本替换
        // 不可靠）→ stale；重装修复
        let mut v: serde_json::Value = serde_json::from_str(&once).expect("parse");
        v["hooks"]["Stop"][0]["command"] = serde_json::json!("echo tampered --pulse-pet-managed");
        fs::write(&settings, serde_json::to_string_pretty(&v).unwrap()).expect("write");
        assert_eq!(
            cc_config_state(&settings, &canonical_cc_command(false, &hooks)).expect("state"),
            ConfigState::Stale,
            "command 形态不一致 → stale"
        );
        install_cc(&settings, &hooks).expect("reinstall");
        assert_eq!(read(&settings), once);
        assert_eq!(
            cc_config_state(&settings, &canonical_cc_command(false, &hooks)).expect("state"),
            ConfigState::Installed
        );
        fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn duplicate_feature_entries_are_stale() {
        let dir = tempdir("cc-dup");
        let settings = dir.join("settings.json");
        let hooks = dir.join("hooks");
        install_cc(&settings, &hooks).expect("install");
        // 复制一条 canonical 到 matcher 组内 → 特征条目 >1 → stale（TC-INT-07-4）
        let mut v: serde_json::Value = serde_json::from_str(&read(&settings)).expect("parse");
        let entry = v["hooks"]["Stop"][0].clone();
        v["hooks"]["PreToolUse"]
            .as_array_mut()
            .expect("arr")
            .push(serde_json::json!({ "matcher": ".*", "hooks": [entry] }));
        fs::write(&settings, serde_json::to_string_pretty(&v).unwrap()).expect("write");
        assert_eq!(
            cc_config_state(&settings, &canonical_cc_command(false, &hooks)).expect("state"),
            ConfigState::Stale
        );
        fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn uninstall_removes_feature_entries_recursively_and_cleans_containers() {
        let dir = tempdir("cc-uninstall");
        let settings = dir.join("settings.json");
        let hooks = dir.join("hooks");
        let original = r#"{
  "env": { "A": "1" },
  "hooks": {
    "PreToolUse": [
      { "matcher": "Edit|Write", "hooks": [ { "type": "command", "command": "node /x/hook.js --pulse-pet-managed" } ] },
      { "type": "command", "command": "echo user-direct" }
    ],
    "Notification": [ { "type": "command", "command": "echo notify" } ]
  }
}"#;
        fs::write(&settings, original).expect("write");
        install_cc(&settings, &hooks).expect("install");
        uninstall_cc(&settings, &hooks).expect("uninstall");
        let v: serde_json::Value = serde_json::from_str(&read(&settings)).expect("parse");
        // 特征条目全部移除（含 matcher 组内递归）；用户条目保留
        let text = read(&settings);
        assert!(!text.contains(MANAGED_FLAG));
        assert!(!text.contains(".pulsepet"));
        assert!(text.contains("echo user-direct"));
        assert!(text.contains("echo notify"));
        assert!(text.contains("\"env\""));
        // 空容器清理：我们建的事件键删除；Notification（用户条目仍在）保留；
        // PreToolUse 里 matcher 组被掏空但组壳保留（保守，仅移除特征条目）
        let hooks_obj = v["hooks"].as_object().expect("hooks");
        assert!(hooks_obj.contains_key("Notification"));
        assert!(hooks_obj.contains_key("PreToolUse"));
        assert!(!hooks_obj.contains_key("Stop"));
        // 未注册新事件键 → hooks 未被清空（Notification/PreToolUse 仍在）→ hooks 键保留
        // 脚本删除
        assert!(!hooks.join("claude-code-hook.js").exists());
        assert!(!hooks.join("package.json").exists());
        // 状态 → 未安装
        assert_eq!(
            cc_config_state(&settings, &canonical_cc_command(false, &hooks)).expect("state"),
            ConfigState::NotInstalled
        );
        // 二次卸载 no-op（文件字节不变）
        let before = read(&settings);
        uninstall_cc(&settings, &hooks).expect("uninstall 2");
        assert_eq!(read(&settings), before);
        fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn uninstall_cleans_hooks_key_when_all_events_emptied() {
        let dir = tempdir("cc-cc-clean");
        let settings = dir.join("settings.json");
        let hooks = dir.join("hooks");
        fs::write(&settings, "{}").expect("write");
        install_cc(&settings, &hooks).expect("install");
        uninstall_cc(&settings, &hooks).expect("uninstall");
        let v: serde_json::Value = serde_json::from_str(&read(&settings)).expect("parse");
        assert!(v.get("hooks").is_none(), "hooks 对象空则删 hooks 键");
        fs::remove_dir_all(&dir).ok();
    }

    // ---- 防御路径（TC-INT-08-1/2/3） ----

    #[test]
    fn parse_failure_does_not_write() {
        let dir = tempdir("cc-parse");
        let settings = dir.join("settings.json");
        let hooks = dir.join("hooks");
        for bad in ["{ not json", "[1,2]", "\"str\"", "{\n\"hooks\": []\n}"] {
            fs::write(&settings, bad).expect("write");
            let err = install_cc(&settings, &hooks).expect_err("should refuse");
            assert!(!err.is_empty());
            assert_eq!(read(&settings), bad, "原文件字节不变（不落笔）");
        }
        fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn symlink_settings_is_rejected() {
        #[cfg(unix)]
        {
            let dir = tempdir("cc-symlink");
            let real = dir.join("real.json");
            let link = dir.join("link.json");
            fs::write(&real, "{}").expect("write");
            std::os::unix::fs::symlink(&real, &link).expect("symlink");
            let err = install_cc(&link, &dir.join("hooks")).expect_err("refuse symlink");
            assert!(err.contains("符号链接") || err.contains("symlink"));
            fs::remove_dir_all(&dir).ok();
        }
    }

    #[test]
    fn backup_created_and_old_backups_pruned() {
        let dir = tempdir("cc-backup");
        let settings = dir.join("settings.json");
        let hooks = dir.join("hooks");
        fs::write(&settings, "{}").expect("write");
        // 预置一份“旧备份”
        let old = dir.join("settings.json.pulsepet-backup-20200101T000000000.json");
        fs::write(&old, "{}").expect("write");
        install_cc(&settings, &hooks).expect("install");
        let backups: Vec<_> = fs::read_dir(&dir)
            .expect("readdir")
            .flatten()
            .map(|e| e.file_name().to_string_lossy().to_string())
            .filter(|n| n.starts_with("settings.json.pulsepet-backup-"))
            .collect();
        assert_eq!(backups.len(), 1, "仅保留最近 1 份（旧备份被清理）");
        assert!(!backups[0].contains("20200101"), "旧备份已删");
        // 备份内容 = 安装前的原文（在二次安装清理它之前读取）
        let backup_path = dir.join(&backups[0]);
        assert_eq!(read(&backup_path), "{}");
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mode = fs::metadata(&backup_path).expect("meta").permissions().mode() & 0o777;
            assert_eq!(mode, 0o600);
        }
        // 再次安装（重装总是重写 → 备份滚动更新，仍只 1 份）
        install_cc(&settings, &hooks).expect("install 2");
        let backups2 = fs::read_dir(&dir)
            .expect("readdir")
            .flatten()
            .map(|e| e.file_name().to_string_lossy().to_string())
            .filter(|n| n.starts_with("settings.json.pulsepet-backup-"))
            .count();
        assert_eq!(backups2, 1);
        // 无 .tmp 残留（原子写 rename 完成）
        let tmps = fs::read_dir(&dir)
            .expect("readdir")
            .flatten()
            .map(|e| e.file_name().to_string_lossy().to_string())
            .filter(|n| n.ends_with(".tmp"))
            .count();
        assert_eq!(tmps, 0);
        fs::remove_dir_all(&dir).ok();
    }

    // ---- 状态组装（build_status 纯函数） ----

    #[test]
    fn build_status_combines_states() {
        let lang = Lang::Zh;
        let ok_hook = HookFileStatus {
            exists: true,
            matches_bundled: true,
        };
        // installed + node 就绪 + 事件新鲜
        let st = build_status(
            ID_CLAUDE_CODE,
            StatusInputs {
                config_state: ConfigState::Installed,
                hook_file: ok_hook.clone(),
                node_available: Some(true),
                last_event_at: Some(1_000),
            },
            lang,
            2_000,
        );
        assert!(st.installed && !st.stale);
        assert!(st.message.contains("已安装"));
        assert!(st.message.contains("node 已就绪"));
        assert!(st.message.contains("事件正常"));
        // 事件超 10 分钟 → 最近无事件
        let st = build_status(
            ID_CLAUDE_CODE,
            StatusInputs {
                config_state: ConfigState::Installed,
                hook_file: ok_hook.clone(),
                node_available: Some(false),
                last_event_at: Some(1_000),
            },
            lang,
            1_000 + LAST_EVENT_FRESH_MS + 1,
        );
        assert!(st.message.contains("最近无事件"));
        assert!(st.message.contains("未检测到 node"));
        // 脚本 md5 不一致（配置 Installed 但文件过时）→ stale
        let st = build_status(
            ID_CLAUDE_CODE,
            StatusInputs {
                config_state: ConfigState::Installed,
                hook_file: HookFileStatus {
                    exists: true,
                    matches_bundled: false,
                },
                node_available: None,
                last_event_at: None,
            },
            lang,
            0,
        );
        assert!(!st.installed && st.stale, "hook 文件与内嵌不一致 → 需更新");
        // 未安装
        let st = build_status(
            ID_OPENCODE,
            StatusInputs {
                config_state: ConfigState::NotInstalled,
                hook_file: HookFileStatus {
                    exists: false,
                    matches_bundled: false,
                },
                node_available: None,
                last_event_at: None,
            },
            Lang::En,
            0,
        );
        assert!(!st.installed && !st.stale);
        assert!(st.message.contains("Not installed"));
    }

    // ---- opencode 接入（TC-INT-12 单测面） ----

    #[test]
    fn opencode_install_uninstall_roundtrip() {
        let dir = tempdir("oc");
        // 空目录 → 新建 opencode.json 骨架 + 插件脚本
        let cfg = install_opencode(&dir).expect("install");
        assert_eq!(cfg, dir.join("opencode.json"));
        assert!(read(&cfg).contains(opencode_config::MARKER));
        assert_eq!(
            read(&opencode_plugin_file(&dir)),
            BUNDLED_OPENCODE_HOOK,
            "插件文件与内嵌逐字一致"
        );
        assert_eq!(
            opencode_config_state(&dir).expect("state").0,
            ConfigState::Installed
        );
        // 幂等
        install_opencode(&dir).expect("install 2");
        assert_eq!(
            opencode_config_state(&dir).expect("state").0,
            ConfigState::Installed
        );
        // 卸载：marker 移除 + 脚本删除
        uninstall_opencode(&dir).expect("uninstall");
        assert!(!read(&cfg).contains(opencode_config::MARKER));
        assert!(!opencode_plugin_file(&dir).exists());
        assert_eq!(
            opencode_config_state(&dir).expect("state").0,
            ConfigState::NotInstalled
        );
        // 二次卸载 no-op
        uninstall_opencode(&dir).expect("uninstall 2");
        fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn opencode_prefers_jsonc_when_no_json() {
        let dir = tempdir("oc-jsonc");
        fs::write(dir.join("opencode.jsonc"), "{\n  // 注释\n  \"plugin\": [\"x\"]\n}\n")
            .expect("write");
        let cfg = install_opencode(&dir).expect("install");
        assert_eq!(cfg, dir.join("opencode.jsonc"));
        let text = read(&cfg);
        assert!(text.contains("// 注释"), "JSONC 注释保留");
        assert!(text.contains(opencode_config::MARKER));
        assert!(text.contains("\"x\""));
        fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn opencode_stale_when_script_differs() {
        let dir = tempdir("oc-stale");
        install_opencode(&dir).expect("install");
        // 手改脚本 → md5 不一致 → stale（重装即修复）
        fs::write(opencode_plugin_file(&dir), "// tampered\n").expect("write");
        assert_eq!(
            opencode_config_state(&dir).expect("state").0,
            ConfigState::Stale
        );
        install_opencode(&dir).expect("reinstall");
        assert_eq!(
            opencode_config_state(&dir).expect("state").0,
            ConfigState::Installed
        );
        fs::remove_dir_all(&dir).ok();
    }

    // ---- TC-INT-08-5：线程与 panic 纪律（源码级钉子） ----

    #[test]
    fn command_paths_have_no_unwrap_or_expect() {
        // 命令路径零 panic：模块源码的非测试部分禁 unwrap()/expect(
        //（测试部分允许）。include_str! 读自身源文件。
        let src = include_str!("mod.rs");
        let code = src.split("#[cfg(test)]").next().unwrap_or("");
        assert!(
            !code.contains(".unwrap()"),
            "integrations 命令路径出现 unwrap()（issue #9 纪律）"
        );
        assert!(
            !code.contains(".expect("),
            "integrations 命令路径出现 expect()（issue #9 纪律）"
        );
        // 三命令 async + spawn_blocking 纪律的结构钉子
        for cmd in [
            "pub async fn integrations_status",
            "pub async fn integrations_install",
            "pub async fn integrations_uninstall",
        ] {
            assert!(code.contains(cmd), "缺少 async 命令：{cmd}");
        }
        assert!(code.contains("spawn_blocking"), "阻塞 I/O 须经 spawn_blocking");
        assert!(code.contains("plog!"), "安装动作须落 plog!");
    }

    #[test]
    fn commands_are_async_futures() {
        // 编译期证明：三命令为 async fn——返回值可被 Box::pin 成 Future（同步
        // fn 的返回 Result 无法通过这些类型断言，TC-INT-08-5）。
        type StatusFut = std::pin::Pin<
            Box<dyn std::future::Future<Output = Result<Vec<IntegrationStatus>, String>>>,
        >;
        type OneFut = std::pin::Pin<
            Box<dyn std::future::Future<Output = Result<IntegrationStatus, String>>>,
        >;
        let _status: fn(tauri::AppHandle) -> StatusFut =
            |app| Box::pin(integrations_status(app));
        let _install: fn(tauri::AppHandle, String) -> OneFut =
            |app, id| Box::pin(integrations_install(app, id));
        let _uninstall: fn(tauri::AppHandle, String) -> OneFut =
            |app, id| Box::pin(integrations_uninstall(app, id));
    }
}
