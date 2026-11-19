"""Resolve data-section anchors (rdata tables / vtables / globals) by relocating
the referencing instruction inside an already-mapped function.

For every xref to a data anchor, if the containing function is mapped to the
new build, we locate the same rip-relative instruction in the new function
body (same ordinal position among all rip-relative instructions that point at
the target in the old body) and read its displacement there.
"""
import json, os, struct

OLD = r"C:\tfdwork\old.exe"
NEW = r"C:\tfdwork\new.exe"
OUT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\offset_rework"
OLD_IDA = r"C:\tfdwork\old_ida.json"
ALL = os.path.join(OUT, "anchors_all.json")
V3 = os.path.join(OUT, "offset_map_v3_raw.json")

RIP_PREFIXES = [b"\x48\x8d", b"\x4c\x8d", b"\x48\x8b", b"\x4c\x8b", b"\x48\x89", b"\x4c\x89",
                b"\x48\x3b", b"\x4c\x3b", b"\x48\x39", b"\x4c\x39", b"\xf3\x0f", b"\x66\x0f"]
MODRM_RIP = (0x05, 0x0d, 0x15, 0x1d, 0x25, 0x2d, 0x35, 0x3d)


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


def refs_to(body, body_rva, target_rva):
    """all rip-relative operand sites inside body whose effective address == target"""
    hits = []
    for off in range(0, len(body) - 9):
        pfx = body[off:off + 2]
        if pfx not in RIP_PREFIXES:
            continue
        modrm = body[off + 2]
        if modrm not in MODRM_RIP:
            continue
        for insn_len in (6, 7, 8):
            disp = struct.unpack_from("<i", body, off + insn_len - 4)[0]
            tgt = body_rva + off + insn_len + disp
            if tgt == target_rva:
                hits.append({"off": off, "len": insn_len, "head": body[off:off + insn_len].hex()})
                break
    return hits


def as_int(v):
    if v is None:
        return None
    if isinstance(v, int):
        return v
    return int(v, 16)


def main():
    old_data, _, old_secs = pe_info(OLD)
    new_data, _, new_secs = pe_info(NEW)
    oldj = json.load(open(OLD_IDA, encoding="utf-8"))
    aux_path = r"C:\tfdwork\aux_targets.json"
    if os.path.exists(aux_path):
        aux = json.load(open(aux_path, encoding="utf-8"))
        for k, v in aux["targets"].items():
            oldj["targets"].setdefault(k, v)
    old_funcs = {int(f["rva"], 16): f["size"] for f in oldj["functions"]}
    mapped = {}
    for r in json.load(open(V3, encoding="utf-8"))["anchors"]:
        if r.get("new_rva") and r.get("status") in ("strong", "good", "weak"):
            mapped[int(r["old_rva"], 16)] = int(r["new_rva"], 16)

    targets = [int(a["rva"], 16) for a in json.load(open(ALL, encoding="utf-8"))["anchors"]
               if a["section"] in (".rdata", ".data", "?")]
    targets.sort()

    rows = []
    for t in targets:
        key = "0x%x" % t
        rec = oldj["targets"].get(key, {})
        votes = {}
        detail = []
        for ref in rec.get("refs", []):
            fstart = as_int(ref.get("func_rva"))
            frva = as_int(ref.get("from_rva"))
            if fstart is None or fstart not in mapped:
                continue
            fsize = old_funcs.get(fstart, 0)
            ooff = rva_to_off(fstart, old_secs)
            if not ooff or fsize <= 0:
                continue
            old_body = old_data[ooff:ooff + fsize]
            hits = [h for h in refs_to(old_body, fstart, t) if h["off"] <= frva - fstart]
            if not hits:
                continue
            hits.sort(key=lambda h: h["off"])
            idx = len(hits) - 1  # nearest preceding site
            new_start = mapped[fstart]
            noff = rva_to_off(new_start, new_secs)
            if not noff:
                continue
            new_body = new_data[noff:noff + fsize]
            found = refs_to(new_body, new_start, t)
            # take the same ordinal among all sites pointing at the *same* target
            seen = sorted(set(h["off"] for h in found))
            if len(seen) < len(hits) or idx >= len(seen):
                continue
            pos = seen[idx]
            disp = struct.unpack_from("<i", new_body, pos + 3)[0]
            new_target = new_start + pos + 7 + disp
            votes[new_target] = votes.get(new_target, 0) + 1
            detail.append({"from": ref.get("from_rva"), "func": ref.get("func_rva"),
                           "new_target": "0x%x" % new_target, "ord": idx})
        if votes:
            best = sorted(votes.items(), key=lambda kv: -kv[1])[0]
            rec_out = {"old_rva": key, "new_rva": "0x%x" % best[0], "votes": best[1],
                       "sites": len(detail), "delta": "0x%x" % (best[0] - t), "detail": detail}
        else:
            rec_out = {"old_rva": key, "new_rva": None, "votes": 0, "sites": len(detail), "detail": detail}
        rows.append(rec_out)

    solved = sum(1 for r in rows if r["new_rva"])
    with open(os.path.join(OUT, "data_anchors_v3.json"), "w", encoding="utf-8") as f:
        json.dump({"targets": len(rows), "solved": solved, "rows": rows}, f, ensure_ascii=False, indent=1)

    lines = ["# data anchors via mapped-caller relocation", "",
             "targets %d, solved %d" % (len(rows), solved), ""]
    for r in rows:
        lines.append("- %s -> %s votes %d delta %s" % (r["old_rva"], r["new_rva"], r["votes"], r.get("delta")))
    open(os.path.join(OUT, "data_anchors_v3.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("targets %d solved %d" % (len(rows), solved))


if __name__ == "__main__":
    main()
