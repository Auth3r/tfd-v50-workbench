"""Sanity-check the rewritten bridge: every literal address must land in a
section of the new build, and function anchors must be real function starts.
"""
import json, os, re, struct

OUT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\offset_rework"
JS = os.path.join(OUT, "old_bridge_b26722146.js")
NEW = r"C:\tfdwork\new.exe"
NEW_IDA = r"C:\tfdwork\new_ida.json"

pat = re.compile(r"(?:image\.add|base\.add)\(0x([0-9a-fA-F]+)\)")


def pe_info(path):
    with open(path, "rb") as f:
        data = f.read()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    optsize = struct.unpack_from("<H", data, pe + 20)[0]
    opt = pe + 24
    sec = opt + optsize
    secs = []
    for i in range(nsec):
        name = data[sec + i * 40: sec + i * 40 + 8].decode("latin1").rstrip("\0")
        vsize, va, rawsize, rawptr = struct.unpack_from("<IIII", data, sec + i * 40 + 8)
        secs.append({"name": name, "va": va, "vsize": vsize, "rawsize": rawsize, "rawptr": rawptr})
    return data, secs


def main():
    data, secs = pe_info(NEW)
    newj = json.load(open(NEW_IDA, encoding="utf-8"))
    starts = set()
    for f in newj["functions"]:
        starts.add(f["rva"] if isinstance(f["rva"], int) else int(f["rva"], 16))

    text = open(JS, encoding="utf-8", errors="replace").read()
    addrs = {}
    for m in pat.finditer(text):
        addrs[int(m.group(1), 16)] = addrs.get(int(m.group(1), 16), 0) + 1

    bad_section, bad_func = [], []
    for a, c in sorted(addrs.items()):
        sec = None
        for s in secs:
            if s["va"] <= a < s["va"] + max(s["vsize"], s["rawsize"]):
                sec = s["name"]
                break
        if sec is None:
            bad_section.append("0x%x x%d" % (a, c))
        elif sec == ".text" and a not in starts:
            bad_func.append("0x%x" % a)

    print(json.dumps({"distinct": len(addrs), "occurrences": sum(addrs.values()),
                      "not_in_any_section": bad_section,
                      "text_but_not_func_start": bad_func}, ensure_ascii=False))


if __name__ == "__main__":
    main()
