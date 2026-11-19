import json, os, re

OUT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\offset_rework"
JS = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\old_bridge_full.js"
V3 = os.path.join(OUT, "offset_map_v3.json")

pat = re.compile(r"(image\.add|base\.add)\(0x([0-9a-fA-F]+)\)")


def main():
    text = open(JS, encoding="utf-8", errors="replace").read()
    addrs = {}
    for m in pat.finditer(text):
        line = text.count("\n", 0, m.start()) + 1
        addrs.setdefault(int(m.group(2), 16), []).append(line)

    mapped = {a["old_rva"]: a for a in json.load(open(V3, encoding="utf-8"))["anchors"]
              if a.get("new_rva")}
    rows = []
    for rva in sorted(addrs):
        key = "0x%x" % rva
        m = mapped.get(key)
        rows.append({"old_rva": key, "lines": addrs[rva], "mapped": bool(m),
                     "new_rva": m["new_rva"] if m else None,
                     "method": m.get("method") if m else None})
    ok = sum(1 for r in rows if r["mapped"])
    payload = {"total": len(rows), "mapped": ok, "items": rows}
    with open(os.path.join(OUT, "addrs_real.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print(json.dumps({"total": len(rows), "mapped": ok, "missing": len(rows) - ok}, ensure_ascii=False))
    for r in rows:
        if not r["mapped"]:
            print("  missing", r["old_rva"], "lines", r["lines"][:3])


if __name__ == "__main__":
    main()
