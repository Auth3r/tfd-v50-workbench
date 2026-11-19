import json, os, re, struct

OLD = r"E:\第二后裔\The First Descendant\M1\Binaries\Win64\M1-Win64-Shipping.exe"
JS = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\old_bridge_full.js"
OUT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\offset_rework"
OLD_IDA = r"C:\tfdwork\old_ida.json"

pat = re.compile(r"0x([0-9a-fA-F]{5,16})")


def pe_info(path):
    with open(path, "rb") as f:
        data = f.read()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    optsize = struct.unpack_from("<H", data, pe + 20)[0]
    opt = pe + 24
    magic = struct.unpack_from("<H", data, opt)[0]
    base = struct.unpack_from("<Q", data, opt + 24)[0] if magic == 0x20b else struct.unpack_from("<I", data, opt + 28)[0]
    sec = opt + optsize
    secs = []
    for i in range(nsec):
        name = data[sec + i * 40: sec + i * 40 + 8].decode("latin1").rstrip("\0")
        vsize, va, rawsize, rawptr = struct.unpack_from("<IIII", data, sec + i * 40 + 8)
        secs.append({"name": name, "va": va, "vsize": vsize, "rawsize": rawsize, "rawptr": rawptr})
    return data, base, secs


def main():
    data, image_base, secs = pe_info(OLD)
    ida = json.load(open(OLD_IDA, encoding="utf-8"))
    fn_starts = set(int(f["rva"], 16) for f in ida["functions"])

    hits = {}
    with open(JS, encoding="utf-8", errors="replace") as f:
        for lineno, line in enumerate(f, 1):
            for m in pat.finditer(line):
                v = int(m.group(1), 16)
                if v < 0x10000 or v > 0x100000000:
                    continue
                hits.setdefault(v, []).append(lineno)

    def section_of(rva):
        for s in secs:
            span = max(s["vsize"], s["rawsize"])
            if s["va"] <= rva < s["va"] + span:
                return s["name"]
        return "?"

    rows = []
    for v in sorted(hits):
        rows.append({"rva": "0x%x" % v, "lines": len(hits[v]),
                     "first_line": hits[v][0], "section": section_of(v),
                     "is_func": v in fn_starts, "align16": v % 16 == 0})

    mapped = {}
    v2 = os.path.join(OUT, "offset_map_v2.json")
    if os.path.exists(v2):
        for r in json.load(open(v2, encoding="utf-8"))["anchors"]:
            if r.get("new_rva"):
                mapped[int(r["old_rva"], 16)] = r["status"]

    summary = {"total_distinct": len(rows), "by_section": {}}
    for r in rows:
        summary["by_section"][r["section"]] = summary["by_section"].get(r["section"], 0) + 1
    summary["is_func_start"] = sum(1 for r in rows if r["is_func"])
    summary["in_v2_map"] = sum(1 for r in rows if int(r["rva"], 16) in mapped)

    with open(os.path.join(OUT, "anchors_all.json"), "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "anchors": rows}, f, ensure_ascii=False, indent=1)

    lines = ["# 全部 JS 常量（RVA 候选）", "",
             "去重后 %d 个；按段分布 %s；其中 %d 个是旧库函数起点；%d 个已进 v2 映射" % (
                 len(rows), summary["by_section"], summary["is_func_start"], summary["in_v2_map"]), "",
             "| rva | 段 | 函数起点 | 出现次数 | 首次行号 |", "|---|---|---|---|---|"]
    for r in rows:
        lines.append("| %s | %s | %s | %d | %d |" % (r["rva"], r["section"], "是" if r["is_func"] else "", r["lines"], r["first_line"]))
    open(os.path.join(OUT, "anchors_all.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
