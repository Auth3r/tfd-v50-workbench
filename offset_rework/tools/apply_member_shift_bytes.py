"""Byte-level member shift (+0x10) applied to the canonical migrated bridge.

Reads offset_rework/old_bridge_b26722146.js (103,630 B, canonical) and writes
offset_rework/old_bridge_v2_shift10.js with only the login-path member offsets
bumped by 0x10. No text decoding, so line endings cannot drift.
"""
import pathlib, sys

ROOT = pathlib.Path(r"E:\第二后裔\TFD发布端V50\TFD发布端V50")
SRC = ROOT / "offset_rework" / "old_bridge_b26722146.js"
DST = ROOT / "offset_rework" / "old_bridge_v2_shift10.js"

PAIRS = [
    (b"if (requested || widget.add(0x738).readS32() !== 3) return false;",
     b"if (requested || widget.add(0x748).readS32() !== 3) return false;"),
    (b"if (widget.add(0x720).readPointer().isNull()) return false;",
     b"if (widget.add(0x730).readPointer().isNull()) return false;"),
    (b"if ([0x760, 0x768, 0x770, 0x778].some(offset => !widget.add(offset).readPointer().isNull())) return false;",
     b"if ([0x770, 0x778, 0x780, 0x788].some(offset => !widget.add(offset).readPointer().isNull())) return false;"),
    (b"const page = object.add(0x738).readS32();",
     b"const page = object.add(0x748).readS32();"),
    (b"if (page !== -1 || object.add(0x720).readPointer().isNull()) continue;",
     b"if (page !== -1 || object.add(0x730).readPointer().isNull()) continue;"),
    (b"if ([0x760, 0x768, 0x770, 0x778].some(offset => !object.add(offset).readPointer().isNull())) continue;",
     b"if ([0x770, 0x778, 0x780, 0x788].some(offset => !object.add(offset).readPointer().isNull())) continue;"),
    (b"report('native_title_login_opened', {page: object.add(0x738).readS32(), manual_start_required: true});",
     b"report('native_title_login_opened', {page: object.add(0x748).readS32(), manual_start_required: true});"),
    (b"this.previous=a[0].add(0x738).readS32(); this.page=a[1].toInt32();",
     b"this.previous=a[0].add(0x748).readS32(); this.page=a[1].toInt32();"),
    (b"if (this.page!==3 || this.previous===3 || this.widget.add(0x738).readS32()!==3 ||",
     b"if (this.page!==3 || this.previous===3 || this.widget.add(0x748).readS32()!==3 ||"),
    (b"if ((obj.add(8).readU32() & 0x30) || obj.add(0x7a0).readPointer().isNull()) return;",
     b"if ((obj.add(8).readU32() & 0x30) || obj.add(0x7b0).readPointer().isNull()) return;"),
]

def main():
    data = SRC.read_bytes()
    missing = [p for p, _ in PAIRS if p not in data]
    if missing:
        print("MISSING", len(missing))
        for m in missing:
            print("  ", m.decode("ascii", "replace")[:110])
        return 1
    for old, new in PAIRS:
        data = data.replace(old, new)
    DST.write_bytes(data)
    print("written", DST.name, len(data), "bytes")
    return 0

if __name__ == "__main__":
    sys.exit(main())
