import ida_bytes, ida_funcs, ida_ua, idautils, idc, ida_nalt, ida_idaapi

OUT = "C:/tfdwork/page_writes.txt"
BASE = ida_nalt.get_imagebase()
OFFS = (0x740, 0x748, 0x750, 0x758)
MAXLINES = 6000

lines = []
counts = {o: 0 for o in OFFS}
writes = {o: [] for o in OFFS}
nfun = 0
ninsn = 0

for fn in idautils.Functions():
    f = ida_funcs.get_func(fn)
    if not f:
        continue
    nfun += 1
    end = f.end_ea
    ea = fn
    while ea < end:
        try:
            insn = ida_ua.insn_t()
            if ida_ua.decode_insn(insn, ea) and insn.itype != 0:
                ninsn += 1
                m = insn.get_canon_mnem()
                # Op1 as memory with our displacement
                if insn.Op1.type == 4 and insn.Op1.addr in OFFS:
                    off = insn.Op1.addr
                    counts[off] += 1
                    if len(writes[off]) < MAXLINES:
                        iswr = m.startswith(("mov", "add", "or", "and", "sub", "xor", "inc", "dec", "shl", "shr"))
                        wr = "W" if iswr else "r"
                        imm = ""
                        if insn.Op2.type == 5:
                            imm = " imm=%d" % insn.Op2.value
                        writes[off].append("%s %08x [%s+%03Xh]%s  %s" % (
                            wr, ea - BASE, "mem", off, imm, idc.GetDisasm(ea)))
        except Exception:
            pass
        ea = ida_bytes.next_head(ea, end)
        if ea == ida_idaapi.BADADDR:
            break

with open(OUT, "w", encoding="utf-8") as fh:
    fh.write("imagebase=%x funcs=%d insns=%d\n" % (BASE, nfun, ninsn))
    for off in OFFS:
        fh.write("off +0x%X total=%d\n" % (off, counts[off]))
    for off in OFFS:
        fh.write("\n################ +0x%X ################\n" % off)
        for ln in writes[off]:
            fh.write(ln + "\n")

# xrefs to the old page-switch / showLogin addresses (new RVAs)
xref_out = []
for rva, label in ((0x4AA36B0, "page_switch_old"), (0x4AA2CD0, "show_login"), (0x4AA94A0, "title_cb"), (0x40F8C10, "char_register")):
    ea = BASE + rva
    try:
        xs = list(idautils.XrefsTo(ea))
    except Exception:
        xs = []
    xref_out.append("== %s 0x%x  xrefs=%d" % (label, rva, len(xs)))
    for x in xs[:40]:
        f = ida_funcs.get_func(x.frm)
        nm = idc.get_func_name(f.start_ea) if f else "?"
        xref_out.append("   from %08x type=%d in %s (%08x)  %s" % (
            x.frm - BASE, x.type, nm, (f.start_ea - BASE) if f else 0, idc.GetDisasm(x.frm)))

with open("C:/tfdwork/page_xrefs.txt", "w", encoding="utf-8") as fh:
    fh.write("\n".join(xref_out) + "\n")

print("PAGE_SCAN_DONE funcs=%d insns=%d" % (nfun, ninsn))
