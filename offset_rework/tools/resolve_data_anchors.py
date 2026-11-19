"""Resolve .rdata / .data anchors by relocating the referencing instruction.

Input : work/old_ida.json  (produced by IDA on the OLD build)
        offset_map_v2.json (confident anchor -> new rva)
Output: data_anchors_ida.json
        for each data anchor: candidate xref sites, the containing function,
        whether that function is itself a mapped anchor, and - if yes - the
        relocated target computed by matching the instruction pattern inside
        the new build body at the same ordinal position.
"""
import json, os, struct

OLD = r"E:\第二后裔\The First Descendant\M1\Binaries\Win64\M1-Win64-Shipping.exe"
NEW = r"F:\Codex\TFD-Zero-P0\build-26722146\runtime-copy\M1\Binaries\Win64\M1-Win64-Shipping.exe"
OUT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\offset_rework"
OLD_IDA = r"C:\tfdwork\old_ida.json"
MAP = os.path.join(OUT, "offset_map_v2.json")

DATA_TARGETS = [0x8fc0930, 0x9803f50, 0x9a60570, 0x9a64528, 0x9a6f3b8,
                0x9a776b8, 0x9a781f0, 0x9a86308, 0xb75c300, 0xb75c314, 0xbcbb2b0]

# opcode prefixes whose last 4 bytes are a rip-relative disp32
RIP_PREFIXES = [
    b"\x48\x8d\x05", b"\x48\x8d\x0d", b"\x48\x8d\x15", b"\x48\x8d\x1d",
    b"\x48\x8d\x25", b"\x48\x8d\x2d", b"\x48\x8d\x35", b"\x48\x8d\x3d",
    b"\x4c\x8d\x05", b"\x4c\x8d\x0d", b"\x4c\x8d\x15", b"\x4c\x8d\x1d",
    b"\x4c\x8d\x25", b"\x4c\x8d\x2d", b"\x4c\x8d\x35", b"\x4c\x8d\x3d",
    b"\x48\x8b\x05", b"\x48\x8b\x0d", b"\x48\x8b\x15", b"\x48\x8b\x1d",
    b"\x48\x8b\x25", b"\x48\x8b\x2d", b"\x48\x8b\x35", b"\x48\x8b\x3d",
    b"\x4c\x8b\x05", b"\x4c\x8b\x0d", b"\x4c\x8b\x15", b"\x4c\x8b\x1d",
    b"\x4c\x8b\x25", b"\x4c\x8b\x2d", b"\x4c\x8b\x35", b"\x4c\x8b\x3d",
    b"\x48\x89\x05", b"\x48\x89\x0d", b"\x48\x89\x15", b"\x48\x89\x1d",
    b"\x48\x89\x25", b"\x48\x89\x2d", b"\x48\x89\x35", b"\x48\x89\x3d",
    b"\x4c\x89\x05", b"\x4c\x89\x0d", b"\x4c\x89\x15", b"\x4c\x89\x1d",
    b"\x4c\x89\x25", b"\x4c\x89\x2d", b"\x4c\x89\x35", b"\x4c\x89\x3d",
    b"\x48\x8d\x05\x00",  # placeholder never matches target logic
]


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


def find_refs(body, body_rva, target_rva):
    """Find rip-relative instructions inside body whose target == target_rva."""
    hits = []
    prefixes = [p for p in RIP_PREFIXES if len(p) == 3]
    for pfx in prefixes:
        p = body.find(pfx)
        while p != -1:
            disp_off = p + 3
            if disp_off + 4 <= len(body):
                disp = struct.unpack_from("<i", body, disp_off)[0]
                insn_rva = body_rva + p
                tgt = insn_rva + 7 + disp
                if tgt == target_rva:
                    hits.append({"ordinal_opcode": pfx.hex(), "offset_in_func": p,
                                 "insn_rva": insn_rva, "disp": disp,
                                 "head16": body[p:p + 16].hex()})
            p = body.find(pfx, p + 1)
    return hits


def main():
    old_data, old_base, old_secs = pe_info(OLD)
    new_data, new_base, new_secs = pe_info(NEW)
    v2 = json.load(open(MAP, encoding="utf-8"))
    mapped = {}
    for r in v2["anchors"]:
        if r.get("status") in ("strong", "good", "weak") and r.get("new_rva"):
            mapped[int(r["old_rva"], 16)] = int(r["new_rva"], 16)
    ida = json.load(open(OLD_IDA, encoding="utf-8"))
    funcs = {int(f["rva"], 16): f["size"] for f in ida["functions"]}

    rows = []
    for t in DATA_TARGETS:
        key = "0x%x" % t
        rec = ida["targets"].get(key, {})
        refs = rec.get("refs", [])
        cand = []
        for ref in refs:
            frva = int(ref["from_rva"], 16) if ref.get("from_rva") else None
            fstart = int(ref["func_rva"], 16) if ref.get("func_rva") else None
            if frva is None or fstart is None:
                cand.append({"from_rva": ref.get("from_rva"), "func_rva": ref.get("func_rva"),
                             "mapped_func": False, "insn": ref.get("insn")})
                continue
            mapped_new = mapped.get(fstart)
            entry = {"from_rva": ref.get("from_rva"), "func_rva": ref.get("func_rva"),
                     "func_size": funcs.get(fstart), "insn": ref.get("insn"),
                     "mapped_func": mapped_new is not None,
                     "func_new_rva": ("0x%x" % mapped_new) if mapped_new else None,
                     "resolved": None}
            if mapped_new is not None and fstart in funcs:
                fsize = funcs[fstart]
                old_off = rva_to_off(fstart, old_secs)
                old_body = old_data[old_off:old_off + fsize] if old_off else b""
                hits = [h for h in find_refs(old_body, fstart, t) if h["insn_rva"] <= frva]
                if hits:
                    h = max(hits, key=lambda x: x["insn_rva"])
                    new_off = rva_to_off(mapped_new, new_secs)
                    new_body = new_data[new_off:new_off + fsize] if new_off else b""
                    same = []
                    p = new_body.find(bytes.fromhex(h["ordinal_opcode"]))
                    while p != -1:
                        same.append(p)
                        p = new_body.find(bytes.fromhex(h["ordinal_opcode"]), p + 1)
                    # pick the occurrence at the same ordinal index as in old body
                    order_old = [hh["offset_in_func"] for hh in
                                 sorted(find_refs(old_body, fstart, t), key=lambda x: x["offset_in_func"])]
                    idx = order_old.index(h["offset_in_func"]) if h["offset_in_func"] in order_old else 0
                    if len(same) > idx:
                        newpos = same[idx]
                        disp = struct.unpack_from("<i", new_body, newpos + 3)[0]
                        insn_new = mapped_new + newpos
                        entry["resolved"] = {
                            "ordinal": idx, "of": len(same),
                            "insn_new_rva": "0x%x" % insn_new,
                            "target_rva": "0x%x" % (insn_new + 7 + disp),
                            "delta": "0x%x" % ((insn_new + 7 + disp) - t),
                        }
            cand.append(entry)
        rows.append({"target": key, "ref_count": len(refs), "candidates": cand,
                     "section": next((s["name"] for s in old_secs
                                      if s["va"] <= t < s["va"] + max(s["vsize"], s["rawsize"])), "?")})

    with open(os.path.join(OUT, "data_anchors_ida.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)

    lines = ["# data anchors via IDA xref relocation", ""]
    for r in rows:
        lines.append("## %s (%s) refs=%d" % (r["target"], r["section"], r["ref_count"]))
        if not r["candidates"]:
            lines.append("- no xref")
        for c in r["candidates"]:
            lines.append("- from %s in func %s mapped=%s -> %s" % (
                c.get("from_rva"), c.get("func_rva"), c.get("mapped_func"),
                (c.get("resolved") or {}).get("target_rva", "unresolved") if c.get("resolved") else "unresolved"))
        lines.append("")
    open(os.path.join(OUT, "data_anchors_ida.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
