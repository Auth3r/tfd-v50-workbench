"""Resolve data anchors by instruction-ordinal relocation.

For each xref to a data anchor inside an already-mapped function:
  * in the OLD function body, collect all rip-relative sites grouped by their
    3-byte instruction head (e.g. 48 8D 05 = lea rax,[rip+x]); locate the
    referencing site and remember its ordinal among that group.
  * in the NEW function body (same function, relocated), find the same head
    group and take the same ordinal -> read disp32 -> effective address is the
    new location of the anchor.
Votes across several xrefs/functions decide the winner.
"""
import json, os, struct

OLD = r"C:\tfdwork\old.exe"
NEW = r"C:\tfdwork\new.exe"
OUT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\offset_rework"
OLD_IDA = r"C:\tfdwork\old_ida.json"
AUX = r"C:\tfdwork\aux_targets.json"
ALL = os.path.join(OUT, "anchors_all.json")
V3 = os.path.join(OUT, "offset_map_v3_raw.json")

REX = (0x48, 0x4c, 0x49, 0x4d)
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
    # strict
    for s in secs:
        span = max(s["vsize"], s["rawsize"])
        if s["va"] <= rva < s["va"] + span:
            d = rva - s["va"]
            return None if d >= s["rawsize"] else s["rawptr"] + d
    return None


def sites(body, body_rva):
    """[(off, head3, insn_len, target_rva)] for rip-relative operands"""
    out = []
    n = len(body) - 9
    for off in range(0, n):
        b1 = body[off]
        if b1 not in REX:
            continue
        modrm = body[off + 2]
        if modrm not in MODRM_RIP:
            continue
        head3 = body[off:off + 3]
        for ln in (7, 8):
            disp = struct.unpack_from("<i", body, off + ln - 4)[0]
            tgt = body_rva + off + ln + disp
            out.append((off, head3, ln, tgt))
            break
    return out


def as_int(v):
    if v is None:
        return None
    return v if isinstance(v, int) else int(v, 16)


def main():
    old_data, _, old_secs = pe_info(OLD)
    new_data, _, new_secs = pe_info(NEW)
    oldj = json.load(open(OLD_IDA, encoding="utf-8"))
    if os.path.exists(AUX):
        aux = json.load(open(AUX, encoding="utf-8"))
        for k, v in aux["targets"].items():
            oldj["targets"].setdefault(k, v)
    old_funcs = {int(f["rva"], 16): f["size"] for f in oldj["functions"]}

    mapped = {}
    for r in json.load(open(V3, encoding="utf-8"))["anchors"]:
        if r.get("new_rva") and r.get("status") in ("strong", "good", "weak"):
            mapped[int(r["old_rva"], 16)] = int(r["new_rva"], 16)
    extra_path = os.path.join(OUT, "map_extra.json")
    if os.path.exists(extra_path):
        for k, v in json.load(open(extra_path, encoding="utf-8"))["extra"].items():
            mapped[int(k, 16)] = v["new_rva"]

    targets = [int(a["rva"], 16) for a in json.load(open(ALL, encoding="utf-8"))["anchors"]
               if a["section"] in (".rdata", ".data", "?")]

    rows = []
    for t in sorted(targets):
        key = "0x%x" % t
        rec = oldj["targets"].get(key, {})
        votes = {}
        details = []
        for ref in rec.get("refs", []):
            fstart = as_int(ref.get("func_rva"))
            frva = as_int(ref.get("from_rva"))
            if fstart is None or fstart not in mapped or frva is None:
                continue
            fsize = old_funcs.get(fstart, 0)
            ooff = rva_to_off(fstart, old_secs)
            if not ooff or fsize <= 0:
                continue
            old_body = old_data[ooff:ooff + fsize]
            old_sites = sites(old_body, fstart)
            cand = [s for s in old_sites if s[3] == t and s[0] <= frva - fstart]
            if not cand:
                continue
            site = max(cand, key=lambda s: s[0])
            group_old = [s for s in old_sites if s[1] == site[1]]
            idx = group_old.index(site)

            new_start = mapped[fstart]
            nooff = rva_to_off(new_start, new_secs)
            if not nooff:
                continue
            new_body = new_data[nooff:nooff + fsize]
            new_sites = sites(new_body, new_start)
            group_new = [s for s in new_sites if s[1] == site[1]]
            if idx >= len(group_new):
                continue
            ns = group_new[idx]
            disp = struct.unpack_from("<i", new_body, ns[0] + ns[2] - 4)[0]
            new_target = new_start + ns[0] + ns[2] + disp
            votes[new_target] = votes.get(new_target, 0) + 1
            details.append({"from": "0x%x" % frva, "func": "0x%x" % fstart,
                            "ord": idx, "of": len(group_new), "new": "0x%x" % new_target})

        if votes:
            best = sorted(votes.items(), key=lambda kv: -kv[1])[0]
            r_out = {"old_rva": key, "new_rva": "0x%x" % best[0], "votes": best[1],
                     "delta": "0x%x" % (best[0] - t), "sites": len(details), "detail": details}
        else:
            r_out = {"old_rva": key, "new_rva": None, "votes": 0, "sites": len(details), "detail": details}
        rows.append(r_out)

    solved = sum(1 for r in rows if r["new_rva"])
    with open(os.path.join(OUT, "data_anchors_v3.json"), "w", encoding="utf-8") as f:
        json.dump({"targets": len(rows), "solved": solved, "rows": rows}, f, ensure_ascii=False, indent=1)
    lines = ["# data anchors v3", "", "targets %d solved %d" % (len(rows), solved), ""]
    for r in rows:
        lines.append("- %s -> %s votes %d sited %d" % (r["old_rva"], r["new_rva"], r["votes"], r["sites"]))
    open(os.path.join(OUT, "data_anchors_v3.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("targets %d solved %d" % (len(rows), solved))


if __name__ == "__main__":
    main()
