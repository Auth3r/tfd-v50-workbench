# -*- coding: utf-8 -*-
"""把 36 角色真档里的"非角色"表 graft 进 zero1 空档；characters / selection 保持为空。

用法：
    python graft_nonchar.py [--dry]

不覆盖用户真档：只写 zero1 目录下的库，写前自动备份 .bak-pre-graft。
"""
import os
import shutil
import sqlite3
import sys
import time

ROOT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50"
SRC = os.path.join(ROOT, r"data\launcher\saves\04f2858b03d3e1f379515d84ba575f03\characters.sqlite3")
DST = os.path.join(ROOT, r"data\launcher\saves\e4962e832b9f80bce3c1f8c8d4622756\characters.sqlite3")

# 只搬"账号级状态"，绝不搬角色
COPY = [
    "account_collections",
    "account_currencies",
    "account_item_sequence",
    "account_mastery",
    "account_preferences",
    "account_world_state",
    "option_preset_selection",
    "option_presets",
    "local_feature_state",
]
SKIP_ALWAYS = ["characters", "account_character_selection", "accounts", "sqlite_sequence"]


def cols(con, schema, table):
    return [r[1] for r in con.execute("PRAGMA %s.table_info(%s)" % (schema, table)).fetchall()]


def main():
    dry = "--dry" in sys.argv
    if not os.path.exists(SRC) or not os.path.exists(DST):
        print("MISSING db")
        return 1
    bak = DST + ".bak-pre-graft"
    if not dry and not os.path.exists(bak):
        shutil.copy2(DST, bak)
        print("backup ->", bak)

    con = sqlite3.connect(DST)
    con.execute("ATTACH DATABASE ? AS src", (SRC,))
    src_tables = [r[0] for r in con.execute(
        "select name from src.sqlite_master where type='table'").fetchall()]
    dst_tables = [r[0] for r in con.execute(
        "select name from main.sqlite_master where type='table'").fetchall()]

    for t in COPY:
        if t not in src_tables:
            print("skip (not in src):", t)
            continue
        if t not in dst_tables:
            ddl = con.execute(
                "select sql from src.sqlite_master where type='table' and name=?", (t,)).fetchone()[0]
            print("create in dst:", t)
            if not dry:
                con.execute(ddl)
            dst_tables.append(t)
        sc = cols(con, "src", t)
        dc = cols(con, "main", t)
        if sc != dc:
            print("SCHEMA DIFF", t, sc, dc)
            continue
        n_src = con.execute("select count(*) from src.%s" % t).fetchone()[0]
        if dry:
            print("would copy %-30s %d rows" % (t, n_src))
            continue
        con.execute("delete from main.%s" % t)
        con.execute("insert into main.%s select * from src.%s" % (t, t))
        n = con.execute("select count(*) from main.%s" % t).fetchone()[0]
        print("copied %-30s %d rows" % (t, n))

    if not dry:
        # option_presets / item sequence 的自增计数一并带过来
        seq = con.execute("select name,seq from src.sqlite_sequence").fetchall()
        for name, s in seq:
            if name in SKIP_ALWAYS:
                continue
            try:
                con.execute("delete from main.sqlite_sequence where name=?", (name,))
                con.execute("insert into main.sqlite_sequence(name,seq) values(?,?)", (name, s))
            except Exception as e:
                print("seq skip", name, repr(e))
        con.commit()
        print("chars now:", con.execute("select count(*) from main.characters").fetchone()[0])
        print("selection now:", con.execute("select count(*) from main.account_character_selection").fetchone()[0])
        print("mastery:", con.execute("select * from main.account_mastery").fetchall())
    con.execute("DETACH DATABASE src")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
