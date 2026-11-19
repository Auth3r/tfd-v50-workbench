"""Resolve still-unmapped code anchors by bracketing them between already-mapped
neighbours: new order follows old order, so only function starts inside that
window can be the answer; exact size equality then usually leaves one candidate.
"""
import json, os

OUT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\offset_rework"
MAP = os.path.join(OUT, "offset_map_v3.json")
OLD_IDA = r"C:\tfdwork\old_ida.json"
NEW_IDA = r"C:\tfdwork\new_ida.json"


def main():
    oldf = {int(f["rva"], 16): f["size"] for f in json.load(open(OLD_IDA, encoding="utf-8"))["functions"]}
    newf = {}
    for f in json.load(open(NEW_IDA, encoding="utf-8"))["functions"]:
        rva = f["rva"] if isinstance(f["rva"], int) else int(f["rva"], 16)
        newf[rva] = f["size"]

    anchors = json.load(open(MAP, encoding="utf-8"))["anchors"]
    mapped = sorted((int(a["old_rva"], 16), int(a["new_rva"], 16))
                    for a in anchors if a.get("new_rva") and a.get("is_func_old"))
    okeys = [o for o, _ in mapped]
    todo = [int(a["old_rva"], 16) for a in anchors
            if not a.get("new_rva") and a.get("is_func_old") and int(a["old_rva"], 16) in oldf]
    nstarts = sorted(newf)

    import bisect
    solved = {}
    for o in sorted(todo):
        size = oldf[o]
        i = bisect.bisect_left(okeys, o)
        lo = mapped[i - 1][1] if i > 0 else None
        hi = mapped[i][1] if i < len(mapped) else None
        a = bisect.bisect_left(nstarts, lo) if lo else 0
        b = bisect.bisect_right(nstarts, hi) if hi else len(nstarts)
        cands = [n for n in nstarts[a:b] if abs(newf[n] - size) <= 2]
        if len(cands) == 1:
            solved["0x%x" % o] = {"new_rva": cands[0], "size": size, "method": "bracket_size",
                                  "window": ["0x%x" % lo if lo else None, "0x%x" % hi if hi else None]}
        elif cands:
            solved["0x%x" % o] = {"new_rva": None, "size": size, "method": "bracket_ambiguous",
                                  "cands": ["0x%x" % c for c in cands[:6]],
                                  "window": ["0x%x" % lo if lo else None, "0x%x" % hi if hi else None]}

    json.dump(solved, open(os.path.join(OUT, "bracket_result.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    for k, v in solved.items():
        print("%-11s -> %-11s %s" % (k, ("0x%x" % v["new_rva"]) if v["new_rva"] else "-", v["method"]))


if __name__ == "__main__":
    main()
