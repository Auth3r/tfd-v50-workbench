"""脱壳式修改：spawn 启动器 → 挂 LoadLibraryW → client.dll 一加载就改内存 → resume。
要改的内容写在 PATCHES 里（明文替换，等长）。
"""
import sys
import time
from pathlib import Path

HERE = Path(r'E:\The First Descendant\TFD发布端V50')
VENDOR = Path(r'E:\The First Descendant\The First Descendant\TFD-Offline\.tfd-patch'
              r'\releases\1.0.7-c2cafd1f3ee39906\vendor')
sys.path.insert(0, str(VENDOR))
import frida  # noqa: E402

EXE = str(HERE / 'TFDLauncher.exe')
LOG = HERE / 'unpack_patch.log'

# 明文替换表：原名 -> 新名（必须等长）
PATCHES = [
    ('1131987001', '0000000000'),
]

JS = r"""
const patches = %PATCHES%;

function toHex(s) {
    let out = '';
    for (let i = 0; i < s.length; i++) out += s.charCodeAt(i).toString(16).padStart(2, '0') + ' ';
    return out.trim();
}

const k32 = Process.getModuleByName('kernel32.dll');
['LoadLibraryW', 'LoadLibraryExW', 'LoadLibraryA'].forEach(function (name) {
    let addr = null;
    try { addr = k32.findExportByName(name); } catch (e) {}
    if (!addr) return;
    Interceptor.attach(addr, {
        onLeave(retval) {
            if (retval.isNull()) return;
            try {
                const h = retval;
                const e_lfanew = h.add(0x3c).readU32();
                if (h.add(e_lfanew).readU32() !== 0x00004550) return;
                const sizeOfImage = h.add(e_lfanew + 24 + 56).readU32();
                if (sizeOfImage < 0x1000 || sizeOfImage > 0x8000000) return;
                for (let k = 0; k < patches.length; k++) {
                    const from = patches[k][0], to = patches[k][1];
                    const pat = toHex(from);
                    let n = 0;
                    Memory.scanSync(h, sizeOfImage, pat, {
                        onMatch(a) {
                            a.writeByteArray(Array.from(new Uint8Array(
                                to.split('').map(c => c.charCodeAt(0)))));
                            n++;
                        }
                    });
                    if (n > 0) send({ patched: from, count: n, size: sizeOfImage });
                }
            } catch (e) {
                send({ err: String(e) });
            }
        }
    });
});
send({ ready: true });
""" .replace('%PATCHES%',
              '[' + ','.join('["%s","%s"]' % (a, b) for a, b in PATCHES) + ']')


def log(msg):
    try:
        with open(LOG, 'a', encoding='utf-8') as fh:
            fh.write('%s %s\n' % (time.strftime('%H:%M:%S'), msg))
    except Exception:
        pass


def main():
    with open(LOG, 'w', encoding='utf-8') as fh:
        fh.write('=== unpack patch ===\n')

    dev = frida.get_local_device()
    pid = dev.spawn([EXE], cwd=str(HERE))
    log('spawned pid=%s' % pid)

    session = dev.attach(pid)
    script = session.create_script(JS)
    script.on('message', lambda m, d: log('MSG %r' % (m.get('payload'),)))
    script.load()
    log('hook installed')

    dev.resume(pid)
    log('resumed')
    time.sleep(3)
    log('done (app continues)')


if __name__ == '__main__':
    main()
