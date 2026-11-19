"""Write a new bridge JS with every known anchor rewritten to the 26722146 address.

Only literal `image.add(0xXXXX)` / `base.add(0xXXXX)` forms are touched; anything
not in the map is left untouched and reported.
"""
import json, os, re

OUT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\offset_rework"
SRC = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\old_bridge_full.js.bak-c0147688"
DST = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\offset_rework\old_bridge_b26722146.js"
MAP = os.path.join(OUT, "offset_map_v3.json")

pat = re.compile(r"(image\.add|base\.add)\(0x([0-9a-fA-F]+)\)")


def main():
    raw = open(SRC, "rb").read()
    text = raw.decode("ascii")
    anchors = {a["old_rva"]: a for a in json.load(open(MAP, encoding="utf-8"))["anchors"]}
    # derive the +0x14 sibling of the shared global struct
    base = anchors.get("0xb75c300")
    if base and base.get("new_rva"):
        sib = anchors.get("0xb75c314")
        if sib is None or not sib.get("new_rva"):
            anchors["0xb75c314"] = {
                "old_rva": "0xb75c314", "new_rva": "0x%x" % (int(base["new_rva"], 16) + 0x14),
                "method": "derived", "delta": base.get("delta")}

    stats, left = {}, {}
    def sub(m):
        kind, hexval = m.group(1), m.group(2)
        old = int(hexval, 16)
        rec = anchors.get("0x%x" % old)
        if rec and rec.get("new_rva"):
            new = int(rec["new_rva"], 16)
            stats["0x%x" % old] = stats.get("0x%x" % old, 0) + 1
            return "%s(0x%x)" % (kind, new)
        left["0x%x" % old] = left.get("0x%x" % old, 0) + 1
        return m.group(0)

    new_text = pat.sub(sub, text)
    with open(DST, "wb") as f:
        f.write(new_text.encode("ascii"))

    report = {
        "src_len": len(text), "dst_len": len(new_text),
        "anchors_replaced": len(stats), "occurrences_replaced": sum(stats.values()),
        "anchors_left": len(left), "occurrences_left": sum(left.values()),
        "left_detail": left,
        "by_method": {},
    }
    for k in stats:
        m = anchors[k].get("method", "?")
        report["by_method"][m] = report["by_method"].get(m, 0) + 1
    with open(os.path.join(OUT, "patch_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in report.items() if k != "left_detail"}, ensure_ascii=False))
    print("left:", json.dumps(left, ensure_ascii=False))


if __name__ == "__main__":
    main()
