import json, os, struct, sys

OLD = r"E:\第二后裔\The First Descendant\M1\Binaries\Win64\M1-Win64-Shipping.exe"
NEW = r"F:\Codex\TFD-Zero-P0\build-26722146\runtime-copy\M1\Binaries\Win64\M1-Win64-Shipping.exe"
OUT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\offset_rework"
ALL = os.path.join(OUT, "anchors_all.json")
V2 = os.path.join(OUT, "offset_map_v2.json")

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


def off_to_rva(off, sections):
    for s in sections:
        if s["rawptr"] <= off < s["rawptr"] + s["rawsize"]:
            return s["va"] + (off - s["rawptr"])
    return None


def score(new_data, off, body):
    best = 0.0
    for shift in (0, -4, 4, -8, 8, -12, 12, -16, 16):
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


def main():
    old_data, old_base, old_secs = pe_info(OLD)
    new_data, new_base, new_secs = pe_info(NEW)
    todos = [int(a["rva"], 16) for a in json.load(open(ALL, encoding="utf-8"))["anchors"]]
    mapped = {}
    if os.path.exists(V2):
        for r in json.load(open(V2, encoding="utf-8"))["anchors"]:
            if r.get("status") in ("strong", "good") and r.get("new_rva"):
                mapped[int(r["old_rva"], 16)] = r["new_rva"]

    results = []
    for idx, rva in enumerate(todos):
        rec = {"old_rva": "0x%x" % rva, "known": mapped.get(rva)}
        off = rva_to_off(rva, old_secs)
        if off is None or off + BODY > len(old_data):
            rec["status"] = "bad_rva"
            results.append(rec)
            continue
        body = old_data[off:off + BODY]
        votes = {}
        for so in SEED_OFFSETS:
            seed = body[so:so + SEED_LEN]
            if len(set(seed)) == 1:
                continue
            p = new_data.find(seed)
            hits = 0
            while p != -1 and hits < 48:
                cand = p - so
                if 0 <= cand < len(new_data) - BODY:
                    cand_rva = off_to_rva(cand, new_secs)
                    if cand_rva is not None:
                        d = cand_rva - rva
                        if DELTA_MIN <= d <= DELTA_MAX:
                            votes[cand] = votes.get(cand, 0) + 1
                p = new_data.find(seed, p + 1)
                hits += 1
        if votes:
            ranked = sorted(votes.items(), key=lambda kv: (-kv[1], kv[0]))
            best_off, vn = ranked[0]
            sc = score(new_data, best_off, body)
            new_rva = off_to_rva(best_off, new_secs)
            rec.update({"new_rva": "0x%x" % new_rva, "score": round(sc, 4), "votes": vn,
                        "seed_variants": len(votes), "delta": "0x%x" % (new_rva - rva)})
            if sc >= 0.995 and vn >= 2:
                rec["status"] = "strong"
            elif sc >= 0.90:
                rec["status"] = "good"
            elif sc >= 0.70:
                rec["status"] = "weak"
            else:
                rec["status"] = "poor"
        else:
            rec["status"] = "no_seed_hit"
        results.append(rec)
        if idx % 25 == 0:
            print("progress %d/%d" % (idx, len(todos)), flush=True)

    summary = {"anchors": len(results)}
    for k in ("strong", "good", "weak", "poor", "no_seed_hit", "bad_rva"):
        summary[k] = sum(1 for r in results if r.get("status") == k)
    summary["already_known"] = sum(1 for r in results if r.get("known"))

    clusters = {}
    for r in results:
        if r.get("delta"):
            clusters.setdefault(r["delta"], []).append(r["old_rva"])

    payload = {"summary": summary,
               "clusters": {k: {"count": len(v), "members": v} for k, v in
                            sorted(clusters.items(), key=lambda kv: -len(kv[1]))},
               "anchors": results}
    with open(os.path.join(OUT, "offset_map_v3_raw.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    lines = ["# full anchor match (300 candidates)", "", "summary: " + json.dumps(summary, ensure_ascii=False), "",
             "## delta clusters (count>=3)", "", "| delta | count | members |", "|---|---|---|"]
    for k, v in sorted(clusters.items(), key=lambda kv: -len(kv[1])):
        if len(v) >= 3:
            lines.append("| %s | %d | %s |" % (k, len(v), ", ".join(v[:8])))
    lines += ["", "## anchors", "", "| old RVA | status | new RVA | delta | score | votes |", "|---|---|---|---|---|---|"]
    for r in results:
        lines.append("| %s | %s | %s | %s | %s | %s |" % (
            r["old_rva"], r.get("status"), r.get("new_rva", ""), r.get("delta", ""),
            r.get("score", ""), r.get("votes", "")))
    open(os.path.join(OUT, "match_report_v3.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
