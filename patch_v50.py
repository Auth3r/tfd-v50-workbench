"""在 V50 启动器进程内执行：绕过授权 + 用完整旧桥 + 让 V50 自己起服务并拉起旧客户端。

由 V50免授权启动.py 注入执行，不要直接运行。
"""
import asyncio
import gc
import hashlib
import inspect
import json
import os
import re
import sys
import threading
import time
import traceback
from pathlib import Path

CLIENT_GLOBS = ('M1/Binaries/Win64/M1-Win64-Shipping.exe',
                '*/M1/Binaries/Win64/M1-Win64-Shipping.exe',
                '*/*/M1/Binaries/Win64/M1-Win64-Shipping.exe')


def _env_path(name):
    v = os.environ.get(name, '').strip().strip('"')
    return Path(v) if v else None


# 启动器目录：优先用注入器传进来的 TFD_HOME，否则用本文件所在目录
_home = _env_path('TFD_HOME')
if _home and _home.is_dir():
    HERE = _home
elif '__file__' in globals():
    HERE = Path(__file__).resolve().parent
else:
    HERE = Path.cwd()

LOG = HERE / 'patch_v50.log'
FULL_BRIDGE = HERE / 'old_bridge_full.js'


def _patch_dirs():
    """找附近的 .tfd-patch 目录（含一级子目录里的）。"""
    out = []
    for root in [HERE, *list(HERE.parents)[:3]]:
        if not root.is_dir():
            continue
        dirs = [root / '.tfd-patch']
        try:
            dirs += [d / '.tfd-patch' for d in root.iterdir()
                     if d.is_dir() and (d / '.tfd-patch').is_dir()]
        except Exception:
            pass
        out += [d for d in dirs if d.is_dir()]
    return out


def _find_client():
    """客户端 exe：TFD_CLIENT > client.txt > active.json 的 client > 扫附近 > 老路径兜底。"""
    env = _env_path('TFD_CLIENT')
    if env and env.is_file():
        return env
    saved = HERE / 'client.txt'
    if saved.is_file():
        try:
            p = Path(saved.read_text(encoding='utf-8').strip().strip('"'))
        except Exception:
            p = None
        if p and p.is_file():
            return p
    for patch_dir in _patch_dirs():
        try:
            client = json.loads((patch_dir / 'active.json')
                                .read_text(encoding='utf-8')).get('client')
        except Exception:
            continue
        if client and Path(client).is_file():
            return Path(client)
    for root in [HERE, *list(HERE.parents)[:3]]:
        for pat in CLIENT_GLOBS:
            try:
                hits = sorted(root.glob(pat))
            except Exception:
                hits = []
            for p in hits:
                if p.is_file():
                    return p
    return Path(r'E:\The First Descendant\The First Descendant\客户端'
                r'\The First Descendant.part01\The First Descendant'
                r'\M1\Binaries\Win64\M1-Win64-Shipping.exe')


OLD_EXE = _find_client()


def w(*a):
    try:
        with open(LOG, 'a', encoding='utf-8') as fh:
            print(time.strftime('%H:%M:%S'), *a, file=fh)
    except Exception:
        pass


def kill_notice():
    """禁用「同步更新版本 / 加群」弹窗，并关掉已经弹出的那个。"""
    import ctypes
    from ctypes import wintypes

    try:
        import launcher_branding as LB
        LB.show_release_notice = lambda *a, **k: None
        w('弹窗函数已禁用')
    except Exception as e:
        w('禁用弹窗失败: %r' % (e,))
    try:
        import launcher as L
        if getattr(L, 'show_release_notice', None) is not None:
            L.show_release_notice = lambda *a, **k: None
    except Exception:
        pass

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    pid_me = kernel32.GetCurrentProcessId()
    hits = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, lp):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == pid_me and user32.IsWindowVisible(hwnd):
            t = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, t, 256)
            if any(k in t.value for k in ('更新', '加群', '版本')):
                hits.append((hwnd, t.value))
        return True

    for _ in range(30):
        hits.clear()
        user32.EnumWindows(cb, 0)
        for hwnd, title in hits:
            user32.PostMessageW(hwnd, 0x0010, 0, 0)   # WM_CLOSE
            w('已关闭弹窗: %r' % title)
        if not hits:
            break
        time.sleep(0.3)


_STD_KEEP = []


def _patch_popen(SP):
    """这个窗口进程的 std 句柄是无效值(0xFFFFFFFFFFFFFFFF)，subprocess 只要有一个流
    是 None 就会 DuplicateHandle 它 → WinError 6(句柄无效)。这里把三个流全部显式化：
    None 一律换成 DEVNULL；实测三者都指定时管道工作正常。"""
    if getattr(SP.Popen, '_dsh_patched', False):
        return
    orig_init = SP.Popen.__init__

    def popen_init(self, args, *a, **k):
        for name in ('stdin', 'stdout', 'stderr'):
            if k.get(name, None) is None:
                k[name] = SP.DEVNULL
        # 让游戏自己写 UE 日志，便于排查闪退原因
        try:
            if isinstance(args, (list, tuple)) and args:
                first = str(args[0])
                if 'M1-Win64-Shipping' in first and '-log' not in args:
                    args = list(args) + ['-log']
                    w('客户端已加 -log: %r' % (first,))
        except Exception:
            pass
        try:
            return orig_init(self, args, *a, **k)
        except OSError as e:
            if getattr(e, 'winerror', None) != 6:
                raise
            w('Popen 仍句柄无效，全改 DEVNULL 重试: %r' % (args,))
            for name in ('stdin', 'stdout', 'stderr'):
                k[name] = SP.DEVNULL
            return orig_init(self, args, *a, **k)

    popen_init._dsh_patched = True
    SP.Popen.__init__ = popen_init
    w('Popen 已接管（std 流全部显式化）')


def _quarantine_vaults(LL, home):
    """把本机 DPAPI 解不开的凭据文件挪开（改名 .vendor.bak），让启动器重新生成本机的。
    覆盖 home 及 data 下所有 licensing 目录（不同模块读的位置不一样）。"""
    moved = []
    seen = set()
    for base in (home, home / 'data'):
        if not base.is_dir():
            continue
        try:
            files = list(base.rglob('*.dpapi'))
        except Exception:
            files = []
        for p in files:
            if p in seen or not p.is_file():
                continue
            seen.add(p)
            try:
                LL.protect(p.read_bytes(), decrypt=True)   # 本机能解开 -> 保留
                continue
            except Exception:
                pass
            target = p.with_name(p.name + '.vendor.bak')
            try:
                if target.exists():
                    target.unlink()
                p.rename(target)
                moved.append(str(p))
            except Exception as e:
                w('挪走失败 %s: %r' % (p, e))
    return moved


def _make_client(LL, home, data_dir):
    """构造 LicenseClient；设备凭据读不了就先挪走旧凭据，再重试一次。"""
    try:
        return LL.LicenseClient(home, data_dir)
    except Exception as first:
        w('设备凭据读取失败: %r' % (first,))
        moved = _quarantine_vaults(LL, home)
        w('已挪走旧凭据: %r' % (moved,))
        try:
            return LL.LicenseClient(home, data_dir)
        except Exception:
            try:
                import device_identity as DI
                w('device_identity 属性: %r' % [n for n in dir(DI) if not n.startswith('_')])
                for name in ('VAULT', 'VAULT_PATH', 'DIR', 'PATH', 'ROOT', 'DATA', 'FILENAME'):
                    if hasattr(DI, name):
                        w('  %s = %r' % (name, getattr(DI, name)))
            except Exception:
                pass
            raise


def _trace_store(LS):
    """把 LS.Store 上跟角色/账号/会话相关的方法全部包一层日志，抓服务端真实读了哪个
    account_uid、返回几个角色。开关：环境变量 TFD_TRACE_STORE=1（默认开）。"""
    if os.environ.get('TFD_TRACE_STORE', '1') not in ('1', 'true', 'yes'):
        return
    keys = ('character', 'account', 'session', 'payload', 'profile', 'snapshot',
            'login', 'ticket', 'mastery', 'currency')

    def wrap(obj, name, label):
        try:
            orig = getattr(obj, name)
        except Exception:
            return
        if not callable(orig) or getattr(orig, '_tfd_traced', False):
            return

        def f(*a, **k):
            try:
                res = orig(*a, **k)
            except Exception as e:
                w('TRACE %s%r -> EXC %r' % (label, a[1:], e))
                raise
            try:
                s = repr(res)
            except Exception:
                s = '<unrepr>'
            if isinstance(res, dict):
                try:
                    shape = {}
                    for kk, vv in res.items():
                        if isinstance(vv, (list, tuple)):
                            shape[kk] = 'list[%d]' % len(vv)
                        elif isinstance(vv, dict):
                            shape[kk] = 'dict{%d}' % len(vv)
                        else:
                            shape[kk] = type(vv).__name__
                    s = 'SHAPE ' + repr(shape) + ' | ' + s
                except Exception:
                    pass
            w('TRACE %s%r -> %s' % (label, a[1:], s[:3000]))
            return res

        f._tfd_traced = True
        try:
            setattr(obj, name, f)
        except Exception:
            pass

    try:
        for name in dir(LS.Store):
            if not name.startswith('__') and any(k in name for k in keys):
                wrap(LS.Store, name, 'Store.' + name)
        for name in dir(LS):
            if name.startswith('_'):
                continue
            if not any(k in name for k in keys):
                continue
            obj = getattr(LS, name, None)
            if callable(obj):
                wrap(LS, name, 'LS.' + name)
        mods = [m for m in sys.modules
                if any(k in m.lower() for k in ('login', 'service', 'protocol',
                                                'account', 'session', 'profile'))]
        w('相关模块: %r' % (mods,))
        w('Store 跟踪已挂')
    except Exception as e:
        w('Store 跟踪失败 %r' % (e,))


def _find_schema():
    """全模块扫描：谁的手里含有 'M1AccountSimpleInfo' 这段定义（dict/list/str/函数常量）。
    用来定位真正的报文编码表。开关：TFD_FIND_SCHEMA=1。"""
    if os.environ.get('TFD_FIND_SCHEMA', '') not in ('1', 'true', 'yes'):
        return
    needle = 'M1AccountSimpleInfo'
    seen = 0
    for modname, mod in list(sys.modules.items()):
        d = getattr(mod, '__dict__', None)
        if not isinstance(d, dict):
            continue
        for n, v in list(d.items()):
            try:
                if isinstance(v, str) and needle in v:
                    w('FIND %s.%s str len=%d head=%r' % (modname, n, len(v), v[:400]))
                    seen += 1
                elif isinstance(v, (dict, list, tuple, set)):
                    r = repr(v)
                    if needle in r:
                        w('FIND %s.%s %s len=%d -> %s'
                          % (modname, n, type(v).__name__, len(v), r[:1200]))
                        seen += 1
                elif callable(v):
                    c = getattr(v, '__code__', None)
                    if c is not None and any(isinstance(k, str) and needle in k
                                            for k in c.co_consts):
                        w('FIND fn %s.%s consts=%r' % (modname, n, list(c.co_consts)[:25]))
                        seen += 1
            except Exception:
                continue
    w('FIND 完成 hits=%d' % (seen,))


def _dump_proto_def():
    """把 content_protocol.PROTOCOL 里账号/角色/认证相关的编码器定义掏出来：
    名字、闭包、code consts，从而知道字段顺序与整型宽度。开关：TFD_DUMP_PROTO=1。"""
    if os.environ.get('TFD_DUMP_PROTO', '') not in ('1', 'true', 'yes'):
        return
    try:
        import content_protocol as CP
    except Exception as e:
        w('PROTO 导入失败 %r' % (e,))
        return
    P = getattr(CP, 'PROTOCOL', None)
    if P is None:
        w('PROTO 无 PROTOCOL')
        return
    try:
        w('PROTO type=%r' % (type(P),))
        if isinstance(P, dict):
            keys = list(P.keys())
        else:
            keys = [n for n in dir(P) if not n.startswith('_')]
        w('PROTO keys(%d)=%r' % (len(keys), keys[:160]))
    except Exception as e:
        w('PROTO 枚举失败 %r' % (e,))
        return
    for k in keys:
        name = k if isinstance(k, str) else str(k)
        if not any(t in name for t in ('Account', 'Character', 'Auth', 'Wearing')):
            continue
        try:
            v = P[k] if isinstance(P, dict) else getattr(P, k, None)
        except Exception:
            continue
        w('PROTO %s -> %r' % (name, v))
        code = getattr(v, '__code__', None)
        if code is not None:
            w('PROTO %s consts=%r' % (name, list(code.co_consts)[:40]))
            w('PROTO %s names=%r' % (name, list(code.co_names)[:40]))
        cl = getattr(v, '__closure__', None)
        if cl:
            for i, c in enumerate(cl):
                try:
                    cv = c.cell_contents
                except Exception:
                    cv = '<empty>'
                w('PROTO %s closure[%d]=%r' % (name, i, cv))


def _dump_schema():
    """把协议层里跟账号/角色相关的 schema 定义整段打出来（字段名 + 类型），
    用来对比客户端期望的类型宽度。开关：TFD_DUMP_SCHEMA=1。"""
    if os.environ.get('TFD_DUMP_SCHEMA', '') not in ('1', 'true', 'yes'):
        return
    try:
        import protocol
        import content_protocol
    except Exception as e:
        w('SCHEMA 导入失败 %r' % (e,))
        return
    for mod in (protocol, content_protocol):
        try:
            attrs = [n for n in dir(mod) if not n.startswith('_')]
            w('SCHEMA %s attrs=%r' % (mod.__name__, attrs[:100]))
        except Exception:
            attrs = []
        for n in attrs:
            o = getattr(mod, n, None)
            try:
                r = repr(o)
            except Exception:
                continue
            if ('M1AccountSimpleInfo' in r or 'CharacterList' in r
                    or 'M1CharacterSimpleInfo' in r):
                w('SCHEMA %s.%s = %s' % (mod.__name__, n, r[:2000]))


def _probe_wire():
    """抓启动器实际写出去的字节：包一层 asyncio.StreamWriter.write。
    开关：TFD_PROBE_WIRE=1。"""
    if os.environ.get('TFD_PROBE_WIRE', '') not in ('1', 'true', 'yes'):
        return
    try:
        import asyncio.streams as _st
    except Exception as e:
        w('WIRE 导入失败 %r' % (e,))
        return
    orig_write = _st.StreamWriter.write
    if getattr(orig_write, '_tfd_wrapped', False):
        return

    def write(self, data):
        try:
            b = bytes(data)
            w('WIRE out len=%d hex=%s' % (len(b), b[:220].hex()))
        except Exception:
            pass
        return orig_write(self, data)

    write._tfd_wrapped = True
    _st.StreamWriter.write = write
    w('WIRE 已挂 StreamWriter.write')

    orig_drain = _st.StreamWriter.drain

    def drain(self):
        return orig_drain(self)

    _st.StreamWriter.drain = drain


def _probe_handlers():
    """把 login_server 里像"处理请求/派发"的函数包一层，打印 procedure 与返回值。
    开关：TFD_PROBE_HANDLERS=1。"""
    if os.environ.get('TFD_PROBE_HANDLERS', '') not in ('1', 'true', 'yes'):
        return
    try:
        import login_server as _ls
    except Exception as e:
        w('HANDLERS 导入失败 %r' % (e,))
        return
    keys = ('handle', 'dispatch', 'request', 'proc', 'serve', 'create', 'character', 'rpc')
    try:
        attrs = [n for n in dir(_ls) if not n.startswith('__')]
        w('HANDLERS attrs=%r' % (attrs[:120],))
    except Exception:
        pass
    for mod_name in ('login_server', 'launcher_accounts'):
        try:
            mod = __import__(mod_name)
        except Exception:
            continue
        try:
            mod_attrs = [n for n in dir(mod) if not n.startswith('__')]
            w('HANDLERS %s attrs=%r' % (mod_name, mod_attrs[:120]))
        except Exception:
            continue
        for n in mod_attrs:
            v = getattr(mod, n, None)
            if isinstance(v, dict):
                try:
                    ks = list(v.keys())
                    w('HANDLERS %s.%s keys(%d)=%r' % (mod_name, n, len(ks), ks[:40]))
                except Exception:
                    pass
    for n in ('GAME_ACCOUNT_REQUEST', 'LOGIN_REQUEST', 'CLIENT_LOGIN',
              'ACCOUNT_SIMPLE', 'PRIVATE_WORLD_RESPONSE', 'HANDSHAKE',
              'TITLE_INVENTORY', 'INVENTORY_SLOT_REQUEST', 'INVENTORY_SLOTS',
              'JOIN_DEDICATED', 'JOIN_DEDICATED_RESULT', 'OPTION_PRESET',
              'BOOST_EFFECTS', 'JUNK_ITEM_FILTER', 'JUNK_ANCESTOR_FILTER', 'DEDI_OID'):
        try:
            v = getattr(_ls, n, None)
            w('HANDLERSX %s type=%s repr=%r' % (n, type(v).__name__, repr(v)[:700]))
        except Exception as e:
            w('HANDLERSX %s ERR %r' % (n, e))
    for name in dir(_ls):
        if name.startswith('__'):
            continue
        obj = getattr(_ls, name, None)
        if isinstance(obj, dict):
            try:
                ks = list(obj.keys())[:20]
                w('HANDLERS dict %s keys=%r' % (name, ks))
            except Exception:
                pass
            continue
        if not callable(obj):
            continue
        if not any(k in name.lower() for k in keys):
            continue
        orig = obj
        if getattr(orig, '_tfd_wrapped', False):
            continue

        def make(orig, label):
            def f(*a, **k):
                try:
                    res = orig(*a, **k)
                except Exception as e:
                    w('HANDLERS %s EXC %r' % (label, e))
                    raise
                try:
                    r = repr(res)
                except Exception:
                    r = '<unrepr>'
                w('HANDLERS %s(%r) -> %s' % (label, a[1:3], r[:900]))
                return res
            f._tfd_wrapped = True
            return f

        try:
            setattr(_ls, name, make(orig, name))
        except Exception:
            pass


def _compat_int64(LS):
    """新版(build 26722146)账号结构里 CreatedTime 等字段是 64 位整数。
    若编码器按数值大小决定整型宽度，值为 0 会写成短整型，导致后续字节流整体错位
    （WearingList 之后全被读成 0，CharacterList 直接空）。
    这里把这些字段撑到 >2^32，强制写满 64 位，验证/修复错位。
    开关：TFD_FORCE_INT64（逗号分隔字段名）；旧客户端自动跳过。"""
    force = os.environ.get('TFD_FORCE_INT64', '').strip()
    if not force:
        return
    if str(globals().get('_TFD_CLIENT_SHA', '')).lower().startswith('c0147688'):
        w('INT64 补丁跳过（旧客户端）')
        return
    keys = [x.strip() for x in force.split(',') if x.strip()]
    orig = getattr(LS, 'account_snapshot', None)
    if not callable(orig):
        w('INT64: account_snapshot 不存在')
        return

    def f(*a, **k):
        res = orig(*a, **k)
        try:
            big = 1 << 40
            changed = []
            for kk in keys:
                if kk in res and isinstance(res[kk], int):
                    res[kk] = big
                    changed.append(kk)
            w('INT64 撑大 %r' % (changed,))
        except Exception as e:
            w('INT64 失败 %r' % (e,))
        return res

    f._tfd_traced = True
    try:
        setattr(LS, 'account_snapshot', f)
        w('INT64 已挂 %r' % (keys,))
    except Exception as e:
        w('INT64 挂载失败 %r' % (e,))


def _trim_topfields(LS):
    """实验钩子：按 TFD_DROP_TOPFIELD 从 account_snapshot 结果里删掉顶层字段，
    用来验证"某个字段类型/长度变了导致后续字节流错位"的假设。"""
    drop = os.environ.get('TFD_DROP_TOPFIELD', '').strip()
    if not drop:
        return
    drop_set = set(x.strip() for x in drop.split(',') if x.strip())
    orig = getattr(LS, 'account_snapshot', None)
    if not callable(orig):
        w('DROP: account_snapshot 不存在')
        return

    def f(*a, **k):
        res = orig(*a, **k)
        try:
            dropped = [kk for kk in list(res.keys()) if kk in drop_set]
            for kk in dropped:
                res.pop(kk, None)
            w('DROP removed=%r keep_count=%d' % (dropped, len(res)))
        except Exception as e:
            w('DROP 失败 %r' % (e,))
        return res

    f._tfd_traced = True
    try:
        setattr(LS, 'account_snapshot', f)
        w('DROP 已挂 %r' % (sorted(drop_set),))
    except Exception as e:
        w('DROP 挂载失败 %r' % (e,))


def _trim_characters(LS):
    """实验钩子：按 TFD_TRIM_CHAR 只保留 CharacterList 每条里的指定字段，
    用来在实机上做字段级二分，定位新版客户端到底吃不下哪个字段。"""
    keep = os.environ.get('TFD_TRIM_CHAR', '').strip()
    if not keep:
        return
    keep_set = set(x.strip() for x in keep.split(',') if x.strip())
    orig = getattr(LS, 'account_snapshot', None)
    if not callable(orig):
        w('TRIM: account_snapshot 不存在')
        return

    def f(*a, **k):
        res = orig(*a, **k)
        try:
            chars = (res or {}).get('CharacterList') or []
            keep_src = chars
            out = []
            for c in keep_src:
                out.append({kk: vv for kk, vv in c.items() if kk in keep_set})
            res['CharacterList'] = out
            w('TRIM keep=%r entries=%d keys=%r'
              % (sorted(keep_set), len(out), sorted(out[0].keys()) if out else []))
        except Exception as e:
            w('TRIM 失败 %r' % (e,))
        return res

    f._tfd_traced = True
    try:
        setattr(LS, 'account_snapshot', f)
        w('TRIM 已挂 keep=%r' % (sorted(keep_set),))
    except Exception as e:
        w('TRIM 挂载失败 %r' % (e,))


def _limit_characters(LS):
    """实验钩子：按 TFD_TRIM_COUNT 把 CharacterList 截断成前 N 条，
    用来测"新版客户端最多能读几条"。"""
    n_raw = os.environ.get('TFD_TRIM_COUNT', '').strip()
    if not n_raw:
        return
    try:
        limit = int(n_raw)
    except ValueError:
        w('LIMIT 参数不是整数: %r' % n_raw)
        return
    orig = getattr(LS, 'account_snapshot', None)
    if not callable(orig):
        w('LIMIT: account_snapshot 不存在')
        return

    def f(*a, **k):
        res = orig(*a, **k)
        try:
            chars = (res or {}).get('CharacterList') or []
            before = len(chars)
            res['CharacterList'] = list(chars)[:limit]
            w('LIMIT %d -> %d (db=%d)' % (before, len(res['CharacterList']), before))
        except Exception as e:
            w('LIMIT 失败 %r' % (e,))
        return res

    f._tfd_traced = True
    try:
        setattr(LS, 'account_snapshot', f)
        w('LIMIT 已挂 n=%d' % limit)
    except Exception as e:
        w('LIMIT 挂载失败 %r' % (e,))


def _trace_proto():
    """抓协议编码层：哪些字段被真正写进包里。"""
    if os.environ.get('TFD_TRACE_PROTO', '1') not in ('1', 'true', 'yes'):
        return
    import protocol
    import content_protocol
    keys = ('encode', 'serialize', 'dump', 'pack', 'build', 'response', 'account',
            'write', 'frame')

    def wrap(obj, name, label):
        try:
            orig = getattr(obj, name)
        except Exception:
            return
        if not callable(orig) or getattr(orig, '_tfd_traced', False):
            return

        def f(*a, **k):
            res = orig(*a, **k)
            try:
                if isinstance(res, (bytes, bytearray)):
                    s = 'bytes[%d] %s' % (len(res), bytes(res[:160]).hex())
                    if b'CharacterTid' in bytes(res):
                        s += ' HAS_KEY_CharacterTid'
                else:
                    s = repr(res)[:600]
                w('PROTO %s%r -> %s' % (label, a[:2], s))
            except Exception:
                pass
            return res

        f._tfd_traced = True
        try:
            setattr(obj, name, f)
        except Exception:
            pass

    for mod in (protocol, content_protocol):
        for name in dir(mod):
            if name.startswith('_'):
                continue
            if not any(kk in name.lower() for kk in keys):
                continue
            if callable(getattr(mod, name, None)):
                wrap(mod, name, mod.__name__ + '.' + name)
    w('协议层跟踪已挂')


def main():
    here = HERE
    kill_notice()
    data_dir = here / 'data'
    launcher_data = data_dir / 'launcher'
    uid_file = here / 'account_uid.txt'
    uid = uid_file.read_text().strip() if uid_file.exists() else \
        '04f2858b03d3e1f379515d84ba575f03'

    import client_trust as CT
    import runtime_content as RC
    import content_local as CL
    import launcher_licensing as LL
    import launcher_runtime as LR
    import login_server as LS

    moved = _quarantine_vaults(LL, here)
    if moved:
        w('已挪走本机解不开的凭据: %s' % ', '.join(moved))

    try:
        import subprocess as SP
        _patch_popen(SP)
        p = SP.Popen(['cmd', '/c', 'echo tfd-probe'], stdout=SP.PIPE, stderr=SP.PIPE)
        out = p.communicate(timeout=8)[0] or b''
        w('管道自检: %s' % ('OK' if b'tfd-probe' in out else '空输出'))
    except Exception as e:
        w('Popen 接管失败: %r' % (e,))
    client = _make_client(LL, here, data_dir)
    now = int(time.time())
    exp = now + 3600 * 24 * 365
    issuer = CT.LEASE_PUBLIC_KEY

    LL.LicenseClient.validate_local = lambda self, *a, **k: None
    LL.LicenseClient.connection_check = lambda self, *a, **k: None
    LL.LicenseClient.renew = lambda self, *a, **k: None
    LL.LicenseClient.request = lambda self, action=None, values=None, **k: {'ok': True}

    # 界面登录会联网取品牌信息，离线时返回本地缓存
    _orig_fetch = getattr(LL.LicenseClient, '_dsh_orig_fetch', LL.LicenseClient.fetch_branding)
    LL.LicenseClient._dsh_orig_fetch = _orig_fetch

    def _fetch_branding(self, *a, **k):
        try:
            return _orig_fetch(self, *a, **k)
        except Exception:
            for attr in ('cached_branding', 'branding', '_branding'):
                v = getattr(self, attr, None)
                if isinstance(v, dict) and v:
                    return v
            return {'group': '', 'product': 'tfd-local-service', 'revision': 0}

    LL.LicenseClient.fetch_branding = _fetch_branding
    w('fetch_branding 已置为离线')
    try:
        LL.LicenseClient.is_trial = property(lambda self: False)
        LL.LicenseClient.trial_remaining = lambda self: 0
    except Exception:
        pass

    client.valid_until = exp
    client.claims = {'device_id': client.device_id, 'account': uid, 'account_id': uid,
                     'expires': exp, 'issuer': issuer, 'token': 'local-token',
                     'public_key': client.public, 'last_seen': now}
    client.lease = {'payload': dict(client.claims), 'signature': ''}
    RC._remote = CL.LocalContent(client)

    _h = hashlib.sha256()
    with open(OLD_EXE, 'rb') as fh:
        for ch in iter(lambda: fh.read(1 << 20), b''):
            _h.update(ch)
    LR.CLIENT_SHA256 = _h.hexdigest()
    globals()['_TFD_CLIENT_SHA'] = _h.hexdigest()
    w('CLIENT_SHA256 -> %s' % _h.hexdigest()[:16])

    store = LS.Store(launcher_data / 'saves' / 'local_runtime.sqlite3')
    _trace_store(LS)
    _compat_int64(LS)
    _trim_topfields(LS)
    _trim_characters(LS)
    try:
        _limit_characters(LS)
    except Exception as e:
        w('LIMIT 挂载异常 %r' % (e,))
    try:
        _trace_proto()
    except Exception as e:
        w('协议层跟踪失败 %r' % (e,))
    try:
        _dump_schema()
    except Exception as e:
        w('SCHEMA dump 失败 %r' % (e,))
    try:
        _dump_proto_def()
    except Exception as e:
        w('PROTO dump 失败 %r' % (e,))
    try:
        _find_schema()
    except Exception as e:
        w('FIND 失败 %r' % (e,))
    try:
        _probe_handlers()
    except Exception as e:
        w('HANDLERS 失败 %r' % (e,))
    try:
        _probe_wire()
    except Exception as e:
        w('WIRE 失败 %r' % (e,))
    try:
        if not store.list_characters(1):
            store.create_character(1, 101000003)
    except Exception:
        pass
    ticket = store.issue_session(1)
    if isinstance(ticket, dict):
        ticket = ticket.get('ticket') or 'local-ticket'
    w('ticket=%r' % (ticket,))

    # 完整旧桥：去掉 LAUNCH 定义（V50 自己会提供）
    # 按客户端 build 自动选桥：c0147688(旧 build 26263743) 用原桥；其它(新 build 26722146)用迁移版
    bridge_file = FULL_BRIDGE
    sha12 = (LR.CLIENT_SHA256 or '').lower()[:8]
    if sha12 == 'c0147688':
        cand = HERE / 'old_bridge_full.js.bak-c0147688'
        if cand.exists():
            bridge_file = cand
    else:
        cand = HERE / 'offset_rework' / 'old_bridge_v4_direct.js'
        if cand.exists():
            bridge_file = cand
    w('桥选择: %s (client sha %s)' % (bridge_file.name, sha12))
    full = bridge_file.read_text(encoding='utf-8')
    m = re.search(r'const LAUNCH = (\{.*?\});', full, re.S)
    bridge_js = full[:m.start()] + full[m.end():] if m else full
    w('桥 %d 字符' % len(bridge_js))

    real_rt = LR.resource_text

    def fake_rt(rel, *a, **k):
        rs = str(rel)
        if rs.endswith('launcher_bridge.js'):
            return bridge_js
        if 'tools/' in rs and rs.endswith('.js'):
            return '// skipped'
        return real_rt(rel, *a, **k)

    LR.resource_text = fake_rt

    auth = dict(client.claims)
    auth.update({'session_token': ticket, 'sub': uid, 'iss': issuer,
                 'aud': 'tfd-local-service', 'iat': now, 'exp': exp, 'jti': 'local-jti',
                 'device': client.device_id, 'authorized': True, 'ticket': ticket,
                 'username': 'demo', 'uid': 1})
    auth['lease'] = {'payload': dict(auth), 'signature': ''}
    LL.LicenseClient.restore = lambda self, *a, **k: dict(auth)

    def _imp(self, values):
        self.claims = dict(values)
        self.valid_until = int(values.get('expires') or 0)
        self.token = values.get('session_token')
        self.lease = values.get('lease') or {'payload': dict(values), 'signature': ''}
        return dict(values)

    LL.LicenseClient.import_session = _imp
    LL.LicenseClient.runtime_session = lambda self, *a, **k: dict(auth)

    acct = {'account_id': uid, 'username': 'demo', 'name': 'demo', 'uid': 1,
            'account_uid': 1, 'created': True}
    cfg = dict(auth)
    cfg.update({'data': launcher_data, 'authorization': dict(auth), 'account': acct,
                'account_id': uid, 'username': 'demo', 'session': dict(auth),
                'profile': acct, 'record': acct, 'exe': OLD_EXE, 'client': OLD_EXE,
                'game': OLD_EXE, 'path': OLD_EXE, 'server_version': LR.OFFLINE_REVISION,
                'visible': True, 'ticket': ticket, 'login_ticket': ticket,
                'session_ticket': ticket})

    stop = threading.Event()

    # ---- 诊断：本地登录服务到底有没有起来、开在哪个端口 ----
    try:
        _svc_init = LR.LauncherService.__init__

        def _svc_init_logged(self, *a, **k):
            w('LauncherService 构造')
            r = _svc_init(self, *a, **k)
            for attr in ('port', 'host', 'addr', 'address', 'server', 'socket'):
                if hasattr(self, attr):
                    w('  service.%s = %r' % (attr, getattr(self, attr)))
            return r

        LR.LauncherService.__init__ = _svc_init_logged
        w('LauncherService 已加日志')
    except Exception as e:
        w('包装 LauncherService 失败: %r' % (e,))
    try:
        _serve = LS.serve

        def _serve_logged(*a, **k):
            w('login_server.serve 调用: %r' % (a,))
            return _serve(*a, **k)

        LS.serve = _serve_logged
        w('login_server.serve 已加日志')
    except Exception as e:
        w('包装 serve 失败: %r' % (e,))

    def go():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            res = LR.run(cfg, stop, visible=True)
            loop.run_until_complete(res)
            w('run 完成')
        except Exception as e:
            w('run 异常: %s: %s' % (type(e).__name__, str(e)[:200]))
            w(traceback.format_exc())

    # ---- 自动登录（绕过 fetch_branding 的联网依赖）----
    def auto_login():
        try:
            import gc as _gc
            import launcher as _L
            insts = [o for o in _gc.get_objects() if isinstance(o, _L.Launcher)]
            if not insts:
                w('自动登录: 没有 Launcher 实例')
                return
            app = insts[0]

            # 从 account.txt 读取目标账号（格式：用户名 密码）
            user, pw = 'demo', '12345678'
            cfg_file = HERE / 'account.txt'
            try:
                if cfg_file.exists():
                    parts = cfg_file.read_text(encoding='utf-8').strip().split()
                    if parts:
                        user = parts[0]
                        if len(parts) > 1:
                            pw = parts[1]
                    w('account.txt -> %s / %s' % (user, pw))
            except Exception as e:
                w('读取 account.txt 失败 %r' % (e,))

            if user.lower() == 'manual':
                w('manual 模式：保留登录界面，等你手动登录')
                return

            # 账号不存在则本地建号（用启动器自己的派生算法）
            try:
                import launcher_accounts as _LA
                import sqlite3 as _sq
                import secrets as _sec
                norm = _LA.normalize_username(user)
                uname, ukey = norm if isinstance(norm, tuple) else (user, norm)
                w('用户名=%r 键=%r' % (uname, ukey))
                with app.accounts.connection() as con:
                    row = con.execute('select account_id from launcher_accounts where username_key=?',
                                      (ukey,)).fetchone()
                if row is None:
                    salt = _sec.token_bytes(16)
                    ph = _LA.derive(_LA.password_bytes(pw), salt)
                    aid = _sec.token_hex(16)
                    now_ts = int(time.time())
                    with app.accounts.connection() as con:
                        con.execute(
                            'insert into launcher_accounts (account_id, username, username_key, salt, '
                            'password_hash, failed_attempts, locked_until, created_at, last_login) '
                            'values (?,?,?,?,?,0,0,?,0)',
                            (aid, uname, ukey, _sq.Binary(salt), _sq.Binary(ph), now_ts))
                        con.commit()
                    w('已本地建号: %s (%s)' % (uname, aid))
                else:
                    w('账号已存在: %s' % uname)
            except Exception as e:
                w('建号检查失败 %r' % (e,))

            acc = None
            try:
                acc = app.accounts.login(user, pw)
            except Exception as e:
                w('自动登录: 密码登录失败 %r，改用账本记录' % (e,))
                try:
                    with app.accounts.connection() as con:
                        row = con.execute(
                            'select account_id, username from launcher_accounts '
                            'order by last_login desc limit 1').fetchone()
                    if row is not None:
                        import launcher_accounts as _LA
                        aid = row['account_id'] if isinstance(row, dict) else row[0]
                        un = row['username'] if isinstance(row, dict) else row[1]
                        acc = _LA.Account(account_id=aid, username=un, created=False)
                except Exception as e2:
                    w('自动登录: 兜底也失败 %r' % (e2,))
            if acc is None:
                return
            app.account = acc
            for how in ('logged_in(acc)', 'logged_in()'):
                try:
                    if how == 'logged_in(acc)':
                        app.logged_in(acc)
                    else:
                        app.logged_in()
                    w('自动登录成功: %s' % how)
                    return
                except Exception as e:
                    w('自动登录 %s 失败 %r' % (how, e))
        except Exception:
            w('自动登录异常:\n' + traceback.format_exc()[-400:])

    threading.Thread(target=auto_login, daemon=True).start()
    threading.Thread(target=go, daemon=True).start()
    w('已启动（等 V50 自己开服务并拉起客户端）')


try:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, 'w', encoding='utf-8') as fh:
        fh.write('=== patch_v50 启动 ===\n')
    main()
except Exception:
    w('FATAL:\n' + traceback.format_exc()[-1200:])
