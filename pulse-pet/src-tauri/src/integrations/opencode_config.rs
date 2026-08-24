//! opencode 配置 JSONC 感知的幂等合并/卸载（v2 M1 Rust 化，V2-DESIGN §1.4.5）。
//!
//! 从 v1 `opencode-plugin/opencode-config.mjs` 逐行移植（TC-INT-08-4：用例 =
//! `opencode-config.test.ts` 全量平移）：保留注释/尾逗号/未知键（仅文本级插入，
//! 不重写其它内容）；定位失败保守返回原文（`located=false`，调用方报 doctor
//! error 且不落笔）。
//!
//! - `merge_plugin`：往顶层 `plugin` 数组合并 `"./plugins/pulse-pet-hook.js"`
//!   一项，带 `// --pulse-pet-managed` 行内标记；已含标记则幂等原样返回。
//! - `uninstall_plugin`：只移除带标记的项（含前导逗号），用户原项保留；
//!   未安装幂等；标记所在行无法定位 `plugin` 项时保守返回原文。
//!
//! 移植口径说明：JS 版以 UTF-16 code unit 扫描，本移植按字节扫描——所有定界
//! 符（`{}[]:,"` 与注释标记）均为 ASCII，多字节 UTF-8 序列不会误命中，行为等价。

/// managed 标记（与 opencode-config.mjs 的 MARKER 逐字一致）。
pub const MARKER: &str = "--pulse-pet-managed";

/// 插件项 spec：opencode 1.18.x 的本地插件用相对配置文件的路径。
pub const PLUGIN_SPEC: &str = "./plugins/pulse-pet-hook.js";

// ---- JSONC tokenizer（记录 token 位置，跳过注释与空白，字符串处理转义）----

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum TokKind {
    OpenBrace,
    CloseBrace,
    OpenBracket,
    CloseBracket,
    Colon,
    Comma,
    Str,
    Literal,
}

#[derive(Debug)]
struct Token {
    kind: TokKind,
    start: usize,
    end: usize,
    /// 仅 `Str` 有意义（字符串字面量内容，转义保持原样）。
    value: String,
}

fn tokenize(text: &str) -> Vec<Token> {
    let b = text.as_bytes();
    let n = b.len();
    let mut i = 0usize;
    let mut tokens: Vec<Token> = Vec::new();
    while i < n {
        let c = b[i];
        // 空白（JS /\s/；此处按字节判 ASCII 空白，多字节空白经 literal 分支跳过）
        if matches!(c, b' ' | b'\t' | b'\n' | b'\r' | 0x0b | 0x0c) {
            i += 1;
            continue;
        }
        // 行注释
        if c == b'/' && i + 1 < n && b[i + 1] == b'/' {
            i += 2;
            while i < n && b[i] != b'\n' {
                i += 1;
            }
            continue;
        }
        // 块注释
        if c == b'/' && i + 1 < n && b[i + 1] == b'*' {
            i += 2;
            while i + 1 < n && !(b[i] == b'*' && b[i + 1] == b'/') {
                i += 1;
            }
            i = std::cmp::min(i + 2, n);
            continue;
        }
        // 标点
        let punct = match c {
            b'{' => Some(TokKind::OpenBrace),
            b'}' => Some(TokKind::CloseBrace),
            b'[' => Some(TokKind::OpenBracket),
            b']' => Some(TokKind::CloseBracket),
            b':' => Some(TokKind::Colon),
            b',' => Some(TokKind::Comma),
            _ => None,
        };
        if let Some(kind) = punct {
            tokens.push(Token {
                kind,
                start: i,
                end: i + 1,
                value: String::new(),
            });
            i += 1;
            continue;
        }
        // 字符串（转义感知；未闭合容错——与 JS 版一致按已闭合处理）
        if c == b'"' {
            let start = i;
            i += 1;
            while i < n && b[i] != b'"' {
                if b[i] == b'\\' {
                    i += 2;
                } else {
                    i += 1;
                }
            }
            i += 1; // 闭合引号（未闭合时越过 n，下方 clamp）
            let inner_end = std::cmp::min(i.saturating_sub(1), n);
            let inner_start = std::cmp::min(start + 1, inner_end);
            tokens.push(Token {
                kind: TokKind::Str,
                start,
                end: std::cmp::min(i, n),
                value: text[inner_start..inner_end].to_string(),
            });
            continue;
        }
        // 字面量（数字/字母/_-+.）
        let start = i;
        while i < n {
            let ch = b[i];
            if ch.is_ascii_alphanumeric() || ch == b'_' || ch == b'-' || ch == b'+' || ch == b'.' {
                i += 1;
            } else {
                break;
            }
        }
        if i > start {
            tokens.push(Token {
                kind: TokKind::Literal,
                start,
                end: i,
                value: String::new(),
            });
        } else {
            // P2-9（M2 遗留）同款防御：非法字符（@、单引号、emoji 首字节等）零消费
            // 会死循环；跳过 1 个字节保证推进，不产出 token（该输入本就非法，
            // merge_plugin 定位失败时保守返回原文）。
            i += 1;
        }
    }
    tokens
}

/// 找到与 `open_index` 处的 `[` 匹配的 `]` 的 token 下标（None 未找到）。
fn matching_bracket(tokens: &[Token], open_index: usize) -> Option<usize> {
    let mut depth = 0i32;
    for (k, t) in tokens.iter().enumerate().skip(open_index) {
        match t.kind {
            TokKind::OpenBracket => depth += 1,
            TokKind::CloseBracket => {
                depth -= 1;
                if depth == 0 {
                    return Some(k);
                }
            }
            _ => {}
        }
    }
    None
}

/// 顶层 `plugin` 键：返回其数组 `[` 的 token 下标，或 None。
fn find_top_level_plugin(tokens: &[Token]) -> Option<usize> {
    let mut depth = 0i32;
    for k in 0..tokens.len() {
        let t = &tokens[k];
        match t.kind {
            TokKind::OpenBrace => depth += 1,
            TokKind::CloseBrace => depth -= 1,
            TokKind::Str if depth == 1 && t.value == "plugin" => {
                let colon = tokens.get(k + 1)?;
                let val = tokens.get(k + 2)?;
                if colon.kind == TokKind::Colon && val.kind == TokKind::OpenBracket {
                    return Some(k + 2);
                }
                return None;
            }
            _ => {}
        }
    }
    None
}

/// 顶层对象闭合 `}` 的 token 下标（None 未找到）。
fn top_level_closing_brace(tokens: &[Token]) -> Option<usize> {
    let mut depth = 0i32;
    for (k, t) in tokens.iter().enumerate() {
        match t.kind {
            TokKind::OpenBrace => depth += 1,
            TokKind::CloseBrace => {
                depth -= 1;
                if depth == 0 {
                    return Some(k);
                }
            }
            _ => {}
        }
    }
    None
}

/// 文本级插入/移除结果：`located=false` = 无法安全定位，保守返回原文。
#[derive(Debug, Clone, PartialEq)]
pub struct JsoncOutcome {
    pub text: String,
    pub located: bool,
}

/// 合并 pulse-pet 插件项（幂等，JSONC 感知；opencode-config.mjs::mergePlugin 逐行移植）。
pub fn merge_plugin(text: &str) -> JsoncOutcome {
    if text.contains(MARKER) {
        return JsoncOutcome {
            text: text.to_string(),
            located: true,
        }; // 已安装 → 幂等
    }

    let tokens = tokenize(text);
    let found = find_top_level_plugin(&tokens);

    if let Some(open) = found {
        let Some(close) = matching_bracket(&tokens, open) else {
            return JsoncOutcome { text: text.to_string(), located: false };
        };
        let insert_at = tokens[close].start;
        let prev = &tokens[close - 1];
        let empty = prev.kind == TokKind::OpenBracket;
        let has_trailing_comma = prev.kind == TokKind::Comma;
        let needs_leading_comma = !empty && !has_trailing_comma;
        let entry = format!(
            "{}\"{PLUGIN_SPEC}\" // {MARKER}\n",
            if needs_leading_comma { ", " } else { "" }
        );
        return JsoncOutcome {
            text: format!("{}{}{}", &text[..insert_at], entry, &text[insert_at..]),
            located: true,
        };
    }

    // 无 plugin 键 → 新增
    if let Some(closing) = top_level_closing_brace(&tokens) {
        let close_tok = &tokens[closing];
        let prev = &tokens[closing - 1];
        if prev.kind == TokKind::OpenBrace {
            // 空对象
            let entry = format!("\n  \"plugin\": [\n    \"{PLUGIN_SPEC}\" // {MARKER}\n  ]");
            let at = close_tok.start;
            return JsoncOutcome {
                text: format!("{}{}{}", &text[..at], entry, &text[at..]),
                located: true,
            };
        }
        // 非空对象：在最后一个值之后补逗号（若需要）+ 插入 plugin 块
        let insert_at = prev.end;
        let needs_comma = prev.kind != TokKind::Comma;
        let entry = format!(
            "{}\n  \"plugin\": [\n    \"{PLUGIN_SPEC}\" // {MARKER}\n  ]",
            if needs_comma { "," } else { "" }
        );
        return JsoncOutcome {
            text: format!("{}{}{}", &text[..insert_at], entry, &text[insert_at..]),
            located: true,
        };
    }
    JsoncOutcome {
        text: text.to_string(),
        located: false,
    }
}

/// 卸载：只移除带 marker 的 pulse-pet 项（含其前导逗号），保留其它内容
/// （opencode-config.mjs::uninstallPlugin 逐行移植）。
pub fn uninstall_plugin(text: &str) -> JsoncOutcome {
    let Some(marker_idx) = text.find(MARKER) else {
        return JsoncOutcome {
            text: text.to_string(),
            located: true,
        }; // 未安装 → 幂等
    };

    // 移除范围终点：marker 注释末尾（含其后的换行）。marker 全 ASCII，
    // marker_end 必为 char 边界，直接切片安全。
    let marker_end = marker_idx + MARKER.len();
    let mut end = marker_end;
    if let Some(nl) = text[marker_end..].find('\n') {
        end = marker_end + nl + 1;
    }

    // 在 marker 所在行内，定位 `"./plugins/pulse-pet-hook.js"` 及其可能的前导逗号
    let line_start = text[..marker_idx].rfind('\n').map(|p| p + 1).unwrap_or(0);
    let before = &text[line_start..marker_idx];
    let Some(plugin_pos) = before.rfind(&format!("\"{PLUGIN_SPEC}\"")) else {
        return JsoncOutcome { text: text.to_string(), located: false };
    };

    let mut start = line_start + plugin_pos;
    let before_plugin = &before[..plugin_pos];
    if let Some(cpos) = before_plugin.rfind(',') {
        if before_plugin[cpos + 1..].chars().all(|c| c.is_whitespace()) {
            start -= before_plugin.len() - cpos;
        }
    }

    JsoncOutcome {
        text: format!("{}{}", &text[..start], &text[end..]),
        located: true,
    }
}

// ---------------------------------------------------------------------------
// 测试：opencode-config.test.ts 全量平移（TC-INT-08-4 / TC-EV-01/02 语义不回归）
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    /// JSONC → 严格 JSON（字符串感知地去除注释与尾逗号），校验合并后仍是合法
    /// JSONC（opencode-config.test.ts 的 jsoncToJson 同款移植）。
    fn jsonc_to_json(text: &str) -> serde_json::Value {
        let mut out = String::new();
        let b = text.as_bytes();
        let n = b.len();
        let mut i = 0usize;
        while i < n {
            let c = b[i];
            if c == b'"' {
                let start = i;
                i += 1;
                while i < n && b[i] != b'"' {
                    if b[i] == b'\\' {
                        i += 2;
                    } else {
                        i += 1;
                    }
                }
                i += 1;
                let end = i.min(n);
                // 字符串切片边界：start 与 end 都在引号（ASCII）处，必为边界
                out += &text[start..end];
                continue;
            }
            if c == b'/' && i + 1 < n && b[i + 1] == b'/' {
                while i < n && b[i] != b'\n' {
                    i += 1;
                }
                continue;
            }
            if c == b'/' && i + 1 < n && b[i + 1] == b'*' {
                i += 2;
                while i + 1 < n && !(b[i] == b'*' && b[i + 1] == b'/') {
                    i += 1;
                }
                i = (i + 2).min(n);
                continue;
            }
            if c == b',' {
                let mut j = i + 1;
                while j < n && (b[j] as char).is_whitespace() {
                    j += 1;
                }
                if j < n && (b[j] == b'}' || b[j] == b']') {
                    i += 1; // 尾逗号：跳过
                    continue;
                }
                out.push(',');
                i += 1;
                continue;
            }
            out.push(c as char);
            i += 1;
        }
        serde_json::from_str(&out).expect("jsonc_to_json helper: valid strict json")
    }

    const SPEC: &str = PLUGIN_SPEC;

    #[test]
    fn merge_into_existing_plugin_array_keeps_user_items() {
        let out = merge_plugin("{\n  \"plugin\": [\"my-plugin\"]\n}");
        assert!(out.located);
        assert!(out.text.contains(&format!("\"{SPEC}\"")));
        assert!(out.text.contains(MARKER));
        assert!(out.text.contains("\"my-plugin\""));
        assert_eq!(
            jsonc_to_json(&out.text),
            serde_json::json!({ "plugin": ["my-plugin", SPEC] })
        );
    }

    #[test]
    fn merge_is_idempotent() {
        let once = merge_plugin("{\n  \"plugin\": [\"my-plugin\"]\n}");
        let twice = merge_plugin(&once.text);
        assert_eq!(twice.text, once.text);
        assert_eq!(
            jsonc_to_json(&once.text),
            serde_json::json!({ "plugin": ["my-plugin", SPEC] })
        );
    }

    #[test]
    fn merge_preserves_comments_and_trailing_commas() {
        let src = [
            "{",
            "  // 用户注释",
            "  \"$schema\": \"https://opencode.ai/config.json\",",
            "  \"plugin\": [",
            "    \"foo\", // 尾逗号",
            "  ],",
            "}",
        ]
        .join("\n");
        let out = merge_plugin(&src);
        assert!(out.located);
        assert!(out.text.contains("// 用户注释"));
        assert!(out.text.contains("\"foo\", // 尾逗号"));
        assert!(out.text.contains(&format!("\"{SPEC}\"")));
        assert_eq!(
            jsonc_to_json(&out.text),
            serde_json::json!({
                "$schema": "https://opencode.ai/config.json",
                "plugin": ["foo", SPEC],
            })
        );
    }

    #[test]
    fn merge_adds_plugin_key_when_missing() {
        let out = merge_plugin("{\n  \"$schema\": \"https://opencode.ai/config.json\"\n}");
        assert!(out.located);
        assert!(out.text.contains("\"plugin\""));
        assert_eq!(
            jsonc_to_json(&out.text),
            serde_json::json!({
                "$schema": "https://opencode.ai/config.json",
                "plugin": [SPEC],
            })
        );
    }

    #[test]
    fn merge_into_empty_plugin_array() {
        let out = merge_plugin("{\n  \"plugin\": []\n}");
        assert_eq!(
            jsonc_to_json(&out.text),
            serde_json::json!({ "plugin": [SPEC] })
        );
    }

    #[test]
    fn merge_into_array_with_trailing_comma() {
        let out = merge_plugin("{\n  \"plugin\": [\"a\", \"b\",]\n}");
        assert_eq!(
            jsonc_to_json(&out.text),
            serde_json::json!({ "plugin": ["a", "b", SPEC] })
        );
    }

    #[test]
    fn merge_into_empty_object() {
        let out = merge_plugin("{}");
        assert!(out.located);
        assert_eq!(
            jsonc_to_json(&out.text),
            serde_json::json!({ "plugin": [SPEC] })
        );
    }

    #[test]
    fn block_comments_are_skipped() {
        let src = [
            "{",
            "  /* 顶部块注释，",
            "     跨行 */",
            "  \"plugin\": [",
            "    \"foo\" /* 行内块注释 */",
            "  ]",
            "}",
        ]
        .join("\n");
        let out = merge_plugin(&src);
        assert!(out.located);
        assert!(out.text.contains("/* 顶部块注释，"));
        assert!(out.text.contains("/* 行内块注释 */"));
        assert_eq!(
            jsonc_to_json(&out.text),
            serde_json::json!({ "plugin": ["foo", SPEC] })
        );
    }

    #[test]
    fn illegal_chars_do_not_hang() {
        // P2-9：tokenizer 零消费死循环防御——用例能跑完即证明 tokenizer 总在推进
        let cases = [
            "{\n  \"plugin\": [\"a\"],\n  \"x\": @\n}",
            "{\n  'plugin': ['a']\n}",
            "{\n  \"plugin\": [\"a\"], /* \u{1f600} */ \"y\": 1\n}",
        ];
        for src in cases {
            let out = merge_plugin(src);
            assert!(!out.text.is_empty());
        }
        // 非法但 plugin 数组仍可定位时，合并照常完成（幂等安装不受影响）
        let out = merge_plugin("{\n  \"plugin\": [\"a\"],\n  \"x\": @\n}");
        assert!(out.located);
        let sanitized = out.text.replace("\"x\": @", "\"x\": null");
        assert_eq!(
            jsonc_to_json(&sanitized),
            serde_json::json!({ "plugin": ["a", SPEC], "x": null })
        );
        // 幂等仍成立（TC-EV-01）：二次合并原样返回
        let again = merge_plugin(&out.text);
        assert_eq!(again.text, out.text);
    }

    #[test]
    fn merge_unlocatable_input_returns_original() {
        // 无顶层闭合括号 → 定位失败，保守返回原文 + located=false（调用方报
        // doctor error 不落笔，§1.4.5）
        let src = "not a config at all";
        let out = merge_plugin(src);
        assert_eq!(out.text, src);
        assert!(!out.located);
    }

    #[test]
    fn uninstall_removes_only_managed_item() {
        let installed = merge_plugin("{\n  \"plugin\": [\"foo\", \"bar\"]\n}").text;
        let out = uninstall_plugin(&installed);
        assert!(out.located);
        assert!(!out.text.contains(&format!("\"{SPEC}\"")));
        assert!(!out.text.contains(MARKER));
        assert!(out.text.contains("\"foo\""));
        assert!(out.text.contains("\"bar\""));
        assert_eq!(
            jsonc_to_json(&out.text),
            serde_json::json!({ "plugin": ["foo", "bar"] })
        );
    }

    #[test]
    fn uninstall_when_absent_is_idempotent() {
        let src = "{\n  \"plugin\": [\"foo\"]\n}";
        let out = uninstall_plugin(src);
        assert_eq!(out.text, src);
        assert!(out.located);
    }

    #[test]
    fn uninstall_result_is_valid_jsonc_without_plugin_spec() {
        let installed = merge_plugin("{\n  \"plugin\": [\"foo\"]\n}").text;
        let out = uninstall_plugin(&installed);
        assert_eq!(
            jsonc_to_json(&out.text),
            serde_json::json!({ "plugin": ["foo"] })
        );
    }
}
