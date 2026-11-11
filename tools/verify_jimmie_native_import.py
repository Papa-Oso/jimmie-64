"""Verify the frozen native import; no writes, model loading, or game launch."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-source", action="store_true")
    parser.add_argument("--check-personal", action="store_true")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "docs/jimmie/native-baseline-manifest.json").read_text())
    source = (ROOT / manifest["source_snapshot"]).resolve()
    personal = ROOT.parent / "jimmie-64"
    errors = []
    checked = {"imported": 0, "canonical_source": 0, "personal": 0}
    def check(path, expected, label, category):
        try:
            actual = digest(path)
        except OSError as exc:
            errors.append(f"{label}: {exc}")
            return
        checked[category] += 1
        if actual != expected:
            errors.append(f"{label}: hash differs from frozen import")
    for item in manifest["files"]:
        check(ROOT / item["path"], item["source_sha256"], item["path"], "imported")
        if args.check_source:
            check(source / item["path"], item["source_sha256"], "source:" + item["path"], "canonical_source")
    if args.check_personal:
        for item in manifest["protected_personal_files"]:
            check(personal / item["path"], item["sha256"], "personal:" + item["path"], "personal")
    print(json.dumps({"passed": not errors, "checked": checked, "errors": errors,
        "limits": "Frozen byte-level import verification only; Git text normalization or deliberate later changes require separate comparison, not overwriting history."}, indent=2))
    return int(bool(errors))

if __name__ == "__main__":
    raise SystemExit(main())
