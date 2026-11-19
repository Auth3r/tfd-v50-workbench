import json, os
import ida_auto, ida_funcs, ida_nalt, idautils, idc

OUT = r"C:\tfdwork"


def main():
    ida_auto.auto_wait()
    base = ida_nalt.get_imagebase()
    funcs = []
    for ea in idautils.Functions():
        f = ida_funcs.get_func(ea)
        if f is None:
            continue
        funcs.append({"rva": f.start_ea - base, "size": f.end_ea - f.start_ea,
                      "name": ida_funcs.get_func_name(f.start_ea) or ""})
    segs = []
    try:
        for s in idautils.Segments():
            segs.append({"name": idc.get_segm_name(s), "start": s - base, "end": idc.get_segm_end(s) - base})
    except Exception as e:
        segs.append({"error": str(e)})
    payload = {"image_base": base, "function_count": len(funcs), "functions": funcs, "segments": segs}
    with open(os.path.join(OUT, "new_ida.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    print("new dump done: %d functions" % len(funcs))
    idc.qexit(0)


main()
