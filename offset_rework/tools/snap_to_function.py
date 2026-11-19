"""For anchors whose best candidate landed inside a function instead of at its
start, snap to the real function start: search the new function table near the
candidate for a function whose size is comparable and whose first 16 bytes
match the old body (allowing a few mismatches for relocated immed/rel32 bytes).
"""
import json, os, struct

OLD = r"C:\tfdwork\old.exe"
OUT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\offset_rework"
ADJ = os.path.join(OUT, "adjudicate.json")
OLD_IDA = r"C:\tfdwork\old_ida.json"
NEW_IDA = r"C:\tfdwork\new_ida.json"


def pe_info(path):
    with open(path, "rb") as f:
        data = f.read()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    optsize = struct.unpack_from("<H", data, pe + 20)[0]
    opt = pe + 24
    sec = opt + optsize
    secs = []
    for i in range(nsec):
        name = data[sec + i * 40: sec + i * 40 + 8].decode("latin1").rstrip("\0")
        vsize, va, rawsize, rawptr = struct.unpack_from("<IIII", data, sec + i * 40 + 8)
        secs.append({"name": name, "va": va, "vsize": vsize, "rawptr": rawptr, "rawsize": rawsize})
    return data, secs


def rva_to_off(rva, secs):
    for s in secs:
        span = max(s["vsize"], s["rawsize"])
        if s["va"] <= rva < s["va"] + span:
            d = rva - s["va"]
            return None if d >= s["rawsize"] else s["rawptr"] + d
    return None


def mismatches(a, b):
    return sum(1 for x, y in zip(a, b) if x != y)


def main():
    data, secs = pe_info(OLD)
    old_funcs = {int(f["rva"], 16): f["size"] for f in json.load(open(OLD_IDA, encoding="utf-8"))["functions"]}
    newj = json.load(open(NEW_IDA, encoding="utf-8"))
    new_funcs = {}
    for f in newj["functions"]:
        k = f["rva"] if isinstance(f["rva"], int) else int(f["rva"], 16)
        new_funcs[k] = f["size"]
    starts = sorted(new_funcs)

    items = [i for i in json.load(open(ADJ, encoding="utf-8"))["items"] if i["verdict"] == "not_func_start"]
    results = []
    for it in items:
        old_rva = int(it["old_rva"], 16)
        cand = int(it["new_rva"], 16)
        osize = old_funcs.get(old_rva, 0)
        ooff = rva_to_off(old_rva, secs)
        pro = data[ooff:ooff + 16] if ooff else b""
        best = None
        for s in starts:
            if s < cand - 0x1000 or s > cand + 0x2000:
                continue
            nsize = new_funcs[s]
            if osize and not (0.4 <= nsize / float(osize) <= 2.2):
                continue
            noff = rva_to_off(s, secs)
            if not noff:
                continue
            np = data[noff:noff + 16]
            if not np:
                continue
            mm = mismatches(pro, np)
            key = (mm, abs(s - cand))
            if best is None or key < best[0]:
                best = (key, s, nsize, mm)
        rec = {"old_rva": it["old_rva"], "candidate": it["new_rva"],
               "old_size": osize if osize else None}
        if best and best[3] <= 6:
            rec["snapped"] = "0x%x" % best[1]
            rec["new_size"] = best[2]
            rec["prologue_mismatch"] = best[3]
            rec["delta"] = "0x%x" % (best[1] - old_rva)
        results.append(rec)

    fixed = sum(1 for r in results if r.get("snapped"))
    with open(os.path.join(OUT, "snap_result.json"), "w", encoding="utf-8") as f:
        json.dump({"total": len(results), "fixed": fixed, "items": results}, f, ensure_ascii=False, indent=1)
    print(json.dumps({"total": len(results), "fixed": fixed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
