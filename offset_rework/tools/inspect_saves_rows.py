"""Dump key rows from the two save databases (copies only)."""
import sqlite3, os, pathlib

TMP = pathlib.Path(os.environ["TEMP"]) / "tfd_dbinspect"
for tag in ("offline", "current"):
    p = TMP / (tag + ".sqlite3")
    print("=" * 60, tag)
    con = sqlite3.connect("file:%s?mode=ro" % p.as_posix(), uri=True)
    cur = con.cursor()
    def dump(sql, limit=8):
        try:
            rows = cur.execute(sql).fetchall()
            for r in rows[:limit]:
                print("   ", str(r)[:300])
            if not rows:
                print("    <empty>")
        except Exception as e:
            print("    ERR", sql.split("(")[0][:40], e)
    print(" accounts:");            dump("select uid,name,created_at from accounts")
    print(" characters:");          dump("select uid,account_uid,template_id,level,exp from characters")
    print(" selection:");           dump("select * from account_character_selection")
    print(" mastery:");             dump("select * from account_mastery")
    print(" currencies(top):");     dump("select currency_type,amount from account_currencies order by amount desc", 5)
    print(" collections count:");   dump("select count(*) from account_collections")
    print(" world_state len:");     dump("select account_uid,length(value_json),revision from account_world_state")
    con.close()
