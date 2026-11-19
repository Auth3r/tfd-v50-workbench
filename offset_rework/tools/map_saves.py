"""Map every launcher save folder to its account + character count (read-only copies)."""
import sqlite3, os, glob, shutil, pathlib

ROOTS = [
    r"E:\第二后裔\TFD发布端V50\TFD发布端V50\data\launcher\saves",
    r"E:\第二后裔\TFD发布端V50\TFD发布端V50\data\launcher",
    r"C:\Users\admin\AppData\Local\TFD-Offline\launcher\saves",
]
seen = set()
for root in ROOTS:
    if not os.path.isdir(root):
        print("MISSING ROOT", root); continue
    for db in glob.glob(os.path.join(root, "**", "characters.sqlite3"), recursive=True):
        if db in seen: continue
        seen.add(db)
        tmp = pathlib.Path(os.environ["TEMP"]) / "tfd_dbinspect" / ("scan_%d.sqlite3" % len(seen))
        try:
            shutil.copy2(db, tmp)
            con = sqlite3.connect("file:%s?mode=ro" % tmp.as_posix(), uri=True)
            acc = con.execute("select uid,name from accounts").fetchall()
            chars = con.execute("select count(*) from characters").fetchone()[0]
            sel = con.execute("select account_uid,character_uid from account_character_selection").fetchall()
            sess = con.execute("select count(*) from local_sessions").fetchone()[0]
            con.close()
            print(os.path.dirname(db))
            print("   accounts=%s chars=%d selection=%s sessions=%d size=%d" %
                  (acc, chars, sel, sess, os.path.getsize(db)))
        except Exception as e:
            print(db, "ERR", e)
