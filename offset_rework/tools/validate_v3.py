import json, os

OUT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\offset_rework"
RAW = os.path.join(OUT, "offset_map_v3_raw.json")
ALL = os.path.join(OUT, "anchors_all.json")


def hexint(s):
    return int(s.replace("0x-", "-0x"), 16)


def main():
    raw = json.load(open(RAW, encoding="utf-8"))["anchors"]
    meta = {int(a["rva"], 16): a for a in json.load(open(ALL, encoding="utf-8"))["anchors"]}
    rows = []
    for r in raw:
        rva = int(r["old_rva"], 16)
        r["section"] = meta.get(rva, {}).get("section", "?")
        r["is_func"] = meta.get(rva, {}).get("is_func", False)
        rows.append(r)

    tab = {}
    for r in rows:
        tab.setdefault(r["section"], {}).setdefault(r.get("status"), 0)
        tab[r["section"]][r.get("status")] += 1

    resolved = [r for r in rows if r.get("new_rva") and r.get("status") in ("strong", "good", "weak")]
    resolved.sort(key=lambda r: int(r["old_rva"], 16))

    viol = []
    running = -10 ** 9
    for r in resolved:
        d = hexint(r["delta"])
        if d < running - 0x2000:
            viol.append({"old_rva": r["old_rva"], "delta": r["delta"], "new_rva": r["new_rva"],
                         "score": r.get("score"), "status": r.get("status"),
                         "section": r["section"], "running_max": "0x%x" % running})
        running = max(running, d)

    dupes = {}
    for r in resolved:
        dupes.setdefault(r["new_rva"], []).append(r["old_rva"])
    collisions = {k: v for k, v in dupes.items() if len(v) > 1}

    unresolved = [r for r in rows if not (r.get("new_rva") and r.get("status") in ("strong", "good", "weak"))]

    preds = []
    for r in unresolved:
        u = int(r["old_rva"], 16)
        before = [x for x in resolved if int(x["old_rva"], 16) < u]
        after = [x for x in resolved if int(x["old_rva"], 16) > u]
        db = hexint(before[-1]["delta"]) if before else None
        da = hexint(after[0]["delta"]) if after else None
        pred = (u + db) if db is not None else None
        preds.append({"old_rva": r["old_rva"], "section": r["section"], "status": r.get("status"),
                      "delta_before": ("0x%x" % db) if db is not None else None,
                      "delta_after": ("0x%x" % da) if da is not None else None,
                      "predicted": ("0x%x" % pred) if pred else None})

    payload = {"status_by_section": tab, "monotonic_violations": viol, "collisions": collisions,
               "resolved": len(resolved), "total": len(rows), "unresolved": preds}
    with open(os.path.join(OUT, "validate_v3.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    lines = ["# v3 consistency check", "",
             "resolved %d / %d" % (len(resolved), len(rows)), "",
             "## status by section", "",
             "| section | strong | good | weak | poor | no_seed_hit | bad_rva |",
             "|---|---|---|---|---|---|---|"]
    for sec, st in tab.items():
        lines.append("| %s | %s |" % (sec, " | ".join(str(st.get(k, 0)) for k in
                     ("strong", "good", "weak", "poor", "no_seed_hit", "bad_rva"))))
    lines += ["", "## monotonicity violations (suspect mismatches)", "",
              "count: %d" % len(viol), ""]
    for v in viol[:25]:
        lines.append("- %s %s delta %s new %s score %s (%s)" % (v["old_rva"], v["section"], v["delta"],
                                                               v["new_rva"], v["score"], v["status"]))
    lines += ["", "## new-address collisions", ""]
    if collisions:
        for k, v in list(collisions.items())[:10]:
            lines.append("- %s <- %s" % (k, ", ".join(v)))
    else:
        lines.append("- none")
    lines += ["", "## unresolved (with neighbour-based prediction)", ""]
    for p in preds:
        lines.append("- %s %s status %s prev_delta %s next_delta %s predicted %s" % (
            p["old_rva"], p["section"], p["status"], p["delta_before"], p["delta_after"], p["predicted"]))
    open(os.path.join(OUT, "validate_v3.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(json.dumps({"status_by_section": tab, "violations": len(viol), "collisions": len(collisions),
                      "unresolved": len(unresolved)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
