"""Peek the live save DB (copy) for account rows, mastery and character counts."""
import sqlite3, shutil, os, glob, pathlib, sys

LIVE = pathlib.Path(r"E:\第二后裔\TFD发布端V50\TFD发布端V50\data\launcher\saves\04f2858b03d3e1f379515d84ba575f03\characters.sqlite3")
TMP = pathlib.Path(os.environ["TEMP"]) / "tfd_live_peek.sqlite3"
for suffix in ("-wal", "-shm"):
    p = pathlib.Path(str(TMP) + suffix)
    if p.exists():
        p.unlink()
shutil.copy2(LIVE, TMP)
for suffix in ("-wal", "-shm"):
    src = pathlib.Path(str(LIVE) + suffix)
    if src.exists():
        shutil.copy2(src, str(TMP) + suffix)

con = sqlite3.connect(str(TMP))
cur = con.cursor()
print("accounts:", cur.execute("select uid,name from accounts").fetchall())
print("chars per account:", cur.execute("select account_uid,count(*) from characters group by account_uid").fetchall())
print("mastery:", cur.execute("select * from account_mastery").fetchall())
print("selection:", cur.execute("select * from account_character_selection").fetchall())
print("sessions:", cur.execute("select account_uid,expires_at from local_sessions").fetchall())
con.close()
