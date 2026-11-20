"""Check the v4 character snapshot against both original byte ranges, offline, with Python 3.10+."""
import argparse
from collections import Counter
from contextlib import closing
from dataclasses import dataclass, fields
from hashlib import sha256
from io import BytesIO
from itertools import zip_longest
import json
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
from zipfile import BadZipFile, ZipFile


ZIP = Path(r"C:\Users\admin\Doubao\chats\2026-11-19\new-chat\TFD-第四批-账号快照反解-v4-20261121.zip")
ZIP_SHA = "6e375440b2cf65c7f6f7abb53b216c405aa9a336ae5949c8d83b5860b7511a2b"
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
    checked_hash(packed, ZIP_SHA, "v4 ZIP")
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


def verify_tail_rule(segment, rows, seq):
    # Independent of the encoder: locate each UID/TID pair, then read byte
    # groups up to the next pair. Reconstruct each integer from high to low.
    starts = []
    for row in rows:
        tag = bytes([2 * row.uid]) + row.tid.to_bytes(4, "little")
        if segment.count(tag) != 1:
            raise ValueError(f"seq={seq} uid={row.uid}: ambiguous or absent row anchor")
        starts.append(segment.index(tag))
    if starts[0] != 0 or sorted(starts) != starts:
        raise ValueError(f"seq={seq}: unordered row anchors")

    matched = 0
    multibyte = []
    for row, start, end in zip(rows, starts, starts[1:] + [len(segment)]):
        pos = start + 5
        for name in COLUMNS[2:]:
            first = pos
            while pos < end and segment[pos] & 0x80:
                pos += 1
            if pos == end:
                raise ValueError(f"seq={seq} uid={row.uid} {name}: no terminating byte")
            pos += 1
            raw = segment[first:pos]
            number = 0
            for byte in reversed(raw):
                number = number * 128 + (byte & 127)
            expected = 2 * getattr(row, name)
            if number != expected:
                raise ValueError(f"seq={seq} uid={row.uid} {name} @{START+first}: "
                                 f"raw={raw.hex(' ')} expected doubled={expected} got={number}")
            matched += 1
            if len(raw) > 1:
                multibyte.append(f"uid{row.uid}.{name} {raw.hex(' ')} -> {number}/2")
        if pos != end:
            raise ValueError(f"seq={seq} uid={row.uid}: tail ends at {START+pos}, anchor at {START+end}")
    print(f"seq={seq} independent tail check: {matched}/{4*len(rows)} doubled values; "
          f"{len(starts)}/{len(rows)} row ends. Multibyte: " + " | ".join(multibyte))


def write_doubled(value):
    if not 0 <= value < 1 << 63:
        raise ValueError(f"value outside nonnegative doubled uint64 range: {value}")
    remaining = 2 * value
    result = bytearray()
    while remaining >= 128:
        result.append(0x80 | (remaining & 127))
        remaining >>= 7
    result.append(remaining)
    return result


def encode_snapshot(rows):
    """Serialize the supplied records in their given order, without frame input."""
    encoded = bytearray()
    widths = []
    for row in rows:
        if not 0 <= row.uid <= 127 or not 0 <= row.tid < 1 << 32:
            raise ValueError(f"uid/Tid outside v4 widths: {row.uid}/{row.tid}")
        start = len(encoded)
        encoded.append(row.uid * 2)
        encoded.extend(row.tid.to_bytes(4, "little"))
        for value in (row.exp, row.level, row.max_level, row.reset_count):
            encoded.extend(write_doubled(value))
        widths.append(len(encoded) - start)
    return bytes(encoded), widths


def byte_diff(reference, encoded):
    """Count differing positions, including unmatched suffix bytes."""
    count = 0
    first = None
    for i, (want, got) in enumerate(zip_longest(reference, encoded)):
        if want != got:
            count += 1
            if first is None:
                first = (i, want, got)
    return count, first


def check_g4(frames, rows):
    passed = True
    for seq, body in sorted(frames.items()):
        try:
            verify_tail_rule(body[START:END], rows, seq)
        except ValueError as error:
            print(f"tail check failed: {error}")
            passed = False
    encoded, widths = encode_snapshot(rows)
    print(f"encoded from SQLite alone: rows={len(rows)} bytes={len(encoded)} "
          f"widths={dict(sorted(Counter(widths).items()))} sha256={sha256(encoded).hexdigest()}")
    for seq, body in sorted(frames.items()):
        reference = body[START:END]
        count, first = byte_diff(reference, encoded)
        print(f"seq={seq} dec_hex[{START}:{END}] reference={len(reference)} encoded={len(encoded)} "
              f"diff_bytes={count} first_difference={'none' if first is None else first[0]}")
        if first is not None:
            offset, want, got = first
            print(f"  segment_offset={offset} frame_offset={START+offset} "
                  f"reference={want if want is None else hex(want)} "
                  f"encoded={got if got is None else hex(got)}")
        passed &= len(reference) == END - START and count == 0
    print("G4 PASS" if passed else "G4 FAIL")
    return passed


def check(path, gate):
    frames, blob = inputs(path)
    if gate == "G4":
        return 0 if check_g4(frames, sqlite_rows(blob)) else 1
    decoded = {}
    for seq, body in sorted(frames.items()):
        segment = body[START:END]
        records, bounds = decode(segment)
        decoded[seq] = records, bounds
        print(f"seq={seq} proc=1400 first={bounds[0][0]} end={bounds[-1][1]} "
              f"bytes={len(segment)} records={len(records)}")
    print("G1 PASS")
    if gate == "G1":
        return 0
    rows = sqlite_rows(blob)
    passed = True
    for seq, (records, bounds) in decoded.items():
        passed &= compare(seq, records, rows, bounds)
    print("G2 PASS" if passed else "G2 FAIL")
    if not passed or gate == "G2":
        return 0 if passed else 1
    return 0 if check_g4(frames, rows) else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", required=True, action="store_true")
    parser.add_argument("--zip", type=Path, default=ZIP)
    parser.add_argument("--gate", choices=("G1", "G2", "G4", "all"), default="all")
    args = parser.parse_args()
    return check(args.zip, args.gate)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, BadZipFile, sqlite3.Error) as exc:
        print(f"CHECK ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
