//! 运行日志与诊断（DESIGN §7.5，2026-08-19 补入）。
//!
//! 背景：Windows release 构建 `windows_subsystem = "windows"` 下 panic 与
//! `eprintln!` 完全静默（v0.1.0 实机首测无任何排障证据）。本模块提供：
//!
//! - `init()`（生产入口）/ `init_at(path)`（测试注入）：打开日志文件（超
//!   1MB 先轮转为 `.old`，只保留一代）→ 安装 panic hook → 写启动横幅
//!   （版本 / OS / debug-release / WebView 版本四要素）；
//! - `plog!` 宏：时间戳前缀 + 追加写文件 + stderr 双写，全仓替换原
//!   `eprintln!`（文案不变）；init 前或文件打开失败时退化为仅 stderr——
//!   日志系统自身故障不阻断 App 启动；
//! - panic hook：panic 消息 + 位置 + 强制 backtrace 落文件——setup 返回
//!   Err 走的 `.expect` panic 由此可回溯。
//!
//! 日志路径：`runtime_dir()` 的父目录（Windows `%LOCALAPPDATA%\pulsepet\`、
//! POSIX `~/.pulsepet/`）下 `pulsepet.log`——与 runtime 目录（token/endpoint，
//! 退出即清）刻意分离：日志跨会话保留，崩溃后残留的上一会话日志正是证据。
//!
//! 内容边界（对齐 TC-SEC）：不打 token 值；panic 消息可能含 OS 错误串原文
//! （路径等），落本机用户目录风险可接受；日志不含事件体。

use std::fs::{File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::{Mutex, OnceLock};

use chrono::Local;

/// 轮转阈值：超 1MB 改名 `.old`（只保留一代，两代足够对照"上次 vs 本次"）。
const ROTATE_BYTES: u64 = 1024 * 1024;

/// 全局日志句柄：None（未 init / 打开失败）→ `log_line` 仅写 stderr。
/// `OnceLock` 保证句柄槽位只建一次；测试多次 `init_at` 经内部 `Option`
/// 替换指向新文件（生产 init 仅一次，两条路径等价）。
static LOG_FILE: OnceLock<Mutex<Option<File>>> = OnceLock::new();

/// 运行日志宏：格式化消息 → `log_line`（时间戳 + 文件 + stderr 双写）。
/// 调用形态与 `eprintln!` 一致（文案沿用 `[pulsepet] ...` 前缀）。
#[macro_export]
macro_rules! plog {
    ($($arg:tt)*) => {
        $crate::logging::log_line(&format!($($arg)*))
    };
}

/// 生产日志路径：`runtime_dir()` 父目录下 `pulsepet.log`。
pub fn log_path() -> PathBuf {
    let dir = crate::runtime::runtime_dir();
    dir.parent()
        .map(|p| p.to_path_buf())
        .unwrap_or(dir)
        .join("pulsepet.log")
}

/// 初始化（生产入口，`run()` 第一行调用）：文件打开失败也装 panic hook
/// 并写横幅（退化为仅 stderr），不向调用方报错——不阻断 App 启动。
pub fn init() {
    if let Err(e) = init_at(&log_path()) {
        eprintln!("[pulsepet] log file open failed (stderr only): {e}");
        set_file(None);
        install_panic_hook();
        banner();
    }
}

/// 注入式初始化（测试）：建目录 → 轮转 → 打开文件 → 装 hook → 写横幅。
/// 文件打开失败返回 Err（此时不装 hook，由 `init` 兜底路径处理）。
pub fn init_at(path: &Path) -> std::io::Result<()> {
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir)?;
    }
    rotate_if_oversize(path)?;
    let file = OpenOptions::new().create(true).append(true).open(path)?;
    set_file(Some(file));
    install_panic_hook();
    banner();
    Ok(())
}

/// 超限轮转：改名 `.old` 只保留一代。Windows rename 到已存在目标会失败，
/// 先删旧 `.old`（POSIX rename 原生覆盖，删除也无害）。
fn rotate_if_oversize(path: &Path) -> std::io::Result<()> {
    let oversize = std::fs::metadata(path)
        .map(|m| m.len() > ROTATE_BYTES)
        .unwrap_or(false);
    if oversize {
        let old = path.with_extension("old");
        let _ = std::fs::remove_file(&old);
        std::fs::rename(path, old)?;
    }
    Ok(())
}

/// 替换全局句柄（首次 `OnceLock::set`，后续原地换 inner Option）。
fn set_file(file: Option<File>) {
    match LOG_FILE.get() {
        Some(slot) => {
            if let Ok(mut guard) = slot.lock() {
                *guard = file;
            }
        }
        None => {
            let _ = LOG_FILE.set(Mutex::new(file));
        }
    }
}

/// 时间戳格式（本地时间，毫秒精度）。
fn timestamp() -> String {
    Local::now().format("%Y-%m-%d %H:%M:%S%.3f").to_string()
}

/// 纯函数：拼一行日志（时间戳 + 消息 + 换行）。单测钉住格式。
fn format_line(ts: &str, msg: &str) -> String {
    format!("{ts} {msg}\n")
}

/// 写一行日志：stderr（`tauri dev` 终端可读）+ 文件（追加）双写。
/// 文件写入失败仅静默丢弃（句柄失效等），不影响运行。
pub fn log_line(msg: &str) {
    let line = format_line(&timestamp(), msg);
    eprint!("{line}");
    write_line(&line);
}

/// 仅写文件（panic hook 内部用，避免与 stderr 双写耦合）。
fn write_line(line: &str) {
    if let Some(slot) = LOG_FILE.get() {
        if let Ok(mut guard) = slot.lock() {
            if let Some(f) = guard.as_mut() {
                let _ = f.write_all(line.as_bytes());
            }
        }
    }
}

/// panic hook：消息 + 位置（file:line）+ 强制 backtrace 落文件（+ stderr）。
/// 覆盖 setup 返回 Err → `.expect` 与任何运行期 panic（原本 GUI 子系统下不可见）。
fn install_panic_hook() {
    std::panic::set_hook(Box::new(|info| {
        let loc = info
            .location()
            .map(|l| format!("{}:{}", l.file(), l.line()))
            .unwrap_or_else(|| "?".to_string());
        log_line(&format!("[pulsepet] PANIC at {loc}: {info}"));
        write_line(&format!("[pulsepet] backtrace:\n{}", std::backtrace::Backtrace::force_capture()));
    }));
}

/// WebView 版本描述：成功记版本串；失败记 Err 原文（Windows 上直接
/// 验证"WebView2 运行时缺失/过老"假设）。两侧实现均为只读查询
/// （NSBundle infoDictionary / WebView2 信息），无 app 实例也可调用。
fn webview_version_desc() -> String {
    match tauri::webview_version() {
        Ok(v) => v,
        Err(e) => format!("unavailable ({e})"),
    }
}

/// 纯函数：启动横幅一行（环境四要素）。单测钉住字段齐全。
fn banner_line(version: &str, os: &str, build: &str, webview: &str) -> String {
    format!(
        "[pulsepet] === PulsePet {version} start (os={os}, build={build}, webview={webview}) ==="
    )
}

/// 写启动横幅：App 版本 / OS / debug-release / WebView 版本。
fn banner() {
    let build = if cfg!(debug_assertions) { "debug" } else { "release" };
    log_line(&banner_line(
        env!("CARGO_PKG_VERSION"),
        std::env::consts::OS,
        build,
        &webview_version_desc(),
    ));
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tmpdir(tag: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "pulsepet-log-test-{}-{tag}",
            std::process::id()
        ));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn format_line_shape() {
        assert_eq!(
            format_line("2026-08-19 12:00:00.123", "[pulsepet] hi"),
            "2026-08-19 12:00:00.123 [pulsepet] hi\n",
        );
    }

    #[test]
    fn banner_line_contains_env_fields() {
        let b = banner_line("9.9.9", "macos", "debug", "WK 123");
        for f in ["9.9.9", "macos", "debug", "WK 123"] {
            assert!(b.contains(f), "banner missing {f}: {b}");
        }
        assert!(b.starts_with("[pulsepet] === PulsePet"));
    }

    // 全局句柄（OnceLock）不可重置，行为类断言合并为单个测试顺序执行，
    // 避免并行测试互相替换句柄产生竞态。
    #[test]
    fn init_write_rotate_and_panic_hook() {
        // ---- ① 横幅 + 追加写 ----
        let dir = tmpdir("behavior");
        let path = dir.join("pulsepet.log");
        init_at(&path).unwrap();
        log_line("[pulsepet] marker-append");
        let content = std::fs::read_to_string(&path).unwrap();
        assert!(content.contains("=== PulsePet"), "banner missing:\n{content}");
        assert!(content.contains("start (os="), "os field missing:\n{content}");
        assert!(content.contains("webview="), "webview field missing:\n{content}");
        assert!(content.contains("marker-append"));
        assert!(content.ends_with('\n'));

        // ---- ② 超限轮转：>1MB 改名 .old，新文件只含横幅 ----
        let big = "x".repeat(ROTATE_BYTES as usize + 1);
        std::fs::write(&path, &big).unwrap();
        init_at(&path).unwrap();
        let old = std::fs::read_to_string(dir.join("pulsepet.old")).unwrap();
        assert_eq!(old.len(), ROTATE_BYTES as usize + 1);
        let cur = std::fs::read_to_string(&path).unwrap();
        assert!(cur.contains("=== PulsePet"), "rotated file lacks banner:\n{cur}");
        assert!(cur.len() < 1024, "rotated file should only hold banner:\n{cur}");

        // ---- ③ panic hook：panic 落文件（消息 + 位置 + backtrace） ----
        let dir_p = tmpdir("panic");
        let path_p = dir_p.join("pulsepet.log");
        init_at(&path_p).unwrap();
        let caught = std::panic::catch_unwind(|| panic!("boom-marker"));
        assert!(caught.is_err());
        let content = std::fs::read_to_string(&path_p).unwrap();
        assert!(content.contains("PANIC"), "panic line missing:\n{content}");
        assert!(content.contains("boom-marker"), "panic msg missing:\n{content}");
        assert!(content.contains("logging.rs"), "panic location missing:\n{content}");
        assert!(content.contains("backtrace"), "backtrace missing:\n{content}");

        let _ = std::fs::remove_dir_all(&dir);
        let _ = std::fs::remove_dir_all(&dir_p);
    }

    // 轮转判定不依赖全局句柄，单独直测（tmp 文件不 init）。
    #[test]
    fn rotate_keeps_small_file_in_place() {
        let dir = tmpdir("rotate-small");
        let path = dir.join("pulsepet.log");
        std::fs::write(&path, "small").unwrap();
        rotate_if_oversize(&path).unwrap();
        assert!(path.exists());
        assert!(!dir.join("pulsepet.old").exists());
        // 不存在的文件不报错（首次启动）
        let absent = dir.join("other.log");
        rotate_if_oversize(&absent).unwrap();
        let _ = std::fs::remove_dir_all(&dir);
    }
}
