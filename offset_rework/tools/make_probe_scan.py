"""Probe v7: dump raw qwords 0x00..0x300 of the account object at 0x44a5370."""
import pathlib, sys

SRC = pathlib.Path(r"E:\第二后裔\TFD发布端V50\TFD发布端V50\offset_rework\old_bridge_v4_direct.js")
DST = pathlib.Path(r"E:\第二后裔\TFD发布端V50\TFD发布端V50\offset_rework\old_bridge_v6_probe_scan.js")

OLD = b"onEnter(a) { this.count = a[1].add(0x70).readS32(); },"
NEW = (b"onEnter(a) { this.count = a[1].add(0xb8).readS32();"
       b" try{const p=a[1];const q=[];for(let o=0;o<=0x300;o+=8){q.push(o.toString(16)+'='+"
       b"p.add(o).readU64().toString(16));}report('probe_acct_scan',{p:p.toString(),"
       b"c130:a[0].add(0x130).readU8(),dump:q.join('|')});}catch(e){"
       b"report('probe_acct_err',{e:String(e)});} },")

data = SRC.read_bytes()
if data.count(OLD) != 1:
    print("anchor count", data.count(OLD))
    sys.exit(1)
data = data.replace(OLD, NEW)
DST.write_bytes(data)
print("written", DST, len(data))
