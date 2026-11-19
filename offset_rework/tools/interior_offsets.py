import bisect, json, os

OUT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\offset_rework"
ADJ = os.path.join(OUT, "adjudicate.json")
OLD_IDA = r"C:\tfdwork\old_ida.json"
NEW_IDA = r"C:\tfdwork\new_ida.json"


def main():
    oldf = sorted((int(f["rva"], 16), f["size"]) for f in json.load(open(OLD_IDA, encoding="utf-8"))["functions"])
    newf = sorted(((f["rva"] if isinstance(f["rva"], int) else int(f["rva"], 16)), f["size"])
                  for f in json.load(open(NEW_IDA, encoding="utf-8"))["functions"])
    okeys = [k for k, _ in oldf]
    nkeys = [k for k, _ in newf]

    for it in json.load(open(ADJ, encoding="utf-8"))["items"]:
        if it["verdict"] != "not_func_start":
            continue
        o = int(it["old_rva"], 16)
        c = int(it["new_rva"], 16)
        oi = bisect.bisect_right(okeys, o) - 1
        ni = bisect.bisect_right(nkeys, c) - 1
        o_off = o - okeys[oi]
        n_off = c - nkeys[ni]
        same_func = okeys[oi] == o
        print("%-11s old_func 0x%-9x +0x%-4x | new_func 0x%-9x +0x%-4x | same_offset %s | old_is_start %s"
              % (it["old_rva"], okeys[oi], o_off, nkeys[ni], n_off, o_off == n_off, same_func))


if __name__ == "__main__":
    main()
