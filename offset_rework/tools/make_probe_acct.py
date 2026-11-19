"""Build a probe bridge: adds a dump of the account object at 0x44a5370.
Output: offset_rework/old_bridge_v5_probe_acct.js (byte-level replace, CRLF kept).
"""
import pathlib, sys

SRC = pathlib.Path(r"E:\第二后裔\TFD发布端V50\TFD发布端V50\offset_rework\old_bridge_v4_direct.js")
DST = pathlib.Path(r"E:\第二后裔\TFD发布端V50\TFD发布端V50\offset_rework\old_bridge_v5_probe_acct.js")

OLD = b"onEnter(a) { this.count = a[1].add(0x70).readS32(); },"
NEW = (b"onEnter(a) { this.count = a[1].add(0x70).readS32();"
       b" try{const p=a[1];const dp=[];for(let o=0x40;o<=0x120;o+=8){dp.push(o.toString(16)+':'+"
       b"p.add(o).readS32());}report('probe_acct_obj',{p:p.toString(),a0:a[0].toString(),"
       b"a2:(a[2]?a[2].toString():'0'),dump:dp.join(',')});}catch(e){"
       b"report('probe_acct_err',{e:String(e)});} },")

data = SRC.read_bytes()
if data.count(OLD) != 1:
    print("anchor count", data.count(OLD))
    sys.exit(1)
data = data.replace(OLD, NEW)
DST.write_bytes(data)
print("written", DST, len(data))
