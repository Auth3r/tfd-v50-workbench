"""Temporary diagnostic build: report what prepareTitle sees."""
src = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\offset_rework\old_bridge_b26722146.js"
dst = r"E:\第二后裔\TFD发布端V50\TFD发布端V50\old_bridge_full.js"

text = open(src, "rb").read().decode("ascii")

probe = ("function prepareTitle(component) {if(!globalThis.__pp||Date.now()-globalThis.__pp>1000){"
         "globalThis.__pp=Date.now();report('probe_prepare',{count:base.add(0xb89c294).readS32(),"
         "chunks:base.add(0xb89c280).readPointer().toString(),prepared:titlePrepared,"
         "requested:requested,scan:titleScan});}")
text = text.replace("function prepareTitle(component) {", probe, 1)

auth = ("function authenticateLobby(widget, component) {report('probe_auth',"
        "{page:widget.add(0x738).readS32(),requested:requested});")
text = text.replace("function authenticateLobby(widget, component) {", auth, 1)

open(dst, "wb").write(text.encode("ascii"))
print("probe build written", len(text))
