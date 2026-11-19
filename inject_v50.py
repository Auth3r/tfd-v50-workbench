"""注入器：
1) 一发现 V50 启动器进程就注入「关弹窗」线程
2) 稍等再注入免授权主补丁

不写死任何绝对路径：
- frida(vendor)：优先环境变量 TFD_VENDOR，其次本目录 vendor\，其次统一补丁 .tfd-patch，
  最后扫附近目录里带 frida 包的文件夹。
- 客户端 exe：优先 TFD_CLIENT，其次 .tfd-patch\active.json 的 client，其次扫附近的
  M1\\Binaries\\Win64\\M1-Win64-Shipping.exe。
"""
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
FALLBACK_VENDOR = Path(r'E:\The First Descendant\The First Descendant\TFD-Offline\.tfd-patch'
                       r'\releases\1.0.7-c2cafd1f3ee39906\vendor')
FALLBACK_CLIENT = Path(r'E:\The First Descendant\The First Descendant\客户端'
                       r'\The First Descendant.part01\The First Descendant'
                       r'\M1\Binaries\Win64\M1-Win64-Shipping.exe')

CLIENT_GLOBS = ('M1/Binaries/Win64/M1-Win64-Shipping.exe',
                '*/M1/Binaries/Win64/M1-Win64-Shipping.exe',
                '*/*/M1/Binaries/Win64/M1-Win64-Shipping.exe')


def _roots():
    return [HERE, *list(HERE.parents)[:3]]


def _has_frida(path):
    return (path / 'frida' / '__init__.py').is_file()


def find_patch_dirs():
    """返回 [(active.json 的 mtime, .tfd-patch 目录, active.json 内容)]，按最近使用排序。"""
    out = []
    for root in _roots():
        if not root.is_dir():
            continue
        dirs = [root / '.tfd-patch']
        try:
            dirs += [d / '.tfd-patch' for d in root.iterdir()
                     if d.is_dir() and (d / '.tfd-patch').is_dir()]
        except Exception:
            pass
        for patch_dir in dirs:
            if not patch_dir.is_dir():
                continue
            stamp = patch_dir / 'active.json'
            mtime = stamp.stat().st_mtime if stamp.exists() else 0
            try:
                active = json.loads(stamp.read_text(encoding='utf-8'))
            except Exception:
                active = {}
            out.append((mtime, patch_dir, active))
    out.sort(key=lambda t: t[0], reverse=True)
    return out


def find_vendor():
    env = os.environ.get('TFD_VENDOR', '').strip().strip('"')
    if env and _has_frida(Path(env)):
        return Path(env)

    # 1) 本目录自带的 vendor
    if _has_frida(HERE / 'vendor'):
        return HERE / 'vendor'

    # 2) 统一补丁 .tfd-patch 里的 vendor
    for _, patch_dir, active in find_patch_dirs():
        cands = []
        rel = active.get('release')
        if rel:
            cands.append(patch_dir / rel / 'vendor')
        try:
            cands.extend(sorted(patch_dir.glob('releases/*/vendor')))
        except Exception:
            pass
        for cand in cands:
            if _has_frida(cand):
                return cand

    # 3) 附近含 frida 包的目录（本目录 / 上级 / 同级子目录）
    for root in _roots():
        if not root.is_dir():
            continue
        if _has_frida(root):
            return root
        try:
            subs = list(root.iterdir())
        except Exception:
            subs = []
        for sub in subs:
            if sub.is_dir() and _has_frida(sub):
                return sub
    return FALLBACK_VENDOR


def find_client():
    env = os.environ.get('TFD_CLIENT', '').strip().strip('"')
    if env and Path(env).is_file():
        return Path(env)

    # 用户选过的那份（脚本同目录 client.txt）
    saved = HERE / 'client.txt'
    if saved.is_file():
        try:
            p = Path(saved.read_text(encoding='utf-8').strip().strip('"'))
        except Exception:
            p = None
        if p and p.is_file():
            return p

    for _, _, active in find_patch_dirs():
        client = active.get('client')
        if client and Path(client).is_file():
            return Path(client)

    for root in _roots():
        for pat in CLIENT_GLOBS:
            try:
                hits = sorted(root.glob(pat))
            except Exception:
                hits = []
            for p in hits:
                if p.is_file():
                    return p
    return FALLBACK_CLIENT


VENDOR = find_vendor()
CLIENT = find_client()
sys.path.insert(0, str(VENDOR))
try:
    import frida  # noqa: E402
except ImportError:
    sys.exit('找不到 frida（vendor 没定位对）：%s\n'
             '把 frida 包放到本目录 vendor\\ 下，或设置 TFD_VENDOR 指向它。' % VENDOR)

PROBE_JS = "rpc.exports.has=function(){return Process.findModuleByName('python314.dll')!==null;};"

JS = r"""
const mod = Process.findModuleByName('python314.dll');
const f_ensure = new NativeFunction(mod.getExportByName('PyGILState_Ensure'), 'pointer', []);
const f_release = new NativeFunction(mod.getExportByName('PyGILState_Release'), 'void', ['pointer']);
const f_run = new NativeFunction(mod.getExportByName('PyRun_SimpleString'), 'int', ['pointer']);
rpc.exports.run = function (code) {
    const st = f_ensure();
    let rc = -999;
    try { rc = f_run(Memory.allocUtf8String(code)); } finally { f_release(st); }
    return rc;
};
"""


def candidates(dev):
    return [p for p in dev.enumerate_processes() if p.name.casefold() == 'tfdlauncher.exe']


def attach_python(dev, skip=()):
    for pr in candidates(dev):
        if pr.pid in skip:
            continue
        s = None
        try:
            s = dev.attach(pr.pid)
            probe = s.create_script(PROBE_JS)
            probe.load()
            ok = probe.exports_sync.has()
            probe.unload()
            if not ok:
                s.detach()
                continue
            sc = s.create_script(JS)
            sc.load()
            return pr.pid, sc
        except Exception:
            try:
                if s:
                    s.detach()
            except Exception:
                pass
    return None, None


def main():
    killer_src = (HERE / 'kill_notice.py')
    patch_src = (HERE / 'patch_v50.py')
    if not killer_src.exists():
        print('缺少 kill_notice.py')
        return 2

    print('vendor: %s' % VENDOR)
    print('client: %s' % CLIENT)

    dev = frida.get_local_device()

    # 阶段1：等进程并注入关弹窗
    deadline = time.time() + 90
    pid = sc = None
    while time.time() < deadline and sc is None:
        pid, sc = attach_python(dev)
        if sc is None:
            time.sleep(0.6)
    if sc is None:
        print('没有找到 V50 启动器进程（请先运行 TFDLauncher.exe）')
        return 1
    print('发现 pid %s，注入关弹窗…' % pid)
    try:
        sc.exports_sync.run("import sys\n" + killer_src.read_text(encoding='utf-8'))
        print('关弹窗线程已注入')
    except Exception as e:
        print('关弹窗注入失败:', e)

    # 阶段2：主补丁
    if not patch_src.exists():
        print('缺少 patch_v50.py')
        return 2
    time.sleep(6)
    pid2, sc2 = attach_python(dev)
    if sc2 is None:
        print('主补丁注入失败：找不到可用进程')
        return 1
    print('注入主补丁到 pid %s …' % pid2)
    # 把定位好的路径塞进目标进程的环境变量，patch_v50 直接读
    prelude = ('import os\n'
               'os.environ["TFD_HOME"] = %r\n'
               'os.environ["TFD_CLIENT"] = %r\n'
               'os.environ["TFD_VENDOR"] = %r\n'
               % (str(HERE), str(CLIENT), str(VENDOR)))
    try:
        sc2.exports_sync.run(prelude + "import sys\n" + patch_src.read_text(encoding='utf-8'))
        print('主补丁已注入，日志:', HERE / 'patch_v50.log')
    except Exception as e:
        print('主补丁注入失败:', e)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
