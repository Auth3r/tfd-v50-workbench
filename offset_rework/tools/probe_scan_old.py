"""Same scan instrumentation, but built from the pristine old-build bridge so the
identical probe can run against the old client for a differential read."""
import pathlib, sys

ROOT = pathlib.Path(r"E:\第二后裔\TFD发布端V50\TFD发布端V50")
SRC = ROOT / "old_bridge_full.js.bak-c0147688"
DST = ROOT / "offset_rework" / "old_bridge_oldprobe_scan.js"

HEAD_OLD = b"  const klass = lobbyClass(), depth = klass.add(0x38).readS32();"
HEAD_NEW = (b"  try{send({event:'probe_head',count:count,chunks:chunks.toString(),"
            b"klass:lobbyClass().toString(),depth:lobbyClass().add(0x38).readS32(),"
            b"klass30:lobbyClass().add(0x30).readPointer().toString()});}"
            b"catch(e){send({event:'probe_head_err',d:String(e)});}\r\n" + HEAD_OLD)

OWNER_OLD = b"    const owner = widgetOwner(object);"
OWNER_NEW = (b"    try{const ow=widgetOwner(object);const f={};"
             b"for(let o=0x700;o<=0x7c0;o+=8){const q=object.add(o).readU64();"
             b"if(q.toString()!=='0x0')f['0x'+o.toString(16)]=q.toString();}"
             b"send({event:'probe_cand',page:object.add(0x738).readS32(),owner:ow.toString(),"
             b"owner830:ow.isNull()?'NULL':ow.add(0x830).readPointer().toString(),q:f});}"
             b"catch(e){send({event:'probe_cand_err',d:String(e)});}\r\n" + OWNER_OLD)

def main():
    data = SRC.read_bytes()
    for old, new in ((HEAD_OLD, HEAD_NEW), (OWNER_OLD, OWNER_NEW)):
        n = data.count(old)
        if n != 1:
            print("anchor count", n, "for", old[:50]); return 1
        data = data.replace(old, new, 1)
    DST.write_bytes(data)
    print("written", DST.name, len(data))
    return 0

if __name__ == "__main__":
    sys.exit(main())
