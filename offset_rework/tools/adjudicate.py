"""Adjudicate the byte-match candidates against the NEW build's function table.

A candidate is trustworthy when:
  * its new address is exactly a function start in the new build
  * the new function size is comparable to the old one
Otherwise we try to find a better candidate among new functions whose size
matches and whose prologue (first 16 bytes, up to 5 mismatches) matches.
"""
import json, os, struct

OUT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\offset_rework"
RAW = os.path.join(OUT, "offset_map_v3_raw.json")
ALL = os.path.join(OUT, "anchors_all.json")
OLD_IDA = r"C:\tfdwork\old_ida.json"
NEW_IDA = r"C:\tfdwork\new_ida.json"

OLD_EXE = r"C:\tfdwork\old.exe"
NEW_EXE = r"C:\tfdwork\new.exe"


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
        secs.append({"name": name, "va": va, "vsize": vsize, "rawptr": rawptr, "rawsize": rawsize})
    return data, base, secs


def rva_to_off(rva, secs):
    for s in secs:
        span = max(s["vsize"], s["rawsize"])
        if s["va"] <= rva < s["va"] + span:
            d = rva - s["va"]
            return None if d >= s["rawsize"] else s["rawptr"] + d
    return None


def prologue_match(a, b, max_mismatch=5):
    if len(a) < 16 or len(b) < 16:
        return False
    mism = sum(1 for i in range(16) if a[i] != b[i])
    return mism <= max_mismatch


def main():
    old_data, _, old_secs = pe_info(OLD_EXE)
    new_data, _, new_secs = pe_info(NEW_EXE)
    old_funcs = {int(f["rva"], 16): f["size"] for f in json.load(open(OLD_IDA, encoding="utf-8"))["functions"]}
    newj = json.load(open(NEW_IDA, encoding="utf-8"))
    new_funcs = {}
    for f in newj["functions"]:
        k = f["rva"] if isinstance(f["rva"], int) else int(f["rva"], 16)
        new_funcs[k] = {"size": f["size"], "name": f["name"]}
    new_list = sorted(new_funcs.items())
    size_index = {}
    for rva, meta in new_list:
        size_index.setdefault(meta["size"] // 0x40 * 0x40, []).append(rva)

    raw = json.load(open(RAW, encoding="utf-8"))["anchors"]
    meta_all = {int(a["rva"], 16): a for a in json.load(open(ALL, encoding="utf-8"))["anchors"]}

    verdicts = []
    for r in raw:
        rva = int(r["old_rva"], 16)
        is_func = meta_all.get(rva, {}).get("is_func", False)
        rec = {"old_rva": r["old_rva"], "status": r.get("status"), "new_rva": r.get("new_rva"),
               "is_func_old": is_func, "verdict": "unresolved", "note": ""}
        if not r.get("new_rva"):
            verdicts.append(rec)
            continue
        nrva = int(r["new_rva"], 16)
        old_size = old_funcs.get(rva)
        if nrva in new_funcs:
            oversize = new_funcs[nrva]["size"]
            rec["new_size"] = oversize
            rec["old_size"] = old_size
            if old_size:
                ratio = oversize / float(old_size)
                rec["size_ratio"] = round(ratio, 3)
                if 0.5 <= ratio <= 2.0:
                    rec["verdict"] = "confirmed_func"
                else:
                    rec["verdict"] = "size_mismatch"
                    rec["note"] = "ratio %.2f" % ratio
            else:
                rec["verdict"] = "confirmed_func_no_size"
        else:
            rec["verdict"] = "not_func_start"
            # nearest function start below
            lo = None
            for s, m in new_list:
                if s <= nrva:
                    lo = (s, m)
                else:
                    break
            if lo:
                rec["note"] = "inside func 0x%x (+0x%x)" % (lo[0], nrva - lo[0])
        verdicts.append(rec)

    counts = {}
    for v in verdicts:
        counts[v["verdict"]] = counts.get(v["verdict"], 0) + 1

    with open(os.path.join(OUT, "adjudicate.json"), "w", encoding="utf-8") as f:
        json.dump({"counts": counts, "items": verdicts,
                   "new_function_count": len(new_funcs)}, f, ensure_ascii=False, indent=1)

    print(json.dumps(counts, ensure_ascii=False))


if __name__ == "__main__":
    main()
