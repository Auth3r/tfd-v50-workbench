import json, os

OUT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\offset_rework"
ALL = os.path.join(OUT, "anchors_all.json")
V3 = os.path.join(OUT, "offset_map_v3_raw.json")
AUX = r"C:\tfdwork\aux_targets.json"


def as_int(v):
    if v is None:
        return None
    return v if isinstance(v, int) else int(v, 16)


aux = json.load(open(AUX, encoding="utf-8"))["targets"]
mapped = {}
for r in json.load(open(V3, encoding="utf-8"))["anchors"]:
    if r.get("new_rva") and r.get("status") in ("strong", "good", "weak"):
        mapped[int(r["old_rva"], 16)] = int(r["new_rva"], 16)

targets = [int(a["rva"], 16) for a in json.load(open(ALL, encoding="utf-8"))["anchors"]
           if a["section"] in (".rdata", ".data", "?")]

print("mapped functions: %d" % len(mapped))
for t in sorted(targets):
    key = "0x%x" % t
    rec = aux.get(key, {})
    refs = rec.get("refs", [])
    mrefs = [r for r in refs if as_int(r.get("func_rva")) in mapped]
    print("%-12s refs=%-5d mapped_refs=%-4d %s" % (key, len(refs), len(mrefs),
          (refs[0]["insn"] if refs else "")))
