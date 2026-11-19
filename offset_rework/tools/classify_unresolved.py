import json, os, struct

OLD = r"E:\第二后裔\The First Descendant\M1\Binaries\Win64\M1-Win64-Shipping.exe"
NEW = r"F:\Codex\TFD-Zero-P0\build-26722146\runtime-copy\M1\Binaries\Win64\M1-Win64-Shipping.exe"
OUT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\offset_rework"
MAP = os.path.join(OUT, "offset_map_v2.json")

UNRESOLVED = ["0x8fc0930", "0x9803f50", "0x9a60570", "0x9a64528", "0x9a6f3b8",
              "0x9a776b8", "0x9a781f0", "0x9a86308", "0xb75c300", "0xb75c314",
              "0x3641950", "0x36db250", "0x3c3f670", "0x4236d90", "0xbcbb2b0"]


def pe_info(path):
    with open(path, "rb") as f:
        data = f.read()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    optsize = struct.unpack_from("<H", data, pe + 20)[0]
    opt = pe + 24
    magic = struct.unpack_from("<H", data, opt)[0]
    image_base = struct.unpack_from("<Q", data, opt + 24)[0] if magic == 0x20b else struct.unpack_from("<I", data, opt + 28)[0]
    sec = opt + optsize
    sections = []
    for i in range(nsec):
        name = data[sec + i * 40: sec + i * 40 + 8].decode("latin1").rstrip("\0")
        vsize, va, rawsize, rawptr = struct.unpack_from("<IIII", data, sec + i * 40 + 8)
        sections.append({"name": name, "va": va, "vsize": vsize, "rawptr": rawptr, "rawsize": rawsize})
    return data, image_base, sections


def rva_to_off(rva, sections):
    for s in sections:
        span = max(s["vsize"], s["rawsize"])
        if s["va"] <= rva < s["va"] + span:
            d = rva - s["va"]
            return None if d >= s["rawsize"] else s["rawptr"] + d
    return None


def sec_of(rva, sections):
    for s in sections:
        span = max(s["vsize"], s["rawsize"])
        if s["va"] <= rva < s["va"] + span:
            return s["name"]
    return "?"


def main():
    old_data, old_base, old_secs = pe_info(OLD)
    new_data, new_base, new_secs = pe_info(NEW)
    rows = []
    for h in UNRESOLVED:
        rva = int(h, 16)
        off = rva_to_off(rva, old_secs)
        row = {"rva": h, "section": sec_of(rva, old_secs), "aligned16": rva % 16 == 0}
        if off is None:
            row["note"] = "no file bytes"
        else:
            head = old_data[off:off + 32]
            row["head"] = head.hex()
            # does a pointer-shaped run exist? first 4 qwords pointing into old image range
            ptrs = []
            for i in range(4):
                q = struct.unpack_from("<Q", old_data, off + i * 8)[0]
                ptrs.append("0x%x" % q if old_base <= q < old_base + 0x20000000 else None)
            row["qwords"] = ptrs
            # 8-byte seed scan in new exe
            seed8 = old_data[off:off + 8]
            hits = []
            p = new_data.find(seed8)
            while p != -1 and len(hits) < 5:
                hits.append("0x%x" % p)
                p = new_data.find(seed8, p + 1)
            row["seed8_hits"] = hits
        rows.append(row)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "unresolved_classify.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    lines = ["# unresolved anchor classification", "", "| rva | section | 16-aligned | head32 | qwords | seed8 hits |", "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append("| %s | %s | %s | %s | %s | %s |" % (
            r["rva"], r["section"], r["aligned16"], r.get("head", r.get("note", "")),
            r.get("qwords", ""), len(r.get("seed8_hits", []))))
    with open(os.path.join(OUT, "unresolved_classify.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
