"""Locate a function in the new build by sampling rel32-free byte fragments.

Fragments that contain no E8/E9 bytes survive recompilation intact. Each hit
votes for (hit_address - fragment_offset); the winning offset is the new start.
"""
import json, os, struct, collections

OLD = r"C:\tfdwork\old.exe"
NEW = r"C:\tfdwork\new.exe"
OLD_IDA = r"C:\tfdwork\old_ida.json"
TARGETS = [0x43fd5a0, 0x4454710, 0x441bd00, 0x4456440, 0x3c842a0, 0x3c7d270,
           0x3d82090, 0x3dc2090, 0x3fba2d0, 0x3f97720, 0x4443170, 0x44c45f0]


def pe(path):
    d = open(path, "rb").read()
    e = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, e + 6)[0]
    o = struct.unpack_from("<H", d, e + 20)[0]
    sec = e + 24 + o
    out = []
    for i in range(n):
        nm = d[sec + i * 40: sec + i * 40 + 8].decode("latin1").rstrip("\0")
        vs, va, rs, rp = struct.unpack_from("<IIII", d, sec + i * 40 + 8)
        out.append((nm, va, vs, rs, rp))
    return d, out


def off(rva, secs):
    for nm, va, vs, rs, rp in secs:
        if va <= rva < va + max(vs, rs):
            dd = rva - va
            return rp + dd if dd < rs else None
    return None


def main():
    od, osecs = pe(OLD)
    nd, nsecs = pe(NEW)
    text = [s for s in nsecs if s[0] == ".text"][0]
    tb = nd[text[4]:text[4] + text[2]]
    tbase = text[1]
    sizes = {int(f["rva"], 16): f["size"] for f in json.load(open(OLD_IDA, encoding="utf-8"))["functions"]}

    for t in TARGETS:
        size = sizes.get(t, 0)
        oo = off(t, osecs)
        body = od[oo:oo + size]
        votes = collections.Counter()
        used = 0
        for p in range(0, max(0, len(body) - 24), 32):
            frag = body[p:p + 16]
            if len(frag) < 16 or b"\xe8" in frag or b"\xe9" in frag:
                continue
            hits, q = [], tb.find(frag)
            while q != -1 and len(hits) < 40:
                hits.append(q)
                q = tb.find(frag, q + 1)
            used += 1
            for h in hits:
                votes[tbase + h - p] += 1
        print("== 0x%x size %d fragments %d" % (t, size, used))
        for cand, v in votes.most_common(4):
            ns = sizes_by_new(cand) if False else None
            print("   0x%-9x votes %d" % (cand, v))


if __name__ == "__main__":
    main()
