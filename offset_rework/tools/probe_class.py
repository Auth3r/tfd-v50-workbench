"""Compare the tick widget's own class with lobbyClass() on the new build."""
import pathlib, sys

ROOT = pathlib.Path(r"E:\第二后裔\TFD发布端V50\TFD发布端V50")
SRC = ROOT / "offset_rework" / "old_bridge_v2_shift10.js"
DST = ROOT / "offset_rework" / "old_bridge_v3_class.js"

OLD = b"if ((obj.add(8).readU32() & 0x30) || obj.add(0x7b0).readPointer().isNull()) return;"
NEW = (
    b"try{if(!globalThis.__klassProbe){globalThis.__klassProbe=1;"
    b"const t=obj.add(0x10).readPointer();const k=lobbyClass();const f={};"
    b"for(let o=0;o<=0x80;o+=8){const q=t.add(o).readU64();if(q.toString()!=='0x0')f['0x'+o.toString(16)]=q.toString();}"
    b"send({event:'probe_class',obj:obj.toString(),type:t.toString(),klass:k.toString(),"
    b"same:t.equals(k),klass30:k.add(0x30).readPointer().toString(),klass38:k.add(0x38).readS32(),"
    b"type30:t.add(0x30).readPointer().toString(),type38:t.add(0x38).readS32(),typeqw:f});}}"
    b"catch(e){send({event:'probe_class_err',d:String(e)});}\r\n      " + OLD
)

def main():
    data = SRC.read_bytes()
    if OLD not in data:
        print("MISSING guard"); return 1
    data = data.replace(OLD, NEW, 1)
    DST.write_bytes(data)
    print("written", DST.name, len(data))
    return 0

if __name__ == "__main__":
    sys.exit(main())
