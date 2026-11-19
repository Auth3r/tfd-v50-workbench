"""Relocate anchors through their call sites.

For a target T referenced by a `call rel32` inside a function F (old build):
  * index of that call among all E8 sites of F (old)
  * in the new F (mapped), take the E8 site with the same index
  * its rel32 gives T's new address.
Majority vote across several callers filters ordinal drift.
"""
import json, os, struct

OLD = r"C:\tfdwork\old.exe"
NEW = r"C:\tfdwork\new.exe"
OUT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\offset_rework"
V3 = os.path.join(OUT, "offset_map_v3.json")
OLD_IDA = r"C:\tfdwork\old_ida.json"
AUX = [r"C:\tfdwork\aux_targets.json", r"C:\tfdwork\aux_targets2.json"]
EXTRA = os.path.join(OUT, "map_extra.json")
ADJ = os.path.join(OUT, "adjudicate.json")


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


def call_sites(body, body_rva):
    """[(off, target_rva)] for every E8 call whose target leaves the function range."""
    out = []
    p = body.find(b"\xe8")
    while p != -1:
        if p + 5 <= len(body):
            rel = struct.unpack_from("<i", body, p + 1)[0]
            tgt = body_rva + p + 5 + rel
            if 0 <= tgt < 0x10000000:
                out.append((p, tgt))
        p = body.find(b"\xe8", p + 1)
    return out


def as_int(v):
    if v is None:
        return None
    return v if isinstance(v, int) else int(v, 16)


def main():
    old_data, _, old_secs = pe_info(OLD)
    new_data, _, new_secs = pe_info(NEW)
    old_funcs = {int(f["rva"], 16): f["size"] for f in json.load(open(OLD_IDA, encoding="utf-8"))["functions"]}

    mapped = {}
    for r in json.load(open(V3, encoding="utf-8"))["anchors"]:
        if r.get("new_rva"):
            mapped[int(r["old_rva"], 16)] = int(r["new_rva"], 16)
    if os.path.exists(EXTRA):
        for k, v in json.load(open(EXTRA, encoding="utf-8"))["extra"].items():
            mapped[int(k, 16)] = v["new_rva"]

    refs_all = {}
    for path in AUX:
        if not os.path.exists(path):
            continue
        for k, v in json.load(open(path, encoding="utf-8"))["targets"].items():
            refs_all.setdefault(k, []).extend(v.get("refs", []))

    adj = json.load(open(ADJ, encoding="utf-8"))["items"]
    targets = [i["old_rva"] for i in adj if i["verdict"] in ("unresolved", "not_func_start")]
    targets = [t for t in targets if t not in ("0x30200000", "0x60000030")]

    results = []
    for key in sorted(targets, key=lambda x: int(x, 16)):
        t = int(key, 16)
        votes, info = {}, []
        for ref in refs_all.get(key, []):
            fstart = as_int(ref.get("func_rva"))
            frva = as_int(ref.get("from_rva"))
            if fstart is None or frva is None or fstart not in mapped:
                continue
            fsize = old_funcs.get(fstart, 0)
            ooff = rva_to_off(fstart, old_secs)
            if not ooff or not fsize:
                continue
            ob = old_data[ooff:ooff + fsize]
            sites = call_sites(ob, fstart)
            idxs = [i for i, (off, tgt) in enumerate(sites) if tgt == t]
            if not idxs:
                continue
            rel_off = frva - fstart
            match = [i for i, (off, tgt) in enumerate(sites) if off <= rel_off and tgt == t]
            if not match:
                continue
            idx = match[-1]
            ns = mapped[fstart]
            no = rva_to_off(ns, new_secs)
            if not no:
                continue
            nb = new_data[no:no + fsize]
            nsites = call_sites(nb, ns)
            if idx >= len(nsites):
                continue
            votes[nsites[idx][1]] = votes.get(nsites[idx][1], 0) + 1
            info.append({"from": "0x%x" % frva, "func": "0x%x" % fstart, "idx": idx,
                         "of": len(nsites), "new": "0x%x" % nsites[idx][1]})
        best = max(votes.items(), key=lambda kv: kv[1]) if votes else None
        results.append({"old_rva": key, "new_rva": ("0x%x" % best[0]) if best else None,
                        "votes": best[1] if best else 0, "sites": len(info),
                        "delta": ("0x%x" % (best[0] - t)) if best else None, "detail": info})

    solved = [r for r in results if r["new_rva"] and r["votes"] >= 2]
    with open(os.path.join(OUT, "relocate_calls.json"), "w", encoding="utf-8") as f:
        json.dump({"targets": len(results), "solved": len(solved), "rows": results}, f, ensure_ascii=False, indent=1)
    print(json.dumps({"targets": len(results), "votes2plus": len(solved)}, ensure_ascii=False))
    for r in solved[:20]:
        print("  %s -> %s votes %d" % (r["old_rva"], r["new_rva"], r["votes"]))


if __name__ == "__main__":
    main()
