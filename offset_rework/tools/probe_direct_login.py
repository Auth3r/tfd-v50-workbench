"""Call the native login entry directly from the lobby tick, skipping the widget
class-chain scan that finds nothing on the new build."""
import pathlib, sys

ROOT = pathlib.Path(r"E:\第二后裔\TFD发布端V50\TFD发布端V50")
SRC = ROOT / "offset_rework" / "old_bridge_v2_shift10.js"
DST = ROOT / "offset_rework" / "old_bridge_v4_direct.js"

OLD = b"if ((obj.add(8).readU32() & 0x30) || obj.add(0x7b0).readPointer().isNull()) return;"
NEW = OLD + (
    b"\r\n      "
    b"if (!globalThis.__directLogin && Date.now() - born > 22000) {\r\n"
    b"        globalThis.__directLogin = 1;\r\n"
    b"        try {\r\n"
    b"          const dg = obj.add(0x430), n = dg.add(8).readS32();\r\n"
    b"          report('probe_direct_prep', {delegates: dg.readPointer().toString(), count: n});\r\n"
    b"          if (!dg.readPointer().isNull() && n >= 1 && n <= 64) {\r\n"
    b"            launcherAuthentication = true;\r\n"
    b"            login(obj, ticket);\r\n"
    b"            launcherAuthentication = false;\r\n"
    b"            report('probe_direct_called');\r\n"
    b"          }\r\n"
    b"        } catch (e) { report('probe_direct_err', {d: String(e)}); }\r\n"
    b"      }"
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
