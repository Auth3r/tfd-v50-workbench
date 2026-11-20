"""Read-only evidence audit. A missing body contract is not a codec failure."""
import hashlib
import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[3]
HANDOFF = Path(r"E:\第二后裔\TFD发布端V50\TFD发布端V50\handoff")
ROOT = HANDOFF.parent
manifest = json.loads((HANDOFF / "01-资产清单.json").read_text(encoding="utf-8-sig"))
index = {a["path"]: a for a in manifest["assets"]}
checks = []
for key in [r"unpacked\evidence\reflected-structures.json",
            str(PROJECT / "V50-ACCOUNT-LIST-CONTRACT.md"),
            str(PROJECT / "V50-SAVE-MAPPING.md")]:
    path = Path(key) if Path(key).is_absolute() else ROOT / key
    data = path.read_bytes()
    actual = hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()
    expected = index[key]["sha256"]
    checks.append({"path": str(path), "expected": expected, "actual_normalized": actual,
                   "match": actual == expected})
    if actual != expected:
        raise SystemExit(f"ASSET_MISMATCH: {path}")
    print(f"ASSET_MATCH {path.name} sha256_lf={actual}")

reflected = json.loads((ROOT / r"unpacked\evidence\reflected-structures.json").read_bytes())
schemas = {}
for name in ["M1AccountSimpleInfo", "M1CharacterSimpleInfo"]:
    definition = reflected["structs"][name]
    schemas[name] = {"size_candidate": definition["size_candidate"],
                     "descriptor_count": definition["descriptor_count"],
                     "fields": [{k: prop[k] for k in ["name", "gen_flags", "memory_offset_candidate", "synthetic_inner"]}
                                for prop in definition["properties"]]}
    print(f"{name}: native_size_candidate={definition['size_candidate']}; descriptors={definition['descriptor_count']}")
print("SOURCE_LIMITATIONS=" + json.dumps(reflected["limitations"], ensure_ascii=False))

result = {"status": "BLOCKED_MISSING_BODY_MAPPING_CONTRACT", "assets": checks,
          "schemas": schemas, "source_limitations": reflected["limitations"],
          "m03_character_columns": ["uid", "account_uid", "template_id", "exp", "level", "max_level",
                                     "reset_count", "state_json", "revision", "updated_at"],
          "source_columns_without_approved_simpleinfo_mapping": ["exp", "reset_count", "state_json", "revision", "updated_at"],
          "target_fields_without_approved_m03_values": ["EigenFactorLevel", "Favorites", "SelectedLoadoutSlotIndex", "Customizes", "CustomizeOptions", "Paints"],
          "missing": ["Approved M03 snapshot -> account/character body field mapping",
                      "Approved body field serialization rules; memory offsets are not serialization",
                      "Versioned static SHAPE excerpt (patch_v50.log has no expected asset hash)"],
          "m01c_touched": False, "encoder_implemented": False}
(Path(__file__).parent / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print("M03 columns without approved SimpleInfo mapping: " + ", ".join(result["source_columns_without_approved_simpleinfo_mapping"]))
print("SimpleInfo fields without approved M03 values: " + ", ".join(result["target_fields_without_approved_m03_values"]))
print("M04 NOT COMPLETE: no default values, synthetic wire format, or M01c work introduced")
raise SystemExit(1)
