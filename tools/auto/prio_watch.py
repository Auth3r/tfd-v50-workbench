# -*- coding: utf-8 -*-
"""盯 M1-Win64-Shipping，一出现就把优先级提到 High（缓解黑屏）。纯 ctypes。"""
import ctypes
import time

k = ctypes.windll.kernel32
TH32CS_SNAPPROCESS = 0x00000002
HIGH_PRIORITY_CLASS = 0x00000080


class PE32(ctypes.Structure):
    _fields_ = [('dwSize', ctypes.c_ulong), ('cntUsage', ctypes.c_ulong), ('th32ProcessID', ctypes.c_ulong),
                ('th32DefaultHeapID', ctypes.c_void_p), ('th32ModuleID', ctypes.c_ulong),
                ('cntThreads', ctypes.c_ulong), ('th32ParentProcessID', ctypes.c_ulong),
                ('pcPriClassBase', ctypes.c_long), ('dwFlags', ctypes.c_ulong),
                ('szExeFile', ctypes.c_char * 260)]


def scan():
    snap = k.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    pe = PE32()
    pe.dwSize = ctypes.sizeof(PE32)
    out = []
    if k.Process32First(snap, ctypes.byref(pe)):
        while True:
            n = pe.szExeFile.decode('mbcs', 'ignore').lower()
            if 'm1-win64-shipping.exe' in n:
                out.append(int(pe.th32ProcessID))
            if not k.Process32Next(snap, ctypes.byref(pe)):
                break
    k.CloseHandle(snap)
    return out


hit = set()
deadline = time.time() + 180
while time.time() < deadline:
    for pid in scan():
        if pid in hit:
            continue
        h = k.OpenProcess(0x1F0FFF, False, pid)
        if h:
            k.SetPriorityClass(h, HIGH_PRIORITY_CLASS)
            k.CloseHandle(h)
        hit.add(pid)
        print('[prio] pid=%d -> HIGH at %s' % (pid, time.strftime('%H:%M:%S')), flush=True)
    time.sleep(0.2)
print('[prio] end hits=%d' % len(hit), flush=True)
