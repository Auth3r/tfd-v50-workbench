"""Audit the batch-four v2 G1 ruling using only the supplied ZIP (Python 3.10+)."""
import argparse
from collections import Counter
from contextlib import closing, redirect_stdout
from hashlib import sha256
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import BadZipFile, ZipFile


DEFAULT_ZIP = Path(r"C:\Users\admin\Doubao\chats\2026-11-19\new-chat\TFD-第四批-账号快照反解-v2-20261121.zip")
CARD = "01-任务卡.md"
FRAMES = "04-解码全帧.json"
SAVE = "05-账号存档-只读副本.sqlite3"
SAMPLES = "06-考卷样本.json"
UPSTREAM = "07-解码校验.py"
# 02..07 retain the fingerprints of the first edition. 01 and 08 identify v2.
PINS = {
    CARD: "3c6c3aa34cc230f76c8194e34dccc2bbd05b84b9c8d003c05173a7f899629a0b",
    "02-载荷解码规则.md": "2efaf89b287d6d672e819bc10df0ca5e763db29f02ef754dcacc4a7b7a34ada0",
    "03-结构速查.md": "0a22f48ffe003203d6f50aa49cd3de0a29afd717fbd802dc448145dd192eddf7",
    FRAMES: "2874ca49b655e20be8c9f4530aefb34f32a082a33204a93cc53d7d99ae8a8b56",
    SAVE: "0bc1672fd8b15526098a58d41b90ce168d121fbd371ff846ec11c90661e94e04",
    SAMPLES: "f0597d0d3054e4738b5eed688f4ac94df75e98ec28e5e8931c55c2da7229bc6c",
    UPSTREAM: "40d774e4bc92a680db51272b7bf8a618ed7d28296994335d97ed44acc4fbd151",
    "08-G1修订-账号段已定位.md": "9b8d87e13706815fe1217050985c31e1080c7443485101ac7a924ece5e38f335",
}


def read_zip(path):
    raw = path.read_bytes()
    with ZipFile(io.BytesIO(raw)) as archive:
        if sorted(archive.namelist()) != sorted(PINS):
            raise ValueError("unexpected v2 ZIP inventory")
        data = {name: archive.read(name) for name in PINS}
    for name, expected in PINS.items():
        content = data[name] if name == SAVE else data[name].replace(b"\r\n", b"\n")
        actual = sha256(content).hexdigest()
        if actual != expected:
            raise ValueError(f"{name}: sha256 {actual}, expected {expected}")
    print(f"ZIP sha256={sha256(raw).hexdigest()}; member fingerprints matched {len(PINS)}/{len(PINS)}")
    return data


def read_rows(data):
    # The static SQLite header uses WAL mode. Open an exact temporary copy as
    # immutable, without creating SQLite journal files or changing input bytes.
    with TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
        copy = Path(tmp, SAVE)
        copy.write_bytes(data)
        with closing(sqlite3.connect(copy.as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
            db.execute("PRAGMA query_only=ON")
            rows = db.execute("SELECT uid, template_id, level FROM characters ORDER BY uid").fetchall()
        if copy.read_bytes() != data:
            raise ValueError("SQLite copy changed")
    if len(rows) != 36 or len({tid for _, tid, _ in rows}) != 36:
        raise ValueError("expected 36 distinct SQLite character TIDs")
    return rows


def search(data, needle):
    offset = data.find(needle)
    while offset >= 0:
        yield offset
        offset = data.find(needle, offset + 1)


def varuint(data, pos):
    value = 0
    for shift in range(0, 70, 7):
        if pos >= len(data):
            break
        byte = data[pos]
        value |= (byte & 127) << shift
        pos += 1
        if byte < 128:
            return value, pos
    raise ValueError("unterminated or oversized integer")


def rpc_proc(data):
    _, pos = varuint(data, 0)
    doubled, end = varuint(data, pos)
    if doubled & 1:
        raise ValueError("expected a nonnegative procedure in this capture")
    return doubled // 2, data[:end].hex(" ")


def fixed_grid(body, rows, start):
    observed = []
    for index, (uid, tid, _) in enumerate(rows):
        pos = start + index * 9
        actual_uid = body[pos]
        actual_tid = int.from_bytes(body[pos + 1:pos + 5], "little")
        observed.append((pos, actual_uid, actual_tid, actual_uid == 2 * uid, actual_tid == tid))
    return observed


def grid_summary(observed):
    return (f"Uid={sum(r[3] for r in observed)}/36 Tid={sum(r[4] for r in observed)}/36 "
            f"both={sum(r[3] and r[4] for r in observed)}/36")


def main_frame(body, rows, positions):
    tid_starts = [hits[0] for hits in positions]
    starts = [pos - 1 for pos in tid_starts]
    if starts != sorted(starts) or len(set(starts)) != len(starts):
        raise ValueError("first TID occurrences do not form one ordered run")
    pairs = sum(body[pos] == uid * 2 for pos, (uid, _, _) in zip(starts, rows))
    last_tid_end = tid_starts[-1] + 4
    steps = [b - a for a, b in zip(starts, starts[1:])]
    print(f"  first-TID run by SQLite uid: {tid_starts[0]}..{tid_starts[-1]} inclusive starts; "
          f"last TID ends at {last_tid_end} exclusive; preceding UidByte==2*uid {pairs}/36")
    print(f"  UidByte positions={','.join(map(str, starts))}")
    print(f"  adjacent-start distances={dict(sorted(Counter(steps).items()))}; exceptions="
          + ", ".join(f"uid{rows[i][0]}->{rows[i+1][0]}:{s}" for i, s in enumerate(steps) if s != 9))
    print(f"  directly anchored span=[{starts[0]},{last_tid_end}) {last_tid_end-starts[0]} B "
          "(first UidByte through last complete TID)")
    in_range = sum(30076 <= pos <= 30397 for pos in tid_starts)
    inside = sum(30076 <= pos and pos + 3 <= 30397 for pos in tid_starts)
    print(f"  card [30076,30397] inclusive: {30397-30076+1} bytes; TID starts={in_range}/36; "
          f"complete TIDs={inside}/36")
    literal = fixed_grid(body, rows, 30076)
    exact = fixed_grid(body, rows, starts[0])
    print(f"  fixed 9 from literal 30076: {grid_summary(literal)}")
    print(f"  fixed 9 from measured {starts[0]}: {grid_summary(exact)}")
    for i, (pos, actual_uid, actual_tid, uid_ok, tid_ok) in enumerate(exact):
        if not (uid_ok and tid_ok):
            uid, tid, _ = rows[i]
            print(f"  first failed fixed row={i+1}; predicted={pos} bytes={body[pos:pos+9].hex(' ')} "
                  f"UidByte={actual_uid} Tid={actual_tid}; anchored={starts[i]} expected UidByte={2*uid} Tid={tid}")
            break
    # Diagnostic only. Four bounded integers after each TID give a candidate
    # end. Only the following UID anchors independently verify the first 35 ends.
    end_positions = []
    level_matches = Counter()
    for pos, (_, _, level) in zip(tid_starts, rows):
        end = pos + 4
        tail = []
        for _ in range(4):
            value, end = varuint(body, end)
            tail.append(value)
        end_positions.append(end)
        if tail[1] == level * 2:
            level_matches[level] += 1
    chained = sum(a == b for a, b in zip(end_positions[:-1], starts[1:]))
    limit = end_positions[-1]
    counts = Counter(row[2] for row in rows)
    print(f"  four tail varints: next UidByte boundary matches={chained}/35; last row="
          f"{body[starts[-1]:limit].hex(' ')}; candidate records=[{starts[0]},{limit}) {limit-starts[0]} B")
    print(f"  byte before first row @ {starts[0]-1}=0x{body[starts[0]-1]:02x}; "
          f"byte after candidate @ {limit}=0x{body[limit]:02x}; demo @ {body.find(b'demo')}")
    sample_levels = (40, 1, 35)
    for level in sample_levels:
        print(f"  tail integer #2 == {level}*2 (0x{2*level:02x}): {level_matches[level]}/{counts[level]}")
    return (pairs == 36 and all(uid_ok and tid_ok for _, _, _, uid_ok, tid_ok in exact)
            and limit - starts[0] == 320 and in_range == 36
            and all(counts[lvl] and level_matches[lvl] == counts[lvl] for lvl in sample_levels))


def audit(data):
    rows = read_rows(data[SAVE])
    frames = json.loads(data[FRAMES])["frames"]
    selected = sorted((f for f in frames if f["dir"] == "out" and f["plen"] in (49852, 25087)),
                      key=lambda f: (-f["plen"], f["seq"]))
    if Counter(f["plen"] for f in selected) != {49852: 2, 25087: 2}:
        raise ValueError("v2 target frame inventory differs")
    print(f"05.characters={len(rows)}; SQLite immutable/query_only; temporary copy unchanged.")
    passed = True
    for frame in selected:
        body = bytes.fromhex(frame["dec_hex"])
        if len(body) != frame["plen"]:
            raise ValueError("decoded body length differs from plen")
        proc, header = rpc_proc(body)
        positions = [list(search(body, tid.to_bytes(4, "little"))) for _, tid, _ in rows]
        hits = sum(bool(offsets) for offsets in positions)
        big_hits = sum(tid.to_bytes(4, "big") in body for _, tid, _ in rows)
        print(f"seq={frame['seq']} plen={len(body)} header={header} proc={proc}; "
              f"whole-frame TIDs LE={hits}/36 BE={big_hits}/36; "
              f"LE occurrences={sum(map(len, positions))}")
        if hits != 36:
            passed = False
            continue
        if len(body) == 49852:
            ok = main_frame(body, rows, positions)
            passed &= ok and proc == 1400
        else:
            flat = [pos for offsets in positions for pos in offsets]
            in_range = sum(any(21829 <= pos <= 22087 for pos in offsets) for offsets in positions)
            inside = sum(any(21829 <= pos and pos + 3 <= 22087 for pos in offsets) for offsets in positions)
            print(f"  first-to-last TID start={min(flat)}..{max(flat)}; card [21829,22087] inclusive: "
                  f"starts={in_range}/36, complete TIDs={inside}/36")
            passed &= proc == 20000 and in_range == 36
    return passed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, default=DEFAULT_ZIP)
    parser.add_argument("--check", action="store_true", required=True)
    parser.add_argument("--gate", choices=("G1", "G2", "G3", "G4"), default="G1")
    args = parser.parse_args()
    data = read_zip(args.zip)
    if args.gate == "G1":
        # Run only the fingerprinted upstream verifier and its two fixtures.
        with TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
            for name in (UPSTREAM, FRAMES, SAMPLES):
                Path(tmp, name).write_bytes(data[name])
            result = subprocess.run([sys.executable, "-I", "-B", "-X", "utf8", str(Path(tmp, UPSTREAM))],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding="utf-8")
        print(result.stdout, end="")
        if result.returncode:
            raise ValueError(f"upstream verifier exited {result.returncode}")
        passed = audit(data)
        print("G1 PASS" if passed else "G1 FAIL: fixed-width and range assertions contradicted by input.")
        return 0 if passed else 1
    with redirect_stdout(io.StringIO()):
        passed = audit(data)
    if not passed:
        print(f"{args.gate} NOT RUN: G1 FAIL; evaluated only the G1 prerequisite.")
        if args.gate == "G2":
            print("Uid=N/A/36 Tid=N/A/36 Level=N/A/36 Selected=N/A/36; compared rows=0.")
        return 4
    print(f"{args.gate} UNKNOWN: this G1 audit contains no accepted downstream decoder.")
    return 3


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, sqlite3.Error, BadZipFile) as exc:
        print(f"INPUT ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
