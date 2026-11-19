"""Resolve interior anchors: an anchor that sits mid-function in the old build.

The containing function is already mapped, so search its new body for the
instruction bytes that start at the anchor. A 12-byte exact hit that occurs once
is decisive.
"""
import bisect, json, os, struct

OUT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\offset_rework"
MAP = os.path.join(OUT, "offset_map_v3.json")
FIX = os.path.join(OUT, "manual_fixes.json")
OLD = r"C:\tfdwork\old.exe"
NEW = r"C:\tfdwork\new.exe"
OLD_IDA = r"C:\tfdwork\old_ida.json"
NEW_IDA = r"C:\tfdwork\new_ida.json"
SIG = 12


def pe_info(path):
    with open(path, "rb") as f:
        data = f.read()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    optsize = struct.unpack_from("<H", data, pe + 20)[0]
    sec = pe + 24 + optsize
    secs = []
    for i in range(nsec):
        vsize, va, rawsize, rawptr = struct.unpack_from("<IIII", data, sec + i * 40 + 8)
        secs.append({"va": va, "vsize": vsize, "rawsize": rawsize, "rawptr": rawptr})
    return data, secs


def rva_to_off(rva, secs):
    for s in secs:
        if s["va"] <= rva < s["va"] + max(s["vsize"], s["rawsize"]):
            d = rva - s["va"]
            return s["rawptr"] + d if d < s["rawsize"] else None
    return None


def main():
    old_data, old_secs = pe_info(OLD)
    new_data, new_secs = pe_info(NEW)
    oldf = {int(f["rva"], 16): f["size"] for f in json.load(open(OLD_IDA, encoding="utf-8"))["functions"]}
    old_start_keys = sorted(oldf)

    anchors = json.load(open(MAP, encoding="utf-8"))["anchors"]
    mapped = {}
    for a in anchors:
        if a.get("new_rva"):
            mapped[int(a["old_rva"], 16)] = int(a["new_rva"], 16)
    fixes = json.load(open(FIX, encoding="utf-8")) if os.path.exists(FIX) else {}
    for k, v in fixes.items():
        mapped[int(k, 16)] = v["new_rva"]

    todo = [int(a["old_rva"], 16) for a in anchors
            if not a.get("new_rva") and a.get("section") == ".text"
            and int(a["old_rva"], 16) not in oldf]

    for o in sorted(todo):
        i = bisect.bisect_right(old_start_keys, o) - 1
        if i < 0:
            continue
        fs = old_start_keys[i]
        if fs == o or fs not in mapped:
            print("%-11s in 0x%-9x unmapped container" % ("0x%x" % o, fs))
            continue
        osz = oldf[fs]
        oo = rva_to_off(o, old_secs)
        sig = old_data[oo:oo + 32]
        ns = mapped[fs]
        no = rva_to_off(ns, new_secs)
        body = new_data[no:no + max(osz * 3, 0x4000)]
        best, second, bestpos = -1, -1, None
        for p in range(0, len(body) - 32, 1):
            seg = body[p:p + 32]
            score = 0
            for a, b in zip(sig, seg):
                if a == b:
                    score += 1
                else:
                    break
            if score > best:
                second = best
                best, bestpos = score, p
            elif score > second:
                second = score
        verdict = "ok" if best >= 20 and second <= 16 else "ambig"
        print("%-11s in 0x%-9x -> 0x%-9x  best %d second %d at 0x%x %s"
              % ("0x%x" % o, fs, ns, best, second, (ns + bestpos) if bestpos is not None else 0, verdict))
        if verdict == "ok":
            fixes["0x%x" % o] = {"new_rva": ns + bestpos, "method": "interior_prefix", "container": "0x%x" % fs}
    json.dump(fixes, open(FIX, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
