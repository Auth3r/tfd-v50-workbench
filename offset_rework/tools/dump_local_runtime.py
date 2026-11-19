import sqlite3, shutil, os, pathlib

src = pathlib.Path(r"E:\第二后裔\TFD发布端V50\TFD发布端V50\data\launcher\saves\local_runtime.sqlite3")
tmp = pathlib.Path(os.environ["TEMP"]) / "tfd_lr.sqlite3"
for s in ("", "-wal", "-shm"):
    p = pathlib.Path(str(tmp) + s)
    if p.exists():
        p.unlink()
shutil.copy2(src, tmp)
for s in ("-wal", "-shm"):
    q = pathlib.Path(str(src) + s)
    if q.exists() and q.stat().st_size:
        shutil.copy2(q, str(tmp) + s)
con = sqlite3.connect(str(tmp))
cur = con.cursor()
for (t,) in cur.execute("select name from sqlite_master where type='table' order by name"):
    cols = [d[1] for d in cur.execute('pragma table_info("%s")' % t)]
    cnt = cur.execute('select count(*) from "%s"' % t).fetchone()[0]
    print("[%s] n=%d cols=%s" % (t, cnt, cols))
    if t in ("accounts", "characters", "account_mastery", "account_character_selection", "local_sessions", "account_currencies"):
        cols2 = cols
        for r in cur.execute('select * from "%s" limit 8' % t):
            print("    ", dict(zip(cols2, [str(v)[:40] for v in r])))
con.close()
