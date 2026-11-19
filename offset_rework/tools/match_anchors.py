import json, os, re, struct, sys

OLD = r"E:\第二后裔\The First Descendant\M1\Binaries\Win64\M1-Win64-Shipping.exe"
NEW = r"F:\Codex\TFD-Zero-P0\build-26722146\runtime-copy\M1\Binaries\Win64\M1-Win64-Shipping.exe"
JS = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\old_bridge_full.js"
OUT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\offset_rework"

WINDOW = 192
SEED = 16


def pe_info(path):
    with open(path, "rb") as f:
        data = f.read()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise SystemExit("not a PE: %s" % path)
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    optsize = struct.unpack_from("<H", data, pe + 20)[0]
    opt = pe + 24
    magic = struct.unpack_from("<H", data, opt)[0]
    if magic == 0x20b:
        image_base = struct.unpack_from("<Q", data, opt + 24)[0]
    else:
        image_base = struct.unpack_from("<I", data, opt + 28)[0]
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
        abs_addr = int("0x1" + m.group(1), 16)
        rva = abs_addr - 0x140000000
        if 0 < rva < 0x20000000:
            anchors.setdefault(rva, []).append(line)
    return anchors


def scan(new_data, seed, start=0):
    pos = []
    p = new_data.find(seed, start)
    while p != -1:
        pos.append(p)
        p = new_data.find(seed, p + 1)
    return pos


def score_window(old_bytes, new_data, off, length):
    best = 0
    for shift in (-8, -4, 0, 4, 8):
        o = off + shift
        if o < 0 or o + length > len(new_data):
            continue
        mism = 0
        for i in range(length):
            if old_bytes[i] != new_data[o + i]:
                mism += 1
        s = 1.0 - (mism / float(length))
        if s > best:
            best = s
    return best


def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(os.path.join(OUT, "artifacts", "reverse-cases", "CASE-20261119-17"), exist_ok=True)
    old_data, old_base, old_secs = pe_info(OLD)
    new_data, new_base, new_secs = pe_info(NEW)
    anchors = collect_anchors(JS)

    results = []
    for rva in sorted(anchors):
        off = rva_to_off(rva, old_secs)
        rec = {"old_rva": "0x%x" % rva, "js_lines": anchors[rva], "status": "unmapped"}
        if off is None or off + WINDOW > len(old_data):
            rec["status"] = "bad_rva"
            results.append(rec)
            continue
        body = old_data[off:off + WINDOW]
        seed = body[:SEED]
        cands = scan(new_data, seed)
        rec["seed_hits"] = len(cands)
        scored = []
        for c in cands:
            s = score_window(body, new_data, c, WINDOW)
            scored.append((s, c))
        scored.sort(reverse=True)
        if scored:
            best_score, best_off = scored[0]
            new_rva = off_to_rva(best_off, new_secs)
            rec["best_score"] = round(best_score, 4)
            rec["new_rva"] = "0x%x" % new_rva if new_rva is not None else None
            rec["new_abs"] = "0x%x" % (new_base + new_rva) if new_rva is not None else None
            if best_score >= 0.99:
                rec["status"] = "exact"
            elif best_score >= 0.85:
                rec["status"] = "near"
            else:
                rec["status"] = "weak"
            if len(scored) > 1:
                rec["second_score"] = round(scored[1][0], 4)
        else:
            rec["status"] = "no_seed_hit"
        results.append(rec)

    summary = {"count": len(results)}
    for st in ("exact", "near", "weak", "no_seed_hit", "bad_rva", "unmapped"):
        summary[st] = sum(1 for r in results if r["status"] == st)

    payload = {
        "old": {"path": OLD, "image_base": "0x%x" % old_base, "size": len(old_data)},
        "new": {"path": NEW, "image_base": "0x%x" % new_base, "size": len(new_data)},
        "window": WINDOW,
        "seed": SEED,
        "summary": summary,
        "anchors": results,
    }
    with open(os.path.join(OUT, "offset_map.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    lines = []
    lines.append("# anchor match pass 1 (byte signature)")
    lines.append("")
    lines.append("old: %s (%d bytes)" % (OLD, len(old_data)))
    lines.append("new: %s (%d bytes)" % (NEW, len(new_data)))
    lines.append("")
    lines.append("summary: " + json.dumps(summary, ensure_ascii=False))
    lines.append("")
    lines.append("| old RVA | status | score | new RVA | seed hits | js lines |")
    lines.append("|---|---|---|---|---|---|")
    for r in results:
        lines.append("| %s | %s | %s | %s | %s | %s |" % (
            r["old_rva"], r["status"], r.get("best_score", ""), r.get("new_rva", ""),
            r.get("seed_hits", ""), ",".join(str(x) for x in r["js_lines"][:4])))
    with open(os.path.join(OUT, "match_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
