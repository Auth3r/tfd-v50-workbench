import json, os

OUT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\offset_rework"
ADJ = os.path.join(OUT, "adjudicate.json")
ALL = os.path.join(OUT, "anchors_all.json")


def main():
    adj = json.load(open(ADJ, encoding="utf-8"))
    meta = {a["rva"]: a for a in json.load(open(ALL, encoding="utf-8"))["anchors"]}

    groups = {}
    for it in adj["items"]:
        sec = meta.get(it["old_rva"], {}).get("section", "?")
        groups.setdefault(it["verdict"], []).append((sec, it))

    lines = ["# adjudication detail", "", "counts: " + json.dumps(adj["counts"], ensure_ascii=False), ""]
    for verdict, items in groups.items():
        secs = {}
        for sec, it in items:
            secs.setdefault(sec, 0)
            secs[sec] += 1
        lines.append("## %s (%d) %s" % (verdict, len(items), secs))
        if verdict == "confirmed_func":
            continue
        for sec, it in items[:40]:
            lines.append("- %s %s cand %s score %s %s" % (it["old_rva"], sec, it.get("new_rva"),
                                                          it.get("new_size", ""), it.get("note", "")))
        lines.append("")

    # delta stats for confirmed
    deltas = {}
    for it in [x[1] for x in groups.get("confirmed_func", [])]:
        rva = int(it["old_rva"], 16)
        nrva = int(it["new_rva"], 16)
        d = nrva - rva
        deltas[d] = deltas.get(d, 0) + 1
    top = sorted(deltas.items(), key=lambda kv: -kv[1])[:15]
    lines.append("## top deltas among confirmed")
    for d, c in top:
        lines.append("- 0x%x  x%d" % (d, c))

    open(os.path.join(OUT, "adjudicate_detail.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("ok")


if __name__ == "__main__":
    main()
