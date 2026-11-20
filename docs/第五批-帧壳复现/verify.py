"""Offline G5 fixture check. Exit 0 = PASS, 1 = comparison failed, 2 = input error."""
import argparse
from collections import Counter
from hashlib import sha256
from io import BytesIO
from itertools import zip_longest
import json
from pathlib import Path
import re
from struct import Struct
import sys
from zipfile import BadZipFile, ZipFile


ARCHIVE_DIR = Path(r"C:\Users\admin\Doubao\chats\2026-11-19\new-chat")
RULES = "02-载荷解码规则.md"
SAMPLES = "09-帧壳样本.json"
RULES_SHA = "2efaf89b287d6d672e819bc10df0ca5e763db29f02ef754dcacc4a7b7a34ada0"
SAMPLE_SHA = {
    "v1": "1807fdf86e8ab6430a395adb76c6ded662908aa6d3e41e5af19bbe0e5cbaea97",
    "v2": "eb2ea3583ef3d6e890f658a10ae9f80b5f71af0c6f211dfc16fab57b7542ad82",
}
# The 154 reference frames retain the capture order verified in v1.
RUN_A_ROWS = 56
CONTROL_ROW = 5
HEADER = Struct("<IiH")


def load_inputs(path, edition):
    packed = path.read_bytes()
    print(f"ZIP sha256={sha256(packed).hexdigest()}")
    members = {}
    with ZipFile(BytesIO(packed)) as archive:
        for name, expected in ((RULES, RULES_SHA), (SAMPLES, SAMPLE_SHA[edition])):
            raw = archive.read(name).replace(b"\r\n", b"\n")
            digest = sha256(raw).hexdigest()
            if digest != expected:
                raise ValueError(f"{name} LF sha256 expected={expected} actual={digest}")
            print(f"{name} LF sha256={digest} OK")
            members[name] = raw
    match = re.search(rb"^KEY = ([0-9A-Fa-f\s]+)\n\x60{3}", members[RULES], re.M)
    if not match:
        raise ValueError("02: KEY block missing")
    key = bytes.fromhex(match[1].decode("ascii"))
    if len(key) != 30:
        raise ValueError(f"02: unexpected key length {len(key)}")
    return key, json.loads(members[SAMPLES])["frames"]


def build_frame(body, key):
    size = len(body)
    header = HEADER.pack(size, -size, 0x7fff)
    payload = bytes(byte ^ key[index % len(key)] for index, byte in enumerate(body))
    return header + payload


def difference(reference, generated):
    """Frame-relative, zero-based offsets. Missing or extra bytes count too."""
    count = 0
    first = None
    for offset, (want, got) in enumerate(zip_longest(reference, generated)):
        if want != got:
            count += 1
            if first is None:
                first = (offset, want, got)
    return count, first


def show_byte(value):
    return "<end>" if value is None else f"0x{value:02X}"


def describe(first):
    if first is None:
        return "first=none"
    offset, want, got = first
    return f"first={offset} expected={show_byte(want)} actual={show_byte(got)}"


def negative_control(key, body, reference, label):
    # First byte of the second key period, deliberately beyond the header.
    index = 30
    before = build_frame(body, key)
    baseline, _ = difference(reference, before)
    mutated = bytearray(body)
    mutated[index] ^= 1
    after = build_frame(mutated, key)
    count, first = difference(reference, after)
    predicted = 10 + index
    print(f"CONTROL {label} baseline_diff={baseline} body[{index}]={show_byte(body[index])}"
          f"->{show_byte(mutated[index])} expected_diff=1 expected_first={predicted}")
    print(f"CONTROL actual_diff={count} {describe(first)}")
    passed = (baseline == 0 and body[index] == 0x00 and count == 1
              and first == (predicted, 0x21, 0x20))
    print("CONTROL PASS" if passed else "CONTROL FAIL")
    return passed


def check(path, edition):
    key, frames = load_inputs(path, edition)
    split = RUN_A_ROWS
    groups = (("A", frames[:split]), ("B", frames[split:]))
    eligible = sum(row["body_hex"] is not None for row in frames)
    required = 154 if edition == "v2" else 122
    if (len(frames), eligible) != (154, required):
        raise ValueError(f"input inventory: frames={len(frames)} with_body={eligible}")
    print(f"samples={len(frames)} with_body={eligible} without_body={len(frames)-eligible}")
    run_labels = f"run labels in capture order: A=rows 1..{split}, B=rows {split+1}..{len(frames)}"
    if edition == "v1":
        # Preserve the original log format. seq is displayed only.
        print(f"{run_labels}; seq reset {frames[split-1]['seq']}->{frames[split]['seq']}")
    else:
        print(f"{run_labels}; sample ID = 1-based row; seq is informational only")
    stats = Counter()
    first_failure = None
    ordinal = 0
    for run, rows in groups:
        for row in rows:
            ordinal += 1
            if row["body_hex"] is None:
                continue
            body = bytes.fromhex(row["body_hex"])
            generated = build_frame(body, key)
            reference = bytes.fromhex(row["frame_hex"])
            count, first = difference(reference, generated)
            seq = row["seq"]
            label = f"row={ordinal:03} run={run} seq={seq} dir={row['dir']}"
            stats[run, "checked"] += 1
            stats[run, "equal"] += count == 0
            stats[run, "diff"] += count
            print(f"{label} body_bytes={len(body)} ref_bytes={len(reference)} "
                  f"built_bytes={len(generated)} diff={count} {describe(first)}")
            if first is not None and first_failure is None:
                first_failure = f"{label} diff={count} {describe(first)}"

    for run, rows in groups:
        n = stats[run, "checked"]
        print(f"run={run} rows={len(rows)} with_body={n} equal={stats[run,'equal']}/{n} "
              f"without_body={len(rows)-n} differing_bytes={stats[run,'diff']}")
    total_equal = sum(stats[run, "equal"] for run, _ in groups)
    print(f"positive equal={total_equal}/{eligible} first_failing_frame={first_failure or 'none'}")
    control = frames[CONTROL_ROW - 1]
    control_body = bytes.fromhex(control["body_hex"])
    if len(control_body) <= 30:
        raise ValueError(f"negative-control row {CONTROL_ROW} too short")
    control_label = f"A seq={control['seq']}"
    if edition == "v2":
        control_label = f"row={CONTROL_ROW:03} {control_label}"
    control_ok = negative_control(key, control_body, bytes.fromhex(control["frame_hex"]), control_label)
    passed = total_equal == eligible and control_ok
    print("G5 PASS" if passed else "G5 FAIL")
    return 0 if passed else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.add_argument("--edition", choices=("v1", "v2"), default="v2")
    parser.add_argument("--zip", type=Path)
    args = parser.parse_args()
    filename = ("TFD-第五批-帧壳复现-v2-20261121.zip" if args.edition == "v2"
                else "TFD-第五批-帧壳复现-20261121.zip")
    return check(args.zip or ARCHIVE_DIR / filename, args.edition)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, BadZipFile) as error:
        print(f"INPUT ERROR: {error}", file=sys.stderr)
        sys.exit(2)
