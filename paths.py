"""统一路径入口。

所有脚本从这里取路径，不要再写死盘符。解析优先级：
  环境变量 > config.local.json > config.example.json > 本目录默认值

环境变量（临时覆盖用，不改文件）：
  TFD_CLIENT   客户端 exe
  TFD_LAUNCHER 启动器 exe
  TFD_WORK     输出目录（日志/取证/临时文件）
  TFD_SAVE     存档目录
  TFD_VENDOR   frida 所在目录
  TFD_PY       Python 解释器
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CFG_LOCAL = HERE / 'config.local.json'
CFG_TPL = HERE / 'config.example.json'


def _read(p):
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return {}


if CFG_LOCAL.is_file():
    CFG = _read(CFG_LOCAL)
    CFG_SOURCE = 'config.local.json'
else:
    CFG = _read(CFG_TPL)
    CFG_SOURCE = 'config.example.json' if CFG_TPL.is_file() else '(none)'

_PATHS = CFG.get('paths') or {}
_EXPECT = CFG.get('expect') or {}


def _resolve(env_name, cfg_key, default):
    """env > config > default。相对路径按仓库根解析。"""
    v = os.environ.get(env_name, '').strip().strip('"') if env_name else ''
    if not v:
        v = str(_PATHS.get(cfg_key) or '').strip()
    if not v:
        return Path(default) if default else None
    p = Path(v)
    return p if p.is_absolute() else (HERE / p)


def _client():
    explicit = _resolve('TFD_CLIENT', 'client_exe', None)
    if explicit and explicit.is_file():
        return explicit
    # client.txt（选过客户端后会写这里）
    f = HERE / 'client.txt'
    if f.is_file():
        try:
            p = Path(f.read_text(encoding='utf-8').strip().strip('"'))
        except Exception:
            p = None
        if p and p.is_file():
            return p
    return explicit  # 可能为 None


CLIENT = _client()
LAUNCHER = _resolve('TFD_LAUNCHER', 'launcher_exe', HERE / 'TFDLauncher.exe')
WORK = _resolve('TFD_WORK', 'work_dir', HERE / 'runs')
SAVE = _resolve('TFD_SAVE', 'save_dir', HERE / 'data' / 'launcher' / 'saves')
BRIDGE = _resolve(None, 'bridge_js', HERE / 'offset_rework' / 'old_bridge_v30_bt.js')
PYTHON = _resolve('TFD_PY', 'python_exe', Path(sys.executable))
VENDOR = _resolve('TFD_VENDOR', 'vendor_dir', None)

CLIENT_SHA = str(_EXPECT.get('client_sha256') or '').strip().lower()
CLIENT_BUILD = str(_EXPECT.get('client_build') or '').strip()


def ensure_work(name=''):
    """取输出目录（可带文件名），必要时创建目录。"""
    WORK.mkdir(parents=True, exist_ok=True)
    return (WORK / name) if name else WORK


def as_dict():
    return {
        'config_source': CFG_SOURCE,
        'client': str(CLIENT) if CLIENT else '',
        'launcher': str(LAUNCHER),
        'work': str(WORK),
        'save': str(SAVE),
        'bridge': str(BRIDGE),
        'python': str(PYTHON),
        'vendor': str(VENDOR) if VENDOR else '',
        'expect_build': CLIENT_BUILD,
        'expect_sha256': CLIENT_SHA,
    }


if __name__ == '__main__':
    for k, v in as_dict().items():
        print('%-16s %s' % (k, v))
