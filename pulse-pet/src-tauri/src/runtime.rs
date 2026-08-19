//! runtime 目录与 token / endpoint / killswitch 文件（DESIGN §3.1，TC-EV-08/09/10、TC-SEC-04/06）。
//!
//! - POSIX：`~/.pulsepet/runtime/`；Windows：`%LOCALAPPDATA%\pulsepet\runtime\`
//!   （代码路径常量平台区分）。
//! - `update-token`：App 启动时写随机 token（POSIX mode 0600），退出清除，下次启动
//!   重新生成（每会话轮换）。
//! - `endpoint`：写 `127.0.0.1:<port>`，端口回退时更新。
//! - `hooks-disabled`：killswitch，存在则插件整体跳过（服务端不处理此文件，插件侧读取）。
//! - 事件不明文落盘：token/endpoint 是控制面元数据，事件体仅内存传递（TC-SEC-06）。

use std::path::PathBuf;

/// 生成 32 字符随机 token（每会话轮换，DESIGN §3.1）。
pub fn generate_token() -> String {
    use rand::distributions::Alphanumeric;
    use rand::Rng;
    rand::thread_rng()
        .sample_iter(&Alphanumeric)
        .take(32)
        .map(char::from)
        .collect()
}

/// runtime 根目录（平台区分）。
pub fn runtime_dir() -> PathBuf {
    #[cfg(target_os = "windows")]
    {
        let base = std::env::var("LOCALAPPDATA").unwrap_or_else(|_| ".".to_string());
        PathBuf::from(base).join("pulsepet").join("runtime")
    }
    #[cfg(not(target_os = "windows"))]
    {
        let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
        PathBuf::from(home).join(".pulsepet").join("runtime")
    }
}

pub fn token_path() -> PathBuf {
    runtime_dir().join("update-token")
}

pub fn endpoint_path() -> PathBuf {
    runtime_dir().join("endpoint")
}

/// killswitch 路径（插件侧读取存在性；Rust 侧不处理，见 DESIGN §3.1）。
#[allow(dead_code)]
pub fn hooks_disabled_path() -> PathBuf {
    runtime_dir().join("hooks-disabled")
}

/// 确保 runtime 目录存在。
pub fn ensure_runtime_dir() -> std::io::Result<()> {
    std::fs::create_dir_all(runtime_dir())
}

/// 写入 token 文件；POSIX 端强制 mode 0600（TC-SEC-04）。
///
/// P2-10（M2 遗留）：创建即 0600——`OpenOptions::mode(0o600)` 在 open(2) 原子生效，
/// 消除「先 write 后 chmod」之间内容以 umask 默认权限（如 0644）可读的短窗口；
/// umask 只会在 0600 基础上更严，不会更宽。预先存在的旧文件（崩溃残留等）mode
/// 不受 open 影响，写后仍统一收紧一次。Windows 无 POSIX 权限语义，走默认 ACL。
pub fn write_token(token: &str) -> std::io::Result<()> {
    use std::io::Write;
    ensure_runtime_dir()?;
    let path = token_path();
    let mut opts = std::fs::OpenOptions::new();
    opts.write(true).create(true).truncate(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        opts.mode(0o600); // 创建即 0600，无 umask 短窗口
    }
    let mut f = opts.open(&path)?;
    f.write_all(token.as_bytes())?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600))?;
    }
    Ok(())
}

/// 读取 token（无文件返回 None，内容做 trim）。
/// 服务端写、插件读；Rust 侧 v1 不消费（供未来 debug command / whoami 用）。
#[allow(dead_code)]
pub fn read_token() -> Option<String> {
    std::fs::read_to_string(token_path())
        .ok()
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
}

/// 清除 token（App 退出时调用，TC-EV-08）。
pub fn clear_token() {
    let _ = std::fs::remove_file(token_path());
}

/// 清除 endpoint 文件（App 退出时调用）。
pub fn clear_endpoint() {
    let _ = std::fs::remove_file(endpoint_path());
}

#[cfg(test)]
mod tests {
    use super::*;
    #[cfg(unix)]
    use std::os::unix::fs::PermissionsExt;

    #[test]
    fn token_roundtrip() {
        // 测试写真实 runtime 目录有副作用，这里用独立子路径验证写/读/清逻辑。
        // 由于 runtime_dir() 是平台全局路径，测试改为临时目录内验证文件内容语义。
        let tmp = std::env::temp_dir().join(format!("pulsepet-rt-test-{}", std::process::id()));
        std::fs::create_dir_all(&tmp).unwrap();
        let tok = tmp.join("update-token");
        std::fs::write(&tok, "abc123\n").unwrap();
        assert_eq!(
            std::fs::read_to_string(&tok).unwrap().trim(),
            "abc123"
        );
        std::fs::remove_file(&tok).unwrap();
        assert!(!tok.exists());
        std::fs::remove_dir_all(&tmp).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn token_file_is_0600() {
        // 用真实 runtime 路径写 token，验证 mode 0600 后清理（不污染用户目录残留）。
        let prev = read_token();
        // P2-10：先删除确保走「创建」路径——mode 0600 由 OpenOptions 在 open(2) 原子
        // 生效（而非先写后补 chmod），不存在 umask 短窗口。
        let _ = std::fs::remove_file(token_path());
        write_token("test-token").unwrap();
        let meta = std::fs::metadata(token_path()).unwrap();
        assert_eq!(meta.permissions().mode() & 0o777, 0o600);
        clear_token();
        // 恢复之前的状态（若原本有 token 则复原）
        if let Some(p) = prev {
            write_token(&p).unwrap();
        }
    }
}
