/**
 * 生成 PulsePet 占位精灵与图标资源（无第三方依赖，纯 Node 内置 zlib 编码 PNG）。
 *
 * 产出：
 *   - public/placeholder-cat.png     128×128 占位精灵（简洁像素风小猫：坐姿 + 单眨眼）
 *   - scripts/app-icon.png           1024×1024 App 图标源（tauri icon 用它生成全套）
 *   - src-tauri/assets/placeholder-atlas/{pet.json,spritesheet.png}
 *                                    M5 内置占位 atlas（codex 格式 8×9 = 1536×1872，
 *                                    单帧 192×208，9 行姿态 × 8 列；Rust include_bytes!
 *                                    内嵌，见 src-tauri/src/atlas.rs）
 *
 * 素材为作者自绘（CC0），无许可问题（DECISIONS §3.7 / DESIGN §6.1 / §6.2）。
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

// ---- M5 内置占位 atlas（DESIGN §6.2：codex 格式 8×9，单帧 192×208）----
//
// 复用 32×32 CAT 像素画：每帧放在 48×52 的格子空间里（×4 缩放 → 192×208），
// 行间用「毛色 + 姿态动作」区分 9 种状态（idle/running-right/running-left/
// waving/jumping/failed/waiting/running/review，行号与 petdex sprite.zig 一致）。
// 帧数少于 8 的行，多余列复制最后一帧（渲染端按帧时长表只播前面的列）。

const CELL_W = 48; // 192 / 4
const CELL_H = 52; // 208 / 4
const CAT_X = 8; // (48-32)/2
const CAT_Y = 10; // (52-32)/2

/** 每行毛色（替换调色板 W）——行号即 atlas 行。 */
const ROW_FUR = {
  0: [244, 244, 247], // idle 白
  1: [173, 216, 230], // running-right 浅蓝
  2: [203, 186, 230], // running-left 浅紫
  3: [178, 226, 187], // waving 浅绿
  4: [247, 223, 147], // jumping 浅黄
  5: [168, 168, 178], // failed 灰
  6: [247, 197, 160], // waiting 浅橙
  7: [160, 226, 226], // running 浅青
  8: [244, 184, 196], // review 浅玫红
};

/** CAT 里双眼位置（行 10-11：左眼 BB 列 11-12，右眼 KK 列 19-20；PetCanvas EYE_LEFT/4 同源）。 */
const EYE_L = { x: 11, y: 10 };
const EYE_R = { x: 19, y: 10 };

/** 空白 48×52 格子。 */
function blankCells() {
  return Array.from({ length: CELL_H }, () => Array(CELL_W).fill("."));
}

function put(cells, x, y, ch) {
  if (y < 0 || y >= CELL_H || x < 0 || x >= CELL_W) return;
  cells[y][x] = ch;
}

/**
 * 把 CAT 画到 cells 上。options：
 * - fur：替换 W 的颜色（放入局部调色板）
 * - eyes："open" | "blink" | "x"
 * - headShift：头部（CAT 行 <15）水平位移（waiting 张望）
 * - slump：整体下移格数（failed 垂头丧气）
 */
function blitCat(cells, ox, oy, { eyes = "open", headShift = 0, slump = 0 } = {}) {
  for (let gy = 0; gy < 32; gy++) {
    for (let gx = 0; gx < 32; gx++) {
      let ch = CAT[gy][gx];
      // 双眼先统一为 open（原始画右眼是 K 单眨眼，atlas 基线两眼睁开）
      if (gy >= EYE_L.y && gy <= EYE_L.y + 1 && gx >= EYE_L.x && gx <= EYE_L.x + 1) ch = "B";
      if (gy >= EYE_R.y && gy <= EYE_R.y + 1 && gx >= EYE_R.x && gx <= EYE_R.x + 1) ch = "B";
      const sx = ox + gx + (gy < 15 ? headShift : 0);
      const sy = oy + gy + slump;
      if (ch !== ".") put(cells, sx, sy, ch);
    }
  }
  // 眼睛覆盖层
  const eyePts = [];
  for (const e of [EYE_L, EYE_R]) {
    for (let dy = 0; dy <= 1; dy++)
      for (let dx = 0; dx <= 1; dx++) eyePts.push({ x: e.x + dx, y: e.y + dy });
  }
  const adj = (p) => ({ x: p.x + ox + headShift, y: p.y + oy + slump });
  if (eyes === "blink") {
    for (const p of eyePts) {
      const q = adj(p);
      put(cells, q.x, q.y, ".");
    }
    // 下眼皮一条线
    for (const e of [EYE_L, EYE_R]) {
      const q = adj({ x: e.x, y: e.y + 1 });
      put(cells, q.x, q.y, "K");
      put(cells, q.x + 1, q.y, "K");
    }
  } else if (eyes === "x") {
    for (const p of eyePts) {
      const q = adj(p);
      put(cells, q.x, q.y, ".");
    }
    for (const e of [EYE_L, EYE_R]) {
      const cx = e.x + ox + headShift + 0.5;
      const cy = e.y + oy + slump + 0.5;
      for (const [dx, dy] of [
        [-1, -1],
        [1, 1],
        [-1, 1],
        [1, -1],
        [0, 0],
      ]) {
        put(cells, Math.round(cx + dx), Math.round(cy + dy), "K");
      }
    }
  }
}

/** 速度线（奔跑行）：side "left" | "right" | "both"，帧奇偶决定画 2 还是 3 条。 */
function motionDashes(cells, side, frame) {
  const rows = frame % 2 === 0 ? [16, 20] : [15, 18, 21];
  const draw = (x0) => {
    for (const y of rows) {
      put(cells, x0, y, "K");
      put(cells, x0 + 1, y, "K");
    }
  };
  if (side === "left" || side === "both") draw(2);
  if (side === "right" || side === "both") draw(CELL_W - 4);
}

/** 挥手：身体右侧举起的手臂（waving 行 3），高低交替。 */
function waveArm(cells, frame) {
  const top = frame % 2 === 0 ? 12 : 15;
  for (let y = top; y <= 17; y++) put(cells, 23, y, y === 17 ? "K" : "W2");
  put(cells, 24, top, "K");
}

/** review：头顶感叹号，左右交替。 */
function exclaim(cells, frame) {
  const x = frame % 2 === 0 ? 12 : 32;
  for (let y = 3; y <= 6; y++) put(cells, x, y, "K");
  put(cells, x, 8, "K");
}

/** 生成 row 行 col 列这一帧的 48×52 格子。 */
function atlasFrameCells(row, col) {
  const cells = blankCells();
  const fur = ROW_FUR[row];
  let opts = { fur };
  let dx = 0;
  let dy = 0;
  switch (row) {
    case 0: // idle：6 帧眨眼（列 1-2 闭眼，对应 110ms 短帧）
      opts.eyes = col === 1 || col === 2 ? "blink" : "open";
      dy = col >= 4 ? 1 : 0; // 长帧里轻微下沉（呼吸感）
      break;
    case 1: // running-right：向右侧倾 + 左侧速度线
    case 2: {
      // running-left：镜像
      dx = col % 2 === 0 ? 2 : 0;
      dy = col % 2;
      blitCat(cells, CAT_X + (row === 1 ? dx : -dx), CAT_Y + dy, opts);
      motionDashes(cells, row === 1 ? "left" : "right", col);
      return cells;
    }
    case 3: // waving：4 帧，手臂高低交替
      blitCat(cells, CAT_X, CAT_Y, opts);
      waveArm(cells, col);
      return cells;
    case 4: // jumping：5 帧抛物线
      dy = [0, -4, -8, -4, 0][Math.min(col, 4)];
      break;
    case 5: // failed：X 眼 + 下坠 2 格，8 帧轻微起伏
      opts.eyes = "x";
      opts.slump = col % 4 === 3 ? 3 : 2;
      break;
    case 6: // waiting：6 帧头部左右张望
      opts.headShift = col % 2 === 0 ? -1 : 1;
      dy = col === 5 ? 1 : 0;
      break;
    case 7: // running：6 帧原地颠 + 两侧速度线
      dy = col % 2;
      blitCat(cells, CAT_X, CAT_Y + dy, opts);
      motionDashes(cells, "both", col);
      return cells;
    case 8: // review：6 帧头顶感叹号左右
      dy = col === 5 ? 1 : 0;
      break;
  }
  blitCat(cells, CAT_X + dx, CAT_Y + dy, opts);
  if (row === 8) exclaim(cells, col);
  return cells;
}

function cellsToRGBA(cells, pal) {
  const rgba = Buffer.alloc(CELL_W * 4 * CELL_H * 4 * 4);
  for (let gy = 0; gy < CELL_H; gy++) {
    for (let gx = 0; gx < CELL_W; gx++) {
      const c = pal[cells[gy][gx]] ?? [0, 0, 0, 0];
      const a = c.length > 3 ? c[3] : 255; // ROW_FUR 只有 RGB 时默认不透明
      for (let sy = 0; sy < 4; sy++) {
        for (let sx = 0; sx < 4; sx++) {
          const x = gx * 4 + sx;
          const y = gy * 4 + sy;
          const i = (y * (CELL_W * 4) + x) * 4;
          rgba[i] = c[0];
          rgba[i + 1] = c[1];
          rgba[i + 2] = c[2];
          rgba[i + 3] = a;
        }
      }
    }
  }
  return rgba;
}

/** 各行动画实际使用的列数（与前端 sprite.ts 帧时长表一致，多余列复制最后一帧）。 */
const ROW_FRAME_COUNTS = { 0: 6, 1: 8, 2: 8, 3: 4, 4: 5, 5: 8, 6: 6, 7: 6, 8: 6 };

function genPlaceholderAtlas() {
  const W = 1536;
  const H = 1872;
  const fw = 192;
  const fh = 208;
  const sheet = Buffer.alloc(W * H * 4);
  for (let row = 0; row < 9; row++) {
    const lastCol = ROW_FRAME_COUNTS[row] - 1;
    for (let col = 0; col < 8; col++) {
      const srcCol = Math.min(col, lastCol);
      const cells = atlasFrameCells(row, srcCol);
      const pal = { ...PAL, W: ROW_FUR[row], W2: ROW_FUR[row] };
      const rgba = cellsToRGBA(cells, pal);
      // 逐行拷贝（帧宽 192 < sheet 步长 1536，不能整块 copy）
      const ox = col * fw;
      const oy = row * fh;
      for (let y = 0; y < fh; y++) {
        rgba.copy(sheet, ((oy + y) * W + ox) * 4, y * fw * 4, (y + 1) * fw * 4);
      }
    }
  }
  return sheet;
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

  // M5：内置占位 atlas（codex 格式 8×9）
  const atlasDir = join(__dirname, "..", "src-tauri", "assets", "placeholder-atlas");
  mkdirSync(atlasDir, { recursive: true });
  const sheet = genPlaceholderAtlas();
  writeFileSync(join(atlasDir, "spritesheet.png"), encodePNG(1536, 1872, sheet));
  writeFileSync(
    join(atlasDir, "pet.json"),
    JSON.stringify(
      {
        id: "builtin",
        displayName: "内置占位小猫",
        description:
          "PulsePet 内置占位 atlas（codex 格式 8×9 = 1536×1872，单帧 192×208，9 行姿态）。作者自绘，CC0。",
        spritesheetPath: "spritesheet.png",
      },
      null,
      2,
    ) + "\n",
  );
  console.log(`wrote ${atlasDir}/{pet.json,spritesheet.png} (1536×1872)`);
}

main();
