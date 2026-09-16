"""Step1 sqlite3 五分钟：JDBC 心智逐条对照（零模型零框架，讲义 §2 的现场版）。

五段：连接与建表 / 参数化 ? / Row 工厂 / with conn 事务 / 唯一索引冲突。
数据库文件开在系统临时目录里（克隆即学，绝不写学员主目录）；每段跑完即毁。
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

DEPARTMENTS = [("DEV", 100_00), ("SALES", 80_00)]  # 部门预算（分）——金额整数分纪律


def main() -> None:
    print("== Step1 sqlite3 五分钟：JDBC 心智逐条对照 ==")
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "dept.db"

        print("[1] 连接与建表：connect(path) ≈ DriverManager.getConnection(url)")
        conn = sqlite3.connect(db)  # 文件不存在则创建——零安装零服务，一个文件就是一个库
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS departments (
                dept        TEXT PRIMARY KEY,
                budget_cents INTEGER NOT NULL
            )
            """
        )
        conn.commit()  # DDL 也是写操作：忘了这行，建表在关库时一并消失（§5 坑位预告）
        print("  建表 + 提交完成（CREATE TABLE IF NOT EXISTS——可重复执行的迁移脚本风格）")

        print("[2] 参数化 ?：execute(sql, params) ≈ PreparedStatement.setString(1, ...)")
        conn.executemany("INSERT INTO departments (dept, budget_cents) VALUES (?, ?)", DEPARTMENTS)
        conn.commit()
        evil = "x' OR '1'='1"  # 经典注入载荷：拼进 SQL 就是永真条件
        safe_rows = conn.execute("SELECT dept FROM departments WHERE dept = ?", (evil,)).fetchall()
        unsafe_rows = conn.execute(f"SELECT dept FROM departments WHERE dept = '{evil}'").fetchall()
        print(f"  恶意输入 {evil!r}:")
        print(f"    参数化 ?  查到 {len(safe_rows)} 行（整串被当『值』，查无此部门）")
        print(f"    f-string 拼接查到 {len(unsafe_rows)} 行（整串被当『SQL 的一部分』，全表泄露）")

        print("[3] Row 工厂：row['dept'] ≈ rs.getString(\"dept\")——按名取列，不赌下标")
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT dept, budget_cents FROM departments WHERE dept = ?", ("DEV",)).fetchone()
        print(f"  row['dept']={row['dept']!r}  row['budget_cents']={row['budget_cents']}（建 Row 工厂后行像 dict）")

        print("[4] with conn: 事务——Python 默认**不自动提交**（JDBC 默认 autocommit=true）")
        conn.execute("INSERT INTO departments (dept, budget_cents) VALUES ('HR', 50_00)")
        conn.close()  # 忘了 commit 就关：不报错，行「消失」——§5 坑位的最小复现
        reopened = sqlite3.connect(db)
        missing = reopened.execute("SELECT COUNT(*) FROM departments WHERE dept = 'HR'").fetchone()[0]
        print(f"  插入 HR 后不 commit 直接 close，重开查询: {missing} 行（数据没了，且没报错）")
        with reopened:  # with conn: 块正常退出 → commit；异常退出 → rollback（≈ @Transactional）
            reopened.execute("INSERT INTO departments (dept, budget_cents) VALUES ('HR', 50_00)")
        persisted = reopened.execute("SELECT COUNT(*) FROM departments WHERE dept = 'HR'").fetchone()[0]
        print(f"  with conn: 再插一次，重开仍在: {persisted} 行（写路径统一 with conn: 的纪律来源）")

        print("[5] 唯一索引冲突：IntegrityError——EventStore 把它翻译成 EventSeqConflict")
        try:
            with reopened:
                reopened.execute("INSERT INTO departments (dept, budget_cents) VALUES ('DEV', 1_00)")
        except sqlite3.IntegrityError as exc:
            print(f"  PRIMARY KEY 撞车: sqlite3.IntegrityError: {exc}")
            print("  <- eventstore.append 捕获的就是它：翻译成语义化的 EventSeqConflict（讲义 §3）")
        reopened.close()


if __name__ == "__main__":
    main()
