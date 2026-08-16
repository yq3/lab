// opencode 配置 JSONC 感知的幂等合并/卸载（TC-EV-01/02）。
//
// - `mergePlugin`：往顶层 `plugin` 数组合并 `pulse-pet` 一项，带 `// --pulse-pet-managed`
//   行内标记；注释与尾逗号保留（仅做文本级插入，不重写其它内容）。
// - `uninstallPlugin`：只移除带 `--pulse-pet-managed` 标记的项，用户原项保留。
// - 幂等：已含标记则原样返回。
//
// 插入格式（严格 JSON 语义，无尾逗号；标记注释后强制换行，避免吞掉闭合括号）：
//   `"pulse-pet" // --pulse-pet-managed\n`
//
// 供 install.sh / install.ps1 以 `node` 调用，也可被 vitest 直接单测。

const MARKER = "--pulse-pet-managed";
// 插件项 spec：opencode 1.18.x 的本地插件用相对配置文件的路径（`plugin` 数组裸名会被
// 当作 npm 包）。插件文件由 install 脚本拷到 `~/.config/opencode/plugins/`。
const PLUGIN_SPEC = "./plugins/pulse-pet-hook.js";

// ---- JSONC tokenizer（记录 token 位置，跳过注释与空白，字符串处理转义）----

function tokenize(text) {
  const tokens = [];
  let i = 0;
  const n = text.length;
  while (i < n) {
    const c = text[i];
    if (/\s/.test(c)) {
      i += 1;
      continue;
    }
    if (c === "/" && text[i + 1] === "/") {
      i += 2;
      while (i < n && text[i] !== "\n") i += 1;
      continue;
    }
    if (c === "/" && text[i + 1] === "*") {
      i += 2;
      while (i < n && !(text[i] === "*" && text[i + 1] === "/")) i += 1;
      i = Math.min(i + 2, n);
      continue;
    }
    if ("{}[]:,".includes(c)) {
      tokens.push({ type: c, start: i, end: i + 1, value: c });
      i += 1;
      continue;
    }
    if (c === '"') {
      const start = i;
      i += 1;
      while (i < n && text[i] !== '"') {
        if (text[i] === "\\") i += 2;
        else i += 1;
      }
      i += 1; // 闭合引号
      tokens.push({ type: "string", start, end: i, value: text.slice(start + 1, i - 1) });
      continue;
    }
    const start = i;
    while (i < n && /[0-9a-zA-Z_\-+.]/.test(text[i])) i += 1;
    tokens.push({ type: "literal", start, end: i, value: text.slice(start, i) });
  }
  return tokens;
}

/** 找到与 openIndex 处的 `[` 匹配的 `]` 的 token 下标（-1 未找到）。 */
function matchingBracket(tokens, openIndex) {
  let depth = 0;
  for (let k = openIndex; k < tokens.length; k += 1) {
    if (tokens[k].type === "[") depth += 1;
    else if (tokens[k].type === "]") {
      depth -= 1;
      if (depth === 0) return k;
    }
  }
  return -1;
}

/** 顶层 `plugin` 键：返回其数组 `[` 的 token 下标，或 null。 */
function findTopLevelPlugin(tokens) {
  let depth = 0;
  for (let k = 0; k < tokens.length; k += 1) {
    const t = tokens[k];
    if (t.type === "{") depth += 1;
    else if (t.type === "}") depth -= 1;
    else if (t.type === "string" && depth === 1 && t.value === "plugin") {
      const colon = tokens[k + 1];
      const val = tokens[k + 2];
      if (colon?.type === ":" && val?.type === "[") return k + 2;
      return null;
    }
  }
  return null;
}

/** 顶层对象闭合 `}` 的 token 下标（-1 未找到）。 */
function topLevelClosingBrace(tokens) {
  let depth = 0;
  for (let k = 0; k < tokens.length; k += 1) {
    if (tokens[k].type === "{") depth += 1;
    else if (tokens[k].type === "}") {
      depth -= 1;
      if (depth === 0) return k;
    }
  }
  return -1;
}

/**
 * 合并 pulse-pet 插件项（幂等，JSONC 感知）。返回新文本。
 */
export function mergePlugin(
  text,
  { pluginName = PLUGIN_SPEC, marker = MARKER } = {},
) {
  if (typeof text !== "string") return text;
  if (text.includes(marker)) return text; // 已安装 → 幂等

  const tokens = tokenize(text);
  const found = findTopLevelPlugin(tokens);

  if (found) {
    const close = matchingBracket(tokens, found);
    if (close < 0) return text;
    const insertAt = tokens[close].start;
    const prev = tokens[close - 1];
    const empty = prev?.type === "[";
    const hasTrailingComma = prev?.type === ",";
    const needsLeadingComma = !empty && !hasTrailingComma;
    const entry = `${needsLeadingComma ? ", " : ""}"${pluginName}" // ${marker}\n`;
    return text.slice(0, insertAt) + entry + text.slice(insertAt);
  }

  // 无 plugin 键 → 新增
  const closing = topLevelClosingBrace(tokens);
  if (closing >= 0) {
    const closeTok = tokens[closing];
    const prev = tokens[closing - 1];
    if (prev?.type === "{") {
      // 空对象
      const entry = `\n  "plugin": [\n    "${pluginName}" // ${marker}\n  ]`;
      return text.slice(0, closeTok.start) + entry + text.slice(closeTok.start);
    }
    // 非空对象：在最后一个值之后补逗号（若需要）+ 插入 plugin 块
    const insertAt = prev.end;
    const needsComma = prev.type !== ",";
    const entry = `${needsComma ? "," : ""}\n  "plugin": [\n    "${pluginName}" // ${marker}\n  ]`;
    return text.slice(0, insertAt) + entry + text.slice(insertAt);
  }
  return text; // 无法定位，保守返回原文
}

/**
 * 卸载：只移除带 marker 的 pulse-pet 项（含其前导逗号），保留其它内容。
 */
export function uninstallPlugin(
  text,
  { pluginName = PLUGIN_SPEC, marker = MARKER } = {},
) {
  if (typeof text !== "string") return text;
  const markerIdx = text.indexOf(marker);
  if (markerIdx < 0) return text; // 未安装 → 幂等

  // 移除范围终点：marker 注释末尾（含其后的换行）
  const markerEnd = markerIdx + marker.length;
  let end = markerEnd;
  const nl = text.indexOf("\n", markerEnd);
  if (nl !== -1) end = nl + 1;

  // 在 marker 所在行内，定位 `"pulse-pet"` 及其可能的前导逗号
  const lineStart = text.lastIndexOf("\n", markerIdx - 1) + 1;
  const before = text.slice(lineStart, markerIdx);
  const pluginPos = before.lastIndexOf(`"${pluginName}"`);
  if (pluginPos < 0) return text;

  let start = lineStart + pluginPos;
  const beforePlugin = before.slice(0, pluginPos);
  const commaMatch = beforePlugin.match(/,(\s*)$/);
  if (commaMatch) start -= commaMatch[0].length;

  return text.slice(0, start) + text.slice(end);
}

// ---- CLI：node opencode-config.mjs <install|uninstall> <configPath> ----

import { pathToFileURL } from "node:url";

const isMain =
  typeof process !== "undefined" &&
  process.argv[1] != null &&
  import.meta.url === pathToFileURL(process.argv[1]).href;

if (isMain) {
  const [, , cmd, cfgPath] = process.argv;
  const { readFileSync, writeFileSync } = await import("node:fs");
  if (!cmd || !cfgPath) {
    console.error("usage: node opencode-config.mjs <install|uninstall> <configPath>");
    process.exit(2);
  }
  const src = readFileSync(cfgPath, "utf8");
  const out = cmd === "uninstall" ? uninstallPlugin(src) : mergePlugin(src);
  writeFileSync(cfgPath, out);
}
