import sqlite3, shutil, os, pathlib, json

def copy(src):
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
    return tmp

src = pathlib.Path(r"E:\第二后裔\TFD发布端V50\TFD发布端V50\data\launcher\saves\local_runtime.sqlite3")
tmp = copy(src)
con = sqlite3.connect(str(tmp))
cur = con.cursor()
out = []
tables = [r[0] for r in cur.execute("select name from sqlite_master where type='table' order by name")]
out.append("tables: " + ", ".join(tables))
for t in tables:
    n = cur.execute('select count(*) from "%s"' % t).fetchone()[0]
    cols = [d[1] for d in cur.execute('pragma table_info("%s")' % t)]
    out.append("%s n=%d cols=%s" % (t, n, cols))
    if n and t not in ("sqlite_sequence",):
        for r in cur.execute('select * from "%s" limit 5' % t):
            out.append("    " + str([str(v)[:40] for v in r]))
con.close()

outpath = pathlib.Path(os.environ["TEMP"]) / "tfd_lr2.txt"
outpath.write_text("\n".join(out), encoding="utf-8")
print("written", len(out))
