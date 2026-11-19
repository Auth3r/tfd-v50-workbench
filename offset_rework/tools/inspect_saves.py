"""Read-only inspection of the two launcher save databases (copies, never originals)."""
import sqlite3, shutil, os, sys, glob, pathlib

TMP = pathlib.Path(os.environ["TEMP"]) / "tfd_dbinspect"
TMP.mkdir(exist_ok=True)

SRCS = {
    "offline": r"C:\Users\admin\AppData\Local\TFD-Offline\launcher\saves\d7ca2d45e1057455b728c8bf665ce866\characters.sqlite3",
    "current": r"E:\第二后裔\TFD发布端V50\TFD发布端V50\data\launcher\saves\04f2858b03d3e1f379515d84ba575f03\characters.sqlite3",
}

for tag, src in SRCS.items():
    print("=" * 70)
    print(tag, src)
    if not os.path.exists(src):
        print("  MISSING")
        # list the folder to see what is really there
        folder = os.path.dirname(src)
        if os.path.isdir(folder):
            for f in os.listdir(folder):
                p = os.path.join(folder, f)
                print("   ", f, os.path.getsize(p) if os.path.isfile(p) else "<dir>")
        continue
    dst = TMP / (tag + ".sqlite3")
    shutil.copy2(src, dst)
    print("  copied", os.path.getsize(dst), "bytes")
    con = sqlite3.connect("file:%s?mode=ro" % dst.as_posix(), uri=True)
    cur = con.cursor()
    for (name, sql) in cur.execute(
            "select name, sql from sqlite_master where type in ('table','index') order by type desc, name"):
        print("  --", name)
        print("     ", (sql or "").replace("\n", " ")[:400])
    for (name,) in cur.execute("select name from sqlite_master where type='table'"):
        try:
            n = cur.execute('select count(*) from "%s"' % name).fetchone()[0]
            print("   rows in %-24s %s" % (name, n))
        except Exception as e:
            print("   rows in", name, "ERR", e)
    con.close()
