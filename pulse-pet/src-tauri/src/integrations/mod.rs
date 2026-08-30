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

/// Windows 子进程抑制控制台窗口标志（issue #19：GUI 子系统下裸 spawn 控制台
/// 子进程会闪窗抢焦点）。action_exec.rs 有一份同语义常量（模块解耦各持一份）。
#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

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

// 接入 id 常量（ID_OPENCODE / ID_CLAUDE_CODE）已迁 `crate::agents`（v2
// registry：AgentSpec.id 为唯一事实源，本模块经查表引用）。

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

/// canonical 组内 hook 条目（§1.4.2 勘误 2026-08-24：command 条目在 matcher 组
/// 的内层 hooks 数组）。Windows 的 `shell` 字段按 CC schema 语义（S8：per-hook
/// 执行器选择）落在 hook 条目上——组级无此字段。
fn canonical_cc_hook(windows: bool, hooks_dir: &Path) -> serde_json::Value {
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

/// canonical matcher 组（事件数组直接元素；外层**省略 matcher = 全捕**，
/// §1.4.2 勘误形态——满足 PreToolUse 脚本内分类需求）。
fn canonical_cc_group(windows: bool, hooks_dir: &Path) -> serde_json::Value {
    serde_json::json!({ "hooks": [canonical_cc_hook(windows, hooks_dir)] })
}

/// 「pulse-pet 特征」= type:"command" 且 command 含 `--pulse-pet-managed` 或
/// pulsepet 路径（§1.4.3）。特征条目的**合法位置**是 matcher 组内层 hooks 数组；
/// 出现在事件数组直接元素 = 初版坏形态（CC zod 拒绝，勘误前的 R1 产物）。
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

/// 移除事件数组内全部特征条目（§1.4.3 勘误口径）：
/// 1. matcher 组 `{"matcher"?, "hooks":[…]}` 内层的特征条目 → 移除；**特征清空
///    的组整组移除**（只移除因特征而空的组，用户本就空的组不动）；
/// 2. 直接元素位置的坏形态特征条目 → 移除（用户现场修复路径）。
/// 返回移除的特征条目数。
fn remove_feature_entries(arr: &mut Vec<serde_json::Value>) -> usize {
    let mut removed = 0usize;
    let mut emptied_groups: Vec<usize> = Vec::new();
    for (i, entry) in arr.iter_mut().enumerate() {
        if let Some(hooks) = entry.get_mut("hooks").and_then(|h| h.as_array_mut()) {
            let before = hooks.len();
            hooks.retain(|h| !is_feature_entry(h));
            let n = before - hooks.len();
            removed += n;
            if n > 0 && hooks.is_empty() {
                emptied_groups.push(i);
            }
        }
    }
    // 从后往前移除空组（索引稳定）
    for i in emptied_groups.into_iter().rev() {
        arr.remove(i);
    }
    // 坏形态直接元素（裸 command 条目）
    let before = arr.len();
    arr.retain(|e| !is_feature_entry(e));
    removed + (before - arr.len())
}

/// 统计事件数组（§1.4.3 勘误口径）：`(组内特征条目数, 组内与 canonical 完全
/// 一致数, 坏形态直接元素特征条目数)`。CC schema 两层结构：事件数组 → matcher
/// 组 → hooks 数组 → command 条目；不递归更深层（schema 无此形态）。
fn count_key(arr: &[serde_json::Value], canonical: &str) -> (usize, usize, usize) {
    let mut in_groups = 0;
    let mut canonical_ok = 0;
    let mut bad_form = 0;
    for e in arr {
        if let Some(hooks) = e.get("hooks").and_then(|h| h.as_array()) {
            for h in hooks {
                if is_feature_entry(h) {
                    in_groups += 1;
                    if h.get("command").and_then(|v| v.as_str()) == Some(canonical) {
                        canonical_ok += 1;
                    }
                }
            }
        }
        // 直接元素位置的特征条目 = 初版坏形态残留
        if is_feature_entry(e) {
            bad_form += 1;
        }
    }
    (in_groups, canonical_ok, bad_form)
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
                let (in_groups, canonical_ok, bad_form) = count_key(arr, canonical);
                total += in_groups + bad_form;
                // 勘误口径：组内特征恰 1 且与 canonical 一致、无坏形态残留
                if bad_form > 0 || in_groups != 1 || canonical_ok != 1 {
                    all_ok = false;
                }
            }
        }
    }
    // 其它事件键里的特征条目（用户复制走的，含坏形态）也计入总量（多出 → stale）
    for (k, val) in hooks {
        if !CC_EVENTS.contains(&k.as_str()) {
            if let Some(arr) = val.as_array() {
                let (in_groups, _, bad_form) = count_key(arr, canonical);
                total += in_groups + bad_form;
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
/// 每步动作与结果落 plog!（排障口径：日志末行 = 死前最后完成步骤）。
pub fn install_cc(settings: &Path, hooks_dir: &Path) -> Result<(), String> {
    plog!(
        "[pulsepet] integrations cc install: begin (settings={}, exists={}, hooks_dir={})",
        settings.display(),
        settings.is_file(),
        hooks_dir.display()
    );
    let existed = settings.is_file();
    assert_not_symlink(settings).inspect_err(|e| {
        plog!("[pulsepet] integrations cc install: refuse symlink: {e}");
    })?;
    // 解析失败/结构非法 → 报 error 不落笔
    let root = match read_settings_object(settings) {
        Ok(v) => v,
        Err(e) => {
            plog!("[pulsepet] integrations cc install: settings unusable, abort (no write): {e}");
            return Err(e);
        }
    };
    if !existed {
        plog!("[pulsepet] integrations cc install: settings missing → creating fresh {{}}");
    }
    let mut root = root.unwrap_or_else(|| serde_json::json!({}));
    {
        let obj = root
            .as_object_mut()
            .ok_or_else(|| "顶层不是对象".to_string())?;
        if let Some(h) = obj.get("hooks") {
            if !h.is_object() {
                let e = "hooks 不是对象".to_string();
                plog!("[pulsepet] integrations cc install: {e}, abort (no write)");
                return Err(e);
            }
        }
        // 1) 移除全部特征条目（所有事件键，含 matcher 组内递归——升级即重装）
        let mut removed_total = 0usize;
        if let Some(hooks) = obj.get_mut("hooks").and_then(|h| h.as_object_mut()) {
            for (k, v) in hooks.iter_mut() {
                if let Some(arr) = v.as_array_mut() {
                    let n = remove_feature_entries(arr);
                    if n > 0 {
                        plog!("[pulsepet] integrations cc install: removed {n} feature entr{y} under hooks.{k}", y = if n > 1 { "ies" } else { "y" });
                    }
                    removed_total += n;
                }
            }
        }
        if removed_total == 0 {
            plog!("[pulsepet] integrations cc install: no existing feature entries (fresh install)");
        }
        // 2) 逐事件追加 canonical matcher 组（事件数组缺失则建；非数组 → 不落笔）
        let entry = canonical_cc_group(cfg!(windows), hooks_dir);
        let obj = root
            .as_object_mut()
            .ok_or_else(|| "顶层不是对象".to_string())?;
        let hooks = obj
            .entry("hooks")
            .or_insert_with(|| serde_json::json!({}));
        let hooks_obj = hooks
            .as_object_mut()
            .ok_or_else(|| "hooks 不是对象".to_string())?;
        let mut created_keys = 0usize;
        for ev in CC_EVENTS {
            let arr = hooks_obj
                .entry(ev)
                .or_insert_with(|| {
                    created_keys += 1;
                    serde_json::json!([])
                });
            let arr = match arr.as_array_mut() {
                Some(a) => a,
                None => {
                    let e = format!("hooks.{ev} 不是数组");
                    plog!("[pulsepet] integrations cc install: {e}, abort (no write)");
                    return Err(e);
                }
            };
            arr.push(entry.clone());
        }
        plog!(
            "[pulsepet] integrations cc install: appended canonical entries for {} events ({} event keys created)",
            CC_EVENTS.len(),
            created_keys
        );
    }
    // 3) 脚本先行（settings 写失败时至多遗留无害脚本文件，doctor 钉住重装修复）
    write_cc_hook_files(hooks_dir).inspect_err(|e| {
        plog!("[pulsepet] integrations cc install: write hook files failed: {e}");
    })?;
    plog!(
        "[pulsepet] integrations cc install: hook script written ({} bytes, matches bundled)",
        BUNDLED_CC_HOOK.len()
    );
    // 4) 备份 + 原子写（serde_json preserve_order：用户 env 等键序不变）
    let out = format!("{}\n", serde_json::to_string_pretty(&root).map_err(|e| e.to_string())?);
    backup_file(settings).inspect_err(|e| {
        plog!("[pulsepet] integrations cc install: backup failed: {e}");
    })?;
    atomic_write(settings, &out).inspect_err(|e| {
        plog!("[pulsepet] integrations cc install: atomic write failed: {e}");
    })?;
    plog!(
        "[pulsepet] integrations cc install: done ({} bytes → {}, backup kept: 1)",
        out.len(),
        settings.display()
    );
    Ok(())
}

/// 卸载 claude-code 接入：移除全部特征条目（递归进 matcher 组）→ 事件数组空则
/// 删事件键 → hooks 空则删 hooks 键；删除 hook 脚本；二次卸载 no-op。
pub fn uninstall_cc(settings: &Path, hooks_dir: &Path) -> Result<(), String> {
    plog!(
        "[pulsepet] integrations cc uninstall: begin (settings={}, exists={})",
        settings.display(),
        settings.is_file()
    );
    assert_not_symlink(settings).inspect_err(|e| {
        plog!("[pulsepet] integrations cc uninstall: refuse symlink: {e}");
    })?;
    if let Some(mut root) = read_settings_object(settings)? {
        let mut changed = false;
        {
            let obj = root
                .as_object_mut()
                .ok_or_else(|| "顶层不是对象".to_string())?;
            if let Some(hooks) = obj.get_mut("hooks").and_then(|h| h.as_object_mut()) {
                let mut empty_keys: Vec<String> = Vec::new();
                let mut removed_total = 0usize;
                for (k, v) in hooks.iter_mut() {
                    if let Some(arr) = v.as_array_mut() {
                        let removed = remove_feature_entries(arr);
                        if removed > 0 {
                            plog!("[pulsepet] integrations cc uninstall: removed {removed} feature entries under hooks.{k}");
                            changed = true;
                            removed_total += removed;
                            if arr.is_empty() {
                                empty_keys.push(k.clone());
                            }
                        }
                    }
                }
                if removed_total == 0 {
                    plog!("[pulsepet] integrations cc uninstall: no feature entries in settings (config already clean)");
                }
                for k in &empty_keys {
                    hooks.remove(k);
                    plog!("[pulsepet] integrations cc uninstall: removed empty event key hooks.{k}");
                }
                if changed && hooks.is_empty() {
                    obj.remove("hooks");
                    plog!("[pulsepet] integrations cc uninstall: hooks object empty → removed hooks key");
                }
            }
        }
        if changed {
            let out =
                format!("{}\n", serde_json::to_string_pretty(&root).map_err(|e| e.to_string())?);
            backup_file(settings).inspect_err(|e| {
                plog!("[pulsepet] integrations cc uninstall: backup failed: {e}");
            })?;
            atomic_write(settings, &out).inspect_err(|e| {
                plog!("[pulsepet] integrations cc uninstall: atomic write failed: {e}");
            })?;
            plog!("[pulsepet] integrations cc uninstall: settings rewritten ({} bytes)", out.len());
        }
    } else {
        plog!("[pulsepet] integrations cc uninstall: settings missing → skip config rewrite");
    }
    // 删除脚本 + 我们落的 package.json（内容校验，用户手改过则保留）
    let _ = std::fs::remove_file(hooks_dir.join("claude-code-hook.js"));
    let pkg = hooks_dir.join("package.json");
    if let Ok(content) = std::fs::read_to_string(&pkg) {
        if content.trim() == "{\"type\":\"module\"}" {
            let _ = std::fs::remove_file(&pkg);
        }
    }
    plog!(
        "[pulsepet] integrations cc uninstall: done (hook file removed: {})",
        !hooks_dir.join("claude-code-hook.js").exists()
    );
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
    /// §二十（V2-OPEN-ITEMS）：统计源状态行（被动发现式读取的三态呈现）。
    /// 构造点先填 [`StatsSourceStatus::placeholder`]，真值由 status_for /
    /// integrations_status 覆盖（`stats_status_of` → `token_stats::probe_spec`）。
    pub stats: StatsSourceStatus,
}

/// §二十：统计源探测结果的 wire 形态（serde camelCase；state 为字符串枚举
/// ——"ok" / "missing" / "failed" / "none"，前端查表文案键）。
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct StatsSourceStatus {
    /// "ok" | "missing" | "failed" | "none"（none = 无统计源，仅事件链形态）。
    pub state: String,
    /// 数据源路径（Ok/Missing 态 hover title）。
    pub path: Option<String>,
    /// Missing 原因 / Failed 错误摘要（hover title 追加段）。
    pub detail: Option<String>,
}

impl StatsSourceStatus {
    /// 构造点占位（IntegrationStatus 字段必填）；真值经 stats_status_of 覆盖。
    pub fn placeholder() -> Self {
        Self {
            state: "none".to_string(),
            path: None,
            detail: None,
        }
    }
}

/// §二十：probe → wire（消费 `token_stats::probe_spec`——阻塞 I/O，调用方
/// 须在 spawn_blocking 内；判据与 query 编排同源，见 token_stats §20 区块）。
fn stats_status_of(stats: crate::agents::StatsSource) -> StatsSourceStatus {
    let p = crate::token_stats::probe_spec(stats);
    StatsSourceStatus {
        state: match p.state {
            crate::token_stats::ProbeState::Ok => "ok",
            crate::token_stats::ProbeState::Missing(_) => "missing",
            crate::token_stats::ProbeState::Failed(_) => "failed",
            crate::token_stats::ProbeState::NoSource => "none",
        }
        .to_string(),
        path: p.path,
        detail: match p.state {
            crate::token_stats::ProbeState::Missing(m)
            | crate::token_stats::ProbeState::Failed(m) => Some(m),
            _ => None,
        },
    }
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
        stats: StatsSourceStatus::placeholder(),
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
/// Windows 下必须 CREATE_NO_WINDOW（issue #19）：release 为 GUI 子系统，裸 spawn
/// 控制台子进程会闪现控制台窗口扰动面板焦点 → doctor/focus 自激励死循环。
fn detect_node() -> bool {
    let mut cmd = std::process::Command::new("node");
    cmd.arg("--version");
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
    cmd.output().map(|o| o.status.success()).unwrap_or(false)
}

/// 状态名（日志用；与 ConfigState 三态对应）。
fn state_name(s: ConfigState) -> &'static str {
    match s {
        ConfigState::NotInstalled => "not-installed",
        ConfigState::Installed => "installed",
        ConfigState::Stale => "stale",
    }
}

/// 真实环境探测 + 组装（阻塞 I/O：调用方须在 spawn_blocking 内）。
/// 关键探测结论落 plog!（configPath 存在性 / 三态判定 / node 探测耗时 /
/// hookFile 对账）——doctor 是排障第一入口。
///
/// v2 registry（agent-registry §8.1）：原 if/else 两分支拆为
/// `status_opencode` / `status_cc` 两函数，经 `spec.integration.status_probe`
/// 指针分发；node 探测由 `needs_node_probe` 字段控制（查表分发层现测）。
/// **未知 id 明确 Err**——不再默认落 CC 探测（消静默错误 ①，§8.7.2 P1 钉 4）。
pub fn status_for(
    id: &str,
    activity_last: Option<u64>,
    lang: Lang,
) -> Result<IntegrationStatus, String> {
    let Some(spec) = crate::agents::find(id) else {
        return Err(format!("未知接入 id：{id}"));
    };
    let Some(integ) = spec.integration.as_ref() else {
        return Err(format!("agent {id} 无本地接入形态"));
    };
    let mut st = probe_status(integ, activity_last, lang);
    // §二十：统计源状态行（spawn_status / install / uninstall 刷新路径均经
    // 此处，自动携带真值；阻塞 I/O——调用方须在 spawn_blocking 内）
    st.stats = stats_status_of(spec.stats);
    Ok(st)
}

/// 查表探测分发：按 IntegrationSpec 执行——node 现测仅 `needs_node_probe`
/// 的接入执行（CC 独有 spawn node 提为注册表字段），探测函数经指针分发。
fn probe_status(
    integ: &crate::agents::IntegrationSpec,
    activity_last: Option<u64>,
    lang: Lang,
) -> IntegrationStatus {
    if integ.needs_node_probe {
        let t0 = std::time::Instant::now();
        let node = detect_node();
        let probe_ms = t0.elapsed().as_millis();
        plog!("[pulsepet] integrations node probe: available={node} ({probe_ms}ms)");
        (integ.status_probe)(Some(node), activity_last, lang)
    } else {
        (integ.status_probe)(None, activity_last, lang)
    }
}

/// opencode 接入探测（status_for 拆分；阻塞 I/O，调用方须在 spawn_blocking
/// 内）。node 恒 None（opencode 无 node 依赖，由 needs_node_probe=false 保证）。
pub fn status_opencode(
    node: Option<bool>,
    activity_last: Option<u64>,
    lang: Lang,
) -> IntegrationStatus {
    let now_ms = epoch_ms(SystemTime::now());
    let version = env!("CARGO_PKG_VERSION").to_string();
    let dir = opencode_dir();
    let (state, cfg) = match opencode_config_state(&dir) {
        Ok(x) => x,
        Err(e) => {
            plog!("[pulsepet] integrations status opencode: probe failed: {e}");
            return IntegrationStatus {
                id: crate::agents::ID_OPENCODE.to_string(),
                installed: false,
                stale: false,
                version,
                config_path: find_opencode_config(&dir).display().to_string(),
                hook_file: HookFileStatus {
                    exists: false,
                    matches_bundled: false,
                },
                node_available: node,
                last_event_at: activity_last,
                message: lang.intg_error(&e),
                error: Some(e),
                stats: StatsSourceStatus::placeholder(),
            };
        }
    };
    let hook = match hook_file_status(&opencode_plugin_file(&dir), BUNDLED_OPENCODE_HOOK) {
        Ok(h) => h,
        Err(e) => {
            plog!("[pulsepet] integrations status opencode: hook file probe failed: {e}");
            return IntegrationStatus {
                id: crate::agents::ID_OPENCODE.to_string(),
                installed: false,
                stale: false,
                version,
                config_path: cfg.display().to_string(),
                hook_file: HookFileStatus {
                    exists: false,
                    matches_bundled: false,
                },
                node_available: node,
                last_event_at: activity_last,
                message: lang.intg_error(&e),
                error: Some(e),
                stats: StatsSourceStatus::placeholder(),
            };
        }
    };
    plog!(
        "[pulsepet] integrations status opencode: cfg={} (exists={}) marker={} plugin file (exists={}, matches_bundled={}) → {}",
        cfg.display(),
        cfg.is_file(),
        state != ConfigState::NotInstalled,
        hook.exists,
        hook.matches_bundled,
        state_name(state)
    );
    let mut st = build_status(
        crate::agents::ID_OPENCODE,
        StatusInputs {
            config_state: state,
            hook_file: hook,
            node_available: node,
            last_event_at: activity_last,
        },
        lang,
        now_ms,
    );
    st.config_path = cfg.display().to_string();
    st
}

/// claude-code 接入探测（status_for 拆分；阻塞 I/O，调用方须在
/// spawn_blocking 内）。node 探测结果由查表分发层注入（needs_node_probe）。
pub fn status_cc(
    node: Option<bool>,
    activity_last: Option<u64>,
    lang: Lang,
) -> IntegrationStatus {
    let now_ms = epoch_ms(SystemTime::now());
    let version = env!("CARGO_PKG_VERSION").to_string();
    let settings = claude_settings_path();
    let hooks_dir = cc_hooks_dir();
    let canonical = canonical_cc_command(cfg!(windows), &hooks_dir);
    let (state, hook) = (
        cc_config_state(&settings, &canonical),
        hook_file_status(&hooks_dir.join("claude-code-hook.js"), BUNDLED_CC_HOOK),
    );
    match (state, hook) {
        (Ok(state), Ok(hook)) => {
            plog!(
                "[pulsepet] integrations status claude-code: settings={} (exists={}) → {} · hook file (exists={}, matches_bundled={}) · node={}",
                settings.display(),
                settings.is_file(),
                state_name(state),
                hook.exists,
                hook.matches_bundled,
                node.unwrap_or(false)
            );
            let mut st = build_status(
                crate::agents::ID_CLAUDE_CODE,
                StatusInputs {
                    config_state: state,
                    hook_file: hook,
                    node_available: node,
                    last_event_at: activity_last,
                },
                lang,
                now_ms,
            );
            st.config_path = settings.display().to_string();
            st
        }
        (Err(e), _) | (_, Err(e)) => {
            plog!(
                "[pulsepet] integrations status claude-code: probe failed: {e} · node={}",
                node.unwrap_or(false)
            );
            IntegrationStatus {
                id: crate::agents::ID_CLAUDE_CODE.to_string(),
                installed: false,
                stale: false,
                version,
                config_path: settings.display().to_string(),
                hook_file: HookFileStatus {
                    exists: false,
                    matches_bundled: false,
                },
                node_available: node,
                last_event_at: activity_last,
                message: lang.intg_error(&e),
                error: Some(e),
                stats: StatsSourceStatus::placeholder(),
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Tauri 命令（async fn + spawn_blocking + Result + plog!，TC-INT-08-5）
// ---------------------------------------------------------------------------

/// 两个接入的完整状态（即 doctor）。进入设置页 / tauri://focus 时调用。
/// v2 registry（§8.1）：原 `vec![两行]` 硬编码 → 遍历 agents::AGENTS
/// （无接入形态的 agent 不出卡；卡序 = 注册表序，与改前一致）。
#[tauri::command]
pub async fn integrations_status(
    app: tauri::AppHandle,
) -> Result<Vec<IntegrationStatus>, String> {
    let activity = activity_of(&app);
    let lang = i18n::current();
    let blocking = tauri::async_runtime::spawn_blocking(move || {
        let mut out = Vec::new();
        for spec in crate::agents::AGENTS {
            let Some(integ) = spec.integration.as_ref() else {
                continue;
            };
            let last = read_activity_last_event(&activity, spec.id);
            // §二十：统计源状态行（阻塞 I/O——Ok 态真连 db 做 schema 校验，
            // 与 doctor 探测同款 blocking 纪律；无接入形态的 agent 不出卡，
            // 其源探测跳过）
            let mut st = probe_status(integ, last, lang);
            st.stats = stats_status_of(spec.stats);
            out.push(st);
        }
        out
    })
    .await
    .map_err(|e| format!("status task join: {e}"))?;
    Ok(blocking)
}

/// 安装/重装（升级即重装：先移除全部特征条目再写 canonical）。
/// v2 registry（§8.1）：id 守卫 + match 二元分发 → `agents::find` + 注册表
/// 函数指针；CC 独有安装提示 → `install_hint` 字段。
#[tauri::command]
pub async fn integrations_install(
    app: tauri::AppHandle,
    id: String,
) -> Result<IntegrationStatus, String> {
    let Some(spec) = crate::agents::find(&id) else {
        return Err(format!("未知接入 id：{id}"));
    };
    let Some(integ) = spec.integration.as_ref() else {
        return Err(format!("agent {id} 无本地接入形态"));
    };
    let lang = i18n::current();
    let activity = activity_of(&app);
    let install_fn = integ.install;
    let result: Result<(), String> =
        tauri::async_runtime::spawn_blocking(move || install_fn())
            .await
            .map_err(|e| format!("install task join: {e}"))?;
    match result {
        Ok(()) => plog!("[pulsepet] integrations install {id}: ok"),
        Err(ref e) => plog!("[pulsepet] integrations install {id}: failed: {e}"),
    }
    result?;
    let mut st = spawn_status(&activity, &id, lang).await?;
    if integ.install_hint {
        // §1.4.4：Windows 字面路径无逐事件自愈，安装后建议新开 CC 会话
        // v2 M2 L1（P2-1）：安装路径用安装措辞（不再复用卸载文案）
        st.message = format!("{} · {}", st.message, action_hint(lang, "install"));
    }
    Ok(st)
}

/// 卸载（幂等；二次卸载 no-op）。v2 registry（§8.1）：同 install——查表 +
/// 函数指针 + install_hint 字段。
#[tauri::command]
pub async fn integrations_uninstall(
    app: tauri::AppHandle,
    id: String,
) -> Result<IntegrationStatus, String> {
    let Some(spec) = crate::agents::find(&id) else {
        return Err(format!("未知接入 id：{id}"));
    };
    let Some(integ) = spec.integration.as_ref() else {
        return Err(format!("agent {id} 无本地接入形态"));
    };
    let lang = i18n::current();
    let activity = activity_of(&app);
    let uninstall_fn = integ.uninstall;
    let result: Result<(), String> =
        tauri::async_runtime::spawn_blocking(move || uninstall_fn())
            .await
            .map_err(|e| format!("uninstall task join: {e}"))?;
    match result {
        Ok(()) => plog!("[pulsepet] integrations uninstall {id}: ok"),
        Err(ref e) => plog!("[pulsepet] integrations uninstall {id}: failed: {e}"),
    }
    result?;
    let mut st = spawn_status(&activity, &id, lang).await?;
    if integ.install_hint {
        // §1.4.4：Windows 字面路径无逐事件自愈，卸载后建议新开 CC 会话
        st.message = format!("{} · {}", st.message, action_hint(lang, "uninstall"));
    }
    Ok(st)
}

/// 从 managed state 取 AgentActivity（issue #9 铁律：lib.rs 窗口创建前 manage）。
fn activity_of(app: &tauri::AppHandle) -> crate::http_server::AgentActivity {
    use tauri::Manager;
    app.state::<crate::http_server::AgentActivity>().inner().clone()
}

/// 安装/卸载后追加的会话提示（v2 M2 L1/P2-1：install 用安装措辞，不再复用
/// 卸载文案——修复安装后提示条「已安装…已卸载」矛盾；仅 claude-code 路径）。
fn action_hint(lang: Lang, action: &str) -> &'static str {
    match action {
        "install" => lang.intg_install_hint(),
        _ => lang.intg_uninstall_hint(),
    }
}

/// 探测 + 组装单个接入状态（阻塞 I/O → spawn_blocking）。
/// v2 registry：status_for 已查表化（未知 id 明确 Err），此处透传。
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
    .map_err(|e| format!("status task join: {e}"))?
}

// ---------------------------------------------------------------------------
// 测试（TC-INT-03 单测可测部分 + TC-INT-08 五子项；tempdir 注入）
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::agents::{find, ID_CLAUDE_CODE, ID_OPENCODE};
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
        // 勘误形态：组 = {"hooks":[hook]}；shell 字段按 CC schema 语义在 hook 条目上
        let group = canonical_cc_group(true, dir);
        assert!(
            group.get("matcher").is_none(),
            "外层省略 matcher = 全捕"
        );
        let hook = &group["hooks"][0];
        assert_eq!(hook["shell"], serde_json::json!("powershell"));
        assert_eq!(hook["timeout"], serde_json::json!(3));
        assert_eq!(hook["async"], serde_json::json!(true));
        assert_eq!(hook["asyncRewake"], serde_json::json!(false));
        assert_eq!(hook["type"], serde_json::json!("command"));
        assert_eq!(hook["command"], serde_json::json!(c));
        // Unix 条目无 shell 键
        let unix_hook = &canonical_cc_group(false, dir)["hooks"][0];
        assert!(unix_hook.get("shell").is_none());
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
            assert_eq!(arr.len(), 1, "{ev} 下恰一组 canonical matcher 组");
            // 勘误形态：事件数组元素是 {hooks:[…]} 组（非裸 command），无 matcher = 全捕
            assert!(
                arr[0].get("hooks").and_then(|h| h.as_array()).is_some(),
                "{ev} canonical 条目必须是 matcher 组形态（TC-INT-03-1 勘误）"
            );
            assert!(arr[0].get("matcher").is_none(), "{ev} 外层省略 matcher");
            let hook = &arr[0]["hooks"][0];
            assert_eq!(hook["type"], serde_json::json!("command"));
            assert_eq!(
                hook["command"],
                serde_json::json!(canonical_cc_command(false, &hooks))
            );
            assert_eq!(hook["timeout"], serde_json::json!(3));
            assert_eq!(hook["async"], serde_json::json!(true));
            assert_eq!(hook["asyncRewake"], serde_json::json!(false));
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
        // canonical 组追加在既有数组尾部（组形态，command 在组内）
        let pre = v["hooks"]["PreToolUse"].as_array().expect("arr");
        assert_eq!(pre.len(), 3);
        assert!(
            pre[2]["hooks"][0]["command"]
                .as_str()
                .expect("cmd")
                .contains(MANAGED_FLAG)
        );
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
        v["hooks"]["Stop"][0]["hooks"][0]["command"] = serde_json::json!("echo tampered --pulse-pet-managed");
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
        // 复制整个 canonical 组作为直接元素（合法位置的重复组）→ 该事件键下
        // 组内特征 = 2 → stale（TC-INT-07-4）
        let mut v: serde_json::Value = serde_json::from_str(&read(&settings)).expect("parse");
        let group = v["hooks"]["Stop"][0].clone();
        v["hooks"]["PreToolUse"]
            .as_array_mut()
            .expect("arr")
            .push(group);
        fs::write(&settings, serde_json::to_string_pretty(&v).unwrap()).expect("write");
        assert_eq!(
            cc_config_state(&settings, &canonical_cc_command(false, &hooks)).expect("state"),
            ConfigState::Stale
        );
        fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn legacy_bad_form_bare_entries_are_stale_and_reinstall_fixes() {
        // P0 修复核心回归钉子（2026-08-24 勘误）：初版 R1 安装器把裸 command
        // 条目写成事件数组直接元素，CC zod 报 `hooks.<Event>.0.hooks: Expected
        // array` 且整文件被跳过。用户现场 = 8 键全坏形态。重装必须清掉坏形态
        // 并落正确 matcher 组形态。
        let dir = tempdir("cc-legacy");
        let settings = dir.join("settings.json");
        let hooks = dir.join("hooks");
        // 构造用户现场：8 键坏形态（直接元素 = 裸 command 条目）+ env 键
        let bad_hook = serde_json::json!({
            "type": "command",
            "command": canonical_cc_command(false, &hooks),
            "timeout": 3,
            "async": true,
            "asyncRewake": false,
        });
        let mut hooks_obj = serde_json::Map::new();
        for ev in CC_EVENTS {
            hooks_obj.insert(ev.to_string(), serde_json::json!([bad_hook.clone()]));
        }
        let mut v = serde_json::json!({ "env": { "KEY": "val" } });
        v["hooks"] = serde_json::Value::Object(hooks_obj);
        fs::write(&settings, serde_json::to_string_pretty(&v).unwrap()).expect("write");
        // 坏形态残留 → stale（即使 command 串与 canonical 一致）
        assert_eq!(
            cc_config_state(&settings, &canonical_cc_command(false, &hooks)).expect("state"),
            ConfigState::Stale,
            "裸直接元素坏形态必须判 stale（即使 command 一致）"
        );
        // 重装修复
        install_cc(&settings, &hooks).expect("reinstall fixes legacy bad form");
        let after: serde_json::Value = serde_json::from_str(&read(&settings)).expect("parse");
        let text = read(&settings);
        assert!(text.contains("\"env\""), "用户 env 键保留");
        for ev in CC_EVENTS {
            let arr = after["hooks"][ev].as_array().expect("array");
            assert_eq!(arr.len(), 1, "{ev} 恰一组（坏形态已清 + canonical 组）");
            // 组形态（非裸 command）：有 hooks 数组、无 matcher、无顶层 type
            assert!(arr[0].get("hooks").is_some(), "{ev} 是 matcher 组");
            assert!(arr[0].get("type").is_none(), "{ev} 不是裸 command 直接元素");
            assert_eq!(
                arr[0]["hooks"][0]["command"],
                serde_json::json!(canonical_cc_command(false, &hooks))
            );
        }
        assert_eq!(
            cc_config_state(&settings, &canonical_cc_command(false, &hooks)).expect("state"),
            ConfigState::Installed
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
        // 特征条目全部移除（matcher 组内 + 坏形态直接元素）；用户条目保留
        let text = read(&settings);
        assert!(!text.contains(MANAGED_FLAG));
        assert!(!text.contains(".pulsepet"));
        assert!(text.contains("echo user-direct"));
        assert!(text.contains("echo notify"));
        assert!(text.contains("\"env\""));
        // 空容器清理（§1.4.3 勘误）：特征清空的 matcher 组**整组移除**（不再留
        // 空组壳）；我们建的事件键删除；Notification（用户条目仍在）保留；
        // PreToolUse 剩用户直接元素 1 条
        let hooks_obj = v["hooks"].as_object().expect("hooks");
        assert!(hooks_obj.contains_key("Notification"));
        let pre = v["hooks"]["PreToolUse"].as_array().expect("pre");
        assert_eq!(pre.len(), 1, "用户 matcher 组因特征清空被整组移除，canonical 组已删");
        assert_eq!(pre[0]["command"], serde_json::json!("echo user-direct"));
        assert!(!hooks_obj.contains_key("Stop"));
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
    fn detect_node_suppresses_console_window() {
        // issue #19 钉子：detect_node 的 spawn 必须 CREATE_NO_WINDOW——release
        // GUI 子系统下闪控制台窗会扰动面板焦点，与 Settings focus 刷新构成
        // doctor/focus 自激励死循环（Windows release 独有，dev 不复现）。
        let src = include_str!("mod.rs");
        let code = src.split("#[cfg(test)]").next().unwrap_or("");
        assert!(
            code.contains("cmd.creation_flags(CREATE_NO_WINDOW)"),
            "detect_node 须在 Windows 下加 CREATE_NO_WINDOW（issue #19）"
        );
        assert!(
            code.contains("const CREATE_NO_WINDOW: u32 = 0x0800_0000"),
            "CREATE_NO_WINDOW 常量缺失或值错误（issue #19）"
        );
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

    // ---- v2 registry（agent-registry §8.7.2 P1 钉 4）：未知 id 消静默错误① ----

    #[test]
    fn status_for_unknown_id_is_explicit_error() {
        // 收敛前：status_for 的 if/else 把未知 id 一律落 CC 探测分支（读错误
        // 路径 + spawn node）——静默错误 ①，现状无任何测试把守。收敛后必须
        // 明确 Err（消温床）。
        let err = status_for("codex", None, Lang::Zh).expect_err("未知 id 必须 Err");
        assert!(err.contains("codex"), "错误信息须含未知 id 本身：{err}");
        assert!(find("codex").is_none(), "codex 未注册（钉子前提）");
    }

    // ---- v2 M2 L1（P2-1）：安装路径提示文案修复 ----

    #[test]
    fn install_path_hint_uses_install_wording_not_uninstall() {
        // L1：integrations_install 的 claude-code 路径此前误用
        // intg_uninstall_hint（安装后提示条出现「已安装…已卸载」矛盾）。
        let zh = Lang::Zh;
        let en = Lang::En;
        let install_zh = action_hint(zh, "install");
        assert!(install_zh.contains("已安装"), "{install_zh}");
        assert!(!install_zh.contains("已卸载"), "安装路径不得出现卸载措辞：{install_zh}");
        let install_en = action_hint(en, "install");
        assert!(install_en.to_lowercase().contains("installed"));
        assert!(!install_en.to_lowercase().contains("uninstalled"));
        // 卸载路径保持既有文案（语义不变）
        assert_eq!(action_hint(zh, "uninstall"), zh.intg_uninstall_hint());
        // 源码钉子：install 命令追加 hint 走 action_hint("install")
        let src = include_str!("mod.rs");
        assert!(
            src.contains(r#"action_hint(lang, "install")"#),
            "integrations_install 须经 action_hint(\"install\") 取安装提示"
        );
    }
}
