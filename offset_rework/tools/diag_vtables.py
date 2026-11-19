import json, os, struct

OUT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\offset_rework"
ALL = os.path.join(OUT, "anchors_all.json")
V3 = os.path.join(OUT, "offset_map_v3_raw.json")
OLD = r"C:\tfdwork\old.exe"

IMAGE_BASE = 0x140000000


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


def main():
    data, secs = pe_info(OLD)
    mapped = set()
    for r in json.load(open(V3, encoding="utf-8"))["anchors"]:
        if r.get("new_rva") and r.get("status") in ("strong", "good", "weak"):
            mapped.add(int(r["old_rva"], 16))

    targets = [int(a["rva"], 16) for a in json.load(open(ALL, encoding="utf-8"))["anchors"]
               if a["section"] in (".rdata", ".data")]
    for t in sorted(targets):
        off = rva_to_off(t, secs)
        if off is None:
            print("0x%x  no bytes" % t)
            continue
        qs = []
        for i in range(12):
            q = struct.unpack_from("<Q", data, off + i * 8)[0]
            rva = q - IMAGE_BASE if IMAGE_BASE <= q < IMAGE_BASE + 0x10000000 else None
            qs.append(("0x%x" % rva if rva else None, rva in mapped if rva else False))
        hits = [i for i, (r, m) in enumerate(qs) if m]
        print("0x%-10x mapped_entries=%d idx=%s  first_q=%s" % (t, len(hits), hits, qs[0][0]))


if __name__ == "__main__":
    main()
