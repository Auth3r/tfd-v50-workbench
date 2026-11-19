"""Probe the lobby tick guard on the shifted bridge (byte-level, no encoding drift)."""
import pathlib, sys

ROOT = pathlib.Path(r"E:\第二后裔\TFD发布端V50\TFD发布端V50")
SRC = ROOT / "offset_rework" / "old_bridge_v2_shift10.js"
DST = ROOT / "offset_rework" / "old_bridge_v3_probe.js"

OLD = b"if ((obj.add(8).readU32() & 0x30) || obj.add(0x7b0).readPointer().isNull()) return;"
NEW = (
    b"try{send({event:'probe_tick2',flags:obj.add(8).readU32(),"
    b"p748:obj.add(0x748).readS32().toString(),"
    b"p7b0:obj.add(0x7b0).readPointer().toString(),"
    b"p730:obj.add(0x730).readPointer().toString(),"
    b"p700:obj.add(0x710).readPointer().toString()});"
    b"}catch(e){}\n      " + OLD
)

def main():
    data = SRC.read_bytes()
    if OLD not in data:
        print("MISSING guard line")
        return 1
    data = data.replace(OLD, NEW, 1)
    DST.write_bytes(data)
    print("written", DST.name, len(data), "bytes")
    return 0

if __name__ == "__main__":
    sys.exit(main())
