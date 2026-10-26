"""Compare recovered files with the pre-deletion manifest and deletion log."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_MANIFEST = SCRIPT_DIR / "manifest_before.json"
DEFAULT_DELETION_LOG = SCRIPT_DIR / "deletion_log.csv"
DEFAULT_REPORT = SCRIPT_DIR / "recovery_report.csv"
STATUSES = ("FULLY RECOVERED", "CORRUPTED/PARTIAL", "NOT RECOVERED")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify recovered files against the original manifest.")
    parser.add_argument("recovered_folder", type=Path, help="A separate folder containing recovered files")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--deletion-log", type=Path, default=DEFAULT_DELETION_LOG)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    recovered_root = args.recovered_folder.resolve()
    if not recovered_root.is_dir():
        parser.error(f"Recovered folder does not exist: {recovered_root}")
    if not args.manifest.is_file():
        parser.error(f"Manifest not found: {args.manifest}")
    if not args.deletion_log.is_file():
        parser.error(f"Deletion log not found: {args.deletion_log}. Run delete_files.ps1 first.")

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    original_by_name = {entry["name"]: entry for entry in manifest["files"]}
    with args.deletion_log.open("r", encoding="utf-8-sig", newline="") as handle:
        deleted_names = {
            row["FileName"] for row in csv.DictReader(handle)
            if row.get("Status") == "DELETED" and row.get("FileName") in original_by_name
        }
    if not deleted_names:
        parser.error("The deletion log contains no successfully deleted files present in the manifest.")

    recovered_by_name: dict[str, list[Path]] = {}
    for candidate in recovered_root.rglob("*"):
        if candidate.is_file():
            recovered_by_name.setdefault(candidate.name, []).append(candidate)

    rows = []
    counts = {status: 0 for status in STATUSES}
    print(f"Recovery verification for: {recovered_root}")
    print(f"{'FILE':32}  {'STATUS':19}  {'SIZE (BYTES)':>12}")
    print("-" * 70)
    for name in sorted(deleted_names):
        original = original_by_name[name]
        candidates = recovered_by_name.get(name, [])
        matches = [path for path in candidates if sha256_file(path) == original["sha256"]]
        if matches:
            status = "FULLY RECOVERED"
            recovered_path = str(matches[0])
            recovered_size = matches[0].stat().st_size
        elif candidates:
            status = "CORRUPTED/PARTIAL"
            recovered_path = str(candidates[0])
            recovered_size = candidates[0].stat().st_size
        else:
            status = "NOT RECOVERED"
            recovered_path = ""
            recovered_size = ""
        counts[status] += 1
        rows.append({
            "FileName": name,
            "Status": status,
            "OriginalSizeBytes": original["size"],
            "OriginalSHA256": original["sha256"],
            "RecoveredPath": recovered_path,
            "RecoveredSizeBytes": recovered_size,
        })
        shown_size = str(recovered_size) if recovered_size != "" else "-"
        print(f"{name:32}  {status:19}  {shown_size:>12}")

    total = len(deleted_names)
    rate = counts["FULLY RECOVERED"] / total * 100
    print("-" * 70)
    print(f"Summary: {counts['FULLY RECOVERED']} fully recovered, "
          f"{counts['CORRUPTED/PARTIAL']} corrupted/partial, "
          f"{counts['NOT RECOVERED']} not recovered; recovery rate {rate:.1f}% ({total} deleted files).")

    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "FileName", "Status", "OriginalSizeBytes", "OriginalSHA256",
            "RecoveredPath", "RecoveredSizeBytes",
        ])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Detailed results written to: {args.report.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
