import pathlib
root = pathlib.Path(r"E:\第二后裔\TFD发布端V50\TFD发布端V50")
for name in ["old_bridge_full.js",
             "offset_rework/old_bridge_b26722146.js",
             "offset_rework/old_bridge_full.js.v2-shift10",
             "old_bridge_full.js.bak-c0147688"]:
    p = root / name
    b = p.read_bytes()
    print(name, "bytes", len(b), "crlf", b.count(b"\r\n"), "lf", b.count(b"\n"),
          "nonascii", sum(1 for x in b if x > 127))
