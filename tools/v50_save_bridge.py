"""Offline SQLite <-> typed Rust roster acceptance. Python standard library only."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import subprocess
import tempfile
from pathlib import Path

TABLES = {
    "A": ("accounts", ("uid", "name", "created_at"), {1, 2}),
    "C": ("characters", ("uid", "account_uid", "template_id", "exp", "level", "max_level",
                         "reset_count", "state_json", "revision", "updated_at"), {7, 9}),
    "S": ("account_character_selection", ("account_uid", "character_uid"), set()),
}
PROJECT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def readonly(path: Path) -> sqlite3.Connection:
    # A main-file digest cannot authorize a different logical state from a WAL.
    wal = Path(str(path) + "-wal")
    if wal.exists() and wal.stat().st_size:
        raise RuntimeError(f"Nonempty WAL requires an approved stationary snapshot: {wal}")
    c = sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    c.execute("PRAGMA query_only=ON")
    return c


def read_rows(c: sqlite3.Connection) -> dict[str, list[tuple]]:
    rows = {}
    for tag, (table, columns, _) in TABLES.items():
        actual = tuple(r[1] for r in c.execute(f'PRAGMA table_info("{table}")'))
        if actual != columns:
            raise RuntimeError(f"Unmapped columns in {table}: {actual}")
        fields = ",".join(f'"{name}"' for name in columns)
        rows[tag] = c.execute(f'SELECT {fields} FROM "{table}" ORDER BY 1').fetchall()
    return rows


def encode_exchange(rows: dict[str, list[tuple]]) -> str:
    lines = ["TFD-SAVE/1"]
    for tag, (_, _, text_columns) in TABLES.items():
        for row in rows[tag]:
            values = [v.encode("utf-8").hex() if i in text_columns else str(v)
                      for i, v in enumerate(row)]
            lines.append("\t".join([tag, *values]))
    return "\n".join(lines) + "\n"


def decode_exchange(path: Path) -> dict[str, list[tuple]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "TFD-SAVE/1":
        raise RuntimeError("Wrong Rust exchange version")
    rows = {tag: [] for tag in TABLES}
    for line in lines[1:]:
        tag, *values = line.split("\t")
        _, columns, text_columns = TABLES[tag]
        if len(values) != len(columns):
            raise RuntimeError("Wrong column count")
        rows[tag].append(tuple(bytes.fromhex(v).decode("utf-8") if i in text_columns else int(v)
                               for i, v in enumerate(values)))
    return rows


def apply_rows(c: sqlite3.Connection, rows: dict[str, list[tuple]]) -> None:
    for tag, (table, columns, _) in TABLES.items():
        fields = ",".join(f'"{name}"' for name in columns)
        placeholders = ",".join("?" for _ in columns)
        # The copy retains all other tables and identifiers. Replace mapped
        # values explicitly with the Rust-decoded data, under its original keys.
        keys = ("account_uid",) if tag == "S" else ("uid",)
        key_sql = ",".join(f'"{name}"' for name in keys)
        updates = ",".join(f'"{name}"=excluded."{name}"' for name in columns if name not in keys)
        sql = (f'INSERT INTO "{table}" ({fields}) VALUES ({placeholders}) '
               f'ON CONFLICT({key_sql}) DO UPDATE SET {updates}')
        c.executemany(sql, rows[tag])


def verify(source: Path, expected: str, expected_count: int, tool: Path, parent: Path) -> dict:
    source_bytes = source.read_bytes()
    before = hashlib.sha256(source_bytes).hexdigest()
    if before != expected:
        raise RuntimeError(f"Binary asset mismatch: {source}; expected={expected}; actual={before}")
    print(f"SOURCE {source.name} binary_sha256={before} MATCH", flush=True)
    output = Path(tempfile.mkdtemp(prefix=source.stem + "-", dir=parent))
    # Pin exactly the approved main-file bytes on F:. Never open the active
    # source through SQLite, checkpoint it, or incorporate an unapproved WAL.
    pinned = output / "approved-main.sqlite3"
    pinned.write_bytes(source_bytes)
    if digest(pinned) != expected:
        raise RuntimeError("Pinned main-file copy changed")
    wal = Path(str(source) + "-wal")
    source_wal_present = wal.exists() and wal.stat().st_size > 0
    print(f"PINNED approved main-file bytes on F:; source_wal_present={source_wal_present}; live WAL not applied", flush=True)
    with readonly(pinned) as c:
        original = read_rows(c)
        if len(original["C"]) != expected_count:
            raise RuntimeError(f"Expected {expected_count} characters, found {len(original['C'])}")
        input_path, mapped_path = output / "input.tsv", output / "mapped.tsv"
        input_path.write_text(encode_exchange(original), encoding="utf-8", newline="\n")
        subprocess.run([str(tool), str(input_path), str(mapped_path)], check=True)
        mapped = decode_exchange(mapped_path)
        if mapped != original:
            raise RuntimeError("Rust struct exchange changed a field")
        copy = output / "roundtrip.sqlite3"
        if copy.resolve() == source.resolve():
            raise RuntimeError("Destination must be a new copy")
        with sqlite3.connect(copy) as destination:
            c.backup(destination)
    with sqlite3.connect(copy) as c:
        c.execute("PRAGMA foreign_keys=ON")
        c.execute("UPDATE characters SET template_id=0,exp=0,level=0,max_level=0,reset_count=0,"
                  "state_json='{}',revision=0,updated_at='M03-before-restore'")
        c.commit()
        damaged = read_rows(c)
        changed = sum(a != b for a, b in zip(damaged["C"], original["C"]))
        if changed != expected_count:
            raise RuntimeError("The copy was not changed before testing restoration")
        apply_rows(c, mapped)
        c.commit()
        restored = read_rows(c)
        if restored != original:
            raise RuntimeError("SQLite copy differs after restoration")
        if c.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise RuntimeError("SQLite copy integrity failure")
        if c.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("SQLite copy foreign key failure")
    after = digest(source)
    if after != before:
        raise RuntimeError("Original database changed during acceptance")
    for row in restored["C"]:
        print(f"character uid={row[0]} account_uid={row[1]} fields=10/10 equal", flush=True)
    print(f"ROUNDTRIP {source.name}: characters={expected_count}, restored_after_scrub={changed}, "
          f"all_mapped_fields=equal, original_sha256_unchanged=true, integrity=ok", flush=True)
    return {"source": str(source), "source_sha256_before": before, "source_sha256_after": after,
            "pinned_main_file": str(pinned), "source_wal_present": source_wal_present,
            "live_wal_applied": False, "copy": str(copy), "characters": expected_count, "accounts": len(original["A"]),
            "selections": len(original["S"]), "character_fields_equal": expected_count * 10,
            "all_mapped_rows_equal": True, "restored_after_scrub": changed}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--handoff", type=Path, required=True)
    p.add_argument("--tool", type=Path, required=True)
    p.add_argument("--evidence", type=Path, required=True)
    args = p.parse_args()
    args.evidence.resolve().relative_to(PROJECT / "docs" / "evidence")
    args.evidence.mkdir(parents=True, exist_ok=True)
    root = args.handoff.resolve().parent
    manifest = json.loads((args.handoff / "01-资产清单.json").read_text(encoding="utf-8-sig"))
    index = {a["path"]: a for a in manifest["assets"]}
    keys = [(r"data\launcher\saves\04f2858b03d3e1f379515d84ba575f03\characters.sqlite3", 36),
            (r"data\launcher\saves\local_runtime.sqlite3", 1)]
    parent = PROJECT / "target" / "m03-evidence"
    parent.mkdir(parents=True, exist_ok=True)
    results = [verify(root / key, index[key]["sha256"], count, args.tool.resolve(), parent)
               for key, count in keys]
    (args.evidence / "result.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("M03 PASS: main roster=36; runtime roster=1 separately; no account merge; source databases untouched")


if __name__ == "__main__":
    main()
