"""Resolve leftovers with a regional-delta prior.

For an unmapped old anchor A: take already-mapped anchors whose address lies
within +/-0x4000 of A, assume their deltas apply locally, predict the new
address, then look for a function start near the prediction whose size equals
A's old size. Exactly one -> accept.
"""
import json, os, statistics

OUT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\offset_rework"
MAP = os.path.join(OUT, "offset_map_v3.json")
OLD_IDA = r"C:\tfdwork\old_ida.json"
NEW_IDA = r"C:\tfdwork\new_ida.json"
FIX = os.path.join(OUT, "manual_fixes.json")
WIN, SPAN = 0x800, 0x4000


def main():
    oldf = {int(f["rva"], 16): f["size"] for f in json.load(open(OLD_IDA, encoding="utf-8"))["functions"]}
    newf = {}
    for f in json.load(open(NEW_IDA, encoding="utf-8"))["functions"]:
        rva = f["rva"] if isinstance(f["rva"], int) else int(f["rva"], 16)
        newf[rva] = f["size"]
    nstarts = sorted(newf)

    anchors = json.load(open(MAP, encoding="utf-8"))["anchors"]
    mapped = [(int(a["old_rva"], 16), int(a["new_rva"], 16)) for a in anchors if a.get("new_rva")]
    fixes = json.load(open(FIX, encoding="utf-8")) if os.path.exists(FIX) else {}
    todo = [int(a["old_rva"], 16) for a in anchors
            if not a.get("new_rva") and a.get("section") == ".text" and not ("0x%x" % int(a["old_rva"], 16)) in fixes]

    import bisect
    out = dict(fixes)
    for o in sorted(todo):
        size = oldf.get(o)
        near = [(n, n - m) for m, n in mapped if abs(m - o) <= SPAN]
        if not near or size is None:
            continue
        delta = int(statistics.median(d for _, d in near))
        pred = o + delta
        a = bisect.bisect_left(nstarts, pred - WIN)
        b = bisect.bisect_right(nstarts, pred + WIN)
        exact = [n for n in nstarts[a:b] if newf[n] == size]
        loose = [n for n in nstarts[a:b] if abs(newf[n] - size) <= 8]
        if len(exact) == 1:
            out["0x%x" % o] = {"new_rva": exact[0], "method": "delta_size", "delta": delta,
                               "score": 0, "samples": len(near)}
        elif len(loose) == 1:
            out["0x%x" % o] = {"new_rva": loose[0], "method": "delta_size_loose", "delta": delta,
                               "score": abs(newf[loose[0]] - size), "samples": len(near)}

    json.dump(out, open(FIX, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for k, v in out.items():
        print("%-11s -> 0x%-9x %-16s delta 0x%x" % (k, v["new_rva"], v["method"], v.get("delta", 0)))


if __name__ == "__main__":
    main()
