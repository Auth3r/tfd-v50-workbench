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


DEFAULT_ZIP = Path(r"C:\Users\admin\Doubao\chats\2026-11-19\new-chat\TFD-第五批-帧壳复现-20261121.zip")
RULES = "02-载荷解码规则.md"
SAMPLES = "09-帧壳样本.json"
PINS = {
    RULES: "2efaf89b287d6d672e819bc10df0ca5e763db29f02ef754dcacc4a7b7a34ada0",
    SAMPLES: "1807fdf86e8ab6430a395adb76c6ded662908aa6d3e41e5af19bbe0e5cbaea97",
}
HEADER = Struct("<IiH")


def load_inputs(path):
    packed = path.read_bytes()
    print(f"ZIP sha256={sha256(packed).hexdigest()}")
    members = {}
    with ZipFile(BytesIO(packed)) as archive:
        for name, expected in PINS.items():
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


def negative_control(key, body, reference):
    # First byte of the second key period, deliberately beyond the header.
    index = 30
    before = build_frame(body, key)
    baseline, _ = difference(reference, before)
    mutated = bytearray(body)
    mutated[index] ^= 1
    after = build_frame(mutated, key)
    count, first = difference(reference, after)
    predicted = 10 + index
    print(f"CONTROL A seq=12 baseline_diff={baseline} body[{index}]={show_byte(body[index])}"
          f"->{show_byte(mutated[index])} expected_diff=1 expected_first={predicted}")
    print(f"CONTROL actual_diff={count} {describe(first)}")
    passed = baseline == 0 and count == 1 and first == (
        predicted, reference[predicted], reference[predicted] ^ 1
    )
    print("CONTROL PASS" if passed else "CONTROL FAIL")
    return passed


def check(path):
    key, frames = load_inputs(path)
    boundaries = [i for i in range(1, len(frames)) if frames[i]["seq"] < frames[i - 1]["seq"]]
    if len(boundaries) != 1:
        raise ValueError(f"expected two ordered captures; seq reset indices={boundaries}")
    split, = boundaries
    groups = (("A", frames[:split]), ("B", frames[split:]))
    eligible = sum(row["body_hex"] is not None for row in frames)
    if (len(frames), eligible) != (154, 122):
        raise ValueError(f"input inventory: frames={len(frames)} with_body={eligible}")
    print(f"samples={len(frames)} with_body={eligible} without_body={len(frames)-eligible}")
    print(f"run labels in capture order: A=rows 1..{split}, B=rows {split+1}..{len(frames)}; "
          f"seq reset {frames[split-1]['seq']}->{frames[split]['seq']}")
    stats = Counter()
    first_failure = None
    control = None
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
            if run == "A" and seq == 12 and row["dir"] == "out":
                control = (body, reference)

    for run, rows in groups:
        n = stats[run, "checked"]
        print(f"run={run} rows={len(rows)} with_body={n} equal={stats[run,'equal']}/{n} "
              f"without_body={len(rows)-n} differing_bytes={stats[run,'diff']}")
    total_equal = sum(stats[run, "equal"] for run, _ in groups)
    print(f"positive equal={total_equal}/{eligible} first_failing_frame={first_failure or 'none'}")
    if control is None or len(control[0]) <= 30:
        raise ValueError("negative-control fixture A seq=12 missing or too short")
    control_ok = negative_control(key, *control)
    passed = total_equal == eligible and control_ok
    print("G5 PASS" if passed else "G5 FAIL")
    return 0 if passed else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.add_argument("--zip", type=Path, default=DEFAULT_ZIP)
    args = parser.parse_args()
    return check(args.zip)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, BadZipFile) as error:
        print(f"INPUT ERROR: {error}", file=sys.stderr)
        sys.exit(2)
