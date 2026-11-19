"""Locate the rdata tables in the new build by their internal pointer-diff
fingerprint.

Table entries are absolute pointers to code/data. If two neighbouring entries
both live in regions that shifted by the same amount, their difference stays
identical. We therefore compare *differences* between consecutive entries, which
are shift-invariant, and scan the new .rdata for a matching run.
"""
import json, os, struct

OUT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\offset_rework"
ADJ = os.path.join(OUT, "adjudicate.json")
OLD = r"C:\tfdwork\old.exe"
NEW = r"C:\tfdwork\new.exe"
NEW_IDA = r"C:\tfdwork\new_ida.json"

ENTRIES = 16


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


def main():
    old_data, old_base, old_secs = pe_info(OLD)
    new_data, new_base, new_secs = pe_info(NEW)
    new_rdata = next(s for s in new_secs if s["name"] == ".rdata")
    lo = new_rdata["rawptr"]
    hi = lo + new_rdata["rawsize"] - ENTRIES * 8

    items = json.load(open(ADJ, encoding="utf-8"))["items"]
    targets = []
    for i in items:
        if i["verdict"] != "unresolved":
            continue
        rva = int(i["old_rva"], 16)
        off = rva_to_off(rva, old_secs)
        if off is None:
            continue
        if not any(s["name"] == ".rdata" and s["va"] <= rva < s["va"] + s["rawsize"] for s in old_secs):
            continue
        targets.append(rva)

    rows = []
    for t in sorted(targets):
        off = rva_to_off(t, old_secs)
        qs = [struct.unpack_from("<Q", old_data, off + k * 8)[0] for k in range(ENTRIES)]
        if not all(old_base <= q < old_base + 0x10000000 for q in qs):
            continue
        diffs = [qs[k + 1] - qs[k] for k in range(ENTRIES - 1)]
        best = []
        pos = lo
        # fast pre-filter on the most distinctive diff
        target_diff = diffs[0]
        while pos < hi:
            v0, v1 = struct.unpack_from("<QQ", new_data, pos)
            if v1 - v0 == target_diff:
                ok = 1
                cur = v1
                for k in range(1, ENTRIES - 1):
                    nxt = struct.unpack_from("<Q", new_data, pos + (k + 1) * 8)[0]
                    if nxt - cur != diffs[k]:
                        break
                    cur = nxt
                    ok += 1
                if ok >= 6:
                    base_rva = new_rdata["va"] + (pos - lo)
                    best.append((ok, base_rva))
            pos += 8
        best.sort(key=lambda x: (-x[0], x[1]))
        rows.append({"old_rva": "0x%x" % t, "candidates": [
            {"matches": ok, "new_rva": "0x%x" % r, "delta": "0x%x" % (r - t)} for ok, r in best[:5]]})

    with open(os.path.join(OUT, "table_diff_match.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    solved = sum(1 for r in rows if r["candidates"])
    print(json.dumps({"tables": len(rows), "with_candidates": solved}, ensure_ascii=False))
    for r in rows[:10]:
        print(r["old_rva"], r["candidates"][:2])


if __name__ == "__main__":
    main()
