"""Bootstrap: map the functions that reference the unresolved data tables.

These referencing functions are not part of the 300 JS anchors, so they were
never attempted. We match them with the same multi-seed vote, verify delta
plausibility, and store the result so the ordinal relocation can run again.
"""
import json, os, struct

OLD = r"C:\tfdwork\old.exe"
NEW = r"C:\tfdwork\new.exe"
OUT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\offset_rework"
ALL = os.path.join(OUT, "anchors_all.json")
V3 = os.path.join(OUT, "offset_map_v3_raw.json")
DATA = os.path.join(OUT, "data_anchors_v3.json")
AUX = r"C:\tfdwork\aux_targets.json"
OLD_IDA = r"C:\tfdwork\old_ida.json"

BODY = 512
SEED_LEN = 12
SEED_OFFSETS = tuple(range(0, BODY - SEED_LEN + 1, 24))
DELTA_MIN = -0x40000
DELTA_MAX = 0x200000


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


def off_to_rva(off, secs):
    for s in secs:
        if s["rawptr"] <= off < s["rawptr"] + s["rawsize"]:
            return s["va"] + (off - s["rawptr"])
    return None


def score(new_data, off, body):
    best = 0.0
    for shift in (0, -4, 4, -8, 8, -12, 12):
        o = off + shift
        if o < 0 or o + len(body) > len(new_data):
            continue
        mism = 0
        for i, b in enumerate(body):
            if b != new_data[o + i]:
                mism += 1
        s = 1.0 - mism / float(len(body))
        if s > best:
            best = s
    return best


def as_int(v):
    if v is None:
        return None
    return v if isinstance(v, int) else int(v, 16)


def main():
    old_data, _, old_secs = pe_info(OLD)
    new_data, _, new_secs = pe_info(NEW)
    aux = json.load(open(AUX, encoding="utf-8"))["targets"]
    mapped = {}
    v3p = os.path.join(OUT, "offset_map_v3.json")
    for r in json.load(open(v3p, encoding="utf-8"))["anchors"]:
        if r.get("new_rva"):
            mapped[int(r["old_rva"], 16)] = int(r["new_rva"], 16)
    if not mapped:
        for r in json.load(open(V3, encoding="utf-8"))["anchors"]:
            if r.get("new_rva") and r.get("status") in ("strong", "good", "weak"):
                mapped[int(r["old_rva"], 16)] = int(r["new_rva"], 16)

    unresolved = [r["old_rva"] for r in json.load(open(DATA, encoding="utf-8"))["rows"] if not r["new_rva"]]
    need = set()
    for key in unresolved:
        refs = aux.get(key, {}).get("refs", [])
        if len(refs) > 30:
            continue  # global data referenced everywhere; bootstrap would explode
        for ref in refs:
            fs = as_int(ref.get("func_rva"))
            if fs is not None and fs not in mapped:
                need.add(fs)
    need = set(sorted(need)[:80])
    print("referencing functions to map: %d" % len(need))

    extra = {}
    for f in sorted(need):
        off = rva_to_off(f, old_secs)
        if off is None or off + BODY > len(old_data):
            continue
        body = old_data[off:off + BODY]
        votes = {}
        for so in SEED_OFFSETS:
            seed = body[so:so + SEED_LEN]
            if len(set(seed)) == 1:
                continue
            p = new_data.find(seed)
            hits = 0
            while p != -1 and hits < 32:
                cand = p - so
                if 0 <= cand < len(new_data) - BODY:
                    cr = off_to_rva(cand, new_secs)
                    if cr is not None and DELTA_MIN <= cr - f <= DELTA_MAX:
                        votes[cand] = votes.get(cand, 0) + 1
                p = new_data.find(seed, p + 1)
                hits += 1
        if not votes:
            continue
        best_off, vn = sorted(votes.items(), key=lambda kv: (-kv[1], kv[0]))[0]
        sc = score(new_data, best_off, body)
        if sc >= 0.90 and vn >= 2:
            extra[f] = {"new_rva": off_to_rva(best_off, new_secs), "score": round(sc, 4), "votes": vn}
            print("  mapped 0x%x -> 0x%x score %.3f votes %d" % (f, extra[f]["new_rva"], sc, vn))

    with open(os.path.join(OUT, "map_extra.json"), "w", encoding="utf-8") as fh:
        json.dump({"extra": {"0x%x" % k: v for k, v in extra.items()}}, fh, ensure_ascii=False, indent=1)
    print("extra mapped: %d" % len(extra))


if __name__ == "__main__":
    main()
