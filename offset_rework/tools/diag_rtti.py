import json, os, struct

OUT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\offset_rework"
ALL = os.path.join(OUT, "anchors_all.json")
ADJ = os.path.join(OUT, "adjudicate.json")
OLD = r"C:\tfdwork\old.exe"
BASE = 0x140000000


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


def sec_of(rva, secs):
    for s in secs:
        span = max(s["vsize"], s["rawsize"])
        if s["va"] <= rva < s["va"] + span:
            return s["name"]
    return "?"


def cstr(data, off, limit=200):
    end = data.find(b"\x00", off)
    if end == -1:
        return ""
    raw = data[off:min(end, off + limit)]
    for enc in ("ascii", "utf-16-le"):
        try:
            s = raw.decode(enc)
            if all(32 <= ord(c) < 127 for c in s):
                return s
        except Exception:
            pass
    return raw[:40].hex()


def main():
    data, secs = pe_info(OLD)
    items = json.load(open(ADJ, encoding="utf-8"))["items"]
    targets = [int(i["old_rva"], 16) for i in items if i["verdict"] == "unresolved"
               and sec_of(int(i["old_rva"], 16), secs) == ".rdata"]
    print("rdata targets: %d" % len(targets))
    for t in sorted(targets):
        off = rva_to_off(t, secs)
        col_q = struct.unpack_from("<Q", data, off - 8)[0] if off else 0
        if not (BASE <= col_q < BASE + 0x10000000):
            print("0x%-10x  no rtti ptr (qword@-8 = 0x%x)" % (t, col_q))
            continue
        col = col_q - BASE
        coff = rva_to_off(col, secs)
        if coff is None:
            print("0x%-10x  col 0x%x unmapped" % (t, col))
            continue
        sig, offset_, cd_offset, td_rva, chd_rva = struct.unpack_from("<IIIII", data, coff)
        td_off = rva_to_off(td_rva, secs) if BASE <= td_rva + BASE < BASE + 0x10000000 else None
        name = ""
        if td_off is not None:
            # TypeDescriptor: vftable qword + unused qword + 16-byte name
            name = cstr(data, td_off + 16, 220)
        print("0x%-10x col 0x%-8x sig %d td 0x%-8x name %s" % (t, col, sig, td_rva, name))


if __name__ == "__main__":
    main()
