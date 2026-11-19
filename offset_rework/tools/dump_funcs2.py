import ida_funcs, ida_bytes, idc, idautils, ida_nalt, ida_idaapi

BASE = ida_nalt.get_imagebase()
OUT = "C:/tfdwork/page_funcs2.txt"
TARGETS = [0x394D560, 0x3913F80, 0x38E1390, 0x4850220, 0x4850BB0, 0x4850480,
           0x4AA3170, 0x4AA3E20, 0x4AA4220, 0x4AA8550, 0x4AA2820, 0x4ACF6C0]

fh = open(OUT, "w", encoding="utf-8")
fh.write("imagebase=%x\n" % BASE)

for rva in TARGETS:
    ea = BASE + rva
    f = ida_funcs.get_func(ea)
    fh.write("\n\n########## sub_%08X ##########\n" % rva)
    if not f:
        fh.write("  !! not a function\n")
        continue
    fh.write("  start=%08x size=%d name=%s\n" % (f.start_ea - BASE, f.end_ea - f.start_ea, idc.get_func_name(f.start_ea)))
    xr = [x for x in idautils.XrefsTo(f.start_ea) if x.type not in (1, 2)]
    fh.write("  code xrefs=%d\n" % len(xr))
    for x in xr[:12]:
        ff = ida_funcs.get_func(x.frm)
        fh.write("    <- %08x in %08x\n" % (x.frm - BASE, (ff.start_ea - BASE) if ff else 0))
    ea2 = f.start_ea
    n = 0
    while ea2 < f.end_ea and n < 400:
        fh.write("%08x  %s\n" % (ea2 - BASE, idc.GetDisasm(ea2)))
        ea2 = ida_bytes.next_head(ea2, f.end_ea)
        if ea2 == ida_idaapi.BADADDR:
            break
        n += 1

fh.close()
print("DUMP2_DONE")
