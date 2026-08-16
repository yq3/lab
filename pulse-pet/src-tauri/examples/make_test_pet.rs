//! 生成 TC-SP-04/05/09 的测试素材目录（开发/测试辅助，不入包）。
//!
//! 用法：`cargo run --example make_test_pet -- <输出根目录>`
//! 在输出根目录下生成 3 个 pet 目录（可直接拷入 `~/.codex/pets/`）：
//!   - testpet-good/    标准 v1 atlas（1536×1872 webp，9 行不同底色）
//!   - testpet-badgrid/ 非标准网格（1536×2080 = 8×10，TC-SP-05）
//!   - testpet-broken/  pet.json 损坏（TC-SP-09）
//!   - testpet-nosheet/ pet.json 正常但 spritesheet 缺失（TC-SP-09）
//!
//! 编码用 image crate（webp 无损），Rust 侧解码链路与正式加载一致。

use std::path::PathBuf;

fn main() {
    let out = std::env::args()
        .nth(1)
        .map(PathBuf::from)
        .unwrap_or_else(|| std::env::temp_dir().join("pulsepet-test-pets"));
    println!("output root: {}", out.display());

    let row_colors: [[u8; 4]; 9] = [
        [240, 240, 240, 255],
        [173, 216, 230, 255],
        [203, 186, 230, 255],
        [178, 226, 187, 255],
        [247, 223, 147, 255],
        [168, 168, 178, 255],
        [247, 197, 160, 255],
        [160, 226, 226, 255],
        [244, 184, 196, 255],
    ];

    // 标准 v1：9 行 × 8 列，每行一色（肉眼可辨 9 状态映射是否正确）
    let mut sheet = image::RgbaImage::new(1536, 1872);
    for row in 0..9u32 {
        for y in 0..208u32 {
            for x in 0..1536u32 {
                sheet.put_pixel(x, row * 208 + y, image::Rgba(row_colors[row as usize]));
            }
        }
    }
    write_pet(&out, "testpet-good", &sheet, r#"{"id":"testpet-good","displayName":"测试宠物（标准8×9）"}"#);

    // 非标准：8×10 网格（1536×2080）
    let mut bad = image::RgbaImage::new(1536, 2080);
    for row in 0..10u32 {
        let c = row_colors[(row as usize) % 9];
        for y in 0..208u32 {
            for x in 0..1536u32 {
                bad.put_pixel(x, row * 208 + y, image::Rgba(c));
            }
        }
    }
    write_pet(&out, "testpet-badgrid", &bad, r#"{"id":"testpet-badgrid","displayName":"测试宠物（非标准8×10）"}"#);

    // 损坏 pet.json
    let dir = out.join("testpet-broken");
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(dir.join("pet.json"), "{ broken json").unwrap();
    // 借用 good 的 sheet（内容无关，meta 先失败）
    let mut buf = std::io::Cursor::new(Vec::new());
    sheet.write_to(&mut buf, image::ImageFormat::WebP).unwrap();
    std::fs::write(dir.join("spritesheet.webp"), buf.into_inner()).unwrap();
    println!("wrote {}", dir.display());

    // spritesheet 缺失
    let dir = out.join("testpet-nosheet");
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(
        dir.join("pet.json"),
        r#"{"id":"testpet-nosheet","displayName":"测试宠物（缺spritesheet）"}"#,
    )
    .unwrap();
    println!("wrote {}", dir.display());
}

fn write_pet(out: &std::path::Path, name: &str, sheet: &image::RgbaImage, meta: &str) {
    let dir = out.join(name);
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(dir.join("pet.json"), meta).unwrap();
    let mut buf = std::io::Cursor::new(Vec::new());
    sheet.write_to(&mut buf, image::ImageFormat::WebP).unwrap();
    std::fs::write(dir.join("spritesheet.webp"), buf.into_inner()).unwrap();
    println!("wrote {} (1536×{} webp)", dir.display(), sheet.height());
}
