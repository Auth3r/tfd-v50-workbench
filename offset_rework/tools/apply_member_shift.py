"""Apply the widget-class member shift (+0x10) discovered by the old/new layout diff.

Evidence (probe_map on both builds at the title screen):
  OLD 0x6e0..0x7a0  ==  NEW 0x6f0..0x7b0   (whole member block +0x10)
  OLD 0x7a0 = ptr (non-null, guard passes) -> NEW 0x7b0 = ptr (non-null)
  string fields realign at 0x7f0 in both builds

Only the login-path reads are rewritten; other uses of the same numbers belong to
different classes and must stay untouched.
"""
import io, sys, pathlib

ROOT = pathlib.Path(r"E:\第二后裔\TFD发布端V50\TFD发布端V50")
SRC = ROOT / "old_bridge_full.js"
DST = ROOT / "offset_rework" / "old_bridge_full.js.v2-shift10"

PAIRS = [
    # authenticateLobby: page latch, widget pointer, ticket quadruple
    ("if (requested || widget.add(0x738).readS32() !== 3) return false;",
     "if (requested || widget.add(0x748).readS32() !== 3) return false;"),
    ("if (widget.add(0x720).readPointer().isNull()) return false;",
     "if (widget.add(0x730).readPointer().isNull()) return false;"),
    ("if ([0x760, 0x768, 0x770, 0x778].some(offset => !widget.add(offset).readPointer().isNull())) return false;",
     "if ([0x770, 0x778, 0x780, 0x788].some(offset => !widget.add(offset).readPointer().isNull())) return false;"),
    # prepareTitle: scan loop
    ("const page = object.add(0x738).readS32();",
     "const page = object.add(0x748).readS32();"),
    ("if (page !== -1 || object.add(0x720).readPointer().isNull()) continue;",
     "if (page !== -1 || object.add(0x730).readPointer().isNull()) continue;"),
    ("if ([0x760, 0x768, 0x770, 0x778].some(offset => !object.add(offset).readPointer().isNull())) continue;",
     "if ([0x770, 0x778, 0x780, 0x788].some(offset => !object.add(offset).readPointer().isNull())) continue;"),
    ("report('native_title_login_opened', {page: object.add(0x738).readS32(), manual_start_required: true});",
     "report('native_title_login_opened', {page: object.add(0x748).readS32(), manual_start_required: true});"),
    # page-transition hook (rearm latch)
    ("this.previous=a[0].add(0x738).readS32(); this.page=a[1].toInt32();",
     "this.previous=a[0].add(0x748).readS32(); this.page=a[1].toInt32();"),
    ("if (this.page!==3 || this.previous===3 || this.widget.add(0x738).readS32()!==3 ||",
     "if (this.page!==3 || this.previous===3 || this.widget.add(0x748).readS32()!==3 ||"),
    # lobby widget tick guard
    ("if ((obj.add(8).readU32() & 0x30) || obj.add(0x7a0).readPointer().isNull()) return;",
     "if ((obj.add(8).readU32() & 0x30) || obj.add(0x7b0).readPointer().isNull()) return;"),
]

def main():
    text = SRC.read_text(encoding="utf-8", errors="surrogateescape")
    missing = [old for old, _ in PAIRS if old not in text]
    if missing:
        print("MISSING %d patterns:" % len(missing))
        for m in missing:
            print("  ", m[:100])
        return 1
    for old, new in PAIRS:
        text = text.replace(old, new)
    DST.write_text(text, encoding="utf-8", errors="surrogateescape")
    print("written", DST, DST.stat().st_size, "bytes;", len(PAIRS), "edits")
    return 0

if __name__ == "__main__":
    sys.exit(main())
