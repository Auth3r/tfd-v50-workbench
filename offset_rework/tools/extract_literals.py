"""Census of every hex literal that could be an RVA, not just add(0x...) ones."""
import json, os, re

OUT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\offset_rework"
SRC = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\old_bridge_full.js.bak-c0147688"
MAP = os.path.join(OUT, "offset_map_v3.json")
LO, HI = 0x1000000, 0x10000000
lit = re.compile(r"0x([0-9a-fA-F]{6,8})\b")


def main():
    mapped = {a["old_rva"]: a.get("new_rva") for a in json.load(open(MAP, encoding="utf-8"))["anchors"]}
    rows, seen = [], {}
    for ln, line in enumerate(open(SRC, encoding="ascii").read().splitlines(), 1):
        if line.lstrip().startswith("//"):
            continue
        for m in lit.finditer(line):
            v = int(m.group(1), 16)
            if LO <= v < HI:
                key = "0x%x" % v
                seen.setdefault(key, []).append(ln)
    for k, lines in sorted(seen.items(), key=lambda kv: int(kv[0], 16)):
        rows.append({"old_rva": k, "lines": lines, "new_rva": mapped.get(k)})
    missing = [r for r in rows if not r["new_rva"]]
    print(json.dumps({"distinct": len(rows), "mapped": len(rows) - len(missing),
                      "missing": len(missing), "occurrences": sum(len(r["lines"]) for r in rows)},
                     ensure_ascii=False))
    for r in missing:
        print("  miss %-11s lines %s" % (r["old_rva"], r["lines"][:6]))
    json.dump({"rows": rows}, open(os.path.join(OUT, "literals_all.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
