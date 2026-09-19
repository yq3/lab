# anthropics/courses 教程解剖档案

> 对象：anthropics/courses（本地 ~/develop/opensource/anthropics-courses，HEAD f4dbb13，2025-11-13；全量克隆）
> 视角：为 py-night-school（Java 工程师 × Python Agent 夜校）提炼课程设计与教学方式启发
> 证据纪律：结论可溯源到本地路径；区分【核心】（实际文件所见）与【推断】（分析判断）；查不到的标 ⚠️ 不臆测
> 背景：59 个 commit（2024-05-30 起），纯教学内容仓，无 CI/测试目录（根目录仅 LICENSE/README/.gitignore）【核心】

## 1. 定位与形态

- Anthropic 官方教育课程集，README 第一句即定位："This repository currently contains five courses"，并显式给出建议学习顺序（1→5）【核心，README.md】
- 形态：5 门课 = 5 个平级目录，全部以 **Jupyter notebook 为主体**，配少量 README 与 images/ 截图。无统一工具链（无 requirements.txt 在根目录、无 pyproject、无 CI）【核心】
- 明确的成本教学策略：README 加粗提醒 "these courses often favor our lowest-cost model, Claude 3 Haiku, to keep API costs down for students"——为跟练学生算经济账，这是厂商课程特有的人文关怀【核心】
- 与社区教程差异（【推断】）：每门课围绕自家 SDK/API 参数（system prompt、prefill、tool_use schema、Messages API），不教通用框架，"API 参数即课程"是官方厂商课的典型特征

## 2. 结构总览（关键目录树 + 组织逻辑）

```
anthropics-courses/
├── README.md                      # 五课总索引 + 建议顺序 + 成本提示
├── anthropic_api_fundamentals/    # 课1：API 基础（6 个 ipynb + README + images/ + prompting_images/ 素材）
├── prompt_engineering_interactive_tutorial/  # 课2：交互式提示工程（本仓王牌，见下）
│   ├── Anthropic 1P/              # 直连 API 版：00_How-To + 01~09 章 + 3 个附录 + hints.py
│   └── AmazonBedrock/             # Bedrock 版（anthropic-sdk / boto3 两套 + cloudformation + requirements.txt）
├── real_world_prompting/          # 课3：真实世界提示（5 个 walkthrough ipynb，无练习机制）
├── prompt_evaluations/            # 课4：提示评估（9 课，01~04 单 ipynb，05~09 每课一目录 lesson.ipynb+README+promptfooconfig.yaml+数据）
└── tool_use/                      # 课5：工具使用/Agent 雏形（6 个 ipynb + README + images/）
```

- 组织逻辑【核心】：**根 README = 课程矩阵，课程目录 = 自包含学习单元**；目录内一律 `NN_主题.ipynb` 前缀数字排序，编号即课时顺序
- 课2 的多平台分发：同一套 9 章内容维护 "Anthropic 1P" 与 "AmazonBedrock（anthropic/boto3 两 SDK）" 三份拷贝，Bedrock 版自带 requirements.txt 与 CloudFormation 部署文件【核心】
- 图片资产纪律：每课自带 `images/`（截图/图解），课1 另有 `prompting_images/`（练习用输入素材，如动物图、幻灯片页）——**输入素材与讲解截图分目录**【核心】

## 3. 单课解剖

### 3.1 课2《Prompt Engineering Interactive Tutorial》— 全仓唯一有完整练习+自动验收机制的课【核心】

README.md（57 行）结构：
1. **Course introduction and goals**：一段定位 + "After completing this course, you will be able to:" 4 条能力目标（可检验的行为动词：Master/Recognize/Understand/Build）
2. **Course structure and content**：声明 "9 chapters with accompanying exercises" + 明示按序学习 + 两处特色机制：
   > "**Each lesson has an 'Example Playground' area** at the bottom where you are free to experiment"
   > "There is also an [answer key](…Google Sheets…)"
3. **Table of Contents 按 Beginner / Intermediate / Advanced 三级难度分层**列 9 章 + 附录（Chaining Prompts / Tool Use / Search & Retrieval）
4. 成本说明（Claude 3 Haiku）+ 引流 Claude for Sheets 版本

单章 notebook 骨架（以 `Anthropic 1P/01_Basic_Prompt_Structure.ipynb` 为例，32 个 cell，完整读毕）：

| 节 | cell 布局 | 功能 |
|---|---|---|
| 标题+目录 | md：`# Chapter 1` + Lesson/Exercises/Example Playground 三锚点链接 | 章内导航 |
| Setup | code：`%pip install anthropic` → `%store -r API_KEY` → 定义 `get_completion()` helper | 复用 00 课存入 IPython store 的密钥，单 cell 完成"环境即绪" |
| Lesson | md 讲解 + 成对"示例 code cell"（PROMPT → print(get_completion(PROMPT))）| 每个概念点都配一个**可直接运行的最小示例**，示例即文档 |
| Exercises | md 任务描述（含验收描述）+ code 练习格 + md "❓ If you want a hint" + code `from hints import exercise_1_1_hint` | 三段式：做题→要提示→（文件深处）看答案 |
| Congrats! | md：一段"通关确认"话术 | 完成感设计 |
| Example Playground | md 说明 + 复制本课全部示例 code | 自由实验区，README 承诺的机制 |

- **练习自动验收（1~5、8 章的形态）**：练习 cell 内嵌正则评分器，运行即判分【核心】：
  ```python
  # Function to grade exercise correctness
  def grade_exercise(text):
      pattern = re.compile(r'^(?=.*1)(?=.*2)(?=.*3).*$', re.DOTALL)
      return bool(pattern.match(text))
  print("\n--------------------------- GRADING ---------------------------")
  print("This exercise has been correctly solved:", grade_exercise(response))
  ```
- 编辑面约束：练习格首行注释 `# Prompt - this is the only field you should change`——把可改动区域缩到一个变量【核心】
- **6~9 章退化为"无评分器"**：练习格给出 `PROMPT`/`PREFILL`/`EMAILS`（每封邮件行尾注释标注正确类别），提示与解答都从 `hints.py` import 打印（如 `exercise_6_1_solution` 含完整 USER TURN/ASSISTANT TURN 文本）【核心】。全教程共 20 个 `### Exercise` 头【核心，逐文件统计】
- 评分判据透明化：`hints.py` 每条 hint 第一句都先复述评分标准——"The grading function in this exercise is looking for an answer that contains…"（即题目/提示/答案三方对同一验收口径达成一致）【核心，hints.py L1-46】
- 三种验收形态的能力边界【推断】：正则判分只覆盖"输出可字符匹配"的题（1~5、8 章共 14 题），开放式任务（分类、复杂提示搭建）自动退到人工比对——官方也没解决"主观题自动验收"，其处理方式是诚实降级而非硬造
- 00_Tutorial_How-To.ipynb（11 cell）：独立"开箱课"——装依赖、`API_KEY="your_api_key_here"` 明文填入后 `%store`、讲解 Shift+Enter 与翻页规则；并给无 API key 用户兜底："you can … view our static tutorial answer key instead"【核心】
- 第 9 章（复杂提示）Exercise 9.1 就是 **Financial Services Chatbot**（分析税务信息答题），题材与 py-night-school 金融毕业设计同源【核心】

### 3.2 课5《Tool Use》— 新一代课时结构（无评分器，有 Learning goals + Potential solution）【核心】

`tool_use/README.md`：6 课的表格目录 + 一句前置依赖声明 "each lesson builds on key concepts taught in previous ones"。
以 `06_chatbot_with_multiple_tools.ipynb`（77 cell，完整读毕）为例的章节流：

1. **# 标题 + 场景任务书**：一上来就给项目目标——为虚构电子公司 TechNova 做客服 chatbot，列出 4 个工具签名（get_user / get_order_by_id / get_customer_orders / cancel_order）
2. **## Our fake database**：先写 `FakeDatabase` 类（内存假库），并明说"真实世界应接真库"——**先造可运行的世界，再谈接模型**
3. **## Writing our tools → Giving our tools to Claude → process_tool_call 分发函数 → 完整交互脚本**
4. **## Prompt enhancements → An Opus-specific problem（版本特异性坑位!）→ Final version**：迭代式改 prompt，含"某模型才会犯的错"这种一线经验
5. **## Closing notes**：大段免责——"This script and prompt are NOT ready for production"，点出鉴权缺失、知识注入等真实工程缺口
6. **## Exercise（3 条递进任务）+ Bonus**：扩展 FakeDatabase 加改邮箱/手机功能、合并工具、加输入校验；Bonus 换真数据库。**无参考答案、无自动判分**

课1（API fundamentals）的单课骨架是 `# 标题 → ## Learning goals（2 条 bullet）→ 正文 → ## Exercise → ### Potential solution`——solution 直接给在 notebook 末尾，不设门槛（如 05_Streaming：练习要求"写流式 chatbot"，配 gif 演示预期效果 + 附 Potential solution 完整代码）【核心】

### 3.3 课3《Real World Prompting》— 纯 walkthrough 无练习的"改坏为好"叙事【核心】

`02_medical_prompt.ipynb`（47 cell）章节流：`# Lesson 2: A real-world prompt` → **Our prompting goal**（医生问诊摘要场景）→ **Our initial "bad" prompt**（先展示坏提示词与坏输出）→ **Improving the prompt**（五步迭代：Adding a system prompt → Structuring input data → Provide clear instructions → Adding examples → Output XML structure）→ **Recap of the prompt changes**（回头小结每步改了什么）→ **Testing out the new prompt** → **Switching things up: JSON!**。整课无练习无评分，是"沿一条真实需求线把课 2 技术串起来"的案例课。

### 3.4 课4《Prompt Evaluations》— 渐进引入外部工具【核心】

9 课递进：01 评估概念 → 02 Workbench 人工评 → 03/04 手写 code-graded eval（notebook 内直接写 `grade_completion(output, golden_answer)` 循环，展示"三版 prompt 迭代 + 重跑评估"）→ 05~09 全面转用 promptfoo（每课一个目录：lesson.ipynb + promptfooconfig.yaml + prompts.py + 数据 csv + README + 运行结果截图 images/）。即"手写一遍原理 → 换生产工具"的经典对照结构。

以 `03_code_graded_evals/03_code_graded.ipynb`（49 cell）为例，其叙事骨架是**迭代式而不是罗列式**：Our input data（eval_data 列表内联 golden answer）→ Our initial prompt → run → ### Problem 1: Output formatting issues / ### Problem 1: Incorrect answers（原文两个小节标题撞号，未修）→ Our second attempt → Our third attempt（引入 `extract_answer` 正则抽取再判分）。**把"失败输出"当正文素材直接展示**，而非只展示成功路径【核心】。

## 4. 教学机制拆解

### 4.1 练习与验收机制（有没有练习/quiz/作业？完成如何判定？有无自动验证？）

- 有，且是全仓最精华的设计。三种验收形态并存【核心】：
  1. **内嵌正则评分器**（课2 第 1~5、8 章）：运行练习 cell 即输出 `This exercise has been correctly solved: True/False`。判分标准 = 对输出的正则匹配（如"包含 1、2、3"、"恰好 Michael Jordan"），与 hints.py 里披露的标准完全一致
  2. **素材内标注答案**（课2 第 6~9 章）：EMAILS 列表行尾注释即 golden answer，学员肉眼比对；提示与完整解答（USER/ASSISTANT turn 全文）收在 hints.py，由学员主动 import 打印——**答案在但需多按一次键，防偷看又不高墙**
  3. **Potential solution 附尾**（课1/课5）：练习只给任务描述（+预期效果 gif），参考实现在同 notebook 底部，明说"one simple implementation"
- 判定方式全部是**学习者自己运行、肉眼确认**，无 pytest、无 CI、无进度上报；完成进度的唯一"判定"是 Congrats 页的自评话术【核心】
- 跨内容形态：同一套练习另有 Google Sheets 版 answer key 与 Claude for Sheets 版教程【核心，README 链接】

### 4.2 代码组织（每课独立项目？共享依赖？版本锁定？运行入口？）

- 无任何版本锁定：仓库级无 requirements.txt（仅 Bedrock 版目录有一份），notebook 首 cell 现场 `%pip install anthropic`，SDK 版本漂移风险完全交给时间【核心】
- 课2 用 `%store`（IPython store）跨 notebook 传 API_KEY/MODEL_NAME，一次配置全程复用——轻量但依赖 Jupyter 生态【核心】
- 每章自带 `get_completion()` helper 重复出现（setup cell），不抽公共包——**刻意冗余换取每章可独立打开**【核心+推断】
- 运行入口就是 notebook 本身；课4 后半引入 promptfoo 时，目录内补 package.json/promptfooconfig.yaml，成为仓内唯一的"准工程化"目录【核心】

### 4.3 视觉与辅助材料

- images/ 截图大量用于"操作台教学"（Console 界面、Workbench 按钮、promptfoo 报表页），保证学员所见即教员所讲【核心】
- 图解（calculator_diagram / tool_use_flow / messages_diagram）用于流程概念；gif 用于动态预期效果（streaming_chat_exercise.gif 直接当"验收标准"展示）【核心】
- 无视频、无幻灯片、无中文本地化；emoji 用作轻量 UI（❓ 提示按钮、💡 Tips）【核心】

### 4.4 进阶曲线（前置关系、理论实践配比、篇幅节奏）

- 仓级有明确顺序链（fundamentals → prompt eng → real world → evals → tool use），课3 README 直接写明先修课要求【核心】
- 课2 内部 Beginner/Intermediate/Advanced 三级标签 + "按章序学习"的强约束【核心】
- 理论:实践 ≈ 1:1 到 1:2：每小节 md 讲解后立刻跟可运行示例；练习密度约每章 1~3 题【核心，逐章统计 20 题/9 章】
- 篇幅节奏：课2 单章 10~30KB notebook，第 8 章（幻觉）178KB 最重——难度高峰配最长篇幅【核心】
- 高难主题隔离进附录：Chaining Prompts / Tool Use / Search & Retrieval 三篇不进正文编号，统一放 10.x Appendix——主曲线保持在提示工程本体，进阶去处明确【核心】
- 【推断】课2 前半（可自动判分的题）与后半（开放式题）的切换，本质是"客观题→主观题"的爬坡，与 py-night-school 的六段式"练习+验收"前紧后松思路同构

## 5. 对 py-night-school 的可借鉴点（编号列表，每条给具体落地建议）

1. **正则判分器直接内嵌练习文件**（来自课2）：我们的"练习 = TODO + pytest 自动验收"可加一层降级形态——凡输出是自然语言的题，在练习脚本尾部内嵌 `def grade(text)` + 醒目的 `------ GRADING ------` 打印横幅，学员改完一跑就知道过没过，与 pytest 互补（pytest 管 Python 语义，grade 管输出语义）
2. **"this is the only field you should change" 注释约束编辑面**：所有练习 TODO 上方加同款注释，把可改区域压到最小变量，降低 Java 学员在陌生 Python 代码里迷路的成本
3. **hint 与 solution 分层渐进披露**：仿 hints.py，做 `hints.py`（或 exercise 附 `--hint` CLI）：每条 hint 第一句先复述验收标准，再给方向；solution 放文件末尾/单独命令，需要显式动作才能看到。防止"答案就在题目下面"的纵向泄漏
4. **Learning goals + Congrats + Example Playground 三件套进六段式**：课时开头 2~3 条行为动词目标（已有"目标"段，对齐为 Master/Recognize/Build 式动词）；结尾加一段通关确认文案；每课附"自由实验区"（Example Playground）——正好可放"无框架 mini-agent 对照组"的胡乱折腾位
5. **先造假世界再接模型**（来自课5 FakeDatabase）：金融毕业设计先写内存版 `FakeMarket`/`FakeBroker`（含订单、持仓、行情的假数据类），学员先跑通工具层，再上 LLM 调用——把"工具定义→分发→回填"的 Agent 循环与"API 调用"解耦教学
6. **Closing notes 式的"生产差距声明"**：每课末尾固定一小节，明说"本课代码 NOT ready for production"+ 列 2~3 个真实缺口（鉴权、重试、成本），对 Java 工程师这种职业学习者尤其建立信任
7. **成本前置提示**：在课程 README 就声明"示例统一用最便宜模型/本地 mock，跟练预计花费 X 元"，对应 Anthropic 的 Haiku 策略
8. **题面=素材=答案三方对齐**（EMAILS 行尾注释即 golden answer）：金融练习的行情/票据素材里直接注释期望值，方便学员自检，也方便我们后续把同一批素材升级为 pytest 断言数据源
9. **无评分器题的诚实降级**：开放式大题（如毕业设计）不必硬造自动判分，学课5 给"任务描述 + 递进 3 条 + Bonus"结构即可，验收交给人工 rubric——但要显式声明这是有意为之
10. **"改坏为好"叙事课型**（来自课3）：一门 walkthrough 课固定走"目标 → 坏提示词及其坏输出 → 五步改进 → Recap → 测试"，天然适配六段式里"概念+对照"到"动手"之间的过渡段——Java 学员对 before/after 代码评审有肌肉记忆，此课型等价于提示词 code review

## 6. 局限与反例（不适合我们或做得不到位的地方）

1. **无版本锁定、无 CI、无回归测试**：notebook 输出会随 SDK/模型漂移而失真（课2 仍在用 claude-3-haiku-20240307）。我们做 pytest 验收仓恰恰要反着来：锁版本、CI 跑练习文件本身
2. **依赖 Jupyter + IPython `%store`**：对终端党/Java IDE 党不友好；我们的学员习惯 IDEA，纯 .py + pytest 的形态比 ipynb 更贴其肌肉记忆（ipynb 可只作为阅读版）
3. **同一课程三份平台拷贝**（1P/Bedrock×2）：内容靠复制维护，已经出现章节文件名不一致（`07_Using_Examples _Few-Shot_Prompting.ipynb` 中间混入空格）【核心】。我们要平台变体时应模板化生成而非手工拷贝
4. **评分器只认输出表面特征**：正则判"包含 giggles"这类标准脆弱且可被投机 prompt 骗过；我们的 pytest 验收应尽量断言结构/类型/行为而非字符串包含
5. **纯单机自学、无作业提交/反馈回路**：完成度全靠自觉，没有同伴/批改环节；夜校场景反而有真人节点，应利用而非照抄其"孤儿练习"模式
6. **篇幅失衡与内容陈旧**：第 8 章 178KB 远超其他章；课程锚定 2024 年的 Claude 3 命名体系，2025-11 的 HEAD 也未跟进新模型/新 SDK 特性——厂商课程更新受产品线牵制，社区课更敏捷【核心+推断】
7. **评估课直接教第三方工具**（课4 后半全押 promptfoo）：对"无框架手写"派而言跳过了自研评估的中间态，我们若走"手写 mini-agent + pytest 验收"路线，恰好可以补上这块官方留白
