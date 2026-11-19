"""Merge everything known into one mapping table with explicit confidence.

sources, in order of trust:
  1. confirmed_func   : byte match landed exactly on a new function start, size comparable
  2. snap_func        : candidate was a few bytes inside a new function; snap to its start
  3. data_reloc       : rdata/data anchor relocated through a mapped caller instruction
  4. derived          : known struct base + constant offset
"""
import json, os

OUT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\offset_rework"
ADJ = os.path.join(OUT, "adjudicate.json")
ALL = os.path.join(OUT, "anchors_all.json")
DATA = os.path.join(OUT, "data_anchors_v3.json")
NEW_IDA = r"C:\tfdwork\new_ida.json"
OLD_IDA = r"C:\tfdwork\old_ida.json"

IGNORE = {"0x30200000", "0x60000030"}


def main():
    adj = json.load(open(ADJ, encoding="utf-8"))["items"]
    meta = {a["rva"]: a for a in json.load(open(ALL, encoding="utf-8"))["anchors"]}
    old_funcs = {int(f["rva"], 16): f["size"] for f in json.load(open(OLD_IDA, encoding="utf-8"))["functions"]}
    newj = json.load(open(NEW_IDA, encoding="utf-8"))
    new_starts = sorted((f["rva"] if isinstance(f["rva"], int) else int(f["rva"], 16), f["size"])
                        for f in newj["functions"])

    import bisect
    keys = [s for s, _ in new_starts]

    data_rows = {}
    if os.path.exists(DATA):
        for r in json.load(open(DATA, encoding="utf-8"))["rows"]:
            if r.get("new_rva"):
                data_rows[r["old_rva"]] = {"new_rva": r["new_rva"], "votes": r["votes"]}

    out = []
    for it in adj:
        old_key = it["old_rva"]
        if old_key in IGNORE:
            continue
        rva = int(old_key, 16)
        rec = {"old_rva": old_key, "section": meta.get(old_key, {}).get("section", "?"),
               "is_func_old": old_key in [k for k in meta if meta[k].get("is_func")] or meta.get(old_key, {}).get("is_func", False)}
        if it["verdict"] == "confirmed_func":
            rec.update({"new_rva": it["new_rva"], "method": "confirm_func",
                        "delta": "0x%x" % (int(it["new_rva"], 16) - rva),
                        "old_size": it.get("old_size"), "new_size": it.get("new_size")})
        elif it["verdict"] == "not_func_start" and it.get("new_rva"):
            cand = int(it["new_rva"], 16)
            i = bisect.bisect_right(keys, cand) - 1
            old_size = old_funcs.get(rva)
            old_start = None
            for s, sz in sorted(((int(f["rva"], 16), f["size"])
                                 for f in json.load(open(OLD_IDA, encoding="utf-8"))["functions"])):
                pass  # placeholder, real lookup below
            in_new = keys[i] if i >= 0 else None
            off_new = cand - in_new if in_new is not None else None
            # locate the old function that contains this anchor
            old_starts = sorted(old_funcs)
            j = bisect.bisect_right(old_starts, rva) - 1
            old_fstart = old_starts[j] if j >= 0 else None
            off_old = rva - old_fstart if old_fstart is not None else None
            is_old_start = (old_fstart == rva)

            if not is_old_start and off_old is not None and off_new is not None and off_old == off_new:
                # same intra-function slot on both sides: accept the candidate itself
                rec.update({"new_rva": "0x%x" % cand, "method": "interior_offset",
                            "delta": "0x%x" % (cand - rva), "off": off_old})
            elif is_old_start and off_new is not None and off_new <= 0x60 and i >= 0:
                rec.update({"new_rva": "0x%x" % keys[i], "method": "snap_func",
                            "delta": "0x%x" % (keys[i] - rva), "snap_offset": off_new,
                            "old_size": old_size, "new_size": new_starts[i][1]})
        out.append(rec)

    # data anchors override the unmapped placeholders
    by_key = {o["old_rva"]: o for o in out}
    for key, v in data_rows.items():
        rva = int(key, 16)
        rec = by_key.get(key)
        if rec is None:
            rec = {"old_rva": key, "section": meta.get(key, {}).get("section", "?")}
            out.append(rec)
            by_key[key] = rec
        if rec.get("new_rva"):
            continue
        rec.update({"new_rva": v["new_rva"], "method": "data_reloc", "votes": v["votes"],
                    "delta": "0x%x" % (int(v["new_rva"], 16) - rva)})

    # derived: 0xb75c314 = 0xb75c300 + 0x14 (same global struct)
    base = next((o for o in out if o["old_rva"] == "0xb75c300"), None)
    if base and not any(o["old_rva"] == "0xb75c314" for o in out):
        out.append({"old_rva": "0xb75c314", "section": ".data",
                    "new_rva": "0x%x" % (int(base["new_rva"], 16) + 0x14),
                    "method": "derived", "delta": base["delta"]})

    counts = {}
    for o in out:
        m = o.get("method", "unmapped")
        counts[m] = counts.get(m, 0) + 1

    payload = {"counts": counts, "anchors": sorted(out, key=lambda x: int(x["old_rva"], 16)),
               "unmapped": [i["old_rva"] for i in adj if i["verdict"] == "unresolved"
                            and i["old_rva"] not in IGNORE and i["old_rva"] not in data_rows]}
    with open(os.path.join(OUT, "offset_map_v3.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print(json.dumps(counts, ensure_ascii=False), "unmapped:", len(payload["unmapped"]))


if __name__ == "__main__":
    main()
