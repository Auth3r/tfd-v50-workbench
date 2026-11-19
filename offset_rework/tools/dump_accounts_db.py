import sqlite3, shutil, os, pathlib

src = pathlib.Path(r"E:\第二后裔\TFD发布端V50\TFD发布端V50\data\launcher-accounts.sqlite3")
tmp = pathlib.Path(os.environ["TEMP"]) / "tfd_acc.sqlite3"
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
tables = [r[0] for r in cur.execute("select name from sqlite_master where type='table'")]
print("tables:", tables)
for t in tables:
    try:
        cols = [d[1] for d in cur.execute('pragma table_info("%s")' % t)]
        rows = cur.execute('select * from "%s"' % t).fetchall()
        print("\n[%s] cols=%s rows=%d" % (t, cols, len(rows)))
        for r in rows[:10]:
            print("  ", r)
    except Exception as e:
        print(t, "ERR", e)
con.close()
