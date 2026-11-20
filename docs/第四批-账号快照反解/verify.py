"""Offline RPC and account-segment evidence check for the 2026-11-21 batch.
Exit 0 = pass, 2 = input error, 3 = UNKNOWN, 4 = skipped prerequisite.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ZIP = Path(r"C:\Users\admin\Doubao\chats\2026-11-19\new-chat\TFD-第四批-账号快照反解-20261121.zip")
NAMES = ("01-任务卡.md", "02-载荷解码规则.md", "03-结构速查.md",
         "04-解码全帧.json", "05-账号存档-只读副本.sqlite3", "06-考卷样本.json", "07-解码校验.py")
# Fingerprints of the supplied edition, text normalized to LF, SQLite raw.
HASHES = (
    "5fd0d5742a65049a548c8bc5be39b3957537508a8b6940facab5408493219f19",
    "2efaf89b287d6d672e819bc10df0ca5e763db29f02ef754dcacc4a7b7a34ada0",
    "0a22f48ffe003203d6f50aa49cd3de0a29afd717fbd802dc448145dd192eddf7",
    "2874ca49b655e20be8c9f4530aefb34f32a082a33204a93cc53d7d99ae8a8b56",
    "0bc1672fd8b15526098a58d41b90ce168d121fbd371ff846ec11c90661e94e04",
    "f0597d0d3054e4738b5eed688f4ac94df75e98ec28e5e8931c55c2da7229bc6c",
    "40d774e4bc92a680db51272b7bf8a618ed7d28296994335d97ed44acc4fbd151",
)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def read_inputs(path):
    packed = path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(packed)) as archive:
        if sorted(archive.namelist()) != sorted(NAMES):
            raise ValueError("ZIP member inventory changed")
        inputs = {name: archive.read(name) for name in NAMES}
    for name, expected in zip(NAMES, HASHES):
        material = inputs[name]
        actual = sha(material if name.endswith(".sqlite3") else material.replace(b"\r\n", b"\n"))
        if actual != expected:
            raise ValueError(f"{name}: expected {expected}, observed {actual}")
    print("ZIP sha256=" + sha(packed))
    print("Edition fingerprints matched 7/7 (text LF; SQLite raw).")
    return inputs

def signed_integer(data, off, width):
    value = 0
    for shift in range(0, width, 7):
        if off == len(data):
            raise ValueError("truncated RPC integer")
        ch = data[off]
        off += 1
        value |= (ch & 127) << shift
        if ch < 128 and value < 1 << width:
            return (value >> 1) ^ -(value & 1), off
    raise ValueError("RPC integer exceeds width")

def rpc(data):
    rid, off = signed_integer(data, 0, 32)
    proc, off = signed_integer(data, off, 16)
    return rid, proc, off

def upstream(inputs):
    # The reviewed supplied verifier expects these two JSON files beside it.
    # The SQLite member never leaves the in-memory ZIP.
    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp:
        for name in (NAMES[3], NAMES[5], NAMES[6]):
            (Path(temp) / name).write_bytes(inputs[name])
        p = subprocess.run([sys.executable, "-I", "-B", "-X", "utf8", str(Path(temp) / NAMES[6])],
                           capture_output=True, encoding="utf-8")
    print(p.stdout, end="")
    if p.stderr:
        print(p.stderr, end="")
    print(f"supplied_07_exit={p.returncode}")
    if p.returncode:
        raise ValueError("07 verification failed")

def g1(inputs):
    frames = [(f, bytes.fromhex(f["dec_hex"])) for f in json.loads(inputs[NAMES[3]])["frames"]]
    samples = json.loads(inputs[NAMES[5]])["samples"]
    if len(frames) != 193 or any(len(b) != f["plen"] for f, b in frames):
        raise ValueError("frame inventory/length conflict")

    # Check the header interpretation with three independently labelled controls.
    for proc, length in ((3452, 322), (3452, 223), (10000, 5)):
        sample, = [s for s in samples if s["proc"] == proc and s["res_len"] == length]
        expected = bytes.fromhex(sample["res_hex"])
        matches = [f["seq"] for f, b in frames if f["dir"] == "out" and b == expected and rpc(b)[1] == proc]
        if not matches:
            raise ValueError("independent RPC control failed")
        print(f"control proc={proc} bytes={length} exact copies seq={matches}")
    sample, = [s for s in samples if s["proc"] == 1004]
    ref = bytes.fromhex(sample["req_hex"])
    print(f"06 proc=1004 req_hex={len(ref)} B sha256={sha(ref)} res_err={bool(sample.get('res_err'))}")
    selected = [(f,b) for f,b in frames if f["dir"] == "out" and f["plen"] == 49852 and f["seq"] in (30,38)]
    if sorted(f["seq"] for f,b in selected) != [30,38]:
        raise ValueError("assigned frames missing or ambiguous")
    for f,b in selected:
        rid, proc, head = rpc(b)
        name = b.find(b"demo")
        start = name - 2
        match = next((i for i,(x,y) in enumerate(zip(b[start:], ref)) if x!=y), min(len(b)-start,len(ref)))
        print(f"assigned seq={f['seq']} len={len(b)} header={b[:head].hex(' ')} id={rid} proc={proc} "
              f"demo@{name} copies={b.count(b'demo')}; slice[{start}:{name+5}]={b[start:name+5].hex(' ')}")
        print(f"  candidate@{start} matches {match} leading bytes of 06; next frame[{start+match}]=0x{b[start+match]:02x}, "
              f"06[{match}]=0x{ref[match]:02x}; full reference offset={b.find(ref)}")
    differences = [i for i,(a,b) in enumerate(zip(selected[0][1],selected[1][1])) if a!=b]
    print("assigned frame differences (zero-based offsets):", differences)
    for f,b in frames:
        # These complete envelopes have controls/known prefixes. Other RPC
        # forms in the bundle need not conform to this ordinary-header reader.
        if f["dir"] == "out" and len(b) == len(ref)+3:
            rid,proc,head=rpc(b)
            equal=b[head:]==ref
            print(f"cross-reference seq={f['seq']} len={len(b)} rpc=[{b[:head].hex(' ')}] id={rid} proc={proc} "
                  f"entire body==06.req_hex: {equal}; bytes={len(b)-head}; demo@{b.find(b'demo')}")
        elif f["dir"] == "in" and b in (bytes.fromhex("10 d8 0f"),bytes.fromhex("18 f0 15 00 00")):
            rid,proc,_=rpc(b)
            print(f"inbound corroboration seq={f['seq']} len={len(b)} id={rid} proc={proc}")
    print("G1 UNKNOWN: designated frames have outer RPC 1400. Within them, account segment start/end/length and field count are unresolved.")
    return 3

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip",type=Path,default=ZIP)
    parser.add_argument("--check",action="store_true",help="run in acceptance order; refuse SQLite comparison before G1 passes")
    parser.add_argument("--gate",choices=["G1","G2","G3","G4"])
    args=parser.parse_args()
    inputs=read_inputs(args.zip)
    upstream(inputs)
    first=g1(inputs)
    if args.gate in ("G2","G3","G4"):
        print(f"{args.gate} SKIPPED: prerequisite G1 UNKNOWN; no acceptance comparison executed.")
        return 4
    if args.check:
        print("G2 SQLite comparison: SKIPPED; 0/36 rows compared. G3 and G4 SKIPPED.")
    return first

if __name__=="__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print(f"INPUT ERROR: {error}",file=sys.stderr)
        raise SystemExit(2)
