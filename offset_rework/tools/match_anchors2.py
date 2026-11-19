import json, os, re, struct, sys

OLD = r"E:\第二后裔\The First Descendant\M1\Binaries\Win64\M1-Win64-Shipping.exe"
NEW = r"F:\Codex\TFD-Zero-P0\build-26722146\runtime-copy\M1\Binaries\Win64\M1-Win64-Shipping.exe"
JS = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\old_bridge_full.js"
OUT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\offset_rework"

BODY = 512
SEED_LEN = 12
SEED_OFFSETS = (0, 24, 48, 72, 96, 120)


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
            delta = rva - s["va"]
            if delta >= s["rawsize"]:
                return None
            return s["rawptr"] + delta
    return None


def off_to_rva(off, sections):
    for s in sections:
        if s["rawptr"] <= off < s["rawptr"] + s["rawsize"]:
            return s["va"] + (off - s["rawptr"])
    return None


def collect_anchors(js_path):
    text = open(js_path, "r", encoding="utf-8", errors="replace").read()
    anchors = {}
    for m in re.finditer(r"image\.add\(0x([0-9a-fA-F]+)\)", text):
        line = text.count("\n", 0, m.start()) + 1
        anchors.setdefault(int(m.group(1), 16), []).append(line)
    for m in re.finditer(r"0x1(4[0-9a-fA-F]{7})\b", text):
        line = text.count("\n", 0, m.start()) + 1
        anchors.setdefault(int("0x1" + m.group(1), 16) - 0x140000000, []).append(line)
    return anchors


def score(new_data, off, body):
    best = 0
    for shift in (-12, -8, -4, 0, 4, 8, 12):
        o = off + shift
        if o < 0 or o + BODY > len(new_data) or o + BODY > len(new_data):
            continue
        mism = 0
        for i in range(BODY):
            if body[i] != new_data[o + i]:
                mism += 1
        s = 1.0 - (mism / float(BODY))
        if s > best:
            best = s
    return best


def vote(old_data, new_data, off):
    body = old_data[off:off + BODY]
    votes = {}
    for so in SEED_OFFSETS:
        if so + SEED_LEN > len(body):
            continue
        seed = body[so:so + SEED_LEN]
        if seed.count(seed[0]) == len(seed):
            continue
        p = new_data.find(seed)
        hits = 0
        while p != -1 and hits < 64:
            cand = p - so
            votes[cand] = votes.get(cand, 0) + 1
            p = new_data.find(seed, p + 1)
            hits += 1
    return body, votes


def main():
    old_data, old_base, old_secs = pe_info(OLD)
    new_data, new_base, new_secs = pe_info(NEW)
    anchors = collect_anchors(JS)
    results = []
    for rva in sorted(anchors):
        off = rva_to_off(rva, old_secs)
        rec = {"old_rva": "0x%x" % rva, "js_lines": anchors[rva]}
        if off is None or off + BODY > len(old_data):
            rec["status"] = "bad_rva"
            results.append(rec)
            continue
        body, votes = vote(old_data, new_data, off)
        if votes:
            ranked = sorted(votes.items(), key=lambda kv: (-kv[1], kv[0]))
            best_off, votes_n = ranked[0]
            sc = score(new_data, best_off, body)
            new_rva = off_to_rva(best_off, new_secs)
            rec["new_rva"] = "0x%x" % new_rva if new_rva is not None else None
            rec["score"] = round(sc, 4)
            rec["votes"] = votes_n
            rec["seed_variants"] = len(votes)
            rec["delta"] = ("0x%x" % (new_rva - rva)) if new_rva is not None else None
            if sc >= 0.995 and votes_n >= 2:
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

    clusters = {}
    for r in results:
        if r.get("delta"):
            clusters.setdefault(r["delta"], []).append(r["old_rva"])

    summary = {
        "anchors": len(results),
        "strong": sum(1 for r in results if r.get("status") == "strong"),
        "good": sum(1 for r in results if r.get("status") == "good"),
        "weak": sum(1 for r in results if r.get("status") == "weak"),
        "poor": sum(1 for r in results if r.get("status") == "poor"),
        "no_seed_hit": sum(1 for r in results if r.get("status") == "no_seed_hit"),
        "bad_rva": sum(1 for r in results if r.get("status") == "bad_rva"),
    }
    payload = {"old": OLD, "new": NEW, "summary": summary,
               "clusters": {k: {"count": len(v), "members": v} for k, v in sorted(clusters.items(), key=lambda kv: -len(kv[1]))},
               "anchors": results}
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "offset_map_v2.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    lines = ["# anchor match pass 2 (multi-seed vote + 512B verify)", "",
             "old: %s" % OLD, "new: %s" % NEW, "",
             "summary: " + json.dumps(summary, ensure_ascii=False), "",
             "## delta clusters", "", "| delta | count | members |", "|---|---|---|"]
    for k, v in sorted(clusters.items(), key=lambda kv: -len(kv[1])):
        if len(v) >= 2:
            lines.append("| %s | %d | %s |" % (k, len(v), ", ".join(v)))
    lines += ["", "## anchors", "", "| old RVA | status | new RVA | delta | score | votes | js lines |", "|---|---|---|---|---|---|---|"]
    for r in results:
        lines.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            r["old_rva"], r.get("status"), r.get("new_rva", ""), r.get("delta", ""),
            r.get("score", ""), r.get("votes", ""), ",".join(str(x) for x in r["js_lines"][:3])))
    with open(os.path.join(OUT, "match_report_v2.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
