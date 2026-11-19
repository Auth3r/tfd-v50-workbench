import sqlite3, shutil, os, pathlib

def dump(path, label):
    tmp = pathlib.Path(os.environ["TEMP"]) / ("tfd_dump_" + label + ".sqlite3")
    for s in ("", "-wal", "-shm"):
        p = pathlib.Path(str(tmp) + s)
        if p.exists():
            p.unlink()
    shutil.copy2(path, tmp)
    for s in ("-wal", "-shm"):
        q = pathlib.Path(str(path) + s)
        if q.exists() and q.stat().st_size:
            shutil.copy2(q, str(tmp) + s)
    con = sqlite3.connect(str(tmp))
    cur = con.cursor()
    print("=" * 20, label, path)
    for (t,) in cur.execute("select name from sqlite_master where type='table' order by name"):
        cols = [d[1] for d in cur.execute('pragma table_info("%s")' % t)]
        cnt = cur.execute('select count(*) from "%s"' % t).fetchone()[0]
        print("[%s] n=%d cols=%s" % (t, cnt, cols))
    print("-- characters rows --")
    try:
        cols = [d[1] for d in cur.execute('pragma table_info("characters")')]
        for r in cur.execute('select * from characters limit 6'):
            print("   ", dict(zip(cols, [str(v)[:40] for v in r])))
    except Exception as e:
        print("   ERR", e)
    print("-- accounts/mastery/selection --")
    for q in ("select * from accounts", "select * from account_mastery", "select * from account_character_selection"):
        try:
            print("   ", q, cur.execute(q).fetchall()[:6])
        except Exception as e:
            print("   ", q, "ERR", e)
    con.close()

dump(r"E:\第二后裔\TFD发布端V50\TFD发布端V50\data\launcher\saves\04f2858b03d3e1f379515d84ba575f03\characters.sqlite3", "live")
dump(r"C:\Users\admin\AppData\Local\TFD-Offline\launcher\saves\d7ca2d45e1057455b728c8bf665ce866\characters.sqlite3", "real")
