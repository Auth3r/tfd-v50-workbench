"""Graft the real offline save (Auth3r, 36 characters) onto this launcher's account.

- reads   C:\\...\\TFD-Offline\\launcher\\saves\\d7ca2d45...\\characters.sqlite3
- renames the account row to the launcher's account name (uid stays 1)
- writes  ...\\data\\launcher\\saves\\04f2858b...\\characters.sqlite3
- keeps a .bak-demo copy of whatever was there
"""
import sqlite3, shutil, os, sys, pathlib

SRC = r"C:\Users\admin\AppData\Local\TFD-Offline\launcher\saves\d7ca2d45e1057455b728c8bf665ce866\characters.sqlite3"
DST = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\data\launcher\saves\04f2858b03d3e1f379515d84ba575f03\characters.sqlite3"
WORK = pathlib.Path(os.environ["TEMP"]) / "tfd_graft.sqlite3"
ACCOUNT_NAME = "demo"

def main():
    if not os.path.exists(SRC):
        print("missing source", SRC); return 1
    shutil.copy2(SRC, WORK)
    for suffix in ("-wal", "-shm"):
        p = pathlib.Path(str(WORK) + suffix)
        if p.exists():
            p.unlink()
    con = sqlite3.connect(str(WORK))
    cur = con.cursor()
    rows = cur.execute("select uid,name from accounts").fetchall()
    print("source accounts:", rows)
    for uid, name in rows:
        if name != ACCOUNT_NAME:
            cur.execute("update accounts set name=? where uid=?", (ACCOUNT_NAME, uid))
            print("renamed uid %s: %r -> %r" % (uid, name, ACCOUNT_NAME))
    con.commit()
    acc = cur.execute("select uid,name from accounts").fetchall()
    n = cur.execute("select count(*) from characters").fetchone()[0]
    sel = cur.execute("select account_uid,character_uid from account_character_selection").fetchall()
    lv = cur.execute("select uid,template_id,level from characters order by level desc limit 3").fetchall()
    print("after rename:", acc, "characters:", n, "selection:", sel, "top:", lv)
    con.execute("pragma wal_checkpoint(TRUNCATE)") if False else None
    con.close()
    for suffix in ("-wal", "-shm"):
        p = pathlib.Path(str(WORK) + suffix)
        if p.exists():
            p.unlink()

    if os.path.exists(DST):
        bak = DST + ".bak-demo"
        if not os.path.exists(bak):
            shutil.copy2(DST, bak)
            print("backup ->", bak)
    shutil.copy2(WORK, DST)
    for suffix in ("-wal", "-shm"):
        p = pathlib.Path(DST + suffix)
        if p.exists():
            p.unlink()
    print("installed ->", DST, os.path.getsize(DST), "bytes")
    return 0

if __name__ == "__main__":
    sys.exit(main())
