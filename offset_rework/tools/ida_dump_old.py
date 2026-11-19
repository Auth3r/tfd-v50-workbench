import json, os

import ida_auto
import ida_bytes
import ida_funcs
import ida_nalt
import ida_xref
import idautils
import idc

OUT = r"C:\tfdwork"
TARGETS = [
    0x8fc0930, 0x9803f50, 0x9a60570, 0x9a64528, 0x9a6f3b8, 0x9a776b8, 0x9a781f0, 0x9a86308,
    0xb75c300, 0xb75c314, 0x3641950, 0x36db250, 0x3c3f670, 0x4236d90, 0xbcbb2b0,
]


def main():
    ida_auto.auto_wait()
    image_base = ida_nalt.get_imagebase()
    os.makedirs(OUT, exist_ok=True)

    funcs = []
    for ea in idautils.Functions():
        f = ida_funcs.get_func(ea)
        if f is None:
            continue
        funcs.append({
            "rva": "0x%x" % (f.start_ea - image_base),
            "size": f.end_ea - f.start_ea,
            "name": ida_funcs.get_func_name(f.start_ea) or "",
        })

    xrefs = {}
    for t in TARGETS:
        ea = image_base + t
        rec = {"exists": ida_bytes.is_loaded(ea) if hasattr(ida_bytes, "is_loaded") else True, "refs": []}
        for x in idautils.XrefsTo(ea, 0):
            frm = x.frm
            f = ida_funcs.get_func(frm)
            rec["refs"].append({
                "from_rva": "0x%x" % (frm - image_base),
                "type": int(x.type),
                "func_rva": ("0x%x" % (f.start_ea - image_base)) if f else None,
                "func_size": (f.end_ea - f.start_ea) if f else None,
                "insn": idc.GetDisasm(frm),
                "bytes_16": ida_bytes.get_bytes(frm, 16).hex() if ida_bytes.get_bytes(frm, 16) else None,
            })
        xrefs["0x%x" % t] = rec

    payload = {"image_base": "0x%x" % image_base, "function_count": len(funcs),
               "functions": funcs, "targets": xrefs}
    with open(os.path.join(OUT, "old_ida.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    print("IDA dump done: %d functions" % len(funcs))
    idc.qexit(0)


main()
