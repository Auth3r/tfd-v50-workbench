"""Check the adjudicated v3 character segment, offline, with Python 3.10+."""
import argparse
from collections import Counter
from contextlib import closing
from dataclasses import dataclass, fields
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
from zipfile import BadZipFile, ZipFile


ZIP = Path(r"C:\Users\admin\Doubao\chats\2026-11-19\new-chat\TFD-第四批-账号快照反解-v3-20261121.zip")
ZIP_SHA = "cb312e9eafd51c803aa03c3a10c7cdcbc43219e40dac1fc52bc562980462c803"
FRAMES = "04-解码全帧.json"
SAVE = "05-账号存档-只读副本.sqlite3"
FRAMES_LF_SHA = "2874ca49b655e20be8c9f4530aefb34f32a082a33204a93cc53d7d99ae8a8b56"
SAVE_SHA = "0bc1672fd8b15526098a58d41b90ce168d121fbd371ff846ec11c90661e94e04"
START, END, COUNT = 30075, 30404, 36


@dataclass(frozen=True)
class Character:
    uid: int
    tid: int
    exp: int
    level: int
    max_level: int
    reset_count: int


COLUMNS = tuple(f.name for f in fields(Character))


def checked_hash(data, expected, label):
    digest = sha256(data).hexdigest()
    if digest != expected:
        raise ValueError(f"{label} hash mismatch: expected={expected} actual={digest}")
    print(f"{label} sha256={digest} OK")


def inputs(path):
    packed = path.read_bytes()
    checked_hash(packed, ZIP_SHA, "v3 ZIP")
    with ZipFile(BytesIO(packed)) as archive:
        frames = archive.read(FRAMES)
        save = archive.read(SAVE)
    checked_hash(frames.replace(b"\r\n", b"\n"), FRAMES_LF_SHA, "04 (LF)")
    checked_hash(save, SAVE_SHA, "05 (binary)")
    selected = {}
    for frame in json.loads(frames)["frames"]:
        if frame["dir"] == "out" and frame["plen"] == 49852:
            seq = frame["seq"]
            body = bytes.fromhex(frame["dec_hex"])
            if seq in selected or len(body) != frame["plen"] or body[:3] != bytes.fromhex("18 f0 15"):
                raise ValueError(f"unexpected target for seq={seq}")
            selected[seq] = body
    if set(selected) != {30, 38}:
        raise ValueError(f"unexpected target sequences {sorted(selected)}")
    return selected, save


def doubled_varint(data, pos):
    """Read one unsigned base-128 integer inside the supplied record region."""
    start = pos
    value = 0
    for shift in range(0, 64, 7):
        if pos == len(data):
            raise ValueError(f"truncated varint at {START + start}")
        byte = data[pos]
        pos += 1
        value |= (byte & 127) << shift
        if byte < 128:
            if value.bit_length() > 64 or value % 2:
                raise ValueError(f"invalid doubled integer at {START + start}, raw={value}")
            return value // 2, pos
    raise ValueError(f"overlong varint at {START + start}")


def decode(segment):
    # The cursor is never reset between rows. No DB values or search anchors
    # are supplied to this function. Coordinates in the evidence are absolute.
    pos = 0
    records, bounds = [], []
    for ordinal in range(1, COUNT + 1):
        start = pos
        if pos + 5 > len(segment) or segment[pos] % 2:
            raise ValueError(f"row {ordinal}, invalid uid/Tid at {START + pos}")
        uid = segment[pos] // 2
        tid = int.from_bytes(segment[pos + 1:pos + 5], "little")
        pos += 5
        tail = []
        for name in COLUMNS[2:]:
            try:
                value, pos = doubled_varint(segment, pos)
            except ValueError as error:
                raise ValueError(f"row {ordinal} {name}: {error}") from error
            tail.append(value)
        records.append(Character(uid, tid, *tail))
        bounds.append((START + start, START + pos))
    if pos != len(segment):
        raise ValueError(f"36 rows ended at {START + pos}, expected {START + len(segment)}")
    return records, bounds


def sqlite_rows(blob):
    with TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
        path = Path(tmp, SAVE)
        path.write_bytes(blob)
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
            db.execute("PRAGMA query_only=ON")
            rows = db.execute("SELECT uid, template_id, exp, level, max_level, reset_count "
                              "FROM characters ORDER BY uid").fetchall()
        if sha256(path.read_bytes()).hexdigest() != SAVE_SHA:
            raise ValueError("temporary SQLite copy changed")
    if len(rows) != COUNT or len(set(row[0] for row in rows)) != COUNT:
        raise ValueError(f"unexpected SQLite character inventory: rows={len(rows)}")
    return [Character(*row) for row in rows]


def compare(seq, actual, expected, bounds):
    scores = Counter()
    for index, (got, want) in enumerate(zip(actual, expected)):
        for field in COLUMNS:
            a, b = getattr(got, field), getattr(want, field)
            if a == b:
                scores[field] += 1
            else:
                print(f"DIFF seq={seq} row={index+1} start={bounds[index][0]} "
                      f"field={field} expected={b} actual={a}")
    print(f"seq={seq} " + " ".join(f"{f}={scores[f]}/{COUNT}" for f in COLUMNS))
    return len(actual) == len(expected) == COUNT and all(scores[f] == COUNT for f in COLUMNS)


def check(path, gate):
    frames, blob = inputs(path)
    decoded = {}
    for seq, body in sorted(frames.items()):
        segment = body[START:END]
        records, bounds = decode(segment)
        decoded[seq] = records, bounds
        lengths = Counter(end-start for start, end in bounds)
        print(f"seq={seq} proc=1400 bytes={len(body)} first={bounds[0][0]} end={bounds[-1][1]} "
              f"consumed={len(segment)} count={len(records)} lengths={dict(sorted(lengths.items()))} "
              f"segment_sha256={sha256(segment).hexdigest()}")
    print("G1 PASS: accepted bounds, sequentially consumed in both decoded bodies.")
    if gate == "G1":
        return 0
    expected = sqlite_rows(blob)
    print("05.characters ORDER BY uid: 36 rows; read-only immutable copy verified unchanged.")
    passed = True
    for seq, (records, bounds) in decoded.items():
        # Both frames get their own comparison against SQLite. The first frame
        # also prints the entire wire-decoded table for review.
        if seq == min(decoded):
            print("row  [start,end)    uid  Tid        exp    level  max_level  reset_count")
            for i, (record, (start, end)) in enumerate(zip(records, bounds), 1):
                print(f"{i:02}   [{start},{end}) {record.uid:2}   {record.tid:9}  {record.exp:5}  "
                      f"{record.level:5}  {record.max_level:9}  {record.reset_count:11}")
        passed &= compare(seq, records, expected, bounds)
        in_order = [record.uid for record in records] == list(range(1, COUNT + 1))
        print(f"seq={seq} decoded Uids are 1..36 in order: {in_order}")
        passed &= in_order
        for field in ("exp", "reset_count"):
            nonzero = [(record.uid, getattr(record, field)) for record in records if getattr(record, field)]
            print(f"seq={seq} nonzero {field} (uid,value)={nonzero}")
    print("G2 PASS" if passed else "G2 FAIL")
    return 0 if passed else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", required=True, action="store_true")
    parser.add_argument("--zip", type=Path, default=ZIP)
    parser.add_argument("--gate", choices=("G1", "G2"), default="G2")
    args = parser.parse_args()
    return check(args.zip, args.gate)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, BadZipFile, sqlite3.Error) as exc:
        print(f"CHECK ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
