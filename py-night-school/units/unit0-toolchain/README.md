# Unit 0 起步：工具链一次到位

> 夜校第一晚。目标只有一个：把 Python 侧的「Maven + JDK + IDEA」等价物配齐并形成肌肉记忆，之后 29 课不再为工具分心。本单元不教语言（那是 Unit 1 的事），只建立**让练习可以被自动验收**的地基。

## 你将装好

| 工具 | 角色 | 对应你熟悉的 |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | 项目 + 依赖 + Python 版本管理 | Maven + SDKMAN 二合一 |
| pytest | 练习即测试的「验收老师」 | JUnit 5 |
| ruff | lint + format | Checkstyle + Spotless 二合一 |
| pyright | 静态类型检查 | IDEA 内置编译检查 |
| VS Code + Pylance 或 PyCharm（二选一） | 编辑 / 调试 / 测试的日常界面 | IDEA 的等价物 |
| Jupyter（可选） | 实验草稿纸 | 超级版 jshell |

## 课时

- [L0.1 环境与工具链：从 Maven 到 uv](./L0.1-uv-toolchain/README.md)（预计 2–3 小时）

## 里程碑（本单元结业判据）

在 `L0.1-uv-toolchain/` 目录下三条命令全绿：

```bash
uv run pytest          # 练习验收全绿
uv run ruff check .    # 无 lint 违规
uv run pyright         # 无类型错误
```

同时种下两颗贯穿全程的种子：

- **业务明线**（一门贯穿 30 课的练习剧情）：`data/expense/budget_mock.json`——你的
  agent 未来要预审的报销单数据，从今晚的 `preapprove()` 一路用到 Unit 5 的带门付款；
  金额一律整数「分」；
- **模型端点约定**：`.env` 三变量（`OPENAI_BASE_URL` / `OPENAI_API_KEY` / `MODEL_NAME`），
  不绑任何厂商——L2 第一次真正调用模型前配好即可。

## 离毕业又近的一块

本课的 `preapprove()` 纯函数就是毕业设计「fail-closed 执行门」（fail-closed＝出错时宁可拒绝、绝不放行——L2.4 主讲）中限额检查的雏形——纯函数、整数分、参数化测试，这三个习惯会一直用到 Unit 5。
