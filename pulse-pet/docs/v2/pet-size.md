# PulsePet 宠物大小三档 + 视觉归一化（§十一特性设计）

> 状态：**已实施**（2026-08-28，设计与实施同日；决策记录与实施偏差见 §5）
> 来源：用户需求"允许设置宠物大小（大/中/小三档）" + 实测发现 petdex 导入素材与内置宠物视觉大小悬殊（idle 高度比 1.8×）。
> 决策记录与调研背景存档于 `V2-OPEN-ITEMS.md` §十一；本文是实施版完整设计（含实施中的两处公式修正）。

---

## 1. 背景与起因

所有素材（内置 / codex / petdex）sheet 均为标准 1536×1872（单帧 192×208）、同一缩放路径渲染，视觉大小差异全在**画师对帧面积的占用**（"填帧率"）。2026-08-28 PIL alpha 包围盒实测：

| 素材 | idle 帧内内容（局部坐标） | 填高 | 220 画布 idle 视觉高（改动前） |
|---|---|---|---|
| blinking-kitty（内置） | (56, 48, 88, 108) | 52% | ~114 px |
| wagging-doggy（内置） | (52, 48, 96, 112) | 54% | ~118 px |
| kun-like（petdex） | (36, 5, 119, 198) | 95% | ~210 px |
| line-puppy（petdex） | (18, 5, 155, 198) | 95% | ~210 px |

调研佐证（`docs/v1/desktop-pet-research.md`）：7 个开源同类产品均无"用户可调宠物大小"设置——本特性为差异化功能，无生态行为冲突。

## 2. 决策记录（用户拍板 2026-08-28）

| 项 | 决定 |
|---|---|
| 档位 | **184 / 220 / 280 逻辑像素**（小/中/大）；默认 medium=220（老用户无感）；持久化 `app_state` 新键 `pet.size`（"small"/"medium"/"large"，缺省 medium） |
| 归一化 | **常开无开关**。锚定**内置猫现状**："内置猫现状就是中档、petdex 靠过来"——目标 idle 高 = `canvas × 108/208`，四素材 idle 视觉高度残差 0 |
| 入口 | 仅 panel 设置页「宠物」区三档分段控件（复用 `theme-seg` 样式）；切换即时生效（Rust `set_size` + `pet://size` 广播），无需重启 |
| 插值 | atlas 模式 `ctx.imageSmoothingEnabled = false`（nearest 像素锐化）；占位 PNG 路径零改动 |
| 行为变化 | **内置宠物视觉不变**；仅 petdex/codex 导入素材缩小到与内置一致（中档 idle 210→114）。发布说明需注明 |

## 3. 归一化公式（实施版）

### 3.1 缩放系数

```
s = min( canvas × (108/208) / idleH,  canvas / frameW,  canvas / frameH )
```

- `idleH`：idle 行**逐帧原点并集**的高（Rust `atlas.rs::frame_union_at_origin(row 0)`——帧内局部坐标的并集，非行条带 strip bbox）；缺失/非法/全透明 → 前端回退全帧适配（`computeFrameRect`，原行为）
- 第二三项 = **帧尺寸上限**：内容 ⊆ 帧、帧按 s 缩放后居中恰好放进画布 → 任何素材任何动画帧**永不裁剪**；对极小内容素材（idleH ≪ 108）是安全网，封顶不无限放大

### 3.2 绘制几何

帧居中（与原 `computeFrameRect` 同构，仅 scale 来源不同）：`dx = (canvas − frameW·s)/2`。帧内相对位置保持 → 奔跑帧的帧内位移语义不被破坏、帧间无抖动；帧透明区溢出画布边缘属正常裁剪（nearest 插值下不可见）。

### 3.3 数值验算（idle 视觉高度 px，逻辑）

| 素材 | s（中档） | 小 184 | 中 220 | 大 280 |
|---|---|---|---|---|
| blinking-kitty | 1.0577（= 220/208，锚定项恰等于帧高上限） | 95.5 | **114.2（与改动前一致）** | 145.4 |
| wagging-doggy | 1.0203 | 95.5 | 114.2 | 145.4 |
| kun-like / line-puppy | 0.5769 | 95.5 | 114.2（自 210 靠拢） | 145.4 |

残差：0（四素材均不触上限；doggy 较改动前 −3.6%，无感）。

### 3.4 实施中的两处公式修正（与 §十一原设计的偏差）

1. **防裁剪上限从"全表 content 包围盒"改为"帧尺寸"**：实测发现奔跑行动画让内容遍布整帧宽度——kitty 全表 bbox 达 1520×1772（≈ 整张 sheet），作上限会把宠物压扁到 s≈0.14。帧尺寸上限数学上等价于"每帧内容不裁剪"且不依赖度量数据，更简单更稳。
2. **idle 度量从"行条带 bbox"改为"逐帧原点并集"**：行条带 bbox 含帧间偏移（kitty idle 条带宽 1432 vs 帧内并集 88），作基准毫无区分度。

锚定比率与档位数值不变，残差结论（=0）不变。

## 4. 实现落点

### Rust

| 文件 | 内容 |
|---|---|
| `pet_size.rs`（新，照 `theme.rs` 同构） | `KEY_SIZE="pet.size"` / `SIZE_EVENT="pet://size"` / `logical_of`（184/220/280）；parse-read-write + `pet_get_size`/`pet_set_size` 命令（写库 → 应用窗口 → 广播 `{size, logical}`）+ mock runtime 测试（窗口分支容忍无 pet 窗） |
| `windows.rs` | `apply_pet_size`：`set_size(LogicalSize)` + **内容中心锚定**（`anchored_position`：左上角补偿 ±Δ/2 物理 px，切档原地缩放不"右下生长"）+ 按所在显示器 `clamp_position` 防越屏。启动路径中锚定位被随后的 restore 覆盖属预期（记忆位置优先）；运行中切换时补偿生效并经 Moved 防抖落库 |
| `lib.rs` | setup：窗口创建循环后、`restore_pet_position` **之前**应用档位（非 medium 才应用）——时序铁律 **set_size → restore → show**（`order_nails::pet_size_applied_before_position_restore` 钉子；#9/#20 语义不变） |
| `atlas.rs` | `frame_union_at_origin`（idle 行逐帧原点并集，防御式访问）+ `AtlasMetaDto.idle`（全透明 → null）；resolve 兜底短缓冲**保持不补全**（committer P2-1：补全成全尺寸会让全透明 sheet 通过前端 `makeAtlasPixels` 长度校验 → 宠物窗口全透明不可见，劣于原"校验失败 → 占位猫可见"降级；度量对短缓冲防御式访问 → idle null，无越界） |

### 前端

| 文件 | 内容 |
|---|---|
| `lib/pet-scale.ts`（新） | `IDLE_ANCHOR=108/208`、`computePetScale`（null → 回退）、`frameRectAtScale`；四素材实测 bbox 钉子单测（同档一致 / 上限生效 / 回退） |
| `lib/size-bridge.ts`（新，照 `interaction.ts` 同构） | `PET_SIZES`（与 Rust `logical_of` 锁步，注释互钉）+ payload 解析 + invoke 封装 + `initSizeBridge`（查询 + 订阅 → petStore；pet/panel 双路由） |
| `petStore.ts` | `size: PetSize`（默认 medium）+ `setSize` |
| `PetCanvas.tsx` | canvas 尺寸档位驱动（渲染 effect deps `[size]`，重建即重设 canvas）；`drawAtlas` 归一化分支 + 每帧 `imageSmoothingEnabled=false`（canvas.width 赋值会重置上下文状态）；占位路径效果不变（显式保持平滑插值，atlas 回退时复位 nearest 残留） |
| `Pet.tsx` / `global.css` | `.pet-root/.pet-canvas` 尺寸 → `--pet-size` CSS 变量（兜底 220）；`.pet-bubble` `max-width: 208px` → `calc(100% − 12px)`（随档位，小档 172） |
| `PetMenu.tsx` | clamp 的 windowSize → `PET_SIZES[size]`（ResizeObserver deps 加 winSize） |
| `Settings.tsx` | 「宠物」区三档分段控件（`theme-seg` 结构复刻）；乐观更新 + 失败回滚（照 `onLanguage` 模式） |
| `i18n.ts` | 新键 `settings.size/sizeSmall/sizeMedium/sizeLarge/sizeFail`（zh/en 成对） |

### 联动确认（无需改动）

位置记忆（存左上角 + clamp 兜底）、fireworks（动态读 pet bounds）、MiniCat、拖拽阈值、跨 dpr（LogicalSize + TC-SP-03 链路）、TC-01「不可 resize」语义（`resizable:false` 不变，档位是显式设置非自由缩放）、热键/托盘。

## 5. 附带修复的存量缺陷

| # | 缺陷 | 修复 |
|---|---|---|
| 1 | **en 右键菜单中档 220 下已右裁 ~46px**（"Toggle interaction mode (pass-through: on)" 实测菜单外宽 266px，M8 i18n 漏检；184 档将裁 82px） | ① en 文案缩短为 `"Pass-through: {state}"`（外宽 ~120px）；② 防御 CSS：`.pet-menu` 加 `max-width: calc(100% − 4px)`、菜单项 `overflow:hidden + text-overflow:ellipsis`——未来任何语言/文案/档位最坏只省略文案不裁布局 |
| 2 | atlas.rs resolve 兜底空数据 rgba 缓冲缺 cols 倍（短缓冲，原仅透传无索引故无害） | 度量扫描改防御式访问（短缓冲 → idle null，无越界 panic；`bbox_scan_tolerates_undersized_buffer` 钉子）；缓冲**保持短**不补全——committer P2-1 审查裁定补全会劣化降级路径（全透明 sheet 过校验 → 猫不可见，不如校验失败走占位猫） |

## 6. 验收用例（TC-SZ）

| # | 用例 | 步骤 | 预期 |
|---|---|---|---|
| TC-SZ-01 | 档位切换即时生效 | 设置页「宠物」区点 小/中/大 | 窗口立即变为 184/220/280（原地缩放不右下生长）；分段控件选中态跟随；无需重启 |
| TC-SZ-02 | 持久化与重启恢复 | 切到"大"→ 退出重启 | 恢复大档（plog `pet window size applied: 280px logical`）；面板选中态为"大" |
| TC-SZ-03 | 默认 medium | 无 pet.size 键启动 | 220×220，与历史版本一致（老用户零感知） |
| TC-SZ-04 | 归一化收敛 | 同档位分别选 blinking-kitty / wagging-doggy / kun-like / line-puppy | 四者 idle 视觉高度一致（目视同规格；中档 ≈114px）；petdex 素材明显小于改动前 |
| TC-SZ-05 | 奔跑帧无裁剪 | 触发 working（running 行）观察各档位 | 肢体伸出时不出画布边缘残缺 |
| TC-SZ-06 | nearest 锐化 | 大档对比改动前后 | 像素颗粒锐利不发糊（内置素材放大约 1.35×） |
| TC-SZ-07 | 非法值拒绝 | db 手写 `pet.size=giant` 启动 | 回退 medium 不崩；`pet_set_size("giant")` 返回 Err 且不破坏已存值 |
| TC-SZ-08 | 贴边切档 clamp | 宠物拖至屏幕右下角 → 切"大" | 窗口不越出屏幕可视区 |
| TC-SZ-09 | 小档浮层完整 | 小档右键宠物 + 触发提醒气泡 | zh/en 菜单完整显示（en 修复后）；气泡随 172px 上限折行、snooze 按钮可用 |
| TC-SZ-10 | 时序钉子 | `cargo test order_nails` | set_size → restore → show 断言通过 |
| TC-SZ-11 | 热切换锚定 | 运行中切档（非启动） | 窗口中心不动（左上角补偿 ±Δ/2）；新位置经 Moved 防抖落库 |

自动化覆盖：Rust 单测（parse/read/write、mock 命令往返 + 广播、anchored_position、frame_union、DTO、防御钉子、order_nail）+ 前端 vitest（pet-scale 四素材钉子、size-bridge 解析、atlas idle 解析、i18n 完备性、气泡 CSS 钉子）。测试基线：`cargo test` 346 passed + 3 ignored / `npm test` 433 / `tsc --noEmit` 0 错 / `npm run build` 通过（2026-08-28，tester 复核 B1~B4 db 启动档位场景 + 静态核验全 PASS）。

## 7. 已知边界与观察项

- **档位变更后首次启动**：恢复的记忆位置是旧档位下的左上角（启动链 restore 覆盖锚定补偿）→ 视觉上右下生长一次，此后位置记忆即新档位口径。不修（记忆位置优先语义正确）。
- **极小内容素材**（idleH ≪ 108，生态内暂无）：帧上限封顶 → idle 视觉高度低于档位目标（安全网语义），不放大出帧。
- **v2 11 行 sheet**（1536×2288）：idle 仍 row 0，公式不变。
- **占位 PNG 路径**（无 atlas 兜底）不归一化（非像素放大场景，保持平滑插值与全帧适配）。
