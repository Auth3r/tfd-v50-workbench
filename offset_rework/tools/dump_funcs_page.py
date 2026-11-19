import ida_funcs, ida_bytes, idc, idautils, ida_nalt, ida_idaapi

BASE = ida_nalt.get_imagebase()
OUT = "C:/tfdwork/page_funcs.txt"

TARGETS = [0x4AA36B0, 0x4AA2CD0, 0x4AA94A0, 0x4AA2960, 0x4AA2A60,
           0x4AA3240, 0x4AA39C0, 0x4AA30C0, 0x3947290, 0x3947470,
           0x449D540, 0x44A5370, 0x40F8C10]

fh = open(OUT, "w", encoding="utf-8")
fh.write("imagebase=%x\n" % BASE)


def fname(ea):
    f = ida_funcs.get_func(ea)
    return (idc.get_func_name(f.start_ea), f.start_ea - BASE) if f else ("?", 0)


def dump(rva):
    ea = BASE + rva
    f = ida_funcs.get_func(ea)
    fh.write("\n\n########## sub_%08X ##########\n" % rva)
    if not f:
        fh.write("  !! not a function (or no func record)\n")
        return
    fh.write("  start=%08x size=%d  name=%s\n" % (f.start_ea - BASE, f.end_ea - f.start_ea, idc.get_func_name(f.start_ea)))
    xr = list(idautils.XrefsTo(f.start_ea))
    fh.write("  callers=%d\n" % len(xr))
    for x in xr[:25]:
        if x.type in (1, 2):
            continue
        nm, fa = fname(x.frm)
        fh.write("    <- %08x in %s(%08x)\n" % (x.frm - BASE, nm, fa))
    ea2 = f.start_ea
    while ea2 < f.end_ea:
        line = "%08x  %s" % (ea2 - BASE, idc.GetDisasm(ea2))
        if "+748h" in line or "+740h" in line or "+750h" in line:
            line += "        <<<<<< PAGE?"
        fh.write(line + "\n")
        ea2 = ida_bytes.next_head(ea2, f.end_ea)
        if ea2 == ida_idaapi.BADADDR:
            break


for r in TARGETS:
    dump(r)

# reverse call chain (up to depth 4) for showLogin / title callback entries
fh.write("\n\n########## caller chains ##########\n")


def chain(rva, depth=4, maxnodes=60):
    seen = set()
    frontier = [(BASE + rva, 0)]
    nodes = 0
    while frontier and nodes < maxnodes:
        ea, d = frontier.pop(0)
        if ea in seen or d > depth:
            continue
        seen.add(ea)
        nm, fa = fname(ea)
        fh.write("%s%s(%08x) depth=%d\n" % ("   " * d, nm, fa, d))
        nodes += 1
        for x in idautils.XrefsTo(fa if fa else ea):
            if x.type in (1, 2):
                continue
            f2 = ida_funcs.get_func(x.frm)
            if not f2:
                continue
            pn = idc.get_func_name(f2.start_ea)
            if pn.startswith("sub_"):
                frontier.append((f2.start_ea, d + 1))
            else:
                fh.write("%s%s %s (named, from %08x)\n" % ("   " * (d + 1), pn, "", x.frm - BASE))


fh.write("\n== chain of showLogin 0x4AA2CD0\n")
chain(0x4AA2CD0)
fh.write("\n== chain of title_cb 0x4AA94A0\n")
chain(0x4AA94A0)

fh.close()
print("DUMP_FUNCS_DONE")
