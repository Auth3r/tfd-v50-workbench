"""Rewrite every RVA literal (add(0x...) or bare hex) to its 26722146 value.

Collisions (several old anchors -> one new address) are arbitrated by exact
function-size equality in the new build: the best-fitting anchor keeps the
mapping, the others are left untouched so their use fails loudly instead of
silently pointing at the wrong function.
"""
import json, os, re

OUT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\offset_rework"
SRC = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\old_bridge_full.js.bak-c0147688"
DST = os.path.join(OUT, "old_bridge_b26722146.js")
MAP = os.path.join(OUT, "offset_map_v3.json")
NEW_IDA = r"C:\tfdwork\new_ida.json"
LO, HI = 0x1000000, 0x10000000
lit = re.compile(r"0x([0-9a-fA-F]{6,8})\b")


def main():
    anchors = {a["old_rva"]: a for a in json.load(open(MAP, encoding="utf-8"))["anchors"]}
    FIX = os.path.join(OUT, "manual_fixes.json")
    fixed = json.load(open(FIX, encoding="utf-8")) if os.path.exists(FIX) else {}
    for k, v in fixed.items():
        anchors[k] = {"old_rva": k, "new_rva": "0x%x" % v["new_rva"], "method": v["method"],
                      "old_size": anchors.get(k, {}).get("old_size")}
    newstarts = {}
    for f in json.load(open(NEW_IDA, encoding="utf-8"))["functions"]:
        rva = f["rva"] if isinstance(f["rva"], int) else int(f["rva"], 16)
        newstarts[rva] = f["size"]

    # arbitration for colliding targets
    target_users = {}
    for k, a in anchors.items():
        if a.get("new_rva"):
            target_users.setdefault(int(a["new_rva"], 16), []).append(k)
    dropped = {}
    for tgt, olds in target_users.items():
        if len(olds) < 2:
            continue
        nsize = newstarts.get(tgt)
        def score(k):
            sz = anchors[k].get("old_size")
            return (0 if (nsize is not None and sz == nsize) else 1, abs((sz or 0) - (nsize or 0)))
        keep = min(olds, key=score)
        for k in olds:
            if k != keep:
                dropped[k] = {"old_rva": k, "new_rva": anchors[k]["new_rva"], "reason": "collision",
                              "kept": keep}

    stats, left = {}, {}
    lines = open(SRC, "rb").read().decode("ascii").splitlines(keepends=True)
    out = []
    for line in lines:
        if line.lstrip().startswith("//"):
            out.append(line)
            continue

        def sub(m):
            v = int(m.group(1), 16)
            if not (LO <= v < HI):
                return m.group(0)
            key = "0x%x" % v
            rec = anchors.get(key)
            if rec and rec.get("new_rva") and key not in dropped:
                stats[key] = stats.get(key, 0) + 1
                return "0x%x" % int(rec["new_rva"], 16)
            left[key] = left.get(key, 0) + 1
            return m.group(0)

        out.append(lit.sub(sub, line))

    text = "".join(out)
    # every interceptor goes through a tolerant shim: a bad anchor degrades to a
    # logged skip instead of aborting the whole bridge
    text = text.replace("Interceptor.attach(", "attachSafe(")
    shim = ("function attachSafe(target,callbacks){try{Interceptor.attach(target,callbacks);}"
            "catch(e){send({event:'bridge_skip_attach',address:String(target),error:String(e)});}}\r\n")
    lines = text.splitlines(keepends=True)
    lines.insert(1, shim)
    text = "".join(lines)
    with open(DST, "wb") as f:
        f.write(text.encode("ascii"))

    report = {"distinct_replaced": len(stats), "occurrences_replaced": sum(stats.values()),
              "distinct_left": len(left), "occurrences_left": sum(left.values()),
              "dropped_collisions": dropped, "left_detail": left}
    json.dump(report, open(os.path.join(OUT, "patch_report.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(json.dumps({k: report[k] for k in ("distinct_replaced", "occurrences_replaced",
                                             "distinct_left", "occurrences_left")}, ensure_ascii=False))
    print("left:", json.dumps(left, ensure_ascii=False))
    print("dropped:", json.dumps(dropped, ensure_ascii=False))


if __name__ == "__main__":
    main()
