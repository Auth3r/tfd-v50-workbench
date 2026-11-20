"""开工自检：跑一遍就知道这台机器能不能开。

用法：python -B selfcheck.py
退出码：0 = 全绿，可以启动；1 = 有 FAIL，先修再开。

设计原则：只读、零副作用。不启动任何东西，只检查。
"""
import hashlib
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402

FAIL, WARN, OK = 'FAIL', 'WARN', 'OK'
_rows = []


def rec(level, item, detail):
    _rows.append((level, item, detail))


def sha256_of(p, limit=400 * 1024 * 1024):
    if p.stat().st_size > limit:
        return None
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def procs(names):
    """返回正在运行的进程名集合（小写）。"""
    try:
        out = subprocess.run(['tasklist', '/FO', 'CSV', '/NH'],
                             capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return set()
    hit = set()
    for line in out.splitlines():
        if not line.strip():
            continue
        name = line.split('"')[1] if line.startswith('"') else line.split(',')[0]
        if name.lower() in names:
            hit.add(name.lower())
    return hit


def count_characters(sqlite_path):
    """返回 characters 表行数；读不到返回 None。只读打开。"""
    if not sqlite_path.is_file():
        return None
    try:
        uri = 'file:%s?mode=ro' % sqlite_path.as_posix()
        con = sqlite3.connect(uri, uri=True)
        try:
            cur = con.cursor()
            cur.execute("select name from sqlite_master where type='table'")
            tables = [r[0] for r in cur.fetchall()]
            for t in ('characters', 'character', 'Character'):
                if t in tables:
                    cur.execute('select count(*) from "%s"' % t)
                    return cur.fetchone()[0]
            return None
        finally:
            con.close()
    except Exception:
        return None


def check_python():
    v = sys.version_info
    if v < (3, 7):
        rec(FAIL, 'Python 版本', '需要 3.7+，当前 %s' % sys.version.split()[0])
    elif sys.maxsize <= 2 ** 32:
        rec(FAIL, 'Python 位数', '需要 64 位（32 位加载不了 frida）')
    else:
        rec(OK, 'Python', '%s / %d 位 / %s' % (sys.version.split()[0],
                                              64 if sys.maxsize > 2 ** 32 else 32,
                                              sys.executable))


def check_config():
    if paths.CFG_SOURCE == 'config.local.json':
        rec(OK, '配置文件', 'config.local.json 已存在')
    elif paths.CFG_SOURCE == 'config.example.json':
        rec(WARN, '配置文件', '还没建 config.local.json，现在用的是模板默认值')
    else:
        rec(WARN, '配置文件', '没找到配置文件，全部走默认值')


def check_client():
    if not paths.CLIENT or not Path(paths.CLIENT).is_file():
        rec(FAIL, '客户端 exe', '没找到。填 config.local.json 的 paths.client_exe，'
                                '或跑 “启动V50（免授权）.cmd --pick-client”')
        return
    p = Path(paths.CLIENT)
    size = p.stat().st_size
    got = sha256_of(p)
    if got is None:
        rec(WARN, '客户端 exe', '文件过大，跳过哈希校验：%s' % p)
        return
    if not paths.CLIENT_SHA:
        rec(WARN, '客户端 exe', '没有期望哈希可比对：%s' % p)
    elif got == paths.CLIENT_SHA:
        rec(OK, '客户端 exe', 'build %s 校验通过（%.0f MB）' % (paths.CLIENT_BUILD, size / 1048576))
    else:
        rec(FAIL, '客户端 exe',
            '哈希不符，这份不是 build %s（期望 %s… 实际 %s…）。\n'
            '        差版本会「能启动、然后黑屏或闪退」，先换客户端再排查别的。\n'
            '        %s' % (paths.CLIENT_BUILD, paths.CLIENT_SHA[:12], got[:12], p))


def check_launcher():
    if paths.LAUNCHER.is_file():
        rec(OK, '启动器', '%s（%.0f MB）' % (paths.LAUNCHER.name, paths.LAUNCHER.stat().st_size / 1048576))
    else:
        rec(FAIL, '启动器', '缺 %s' % paths.LAUNCHER)


def check_injector():
    needed = ['inject_v50.py', 'patch_v50.py', 'kill_notice.py']
    missing = [n for n in needed if not (paths.HERE / n).is_file()]
    if missing:
        rec(FAIL, '注入链', '缺文件：%s' % '、'.join(missing))
    else:
        rec(OK, '注入链', 'inject_v50.py / patch_v50.py / kill_notice.py 齐')


def check_bridge():
    b = Path(paths.BRIDGE)
    if b.is_file():
        rec(OK, '桥脚本', '%s（%.0f KB）' % (b.name, b.stat().st_size / 1024))
    else:
        alt = paths.HERE / 'old_bridge_full.js'
        if alt.is_file():
            rec(WARN, '桥脚本', '配置指向的 %s 不在，但有 old_bridge_full.js 可用' % b.name)
        else:
            rec(FAIL, '桥脚本', '缺 %s 和 old_bridge_full.js' % b.name)


def check_frida():
    cands = []
    if paths.VENDOR:
        cands.append(Path(paths.VENDOR))
    cands.append(paths.HERE / 'vendor')
    for root in [paths.HERE, *list(paths.HERE.parents)[:3]]:
        cands.append(root / '.tfd-patch')
        try:
            for d in root.iterdir():
                if (d / '.tfd-patch').is_dir():
                    cands.append(d / '.tfd-patch')
        except Exception:
            pass
    for patch_dir in [c for c in cands if c.is_dir() and c.name == '.tfd-patch']:
        try:
            cands += sorted(patch_dir.glob('releases/*/vendor'))
        except Exception:
            pass

    found = None
    for c in cands:
        if (c / 'frida' / '__init__.py').is_file():
            found = c
            break
    if not found:
        rec(FAIL, 'frida', '没找到 frida 包。放到 vendor\\ 下，或设置 TFD_VENDOR 指向它')
        return
    sys.path.insert(0, str(found))
    try:
        import frida  # noqa: F401
        rec(OK, 'frida', '%s（%s）' % (frida.__version__, found))
    except Exception as e:
        rec(FAIL, 'frida', '找到包但导入失败：%s（%s）' % (e, found))


def check_processes():
    busy = procs({'tfdlauncher.exe', 'm1-win64-shipping.exe'})
    if busy:
        rec(FAIL, '残端进程', '正在运行：%s\n'
                              '        先关掉再开，否则会双开、抢端口、黑屏。' % '、'.join(sorted(busy)))
    else:
        rec(OK, '残端进程', '干净')


def check_lock():
    lock = paths.HERE / 'launcher.lock'
    if lock.is_file():
        rec(WARN, '锁文件', 'launcher.lock 残留，启动前删掉：%s' % lock)
    else:
        rec(OK, '锁文件', '无残留')


def check_save():
    if not paths.SAVE.is_dir():
        rec(WARN, '存档目录', '还不存在：%s\n'
                              '        首次启动会自动建，之后是空档（会走创角）' % paths.SAVE)
        return
    subs = [d for d in paths.SAVE.iterdir() if d.is_dir()]
    if not subs:
        rec(WARN, '存档目录', '空目录，首次启动会走创角分支')
        return
    latest = max(subs, key=lambda d: (d / 'characters.sqlite3').stat().st_mtime
                 if (d / 'characters.sqlite3').is_file() else 0)
    n = count_characters(latest / 'characters.sqlite3')
    if n is None:
        rec(WARN, '存档', '%s 里没有可读的角色表' % latest.name)
    elif n == 0:
        rec(WARN, '存档', '%s：0 个角色（空档）' % latest.name[:12])
    else:
        rec(OK, '存档', '%s：%d 个角色' % (latest.name[:12], n))


def check_workdir():
    try:
        paths.WORK.mkdir(parents=True, exist_ok=True)
        probe = paths.WORK / '.write-probe'
        probe.write_text('ok', encoding='utf-8')
        probe.unlink()
        rec(OK, '输出目录', str(paths.WORK))
    except Exception as e:
        rec(FAIL, '输出目录', '不可写：%s（%s）' % (paths.WORK, e))


def main():
    print('=' * 72)
    print('TFD V50 离线工作台 · 开工自检')
    print('=' * 72)
    check_python()
    check_config()
    check_client()
    check_launcher()
    check_injector()
    check_bridge()
    check_frida()
    check_processes()
    check_lock()
    check_save()
    check_workdir()

    for level, item, detail in _rows:
        print('[%s] %-10s %s' % (level, item, detail))
    bad = sum(1 for r in _rows if r[0] == FAIL)
    warn = sum(1 for r in _rows if r[0] == WARN)
    print('-' * 72)
    print('结果：%d OK / %d WARN / %d FAIL' % (len(_rows) - bad - warn, warn, bad))
    if bad:
        print('有 FAIL，先按上面的提示修，再启动。')
        return 1
    if warn:
        print('能启动，但有 WARN 项，自己确认一下是否符合预期。')
    else:
        print('全绿。可以跑 “启动V50（免授权）.cmd” 了。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
