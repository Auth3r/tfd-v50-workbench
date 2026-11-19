import json, os
import ida_auto, ida_bytes, ida_funcs, ida_nalt, idautils, idc

TARGETS_FILE = r"C:\tfdwork\aux_targets_in.json"
OUT_FILE = r"C:\tfdwork\aux_targets.json"


def main():
    ida_auto.auto_wait()
    base = ida_nalt.get_imagebase()
    targets = json.load(open(TARGETS_FILE, encoding="utf-8"))
    out = {"image_base": base, "targets": {}}
    for t in targets:
        t = int(t)
        ea = base + t
        rec = {"refs": []}
        try:
            for x in idautils.XrefsTo(ea, 0):
                frm = x.frm
                f = ida_funcs.get_func(frm)
                rec["refs"].append({
                    "from_rva": frm - base,
                    "type": int(x.type),
                    "func_rva": (f.start_ea - base) if f else None,
                    "func_size": (f.end_ea - f.start_ea) if f else None,
                    "insn": idc.GetDisasm(frm),
                    "bytes_16": (ida_bytes.get_bytes(frm, 16).hex() if ida_bytes.get_bytes(frm, 16) else None),
                })
        except Exception as e:
            rec["error"] = str(e)
        out["targets"]["0x%x" % t] = rec
    with open(OUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(out, fh)
    print("aux dump: %d targets" % len(out["targets"]))
    idc.qexit(0)


main()
