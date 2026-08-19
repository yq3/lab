//! pet / panel / fireworks 窗口管理（DESIGN §7.1）。
//! M1：panel 唤起、pet 可见性切换、pet 位置保存/恢复。
//! M2：pet 位置保存 ~150ms trailing 防抖（P2-5）、恢复位置 clamp 到可视范围（P2-6）。
//! M6：位置记忆升级显示器维度（DESIGN §6.3）——`pet.position.x/y`（物理像素，
//! `outer_position`）+ `pet.monitor`（所在显示器名）落库；启动还原到上次显示器
//! + 坐标，显示器已不存在则回退主显示器（TC-APP-09/10）；panel 支持可见性
//! 切换（全局热键，TC-APP-06）。

use crate::plog;
use std::sync::mpsc::{self, RecvTimeoutError};
use std::sync::Mutex;
use std::time::Duration;

use rusqlite::Connection;
use tauri::{Emitter, Manager, PhysicalPosition};

const KEY_X: &str = "pet.position.x";
const KEY_Y: &str = "pet.position.y";
/// M6：上次所在显示器标识（`Monitor::name()`；macOS 如 "Color LCD"）。
const KEY_MON: &str = "pet.monitor";

/// Moved 事件防抖时长（P2-5：避免拖拽过程每次同步写 2 条 SQL）。
const MOVE_DEBOUNCE_MS: u64 = 150;

/// 唤起控制面板窗口（托盘菜单 / 单实例锁第二实例触发）。
/// M8 i18n：每次唤起同步标题（语言切换即时生效，无需重启）。
pub fn show_panel(app: &tauri::AppHandle) {
    if let Some(win) = app.get_webview_window("panel") {
        let _ = win.set_title(crate::i18n::current().panel_title());
        let _ = win.show();
        let _ = win.set_focus();
    }
}

/// 切换控制面板可见性（M6 全局热键 ⌘/Ctrl+Shift+P，TC-APP-06）：
/// 已显示 → 隐藏；隐藏 → 显示并聚焦。与托盘「打开控制面板」操作同一窗口
/// 对象，状态天然同步（panel 已开时热键即关闭）。
pub fn toggle_panel(app: &tauri::AppHandle) {
    if let Some(win) = app.get_webview_window("panel") {
        if win.is_visible().unwrap_or(false) {
            let _ = win.hide();
        } else {
            let _ = win.show();
            let _ = win.set_focus();
        }
    }
}

/// 切换 pet 窗口可见性（托盘左键 / 托盘菜单项）。
pub fn toggle_pet(app: &tauri::AppHandle) {
    if let Some(win) = app.get_webview_window("pet") {
        if win.is_visible().unwrap_or(false) {
            let _ = win.hide();
        } else {
            let _ = win.show();
            let _ = win.set_focus();
        }
    }
}

/// 显示烟花窗口（M4，TC-RM-09：全屏透明置顶、无边框、无任务栏项；已可见时无害）。
/// 泛型 Runtime：命令层可在 tauri::test mock runtime 下直调（A5 单测）。
pub fn show_fireworks<R: tauri::Runtime>(app: &tauri::AppHandle<R>) {
    if let Some(win) = app.get_webview_window("fireworks") {
        let _ = win.show();
        plog!("[pulsepet] fireworks window show");
    }
}

/// 隐藏烟花窗口（前端播完回报 / watchdog 兜底）。
pub fn hide_fireworks<R: tauri::Runtime>(app: &tauri::AppHandle<R>) {
    if let Some(win) = app.get_webview_window("fireworks") {
        let _ = win.hide();
        plog!("[pulsepet] fireworks window hide");
    }
}

/// M6：开始原生窗口拖拽（PetCanvas 位移超阈值时调用，TC-WIN-01）。
/// 走 OS 原生 drag loop：跨显示器由系统处理（TC-APP-11）、松开即停；
/// 经 Rust 命令而非 JS `getCurrentWindow().startDragging()`，无需在
/// capabilities 追加 core:window:allow-start-dragging（保持最小权限面）。
#[tauri::command]
pub fn pet_start_drag(app: tauri::AppHandle) -> Result<(), String> {
    let win = app
        .get_webview_window("pet")
        .ok_or_else(|| "pet window not found".to_string())?;
    win.start_dragging()
        .map_err(|e| format!("start_dragging: {e}"))
}

/// M6：切换宠物可见性（PetMenu「隐藏宠物」；与托盘左键同一 toggle，TC-APP-03）。
#[tauri::command]
pub fn pet_toggle_visible(app: tauri::AppHandle) -> Result<(), String> {
    toggle_pet(&app);
    Ok(())
}

/// M6：打开控制面板（可选直达 tab；PetMenu「设置…」→ settings）。
/// 先 show 再 emit：panel 窗口随 App 启动已加载（visible:false），监听器
/// 在挂载时注册，事件不会丢。
#[tauri::command]
pub fn panel_open(app: tauri::AppHandle, tab: Option<String>) -> Result<(), String> {
    show_panel(&app);
    if let Some(tab) = tab.as_deref() {
        let _ = app.emit_to(
            "panel",
            "panel://tab",
            serde_json::json!({ "tab": tab }),
        );
    }
    Ok(())
}

/// 纯函数：把窗口左上角 clamp 到给定显示器可视范围（P2-6，可单测）。
///
/// `(mon_x, mon_y, mon_w, mon_h)` 为显示器物理坐标与尺寸，`(win_w, win_h)` 为窗口
/// 物理尺寸。窗口尺寸大于显示器时退化为贴左上角（`max(mon_x)` 保证下界不越上界）。
pub fn clamp_position(
    x: i32,
    y: i32,
    win_w: i32,
    win_h: i32,
    mon_x: i32,
    mon_y: i32,
    mon_w: i32,
    mon_h: i32,
) -> (i32, i32) {
    let max_x = (mon_x + mon_w - win_w).max(mon_x);
    let max_y = (mon_y + mon_h - win_h).max(mon_y);
    (x.clamp(mon_x, max_x), y.clamp(mon_y, max_y))
}

/// 显示器的纯数据快照（id=名字；供 restore 决策单测，不依赖 tauri::Monitor）。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MonitorRect {
    pub id: String,
    pub x: i32,
    pub y: i32,
    pub w: i32,
    pub h: i32,
}

impl MonitorRect {
    fn from_monitor(m: &tauri::Monitor) -> Self {
        let pos = m.position();
        let size = m.size();
        Self {
            id: m.name().cloned().unwrap_or_default(),
            x: pos.x,
            y: pos.y,
            w: size.width as i32,
            h: size.height as i32,
        }
    }
}

/// M6 启动恢复目标决策（DESIGN §6.3，TC-APP-09/10，纯函数）：
///
/// - 无保存位置 → `None`（沿用系统默认摆放，与 M1 语义一致）；
/// - 保存的显示器 id 在可用列表命中 → clamp 到该显示器可视区（TC-APP-09：
///   还原上次显示器 + 坐标；显示器被系统重排时 clamp 防出屏）；
/// - id 未命中（已拔掉）/ 无 id（M1 遗留数据）→ 回退**主显示器**并 clamp
///   （TC-APP-10：不崩溃、不显示在屏幕外）；
/// - 取不到任何显示器信息 → 原样返回保存坐标（M1 语义：不 clamp 不崩溃）；
/// - 窗口大于显示器 → clamp 退化为贴该屏左上角。
///
/// A7（M6 P2③ 处理定案：保留 + 注释固化）：主屏兜底**优先取
/// `primary_monitor()` 的名字**（实际平台几乎总可取到，列表顺序无关）；
/// 仅当主屏 id 不可得（primary_monitor 失败 / 名字为 None / 名字不在当前
/// 列表——如系统重排瞬间的陈旧名）时，才退 `monitors[0]` 作末位兜底。
/// `available_monitors()` 顺序由 OS 决定（不保证主屏在前），但该分支只在
/// "连主屏都识别不出"的罕见情形生效——任意一块可达屏都优于无兜底，
/// monitors[0] 是有意为之的定案（行为由下方测试钉住）。
pub fn resolve_restore_target(
    saved: Option<(i32, i32)>,
    saved_mon: Option<&str>,
    monitors: &[MonitorRect],
    primary_id: Option<&str>,
    win_w: i32,
    win_h: i32,
) -> Option<(i32, i32)> {
    let (x, y) = saved?;
    if monitors.is_empty() {
        return Some((x, y));
    }
    let fallback = primary_id
        .and_then(|id| monitors.iter().find(|m| m.id == id))
        .unwrap_or(&monitors[0]);
    let target = saved_mon
        .and_then(|id| monitors.iter().find(|m| m.id == id))
        .unwrap_or(fallback);
    Some(clamp_position(x, y, win_w, win_h, target.x, target.y, target.w, target.h))
}

/// 启动时从 app_state 恢复 pet 位置（M6：显示器维度，DESIGN §6.3）。
pub fn restore_pet_position(app: &tauri::AppHandle) {
    let Some(win) = app.get_webview_window("pet") else {
        return;
    };
    let Some(state) = app.try_state::<Mutex<Connection>>() else {
        return;
    };
    let Ok(conn) = state.lock() else {
        return;
    };
    let x = crate::db::get_state(&conn, KEY_X).and_then(|s| s.parse::<i32>().ok());
    let y = crate::db::get_state(&conn, KEY_Y).and_then(|s| s.parse::<i32>().ok());
    let mon = crate::db::get_state(&conn, KEY_MON);
    drop(conn);

    let monitors: Vec<MonitorRect> = win
        .available_monitors()
        .map(|ms| ms.iter().map(MonitorRect::from_monitor).collect())
        .unwrap_or_default();
    let primary_id = win
        .primary_monitor()
        .ok()
        .flatten()
        .and_then(|m| m.name().map(|s| s.to_string()));
    let (out_w, out_h) = win
        .outer_size()
        .map(|s| (s.width as i32, s.height as i32))
        .unwrap_or((220, 220));

    match resolve_restore_target(
        x.zip(y),
        mon.as_deref(),
        &monitors,
        primary_id.as_deref(),
        out_w,
        out_h,
    ) {
        Some((cx, cy)) => {
            let _ = win.set_position(PhysicalPosition::new(cx, cy));
            let target_id = mon
                .as_ref()
                .filter(|id| monitors.iter().any(|m| &m.id == *id))
                .cloned()
                .unwrap_or_else(|| primary_id.clone().unwrap_or_default());
            plog!(
                "[pulsepet] restored pet position: ({cx}, {cy}) on monitor {target_id:?} (saved {:?}, monitors {:?})",
                mon,
                monitors.iter().map(|m| m.id.as_str()).collect::<Vec<_>>()
            );
        }
        None => plog!("[pulsepet] no saved pet position"),
    }
}

/// 把 pet 当前位置 + 所在显示器 id 写入 app_state（Moved 事件 + 退出时调用）。
pub fn save_pet_position(app: &tauri::AppHandle) {
    let Some(win) = app.get_webview_window("pet") else {
        return;
    };
    let Ok(pos) = win.outer_position() else {
        return;
    };
    let mon = win
        .current_monitor()
        .ok()
        .flatten()
        .and_then(|m| m.name().map(|s| s.to_string()));
    let Some(state) = app.try_state::<Mutex<Connection>>() else {
        return;
    };
    let Ok(conn) = state.lock() else {
        return;
    };
    let _ = crate::db::set_state(&conn, KEY_X, &pos.x.to_string());
    let _ = crate::db::set_state(&conn, KEY_Y, &pos.y.to_string());
    if let Some(name) = &mon {
        let _ = crate::db::set_state(&conn, KEY_MON, name);
    }
    plog!(
        "[pulsepet] saved pet position: ({}, {}) monitor {:?}",
        pos.x, pos.y, mon
    );
}

/// Moved 事件的 trailing 防抖保存器（P2-5）。
///
/// 后台线程合并 150ms 内的连续 Moved 事件：静默窗口结束才真正落库，避免拖拽时
/// 每次 Moved 同步写 2 条 SQL。
pub struct PositionSaver {
    tx: mpsc::Sender<()>,
}

impl PositionSaver {
    pub fn new(app: tauri::AppHandle) -> Self {
        let (tx, rx) = mpsc::channel::<()>();
        std::thread::spawn(move || {
            loop {
                // 等待首个保存请求
                if rx.recv().is_err() {
                    break;
                }
                // trailing 防抖：继续等待，直到 150ms 内无新事件才落库
                loop {
                    match rx.recv_timeout(Duration::from_millis(MOVE_DEBOUNCE_MS)) {
                        Ok(()) => continue,
                        Err(RecvTimeoutError::Timeout) => break,
                        Err(RecvTimeoutError::Disconnected) => return,
                    }
                }
                save_pet_position(&app);
            }
        });
        Self { tx }
    }

    /// 通知保存器「发生了一次移动」（防抖合并）。
    pub fn request_save(&self) {
        let _ = self.tx.send(());
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn clamp_keeps_position_inside_monitor() {
        // 显示器 0,0 → 1920×1080，窗口 220×220，位置 (100,150) 完全在内部 → 不变
        assert_eq!(clamp_position(100, 150, 220, 220, 0, 0, 1920, 1080), (100, 150));
    }

    #[test]
    fn clamp_pulls_offscreen_position_back() {
        // 位置超出右下角 → clamp 到可完全显示的右下角
        assert_eq!(clamp_position(2000, 2000, 220, 220, 0, 0, 1920, 1080), (1700, 860));
        // 位置为负（左上角越界）→ clamp 到 0
        assert_eq!(clamp_position(-100, -50, 220, 220, 0, 0, 1920, 1080), (0, 0));
    }

    #[test]
    fn clamp_on_secondary_monitor_coordinates() {
        // 次显示器从 x=1920 起
        assert_eq!(clamp_position(1900, 100, 220, 220, 1920, 0, 1920, 1080), (1920, 100));
    }

    #[test]
    fn clamp_window_larger_than_monitor_degrades_to_top_left() {
        // 窗口比显示器还大 → 退化贴左上角，不 panic
        assert_eq!(clamp_position(500, 500, 4000, 4000, 0, 0, 1920, 1080), (0, 0));
    }

    // ---- M6 restore 决策（TC-APP-09/10）----

    fn monitors() -> Vec<MonitorRect> {
        vec![
            MonitorRect { id: "Color LCD".into(), x: 0, y: 0, w: 1920, h: 1080 },
            MonitorRect { id: "DELL U2720Q".into(), x: 1920, y: 0, w: 2560, h: 1440 },
        ]
    }

    const PRIMARY: Option<&str> = Some("Color LCD");

    #[test]
    fn restore_no_saved_position_keeps_default_placement() {
        // 无保存位置 → None（系统默认摆放，M1 语义）
        assert_eq!(
            resolve_restore_target(None, Some("DELL U2720Q"), &monitors(), PRIMARY, 220, 220),
            None
        );
    }

    #[test]
    fn restore_saved_monitor_and_position() {
        // TC-APP-09：上次在次屏 "DELL U2720Q" (2000, 300) → 原样还原到次屏
        assert_eq!(
            resolve_restore_target(
                Some((2000, 300)),
                Some("DELL U2720Q"),
                &monitors(),
                PRIMARY,
                220,
                220
            ),
            Some((2000, 300))
        );
    }

    #[test]
    fn restore_saved_monitor_rearranged_clamps_into_it() {
        // 显示器还在但被系统重排（次屏现从 x=3000 起，保存坐标 2000 落屏外）
        // → clamp 进该屏可视区，不出屏
        let mut ms = monitors();
        ms[1].x = 3000;
        assert_eq!(
            resolve_restore_target(Some((2000, 100)), Some("DELL U2720Q"), &ms, PRIMARY, 220, 220),
            Some((3000, 100))
        );
    }

    #[test]
    fn restore_missing_monitor_falls_back_to_primary() {
        // TC-APP-10：保存的显示器已拔掉（id 不在可用列表——只剩主屏）→
        // 回退主屏并 clamp（保存坐标 x=4400 在主屏外 → clamp 到主屏右缘内）
        let only_primary = vec![monitors()[0].clone()];
        assert_eq!(
            resolve_restore_target(
                Some((4400, 400)),
                Some("DELL U2720Q"),
                &only_primary,
                PRIMARY,
                220,
                220
            ),
            Some((1700, 400))
        );
    }

    #[test]
    fn restore_legacy_position_without_monitor_id_uses_primary() {
        // M1 遗留数据（只有 x/y 无 pet.monitor）→ 主屏 clamp；屏内坐标不动
        assert_eq!(
            resolve_restore_target(Some((100, 200)), None, &monitors(), PRIMARY, 220, 220),
            Some((100, 200))
        );
        // 遗留坐标落在次屏范围（说明当年在次屏）→ 现按主屏 clamp 拉回可视区
        assert_eq!(
            resolve_restore_target(Some((3000, 200)), None, &monitors(), PRIMARY, 220, 220),
            Some((1700, 200))
        );
    }

    #[test]
    fn restore_no_monitor_info_returns_saved_as_is() {
        // 取不到任何显示器信息（空列表）→ 原样返回，不 clamp 不崩溃（M1 语义）
        assert_eq!(
            resolve_restore_target(Some((5000, -30)), Some("x"), &[], None, 220, 220),
            Some((5000, -30))
        );
    }

    #[test]
    fn restore_primary_unavailable_degrades_to_first_monitor() {
        // 主显示器 id 缺失（primary_monitor 失败）→ 用第一块屏兜底
        assert_eq!(
            resolve_restore_target(Some((2000, 300)), Some("gone"), &monitors(), None, 220, 220),
            Some((1700, 300))
        );
    }

    #[test]
    fn restore_stale_primary_name_degrades_to_monitors_zero_a7() {
        // A7：主屏 id 存在但不在当前列表（陈旧名——如系统重排/重命名瞬间）→
        // 与 primary 缺失同路径：monitors[0] 兜底。列表故意把次屏放首位
        // （available_monitors 顺序由 OS 决定，不保证主屏在前），钉住
        // "兜底取列表第一项（无论它是哪块屏）"的定案语义。
        let mut ms = monitors();
        ms.reverse(); // ["DELL U2720Q", "Color LCD"]
        assert_eq!(
            resolve_restore_target(
                Some((100, 100)),
                Some("gone"),
                &ms,
                Some("Built-in Retina Display"), // 不在列表中的陈旧名
                220,
                220
            ),
            // clamp 到 DELL（monitors[0]，x∈[1920, 4260]）→ 100 拉回 1920
            Some((1920, 100))
        );
    }

    #[test]
    fn restore_window_larger_than_target_monitor() {
        // 窗口比目标屏大 → 贴该屏左上角（次屏坐标基 1920,0）
        assert_eq!(
            resolve_restore_target(
                Some((2000, 300)),
                Some("DELL U2720Q"),
                &monitors(),
                PRIMARY,
                4000,
                4000
            ),
            Some((1920, 0))
        );
    }
}
