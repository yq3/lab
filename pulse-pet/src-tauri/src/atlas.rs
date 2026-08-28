//! M5 atlas 加载器（DESIGN §6.2，TC-SP-04~12）。
//!
//! - 素材格式：codex atlas（`pet.json` + `spritesheet.webp`/`.png`），
//!   v1 8×9 = 1536×1872 / v2 8×11 = 1536×2288，单帧 192×208（或其干净缩放）。
//! - webp/png 解码在 Rust 侧（`image` crate，webp 走 image-webp），解码后把
//!   RGBA 整块经 Tauri command 下发 webview，前端只做 canvas 切帧
//!   （TC-SP-04「无前端解码」）。
//! - 网格尺寸校验（C19 / TC-SP-05）：图块宽高比必须匹配 8×9 或 8×11；
//!   pet.json 声明 cols/rows 时须与实际一致；不符 → 拒载 + 面板提示 +
//!   回退内置占位，不做按单帧强行裁剪。
//! - 加载顺序（TC-SP-06/09）：用户配置 pet（app_state `pet.selected`）→
//!   内置宠物 → `~/.codex/pets/` 扫描 → `~/.petdex/pets/` 扫描；逐级回退，
//!   最终必落内置占位（内嵌资源，永不吃紧）。
//! - 内置宠物（TC-SP-12，编译期内嵌双可选）：小猫 `blinking-kitty`（默认，
//!   无用户配置/所有回退路径的落点）+ 小狗 `wagging-doggy`（线条小狗风格、
//!   摇尾巴；同链路加载/校验/切帧/热替换）。
//!
//! 纯逻辑不依赖 Tauri（扫描根目录可注入），`cargo test` 直接覆盖；
//! Tauri command 在文件末尾薄封装。

use crate::plog;
use std::path::{Path, PathBuf};

/// 单帧逻辑尺寸（codex atlas 标准）。
pub const FRAME_W: u32 = 192;
pub const FRAME_H: u32 = 208;
/// 列数固定 8（v1/v2 同）。
pub const COLS: u32 = 8;

/// 内置小猫 id（默认宠物：无用户配置时加载它；TC-SP-12）。
pub const BUILTIN_ID: &str = "blinking-kitty";
/// 内置小狗 id（M5 补充，线条小狗风格摇尾巴；下拉"内置"分组与小猫并列）。
pub const BUILTIN_DOG_ID: &str = "wagging-doggy";
pub const SOURCE_BUILTIN: &str = "builtin";
pub const SOURCE_CODEX: &str = "codex";
pub const SOURCE_PETDEX: &str = "petdex";

const MAX_META_BYTES: u64 = 64 * 1024;
const MAX_SHEET_BYTES: u64 = 8 * 1024 * 1024;

// ---- 错误与面板提示文案 ----

#[derive(Debug, Clone, PartialEq)]
pub enum AtlasError {
    /// pet.json 缺失 / 损坏 / 超大
    BrokenMeta(String),
    /// spritesheet 缺失 / 解码失败
    BrokenSheet(String),
    /// 网格非标准（TC-SP-05：不做按单帧强行裁剪，直接拒载）
    NonStandardGrid { width: u32, height: u32 },
    /// 文件系统错误（读文件失败 / 超大小上限）
    Io(String),
}

impl std::fmt::Display for AtlasError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            AtlasError::BrokenMeta(r) => write!(f, "pet.json 损坏：{r}"),
            AtlasError::BrokenSheet(r) => write!(f, "spritesheet 异常：{r}"),
            AtlasError::NonStandardGrid { width, height } => {
                write!(f, "网格尺寸非标准（{width}×{height}）")
            }
            AtlasError::Io(r) => write!(f, "读取失败：{r}"),
        }
    }
}

impl AtlasError {
    /// 面板提示文案（TC-SP-05/09 措辞；回退落点 = 默认内置小猫 blinking-kitty）。
    /// M8 i18n：模板随全局语言位切换（zh 与 M5 定案措辞逐字一致）；
    /// 嵌入的 reason 串（OS io 错误等）保持原文，不保证整体单语言。
    pub fn notice_text(&self, id: &str) -> String {
        let lang = crate::i18n::current();
        match self {
            AtlasError::NonStandardGrid { width, height } => lang.atlas_notice_grid(id, *width, *height),
            AtlasError::BrokenMeta(reason) => lang.atlas_notice_meta(id, reason),
            AtlasError::BrokenSheet(reason) => lang.atlas_notice_sheet(id, reason),
            AtlasError::Io(reason) => lang.atlas_notice_io(id, reason),
        }
    }
}

// ---- pet.json ----

/// pet.json 元数据（codex atlas 格式；id/displayName 可缺省回退目录名）。
#[derive(Debug, Clone, PartialEq)]
pub struct PetMeta {
    pub id: String,
    pub display_name: String,
    /// pet.json 可选声明的 spritesheet 文件名（默认 spritesheet.webp / .png）。
    pub spritesheet_path: Option<String>,
    /// 可选声明的网格列数（社区素材一般不写；写了则与实际比对，TC-SP-05）。
    pub cols: Option<u32>,
    /// 可选声明的网格行数。
    pub rows: Option<u32>,
}

pub fn parse_pet_json(bytes: &[u8], fallback_id: &str) -> Result<PetMeta, AtlasError> {
    #[derive(serde::Deserialize)]
    struct Raw {
        id: Option<String>,
        #[serde(default, rename = "displayName")]
        display_name: Option<String>,
        #[serde(default, rename = "spritesheetPath")]
        spritesheet_path: Option<String>,
        cols: Option<u32>,
        rows: Option<u32>,
    }
    let raw: Raw = serde_json::from_slice(bytes)
        .map_err(|e| AtlasError::BrokenMeta(format!("pet.json 解析失败: {e}")))?;
    Ok(PetMeta {
        id: raw.id.unwrap_or_else(|| fallback_id.to_string()),
        display_name: raw.display_name.unwrap_or_else(|| fallback_id.to_string()),
        spritesheet_path: raw.spritesheet_path,
        cols: raw.cols,
        rows: raw.rows,
    })
}

// ---- 网格校验（C19）----

/// 从图块实际尺寸推导网格：宽必须整除 8 列；帧宽高比必须 192:208=12:13；
/// 高必须整除帧高；行数只接受 9（v1）或 11（v2）。干净缩放（如 768×936）可过。
pub fn grid_from_dimensions(width: u32, height: u32) -> Result<(u32, u32, u32, u32), AtlasError> {
    let err = || AtlasError::NonStandardGrid { width, height };
    if width == 0 || height == 0 {
        return Err(err());
    }
    if width % COLS != 0 {
        return Err(err());
    }
    let frame_w = width / COLS;
    // 帧宽高比 192:208 = 12:13；干净缩放要求帧宽是 12 的倍数（192=12×16、96=12×8…），
    // 否则帧高不为整（如 240/8=30 → 30×13/12=32.5，切帧行会错位）。
    if frame_w % 12 != 0 {
        return Err(err());
    }
    let frame_h = frame_w / 12 * 13;
    if height % frame_h != 0 {
        return Err(err());
    }
    let rows = height / frame_h;
    // 只接受 v1（8×9）与 v2（8×11）；其余行数（todo 扩展行等）拒载不误显。
    if rows != 9 && rows != 11 {
        return Err(err());
    }
    Ok((COLS, rows, frame_w, frame_h))
}

/// pet.json 声明的 cols/rows（若有）与实际网格比对（TC-SP-05）。
/// 报错文案带实际图块尺寸（帮助用户定位是元数据还是图的问题）。
pub fn validate_declared(
    meta: &PetMeta,
    cols: u32,
    rows: u32,
    sheet_w: u32,
    sheet_h: u32,
) -> Result<(), AtlasError> {
    if let (Some(dc), Some(dr)) = (meta.cols, meta.rows) {
        if dc != cols || dr != rows {
            return Err(AtlasError::NonStandardGrid {
                width: sheet_w,
                height: sheet_h,
            });
        }
    }
    Ok(())
}

// ---- 解码 ----

/// 像素数据载荷（按值移动传递；无 Clone——rgba 缓冲达数 MB，刻意不做
/// 隐式深拷贝，task-pulsepet-v2-polish #1 清偿死代码 derive）。
pub struct AtlasData {
    pub cols: u32,
    pub rows: u32,
    pub frame_w: u32,
    pub frame_h: u32,
    pub rgba: Vec<u8>,
}

/// 解码/探测上限（M5 P2 ⑥，M7 清偿：解压炸弹防护）：头里声明的尺寸或
/// 需分配的像素缓冲超限即拒，不进入像素分配。16384×16384 / 512MB 覆盖所有
/// 合法干净缩放（6× = 9216×11232 ≈ 414MB），gigapixel 级炸弹在头部阶段拦截。
pub const MAX_SHEET_DIM: u32 = 16384;
pub const MAX_SHEET_ALLOC: u64 = 512 * 1024 * 1024;

fn sheet_limits() -> image::Limits {
    let mut l = image::Limits::default();
    l.max_image_width = Some(MAX_SHEET_DIM);
    l.max_image_height = Some(MAX_SHEET_DIM);
    l.max_alloc = Some(MAX_SHEET_ALLOC);
    l
}

/// image Reader（格式猜测 + limits 加固；M5 P2 ⑥）。
fn sheet_reader(bytes: &[u8]) -> Result<image::ImageReader<std::io::Cursor<&[u8]>>, AtlasError> {
    let reader = image::ImageReader::new(std::io::Cursor::new(bytes))
        .with_guessed_format()
        .map_err(|e| AtlasError::BrokenSheet(format!("格式探测失败: {e}")))?;
    let mut reader = reader;
    reader.limits(sheet_limits());
    Ok(reader)
}

pub fn decode_sheet(bytes: &[u8]) -> Result<image::RgbaImage, AtlasError> {
    sheet_reader(bytes)?
        .decode()
        .map(|d| d.to_rgba8())
        .map_err(|e| AtlasError::BrokenSheet(format!("解码失败: {e}")))
}

/// 只读图像头部的宽高（不解码像素；M5 P2 ⑤，M7 清偿：下拉逐项校验用）。
/// 同样吃 sheet_limits（声明超限尺寸的炸弹在头部阶段即拒）。
pub fn sheet_dimensions(bytes: &[u8]) -> Result<(u32, u32), AtlasError> {
    sheet_reader(bytes)?
        .into_dimensions()
        .map_err(|e| AtlasError::BrokenSheet(format!("读头部尺寸失败: {e}")))
}

/// pet.json + spritesheet 字节 → 校验后的 AtlasData。
pub fn load_from_pair(
    meta_bytes: &[u8],
    sheet_bytes: &[u8],
    fallback_id: &str,
) -> Result<(PetMeta, AtlasData), AtlasError> {
    let meta = parse_pet_json(meta_bytes, fallback_id)?;
    let img = decode_sheet(sheet_bytes)?;
    let (w, h) = img.dimensions();
    let (cols, rows, frame_w, frame_h) = grid_from_dimensions(w, h)?;
    validate_declared(&meta, cols, rows, w, h)?;
    Ok((
        meta,
        AtlasData {
            cols,
            rows,
            frame_w,
            frame_h,
            rgba: img.into_raw(),
        },
    ))
}

// ---- 目录加载 ----

/// 读文件（带大小上限，防超大文件拖垮 UI）。
fn read_capped(path: &Path, max: u64) -> Result<Vec<u8>, AtlasError> {
    let meta = std::fs::metadata(path).map_err(|e| AtlasError::Io(format!("{e}")))?;
    if meta.len() > max {
        return Err(AtlasError::Io(format!(
            "文件过大（{} > {max} bytes）",
            meta.len()
        )));
    }
    std::fs::read(path).map_err(|e| AtlasError::Io(format!("{e}")))
}

/// spritesheet 文件名候选（照 petdex：spritesheetPath → spritesheet.webp → .png）。
fn sheet_candidates(meta: &PetMeta) -> Vec<String> {
    let mut v = Vec::new();
    if let Some(sp) = &meta.spritesheet_path {
        if pet_name_ok(sp) {
            v.push(sp.clone());
        }
    }
    v.push("spritesheet.webp".to_string());
    v.push("spritesheet.png".to_string());
    v
}

/// 加载一个 pet 目录（TC-SP-09：pet.json 缺失/损坏、spritesheet 缺失 → Err）。
pub fn load_pet_dir(dir: &Path) -> Result<(PetMeta, AtlasData), AtlasError> {
    let fallback_id = dir
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("pet");
    let meta_path = dir.join("pet.json");
    if !meta_path.is_file() {
        return Err(AtlasError::BrokenMeta(
            crate::i18n::current().atlas_meta_missing().to_string(),
        ));
    }
    let meta_bytes = read_capped(&meta_path, MAX_META_BYTES)
        .map_err(|e| AtlasError::BrokenMeta(format!("{e}")))?;
    let meta = parse_pet_json(&meta_bytes, fallback_id)?;
    for name in sheet_candidates(&meta) {
        let p = dir.join(&name);
        if !p.is_file() {
            continue;
        }
        let sheet = match read_capped(&p, MAX_SHEET_BYTES) {
            Ok(s) => s,
            Err(e) => return Err(AtlasError::BrokenSheet(format!("{e}"))),
        };
        return load_from_pair(&meta_bytes, &sheet, fallback_id);
    }
    Err(AtlasError::BrokenSheet(
        crate::i18n::current().atlas_sheet_missing().to_string(),
    ))
}

/// 轻量校验（M5 P2 ⑤，M7 清偿）：pet.json + spritesheet **头部尺寸** + 网格/
/// 声明校验，**不做像素解码**——大素材集下拉（list_pets_in）不再逐项全量
/// 解码。代价：IDAT 损坏等像素级问题在校验阶段不可见（选中加载时才暴露，
/// 届时回退 + notice，语义不变）。
pub fn probe_pet_dir(dir: &Path) -> Result<(PetMeta, u32, u32), AtlasError> {
    let fallback_id = dir
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("pet");
    let meta_path = dir.join("pet.json");
    if !meta_path.is_file() {
        return Err(AtlasError::BrokenMeta(
            crate::i18n::current().atlas_meta_missing().to_string(),
        ));
    }
    let meta_bytes = read_capped(&meta_path, MAX_META_BYTES)
        .map_err(|e| AtlasError::BrokenMeta(format!("{e}")))?;
    let meta = parse_pet_json(&meta_bytes, fallback_id)?;
    for name in sheet_candidates(&meta) {
        let p = dir.join(&name);
        if !p.is_file() {
            continue;
        }
        let sheet = match read_capped(&p, MAX_SHEET_BYTES) {
            Ok(s) => s,
            Err(e) => return Err(AtlasError::BrokenSheet(format!("{e}"))),
        };
        let (w, h) = sheet_dimensions(&sheet)?;
        let (cols, rows, _, _) = grid_from_dimensions(w, h)?;
        validate_declared(&meta, cols, rows, w, h)?;
        return Ok((meta, w, h));
    }
    Err(AtlasError::BrokenSheet(
        crate::i18n::current().atlas_sheet_missing().to_string(),
    ))
}

// ---- 内置宠物（编译期内嵌，最终兜底永不吃紧；TC-SP-12 双可选）----

const BUILTIN_CAT_META: &[u8] = include_bytes!("../assets/blinking-kitty/pet.json");
const BUILTIN_CAT_SHEET: &[u8] = include_bytes!("../assets/blinking-kitty/spritesheet.png");
const BUILTIN_DOG_META: &[u8] = include_bytes!("../assets/wagging-doggy/pet.json");
const BUILTIN_DOG_SHEET: &[u8] = include_bytes!("../assets/wagging-doggy/spritesheet.png");

/// 内置宠物表（下拉"内置"分组顺序；第一项 = 无用户配置时的默认）。
const BUILTIN_PETS: &[(&str, &[u8], &[u8])] = &[
    (BUILTIN_ID, BUILTIN_CAT_META, BUILTIN_CAT_SHEET),
    (BUILTIN_DOG_ID, BUILTIN_DOG_META, BUILTIN_DOG_SHEET),
];

/// 按 id 加载内置宠物（blinking-kitty / wagging-doggy；未知 id → Err）。
pub fn load_builtin_pet(id: &str) -> Result<(PetMeta, AtlasData), AtlasError> {
    for (bid, meta, sheet) in BUILTIN_PETS {
        if *bid == id {
            return load_from_pair(meta, sheet, bid);
        }
    }
    Err(AtlasError::BrokenMeta(format!("未知的内置宠物 id: {id}")))
}

/// 默认内置（blinking-kitty）：无用户配置的选择 + 所有回退路径的最终兜底。
pub fn load_builtin() -> Result<(PetMeta, AtlasData), AtlasError> {
    load_builtin_pet(BUILTIN_ID)
}

// ---- 扫描与解析顺序 ----

pub struct ScannedPet {
    pub id: String,
    pub source: &'static str,
    pub path: PathBuf,
}

/// 目录名合法性（照 petdex：1-63 字符，字母数字 - _ .；首字符不为点）。
pub fn pet_name_ok(name: &str) -> bool {
    !name.is_empty()
        && name.len() <= 63
        && !name.starts_with('.')
        && name
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_' || c == '.')
}

/// 单来源目录扫描（名字序，过滤非法名与嵌套）。
fn scan_source_dir(root: &Path, source: &'static str, out: &mut Vec<ScannedPet>) {
    let Ok(entries) = std::fs::read_dir(root) else {
        return; // 目录不存在 → 该级来源为空
    };
    let mut names: Vec<String> = entries
        .filter_map(|e| e.ok())
        .filter(|e| e.file_type().map(|t| t.is_dir()).unwrap_or(false))
        .filter_map(|e| e.file_name().into_string().ok())
        .filter(|n| pet_name_ok(n) && !n.starts_with('.'))
        .collect();
    names.sort();
    for name in names {
        // 同名 id 先到先得（codex 优先于 petdex，TC-SP-06）
        if out.iter().any(|p| p.id == name) {
            continue;
        }
        let path = root.join(&name);
        out.push(ScannedPet {
            id: name,
            source,
            path,
        });
    }
}

/// 按 codex → petdex 顺序扫描（同名 id 先到先得，TC-SP-06 顺序）。
pub fn scan_pets_in(home: &Path) -> Vec<ScannedPet> {
    let mut v = Vec::new();
    scan_source_dir(&home.join(".codex").join("pets"), SOURCE_CODEX, &mut v);
    scan_source_dir(&home.join(".petdex").join("pets"), SOURCE_PETDEX, &mut v);
    v
}

pub struct Selection {
    pub requested: Option<String>,
    pub current_id: String,
    pub current_source: &'static str,
    pub data: AtlasData,
    pub notice: Option<String>,
}

/// 单个 id 的来源查找顺序：内置（blinking-kitty / wagging-doggy）→ codex →
/// petdex（TC-SP-06；内置两只都算 SOURCE_BUILTIN，path 为空占位）。
fn find_pet_dir(id: &str, home: &Path) -> Vec<(&'static str, PathBuf)> {
    if id == BUILTIN_ID || id == BUILTIN_DOG_ID {
        return vec![(SOURCE_BUILTIN, PathBuf::new())];
    }
    if !pet_name_ok(id) {
        return Vec::new();
    }
    vec![
        (SOURCE_CODEX, home.join(".codex").join("pets").join(id)),
        (SOURCE_PETDEX, home.join(".petdex").join("pets").join(id)),
    ]
    .into_iter()
    .filter(|(_, p)| p.is_dir())
    .collect()
}

/// 加载顺序解析（TC-SP-06）：
/// 用户配置 id（内置 → codex → petdex 中找）→ 内置默认（blinking-kitty）→
/// codex 首个 → petdex 首个 → 内置默认（最终兜底）。
pub fn resolve_requested(requested: Option<&str>, home: &Path) -> Selection {
    let mut notice: Option<String> = None;

    // 1. 用户配置的 pet：按 内置 → codex → petdex 顺序找该 id
    if let Some(id) = requested.filter(|s| !s.is_empty()) {
        for (source, path) in find_pet_dir(id, home) {
            if source == SOURCE_BUILTIN {
                match load_builtin_pet(id) {
                    Ok((_, data)) => {
                        return Selection {
                            requested: Some(id.to_string()),
                            current_id: id.to_string(),
                            current_source: SOURCE_BUILTIN,
                            data,
                            notice,
                        }
                    }
                    Err(e) => {
                        notice = Some(e.notice_text(id));
                        break;
                    }
                }
            }
            match load_pet_dir(&path) {
                Ok((_, data)) => {
                    return Selection {
                        requested: Some(id.to_string()),
                        // canonical id = 目录名（与扫描/下拉/持久化一致；
                        // pet.json 的 id 字段社区素材不保证与目录名相同）
                        current_id: id.to_string(),
                        current_source: source,
                        data,
                        notice,
                    }
                }
                Err(e) => {
                    // 记录首个失败原因后继续尝试下一来源
                    if notice.is_none() {
                        notice = Some(e.notice_text(id));
                    }
                }
            }
        }
        if notice.is_none() {
            notice = Some(crate::i18n::current().atlas_notice_not_found(id));
        }
    } else {
        // 2. 无配置：内置占位（显式第二级；成功即用）
        if let Ok((_, data)) = load_builtin() {
            return Selection {
                requested: None,
                current_id: BUILTIN_ID.to_string(),
                current_source: SOURCE_BUILTIN,
                data,
                notice,
            };
        }
        // 3. codex 首个 → petdex 首个
        // A8（M5 P2⑦ 处理定案：保留 + 注释固化）：本扫描段仅在 load_builtin()
        // 失败（内置素材为编译期内嵌、测试期已校验，正常运行不可达）时作为
        // 防御层生效——与 TC-SP-06 文档"内置 → codex → petdex"顺序语义一致
        // （codex/petdex 扫描在"配置了非内置 id"分支真正生效）。删除会让
        // "内嵌资源意外损坏"场景直接落入空数据兜底，防御性保留无害，不删。
        for scanned in scan_pets_in(home) {
            if let Ok((_, data)) = load_pet_dir(&scanned.path) {
                return Selection {
                    requested: None,
                    current_id: scanned.id.clone(),
                    current_source: scanned.source,
                    data,
                    notice,
                };
            }
        }
    }

    // 4. 最终兜底：内置占位（编译期内嵌，load_builtin 失败则无解——用空数据占位防崩）
    match load_builtin() {
        Ok((_, data)) => Selection {
            requested: requested.filter(|s| !s.is_empty()).map(|s| s.to_string()),
            current_id: BUILTIN_ID.to_string(),
            current_source: SOURCE_BUILTIN,
            data,
            notice,
        },
        Err(_) => Selection {
            requested: requested.filter(|s| !s.is_empty()).map(|s| s.to_string()),
            current_id: BUILTIN_ID.to_string(),
            current_source: SOURCE_BUILTIN,
            data: AtlasData {
                cols: COLS,
                rows: 9,
                frame_w: FRAME_W,
                frame_h: FRAME_H,
                rgba: vec![0; (FRAME_W * FRAME_H * 9 * 4) as usize],
            },
            notice,
        },
    }
}

// ---- 面板下拉数据 ----

#[derive(Debug)]
pub struct PetOption {
    pub id: String,
    pub display_name: String,
    pub source: &'static str,
    pub ok: bool,
    pub problem: Option<String>,
}

/// 面板"选择宠物"下拉数据：内置分组（blinking-kitty / wagging-doggy）+
/// codex 扫描 + petdex 扫描（顺序一致）。每项做轻量加载校验（损坏 / 非标准
/// 网格 → ok=false + problem，TC-SP-11③④；TC-SP-12 内置两只并列）。
/// M5 P2 ⑤（M7 清偿）：逐项校验改 **头部尺寸探测**（probe_pet_dir），不再
/// 全量解码——大素材集下拉不再卡顿；内置宠物只解析 pet.json（编译期内嵌
/// 素材已在测试中校验过网格）。
pub fn list_pets_in(home: &Path) -> Vec<PetOption> {
    let mut v = Vec::new();
    for (bid, meta_bytes, _) in BUILTIN_PETS {
        let meta = parse_pet_json(meta_bytes, bid);
        match meta {
            Ok(m) => v.push(PetOption {
                id: bid.to_string(),
                display_name: m.display_name,
                source: SOURCE_BUILTIN,
                ok: true,
                problem: None,
            }),
            Err(e) => v.push(PetOption {
                id: bid.to_string(),
                display_name: bid.to_string(),
                source: SOURCE_BUILTIN,
                ok: false,
                problem: Some(e.notice_text(bid)),
            }),
        }
    }
    for scanned in scan_pets_in(home) {
        let (display_name, ok, problem) = match probe_pet_dir(&scanned.path) {
            Ok((meta, _, _)) => (meta.display_name, true, None),
            Err(e) => (scanned.id.clone(), false, Some(e.notice_text(&scanned.id))),
        };
        v.push(PetOption {
            id: scanned.id,
            display_name,
            source: scanned.source,
            ok,
            problem,
        });
    }
    v
}

// ---- Tauri command 封装 ----

use rusqlite::Connection;
use tauri::ipc::Response;
use tauri::{Emitter, Manager};

#[derive(Clone, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AtlasMetaDto {
    pub requested: Option<String>,
    pub current_id: String,
    pub current_source: String,
    pub cols: u32,
    pub rows: u32,
    pub frame_w: u32,
    pub frame_h: u32,
    pub notice: Option<String>,
}

#[derive(Clone, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PetOptionDto {
    pub id: String,
    pub display_name: String,
    pub source: String,
    pub ok: bool,
    pub problem: Option<String>,
}

/// 受管状态：当前生效的 atlas 选择。
/// （2026-08-24 修订：mini 猫 PNG dataURL 缓存随 atlas_sheet_png 命令一并
/// 回收删除——V2-DESIGN §2.4 修订，唯一消费方消失即回收，不留无消费方代码。）
pub struct AtlasState {
    pub selection: Selection,
}

impl AtlasState {
    /// 从完整 Selection 构造（init_selection 用）。
    pub fn new(selection: Selection) -> Self {
        Self { selection }
    }
}

fn selection_dto(s: &Selection) -> AtlasMetaDto {
    AtlasMetaDto {
        requested: s.requested.clone(),
        current_id: s.current_id.clone(),
        current_source: s.current_source.to_string(),
        cols: s.data.cols,
        rows: s.data.rows,
        frame_w: s.data.frame_w,
        frame_h: s.data.frame_h,
        notice: s.notice.clone(),
    }
}

fn home_dir() -> PathBuf {
    // 与 runtime.rs / token_stats.rs 一致：HOME（unix）；Windows 走 USERPROFILE。
    if cfg!(windows) {
        std::env::var("USERPROFILE")
            .unwrap_or_else(|_| ".".to_string())
            .into()
    } else {
        std::env::var("HOME").unwrap_or_else(|_| ".".to_string()).into()
    }
}

/// setup 时初始化：读 app_state `pet.selected` → 按加载顺序解析。
pub fn init_selection(conn: &Connection) -> Result<AtlasState, String> {
    let requested = crate::db::get_state(conn, "pet.selected").filter(|s| !s.is_empty());
    let selection = resolve_requested(requested.as_deref(), &home_dir());
    log_selection(&selection);
    Ok(AtlasState::new(selection))
}

fn log_selection(s: &Selection) {
    plog!(
        "[pulsepet] atlas: loaded {} from {} ({}×{}, frame {}×{})",
        s.current_id,
        s.current_source,
        s.data.cols * s.data.frame_w,
        s.data.rows * s.data.frame_h,
        s.data.frame_w,
        s.data.frame_h
    );
    if let Some(n) = &s.notice {
        plog!("[pulsepet] atlas: fallback notice: {n}");
    }
}

#[tauri::command]
pub fn atlas_meta(app: tauri::AppHandle) -> Result<AtlasMetaDto, String> {
    let st = app.state::<std::sync::Mutex<AtlasState>>();
    let guard = st.lock().map_err(|e| format!("lock: {e}"))?;
    Ok(selection_dto(&guard.selection))
}

/// RGBA 整块二进制下发（webview 端 invoke 得 ArrayBuffer；无 JSON 数字数组开销）。
#[tauri::command]
pub fn atlas_pixels(app: tauri::AppHandle) -> Result<Response, String> {
    let st = app.state::<std::sync::Mutex<AtlasState>>();
    let guard = st.lock().map_err(|e| format!("lock: {e}"))?;
    Ok(Response::new(guard.selection.data.rgba.clone()))
}

#[tauri::command]
pub fn atlas_list_pets(_app: tauri::AppHandle) -> Result<Vec<PetOptionDto>, String> {
    Ok(list_pets_in(&home_dir())
        .into_iter()
        .map(|p| PetOptionDto {
            id: p.id,
            display_name: p.display_name,
            source: p.source.to_string(),
            ok: p.ok,
            problem: p.problem,
        })
        .collect())
}

/// 选择宠物（None = 恢复自动）：持久化 `pet.selected` → 加载 → 事件通知 webview
/// 热替换（TC-SP-11② / TC-APP-12）。失败回退内置占位 + notice（TC-SP-05/09）。
/// v2 M2：泛型 Runtime（tauri::test mock 可驱动）+ 代次前进使 PNG 缓存失效。
#[tauri::command]
pub fn atlas_select<R: tauri::Runtime>(
    app: tauri::AppHandle<R>,
    id: Option<String>,
) -> Result<AtlasMetaDto, String> {
    {
        let db = app.state::<std::sync::Mutex<Connection>>();
        let conn = db.lock().map_err(|e| format!("db lock: {e}"))?;
        match &id {
            Some(v) => crate::db::set_state(&conn, "pet.selected", v),
            None => crate::db::delete_state(&conn, "pet.selected"),
        }?;
    }
    let selection = resolve_requested(id.as_deref(), &home_dir());
    let dto = selection_dto(&selection);
    log_selection(&selection);
    {
        let st = app.state::<std::sync::Mutex<AtlasState>>();
        let mut guard = st.lock().map_err(|e| format!("lock: {e}"))?;
        guard.selection = selection;
    }
    let _ = app.emit("atlas://changed", dto.clone());
    Ok(dto)
}

// ---- 单测 ----

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::sync::atomic::{AtomicU64, Ordering};

    /// 唯一临时目录（无 tempfile 依赖）。
    fn tempdir(tag: &str) -> PathBuf {
        static SEQ: AtomicU64 = AtomicU64::new(0);
        let n = SEQ.fetch_add(1, Ordering::SeqCst);
        let dir = std::env::temp_dir().join(format!(
            "pulsepet-atlas-test-{}-{}-{}",
            tag,
            std::process::id(),
            n
        ));
        fs::create_dir_all(&dir).unwrap();
        dir
    }

    /// 用 image crate 现编一张纯色 atlas（PNG 或 WebP）。
    fn make_sheet(format: image::ImageFormat, width: u32, height: u32, rgba: [u8; 4]) -> Vec<u8> {
        let img = image::RgbaImage::from_pixel(width, height, image::Rgba(rgba));
        let mut buf = std::io::Cursor::new(Vec::new());
        img.write_to(&mut buf, format).unwrap();
        buf.into_inner()
    }

    fn write_pet(dir: &Path, meta_json: &str, sheet: &[u8], sheet_name: &str) {
        fs::create_dir_all(dir).unwrap();
        fs::write(dir.join("pet.json"), meta_json).unwrap();
        fs::write(dir.join(sheet_name), sheet).unwrap();
    }

    const OK_META: &str = r#"{"id":"testpet","displayName":"测试宠物"}"#;

    // ---- pet.json 解析 ----

    #[test]
    fn parse_pet_json_full_and_minimal() {
        let m = parse_pet_json(OK_META.as_bytes(), "fb").unwrap();
        assert_eq!(m.id, "testpet");
        assert_eq!(m.display_name, "测试宠物");
        assert_eq!(m.spritesheet_path, None);

        // 最小 pet.json（无 id/displayName）→ 回退目录名
        let m2 = parse_pet_json(br#"{}"#, "dirname").unwrap();
        assert_eq!(m2.id, "dirname");
        assert_eq!(m2.display_name, "dirname");

        // 声明 cols/rows 的变体
        let m3 = parse_pet_json(br#"{"id":"x","cols":8,"rows":9}"#, "fb").unwrap();
        assert_eq!(m3.cols, Some(8));
        assert_eq!(m3.rows, Some(9));
    }

    #[test]
    fn parse_pet_json_rejects_broken() {
        assert!(matches!(
            parse_pet_json(b"not json", "fb"),
            Err(AtlasError::BrokenMeta(_))
        ));
        // JSON 但结构错误（id 非字符串）→ 也算损坏
        assert!(matches!(
            parse_pet_json(br#"{"id":123}"#, "fb"),
            Err(AtlasError::BrokenMeta(_))
        ));
    }

    // ---- 网格校验（C19 / TC-SP-05）----

    #[test]
    fn grid_accepts_v1_v2_and_clean_scales() {
        assert_eq!(grid_from_dimensions(1536, 1872).unwrap(), (8, 9, 192, 208));
        assert_eq!(grid_from_dimensions(1536, 2288).unwrap(), (8, 11, 192, 208));
        // 干净缩放：768×936（½）、3072×3744（2×）
        assert_eq!(grid_from_dimensions(768, 936).unwrap(), (8, 9, 96, 104));
        assert_eq!(grid_from_dimensions(3072, 3744).unwrap(), (8, 9, 384, 416));
    }

    #[test]
    fn grid_rejects_non_standard() {
        // 8×10（1536×2080）
        assert!(matches!(
            grid_from_dimensions(1536, 2080),
            Err(AtlasError::NonStandardGrid { .. })
        ));
        // 16×9 语义（3072×1872：帧宽 384 但高不整除帧高 416）
        assert!(matches!(
            grid_from_dimensions(3072, 1872),
            Err(AtlasError::NonStandardGrid { .. })
        ));
        // 宽不整除 8
        assert!(matches!(
            grid_from_dimensions(1500, 1872),
            Err(AtlasError::NonStandardGrid { .. })
        ));
        // 帧宽高比破坏（1536×1873）
        assert!(matches!(
            grid_from_dimensions(1536, 1873),
            Err(AtlasError::NonStandardGrid { .. })
        ));
        // 行数 12（8×12 网格）
        assert!(matches!(
            grid_from_dimensions(1536, 2496),
            Err(AtlasError::NonStandardGrid { .. })
        ));
    }

    #[test]
    fn declared_cols_rows_must_match_actual() {
        let mut m = parse_pet_json(OK_META.as_bytes(), "fb").unwrap();
        assert!(validate_declared(&m, 8, 9, 1536, 1872).is_ok()); // 未声明 → 不比对

        m.cols = Some(8);
        m.rows = Some(9);
        assert!(validate_declared(&m, 8, 9, 1536, 1872).is_ok());

        m.cols = Some(16); // 声明 16 列 ≠ 实际 8 → 拒载（TC-SP-05 前置素材）
        assert!(matches!(
            validate_declared(&m, 8, 9, 1536, 1872),
            Err(AtlasError::NonStandardGrid { .. })
        ));

        m.cols = Some(8);
        m.rows = Some(10); // 声明 8×10
        assert!(matches!(
            validate_declared(&m, 8, 9, 1536, 1872),
            Err(AtlasError::NonStandardGrid { .. })
        ));
    }

    #[test]
    fn notice_text_uses_required_wording() {
        let e = AtlasError::NonStandardGrid {
            width: 1536,
            height: 2080,
        };
        let t = e.notice_text("badpet");
        assert!(t.contains("网格尺寸非标准"), "{t}");
        assert!(t.contains("8×9 / 8×11"), "{t}");
        assert!(t.contains("badpet"), "{t}");
        assert!(t.contains("回退"), "{t}");
    }

    // ---- 解码 ----

    #[test]
    fn decode_png_and_webp() {
        let png = make_sheet(image::ImageFormat::Png, 1536, 1872, [200, 100, 50, 255]);
        let img = decode_sheet(&png).unwrap();
        assert_eq!(img.dimensions(), (1536, 1872));

        let webp = make_sheet(image::ImageFormat::WebP, 1536, 1872, [50, 100, 200, 255]);
        let img2 = decode_sheet(&webp).unwrap();
        assert_eq!(img2.dimensions(), (1536, 1872));
        assert_eq!(img2.get_pixel(0, 0).0, [50, 100, 200, 255]);
    }

    #[test]
    fn decode_rejects_garbage() {
        assert!(matches!(
            decode_sheet(b"garbage bytes"),
            Err(AtlasError::BrokenSheet(_))
        ));
    }

    // ---- M5 P2 ⑤⑥（M7 清偿）：头部探测 + 解压炸弹防护 ----

    /// 手工拼一个 PNG：签名 + IHDR + 一个极小 IDAT（png read_info 需扫到
    /// IDAT 才返回头部信息）+ IEND。像素数据本身是垃圾（不被头部读取触及）。
    fn png_header_only(width: u32, height: u32) -> Vec<u8> {
        // PNG CRC-32（位运算实现，测试内自包含）
        fn crc32(data: &[u8]) -> u32 {
            let mut crc: u32 = 0xFFFF_FFFF;
            for &b in data {
                crc ^= b as u32;
                for _ in 0..8 {
                    crc = if crc & 1 != 0 {
                        (crc >> 1) ^ 0xEDB8_8320
                    } else {
                        crc >> 1
                    };
                }
            }
            !crc
        }
        fn chunk(out: &mut Vec<u8>, kind: &[u8; 4], data: &[u8]) {
            out.extend_from_slice(&(data.len() as u32).to_be_bytes());
            let mut body = Vec::new();
            body.extend_from_slice(kind);
            body.extend_from_slice(data);
            out.extend_from_slice(&body);
            out.extend_from_slice(&crc32(&body).to_be_bytes());
        }
        let mut out = vec![0x89, b'P', b'N', b'G', 0x0D, 0x0A, 0x1A, 0x0A];
        let mut ihdr = Vec::new();
        ihdr.extend_from_slice(&width.to_be_bytes());
        ihdr.extend_from_slice(&height.to_be_bytes());
        ihdr.extend_from_slice(&[8, 0, 0, 0, 0]); // 8bit 灰度/deflate/adaptive/无隔行
        chunk(&mut out, b"IHDR", &ihdr);
        chunk(&mut out, b"IDAT", b"\x00"); // 1 字节垃圾：足够让头部读取推进
        chunk(&mut out, b"IEND", b"");
        out
    }

    #[test]
    fn sheet_dimensions_reads_header_without_pixels() {
        // 只有头部、没有像素数据 → 头部探测仍成功（P2 ⑤：下拉不靠解码）
        let bytes = png_header_only(1536, 1872);
        assert_eq!(sheet_dimensions(&bytes).unwrap(), (1536, 1872));
        // 同结构的全量解码则失败（无 IDAT）——两者差异正是"头部 vs 解码"
        assert!(decode_sheet(&bytes).is_err());
    }

    #[test]
    fn limits_reject_decompression_bomb_at_header_stage() {
        // 同样只有头部的两张图：小尺寸过、声明 30000×30000 的炸弹在头部
        // 阶段被 limits 拦截（未进入像素分配——否则此处已 OOM/极慢）
        assert!(sheet_dimensions(&png_header_only(30000, 30000)).is_err());
        assert!(decode_sheet(&png_header_only(30000, 30000)).is_err());
        assert_eq!(
            sheet_dimensions(&png_header_only(1536, 1872)).unwrap(),
            (1536, 1872)
        );
    }

    #[test]
    fn list_pets_probe_is_header_only_no_full_decode() {
        // 头部合法但 IDAT 是垃圾：probe（下拉校验）判 ok；真正加载才失败。
        // 这是 P2 ⑤ 的语义代价：像素级问题延迟到选中加载时暴露（回退 + notice）。
        let home = tempdir("probe");
        let mut bytes = png_header_only(1536, 1872);
        bytes.extend_from_slice(b"garbage idat bytes");

        let d = home.join(".codex/pets/pixelrot");
        write_pet(&d, OK_META, &bytes, "spritesheet.png");
        let pets = list_pets_in(&home);
        assert_eq!(pets.len(), 3, "{pets:?}");
        assert_eq!(&pets[2].id, "pixelrot");
        assert!(pets[2].ok, "头部探测通过（不解码像素）");
        // 选中加载：解码失败 → 回退 + notice（TC-SP-09 语义不变）
        let s = resolve_requested(Some("pixelrot"), &home);
        assert_eq!(s.current_source, SOURCE_BUILTIN);
        assert!(s.notice.is_some());

        // 头部就非标准（1536×2080）→ probe 直接判 !ok（与原全量解码口径一致）
        let bad = png_header_only(1536, 2080);
        let d2 = home.join(".codex/pets/badgrid");
        write_pet(&d2, OK_META, &bad, "spritesheet.png");
        let pets2 = list_pets_in(&home);
        let bg = pets2.iter().find(|p| p.id == "badgrid").unwrap();
        assert!(!bg.ok);
        assert!(bg.problem.as_deref().unwrap_or("").contains("网格尺寸非标准"));

        fs::remove_dir_all(&home).ok();
    }

    #[test]
    fn load_from_pair_ok_and_bad_grid() {
        let sheet = make_sheet(image::ImageFormat::WebP, 1536, 1872, [1, 2, 3, 255]);
        let (meta, data) = load_from_pair(OK_META.as_bytes(), &sheet, "fb").unwrap();
        assert_eq!(meta.id, "testpet");
        assert_eq!((data.cols, data.rows, data.frame_w, data.frame_h), (8, 9, 192, 208));
        assert_eq!(data.rgba.len(), 1536 * 1872 * 4);

        // 非标准网格图块 → NonStandardGrid（不做按单帧强行裁剪）
        let bad = make_sheet(image::ImageFormat::WebP, 1536, 2080, [1, 2, 3, 255]);
        assert!(matches!(
            load_from_pair(OK_META.as_bytes(), &bad, "fb"),
            Err(AtlasError::NonStandardGrid { .. })
        ));
    }

    // ---- 目录加载（TC-SP-09）----

    #[test]
    fn load_pet_dir_prefers_declared_path_then_webp_then_png() {
        let sheet = make_sheet(image::ImageFormat::Png, 1536, 1872, [9, 9, 9, 255]);
        let webp = make_sheet(image::ImageFormat::WebP, 1536, 1872, [7, 7, 7, 255]);

        let home = tempdir("dirload");
        // 只有 png
        let d1 = home.join("only-png");
        write_pet(&d1, OK_META, &sheet, "spritesheet.png");
        assert!(load_pet_dir(&d1).is_ok());

        // webp 优先于 png
        let d2 = home.join("webp-first");
        fs::create_dir_all(&d2).unwrap();
        fs::write(d2.join("pet.json"), OK_META).unwrap();
        fs::write(d2.join("spritesheet.webp"), &webp).unwrap();
        fs::write(d2.join("spritesheet.png"), &sheet).unwrap();
        let (_, data) = load_pet_dir(&d2).unwrap();
        assert_eq!(data.rgba[0..3], [7, 7, 7]);

        // spritesheetPath 指定自定义文件名
        let d3 = home.join("custom-path");
        write_pet(
            &d3,
            r#"{"id":"x","spritesheetPath":"custom.webp"}"#,
            &webp,
            "custom.webp",
        );
        assert!(load_pet_dir(&d3).is_ok());

        fs::remove_dir_all(&home).ok();
    }

    #[test]
    fn load_pet_dir_reports_broken_meta_and_missing_sheet() {
        let home = tempdir("dirbroken");
        // pet.json 损坏
        let d1 = home.join("broken");
        write_pet(&d1, "{ broken", &[], "spritesheet.webp");
        assert!(matches!(load_pet_dir(&d1), Err(AtlasError::BrokenMeta(_))));

        // pet.json 存在但 spritesheet 缺失
        let d2 = home.join("nosheet");
        fs::create_dir_all(&d2).unwrap();
        fs::write(d2.join("pet.json"), OK_META).unwrap();
        assert!(matches!(load_pet_dir(&d2), Err(AtlasError::BrokenSheet(_))));

        fs::remove_dir_all(&home).ok();
    }

    // ---- 内置宠物（blinking-kitty 默认 + wagging-doggy，TC-SP-12）----

    #[test]
    fn builtin_atlas_is_standard_v1() {
        let (meta, data) = load_builtin().unwrap();
        assert_eq!(meta.id, BUILTIN_ID);
        assert_eq!(meta.id, "blinking-kitty");
        assert!(meta.display_name.contains("blinking-kitty"), "{}", meta.display_name);
        assert_eq!((data.cols, data.rows), (8, 9));
        assert_eq!((data.frame_w, data.frame_h), (192, 208));
        assert_eq!(data.rgba.len(), 1536 * 1872 * 4);
        // 有不透明像素（不是全透明图）
        assert!(data.rgba.chunks_exact(4).any(|p| p[3] > 0));
    }

    #[test]
    fn builtin_dog_wagging_doggy_is_standard_and_distinct() {
        let (meta, data) = load_builtin_pet(BUILTIN_DOG_ID).unwrap();
        assert_eq!(meta.id, "wagging-doggy");
        assert!(meta.display_name.contains("wagging-doggy"), "{}", meta.display_name);
        assert_eq!((data.cols, data.rows), (8, 9));
        assert_eq!((data.frame_w, data.frame_h), (192, 208));
        assert_eq!(data.rgba.len(), 1536 * 1872 * 4);
        assert!(data.rgba.chunks_exact(4).any(|p| p[3] > 0));
        // 与小猫图块不同（不是同一张图的拷贝）
        let (_, cat) = load_builtin().unwrap();
        assert_ne!(data.rgba, cat.rgba, "dog sheet must differ from cat sheet");
    }

    #[test]
    fn builtin_pet_unknown_id_is_error() {
        assert!(load_builtin_pet("no-such-builtin").is_err());
    }

    // ---- 扫描顺序（TC-SP-06）----

    #[test]
    fn scan_order_codex_first_then_petdex_with_dedup() {
        let home = tempdir("scan");
        let sheet = make_sheet(image::ImageFormat::WebP, 1536, 1872, [1, 1, 1, 255]);

        write_pet(&home.join(".codex/pets/zeta"), OK_META, &sheet, "spritesheet.webp");
        write_pet(&home.join(".petdex/pets/alpha"), OK_META, &sheet, "spritesheet.webp");
        // 同名 id 两边都有 → codex 优先
        write_pet(&home.join(".codex/pets/dup"), OK_META, &sheet, "spritesheet.webp");
        write_pet(&home.join(".petdex/pets/dup"), OK_META, &sheet, "spritesheet.webp");
        // 非法名 / 非目录跳过
        fs::create_dir_all(home.join(".codex/pets/.hidden")).unwrap();
        fs::write(home.join(".codex/pets/loose.webp"), &sheet).unwrap();

        let pets = scan_pets_in(&home);
        let ids: Vec<(&str, &str)> = pets.iter().map(|p| (p.id.as_str(), p.source)).collect();
        assert_eq!(
            ids,
            vec![
                ("dup", SOURCE_CODEX),
                ("zeta", SOURCE_CODEX),
                ("alpha", SOURCE_PETDEX),
            ]
        );

        fs::remove_dir_all(&home).ok();
    }

    #[test]
    fn pet_name_validation() {
        assert!(pet_name_ok("boba"));
        assert!(pet_name_ok("my-pet_2.v2"));
        assert!(!pet_name_ok(""));
        assert!(!pet_name_ok(".hidden"));
        assert!(!pet_name_ok("a b"));
        assert!(!pet_name_ok(&"x".repeat(64)));
    }

    // ---- 加载顺序解析（TC-SP-06 / TC-SP-09）----

    #[test]
    fn resolve_order_configured_builtin_codex_petdex() {
        let home = tempdir("resolve");
        let sheet = make_sheet(image::ImageFormat::WebP, 1536, 1872, [1, 1, 1, 255]);

        // 无配置无素材 → 内置默认 blinking-kitty（TC-SP-12）
        let s = resolve_requested(None, &home);
        assert_eq!((s.current_id.as_str(), s.current_source), (BUILTIN_ID, SOURCE_BUILTIN));
        assert_eq!(s.current_id, "blinking-kitty");
        assert!(s.notice.is_none());

        // 配置 id=blinking-kitty → 显式内置小猫
        let s = resolve_requested(Some(BUILTIN_ID), &home);
        assert_eq!((s.current_id.as_str(), s.current_source), (BUILTIN_ID, SOURCE_BUILTIN));

        // 配置 id=wagging-doggy → 内置小狗（TC-SP-12：下拉可切、同链路加载）
        let s = resolve_requested(Some(BUILTIN_DOG_ID), &home);
        assert_eq!(
            (s.current_id.as_str(), s.current_source),
            (BUILTIN_DOG_ID, SOURCE_BUILTIN)
        );
        assert!(s.notice.is_none());

        // 配置 codex 里的 pet → codex
        write_pet(&home.join(".codex/pets/kitty"), OK_META, &sheet, "spritesheet.webp");
        let s = resolve_requested(Some("kitty"), &home);
        assert_eq!((s.current_id.as_str(), s.current_source), ("kitty", SOURCE_CODEX));
        assert!(s.notice.is_none());

        // 配置的 id 两边都有 → codex 优先（内置 → codex → petdex 顺序）
        write_pet(&home.join(".petdex/pets/kitty"), OK_META, &sheet, "spritesheet.webp");
        let s = resolve_requested(Some("kitty"), &home);
        assert_eq!(s.current_source, SOURCE_CODEX);

        // 配置 petdex 独有 pet → petdex
        write_pet(&home.join(".petdex/pets/onlypet"), OK_META, &sheet, "spritesheet.webp");
        let s = resolve_requested(Some("onlypet"), &home);
        assert_eq!(s.current_source, SOURCE_PETDEX);

        fs::remove_dir_all(&home).ok();
    }

    #[test]
    fn resolve_falls_back_when_configured_missing_or_broken() {
        let home = tempdir("fallback");
        let sheet = make_sheet(image::ImageFormat::WebP, 1536, 1872, [1, 1, 1, 255]);

        // 配置不存在 → 回退内置 + 提示
        let s = resolve_requested(Some("ghost"), &home);
        assert_eq!(s.current_source, SOURCE_BUILTIN);
        assert!(s.notice.as_deref().unwrap_or("").contains("ghost"));

        // 配置损坏（pet.json broken）→ 回退内置 + 提示（TC-SP-09）
        let d = home.join(".codex/pets/brokenpet");
        write_pet(&d, "{ broken", &sheet, "spritesheet.webp");
        let s = resolve_requested(Some("brokenpet"), &home);
        assert_eq!(s.current_source, SOURCE_BUILTIN);
        let notice = s.notice.unwrap();
        assert!(notice.contains("brokenpet"), "{notice}");
        assert!(notice.contains("回退"), "{notice}");

        // 配置非标准网格 → 回退内置 + 标准文案（TC-SP-05）
        let bad = make_sheet(image::ImageFormat::WebP, 1536, 2080, [1, 1, 1, 255]);
        let d2 = home.join(".codex/pets/badgrid");
        write_pet(&d2, OK_META, &bad, "spritesheet.webp");
        let s = resolve_requested(Some("badgrid"), &home);
        assert_eq!(s.current_source, SOURCE_BUILTIN);
        assert!(s.notice.unwrap().contains("网格尺寸非标准"));

        fs::remove_dir_all(&home).ok();
    }

    #[test]
    fn resolve_without_config_picks_codex_then_petdex_before_builtin_fallback() {
        // TC-SP-06：无用户配置时的顺序 = 内置占位 → codex 扫描 → petdex 扫描。
        // 注意与「配置了 id」不同：无配置时按 builtin → codex → petdex 逐级取第一个可用。
        let home = tempdir("noconf");
        let sheet = make_sheet(image::ImageFormat::WebP, 1536, 1872, [1, 1, 1, 255]);

        // 只有 petdex 素材 → 无配置时仍落内置占位（内置在 codex 之前），
        // 且默认是 blinking-kitty 而非 wagging-doggy（TC-SP-12）
        write_pet(&home.join(".petdex/pets/lonely"), OK_META, &sheet, "spritesheet.webp");
        let s = resolve_requested(None, &home);
        assert_eq!(s.current_source, SOURCE_BUILTIN);
        assert_eq!(s.current_id, "blinking-kitty");

        fs::remove_dir_all(&home).ok();
    }

    // ---- 面板下拉（TC-SP-11）----

    #[test]
    fn list_pets_marks_broken_and_bad_grid_entries() {
        let home = tempdir("list");
        let sheet = make_sheet(image::ImageFormat::WebP, 1536, 1872, [1, 1, 1, 255]);
        let bad = make_sheet(image::ImageFormat::WebP, 1536, 2080, [1, 1, 1, 255]);

        write_pet(&home.join(".codex/pets/good"), r#"{"id":"good","displayName":"好的"}"#, &sheet, "spritesheet.webp");
        write_pet(&home.join(".codex/pets/broken"), "{ broken", &sheet, "spritesheet.webp");
        write_pet(&home.join(".petdex/pets/badgrid"), OK_META, &bad, "spritesheet.webp");

        let pets = list_pets_in(&home);
        assert_eq!(pets.len(), 5, "{pets:?}");
        // 内置分组两只并列（顺序 = 默认在前，TC-SP-11/12）
        assert_eq!(&pets[0].id, "blinking-kitty");
        assert!(pets[0].ok);
        assert!(pets[0].display_name.contains("blinking-kitty"));
        assert_eq!(&pets[1].id, "wagging-doggy");
        assert!(pets[1].ok);
        assert!(pets[1].display_name.contains("wagging-doggy"));
        // codex 内按名字序：broken < good
        assert_eq!(&pets[2].id, "broken");
        assert!(!pets[2].ok);
        assert!(pets[2].problem.as_deref().unwrap_or("").contains("pet.json"));
        assert_eq!(&pets[3].id, "good");
        assert!(pets[3].ok);
        assert_eq!(&pets[3].display_name, "好的");
        assert_eq!(&pets[4].id, "badgrid");
        assert!(!pets[4].ok);
        assert!(pets[4].problem.as_deref().unwrap_or("").contains("网格尺寸非标准"));

        fs::remove_dir_all(&home).ok();
    }

    // （v2 M2 atlas_sheet_png / base64 / PNG 缓存相关测试随命令一并回收删除
    //  ——2026-08-24 修订：mini 猫移除，唯一消费方消失，V2-DESIGN §2.4。）
}
