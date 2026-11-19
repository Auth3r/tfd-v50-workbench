"""Install the field-scan probe on top of the ORIGINAL (c0147688) bridge, so the
same offsets can be sampled on the old client for layout comparison."""
BAK = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\old_bridge_full.js.bak-c0147688"
DST = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\old_bridge_full.js"

s = open(BAK, "rb").read().decode("ascii")
anchor = "const obj = this.object;"
assert anchor in s, "anchor missing"
probe = ("const obj = this.object;if(!globalThis.__tk||Date.now()-globalThis.__tk>1000){"
         "globalThis.__tk=Date.now();let m={};for(let o=0x6e0;o<=0x860;o+=8){"
         "let v=obj.add(o).readPointer().toString();if(v!=='0x0')m['0x'+o.toString(16)]=v;}"
         "report('probe_map',m);}")
s = s.replace(anchor, probe, 1)
open(DST, "wb").write(s.encode("ascii"))
print("old-client probe installed, bytes", len(s))
