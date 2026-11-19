import json, os, struct

OLD = r"E:\第二后裔\The First Descendant\M1\Binaries\Win64\M1-Win64-Shipping.exe"
NEW = r"F:\Codex\TFD-Zero-P0\build-26722146\runtime-copy\M1\Binaries\Win64\M1-Win64-Shipping.exe"
OUT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\offset_rework"
MAP = os.path.join(OUT, "offset_map_v2.json")

TEXT_UNRESOLVED = [0x3641950, 0x36db250, 0x3c3f670, 0x4236d90]
WIN = 256
SEARCH = 0x6000
STRIDE = 4


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


def similar_count(a, b):
    n = 0
    for x, y in zip(a, b):
        if x == y:
            n += 1
    return n


def main():
    old_data, old_base, old_secs = pe_info(OLD)
    new_data, new_base, new_secs = pe_info(NEW)
    v2 = json.load(open(MAP, encoding="utf-8"))
    known = []
    for r in v2["anchors"]:
        if r.get("delta") and r.get("new_rva") and r.get("status") in ("strong", "good", "weak"):
            try:
                known.append((int(r["old_rva"], 16), int(r["delta"], 16)))
            except ValueError:
                pass
    known.sort()

    out_rows = []
    for u in TEXT_UNRESOLVED:
        prev = [k for k in known if k[0] < u]
        nxt = [k for k in known if k[0] > u]
        base_delta = prev[-1][1] if prev else 0
        bound = (prev[-1][0], nxt[0][0]) if prev and nxt else None
        body_off = rva_to_off(u, old_secs)
        body = old_data[body_off:body_off + WIN]
        pred = u + base_delta
        best = (0.0, None)
        second = (0.0, None)
        start = max(0, pred - SEARCH)
        end = min(len(new_data) - WIN, pred + SEARCH)
        for cand_off in range(start, end, STRIDE):
            sc = similar_count(body, new_data[cand_off:cand_off + WIN]) / float(WIN)
            if sc > best[0]:
                second = best
                best = (sc, cand_off)
            elif sc > second[0]:
                second = (sc, cand_off)
        new_rva = off_to_rva(best[1], new_secs) if best[1] is not None else None
        row = {
            "old_rva": "0x%x" % u,
            "predicted": "0x%x" % pred,
            "base_delta": "0x%x" % base_delta,
            "bracket": ["0x%x" % bound[0], "0x%x" % bound[1]] if bound else None,
            "best_score": round(best[0], 4),
            "second_score": round(second[0], 4),
            "new_rva": "0x%x" % new_rva if new_rva is not None else None,
            "new_delta": "0x%x" % (new_rva - u) if new_rva is not None else None,
        }
        out_rows.append(row)

    json.dump(out_rows, open(os.path.join(OUT, "text_unresolved_pass3.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    lines = ["# pass3 delta-model local search (text anchors)", "",
             "| old rva | predicted | best | second | new rva | delta | bracket |", "|---|---|---|---|---|---|---|"]
    for r in out_rows:
        lines.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            r["old_rva"], r["predicted"], r["best_score"], r["second_score"],
            r["new_rva"], r["new_delta"], r["bracket"]))
    open(os.path.join(OUT, "text_unresolved_pass3.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
