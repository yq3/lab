/**
 * 生成 PulsePet 占位精灵与图标资源（无第三方依赖，纯 Node 内置 zlib 编码 PNG）。
 *
 * 产出：
 *   - public/placeholder-cat.png     128×128 占位精灵（简洁像素风小猫：坐姿 + 单眨眼）
 *   - scripts/app-icon.png           1024×1024 App 图标源（tauri icon 用它生成全套）
 *
 * 素材为作者自绘（CC0），无许可问题（DECISIONS §3.7 / DESIGN §6.1）。
 */
import { deflateSync } from "node:zlib";
import { writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

// ---- 调色板 (RGBA) ----
const PAL = {
  ".": [0, 0, 0, 0],
  K: [58, 58, 68, 255], // 描边
  W: [244, 244, 247, 255], // 白色毛发
  P: [244, 168, 184, 255], // 粉色（内耳/鼻子）
  B: [42, 42, 51, 255], // 眼睛
};

// ---- 32×32 像素画小猫（坐姿 + 右眼单眨眼）----
const CAT = [
  "................................",
  "................................",
  ".........KK..........KK.........",
  "........KPPK........KPPK........",
  "........KPPK........KPPK........",
  ".......KPPPPK......KPPPPK.......",
  "......KWWWWWWWWWWWWWWWWWWK......",
  "......KWWWWWWWWWWWWWWWWWWK......",
  "......KWWWWWWWWWWWWWWWWWWK......",
  "......KWWWWWWWWWWWWWWWWWWK......",
  "......KWWWWBBWWWWWWKKWWWWK......",
  "......KWWWWBBWWWWWWWWWWWWK......",
  "......KWWWWWWWWWWWWWWWWWWK......",
  "......KWWWWWWWPPPPWWWWWWWK......",
  "......KWWWWWWWWPPWWWWWWWWK......",
  "......KWWWWWWWWWWWWWWWWWWK......",
  "......KWWWWWWWWWWWWWWWWWWK......",
  ".........KWWWWWWWWWWWWK.........",
  ".........KWWWWWWWWWWWWK.KK......",
  ".........KWWWWWWWWWWWWK..KK.....",
  ".........KWWWWWWWWWWWWK...KK....",
  ".........KWWWWWWWWWWWWK...KK....",
  ".........KWWWWWWWWWWWWK..KK.....",
  ".........KWWWWWWWWWWWWK.........",
  ".........KWWWWWWWWWWWWK.........",
  ".........KWWWWK..KWWWWK.........",
  ".........KWWWWK..KWWWWK.........",
  ".........KKKKK....KKKKK.........",
  "................................",
  "................................",
  "................................",
  "................................",
];

// ---- PNG 编码（RGBA、8-bit、无隔行）----
const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();

function crc32(buf) {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i++) {
    c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8);
  }
  return (c ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length, 0);
  const typeBuf = Buffer.from(type, "ascii");
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(Buffer.concat([typeBuf, data])), 0);
  return Buffer.concat([len, typeBuf, data, crc]);
}

function encodePNG(width, height, rgba) {
  const sig = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 6; // color type RGBA
  ihdr[10] = 0; // compression
  ihdr[11] = 0; // filter
  ihdr[12] = 0; // interlace

  // 每行前加 filter byte 0
  const stride = width * 4;
  const raw = Buffer.alloc((stride + 1) * height);
  for (let y = 0; y < height; y++) {
    raw[y * (stride + 1)] = 0;
    rgba.copy(raw, y * (stride + 1) + 1, y * stride, (y + 1) * stride);
  }
  const idat = deflateSync(raw, { level: 9 });

  return Buffer.concat([
    sig,
    chunk("IHDR", ihdr),
    chunk("IDAT", idat),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

function gridToRGBA(grid, scale) {
  const gs = grid.length; // 32
  const size = gs * scale;
  const rgba = Buffer.alloc(size * size * 4);
  for (let gy = 0; gy < gs; gy++) {
    for (let gx = 0; gx < gs; gx++) {
      const c = PAL[grid[gy][gx]];
      if (!c) throw new Error(`unknown palette char '${grid[gy][gx]}' at ${gx},${gy}`);
      for (let sy = 0; sy < scale; sy++) {
        for (let sx = 0; sx < scale; sx++) {
          const x = gx * scale + sx;
          const y = gy * scale + sy;
          const i = (y * size + x) * 4;
          rgba[i] = c[0];
          rgba[i + 1] = c[1];
          rgba[i + 2] = c[2];
          rgba[i + 3] = c[3];
        }
      }
    }
  }
  return { size, rgba };
}

function main() {
  // 校验网格
  for (let y = 0; y < CAT.length; y++) {
    if (CAT[y].length !== 32) {
      throw new Error(`row ${y} length ${CAT[y].length} != 32`);
    }
  }

  // 打印 ASCII 预览
  console.log("=== 小猫 ASCII 预览（32×32）===");
  for (const row of CAT) console.log(row);

  const publicDir = join(__dirname, "..", "public");
  mkdirSync(publicDir, { recursive: true });

  const sprite = gridToRGBA(CAT, 4); // 128×128
  writeFileSync(join(publicDir, "placeholder-cat.png"), encodePNG(sprite.size, sprite.size, sprite.rgba));
  console.log(`wrote public/placeholder-cat.png (${sprite.size}×${sprite.size})`);

  const icon = gridToRGBA(CAT, 32); // 1024×1024
  writeFileSync(join(__dirname, "app-icon.png"), encodePNG(icon.size, icon.size, icon.rgba));
  console.log(`wrote scripts/app-icon.png (${icon.size}×${icon.size})`);
}

main();
