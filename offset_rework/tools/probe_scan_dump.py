"""Dump the widget that passes the owner filter inside prepareTitle's scan."""
import pathlib, sys

ROOT = pathlib.Path(r"E:\第二后裔\TFD发布端V50\TFD发布端V50")
SRC = ROOT / "offset_rework" / "old_bridge_v2_shift10.js"
DST = ROOT / "offset_rework" / "old_bridge_v3_dump.js"

OLD = b"    const page = object.add(0x748).readS32();"
NEW = b"""    const page = object.add(0x748).readS32();
    try{const f={};for(let o=0x6e0;o<=0x7c0;o+=8){const q=object.add(o).readU64();if(q.toString()!=='0x0')f['0x'+o.toString(16)]=q.toString();}
      send({event:'probe_scan',page:page,qw:f});}catch(e){send({event:'probe_scan_err',d:String(e)});}"""

def main():
    data = SRC.read_bytes()
    if OLD not in data:
        print("MISSING anchor"); return 1
    data = data.replace(OLD, NEW, 1)
    DST.write_bytes(data)
    print("written", DST.name, len(data))
    return 0

if __name__ == "__main__":
    sys.exit(main())
