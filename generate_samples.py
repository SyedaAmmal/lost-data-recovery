"""Generate test files on the marked virtual disk and record their hashes.

Requires Pillow: python -m pip install Pillow
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import string
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

try:
    from PIL import Image
except ImportError:
    print("Pillow is required. Install it with: python -m pip install Pillow", file=sys.stderr)
    raise SystemExit(2)

SCRIPT_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = SCRIPT_DIR / "manifest_before.json"
MARKER_NAME = ".lost-data-recovery-testdisk"
FILES = [
    ("sample_01_notes.txt", "text", 10_240),
    ("sample_02_meeting.txt", "text", 131_072),
    ("sample_03_journal.txt", "text", 1_048_576),
    ("sample_04_photo.jpg", "jpeg", 0),
    ("sample_05_map.png", "png", 0),
    ("sample_06_report.pdf", "pdf", 49_152),
    ("sample_07_manual.pdf", "pdf", 3_145_728),
    ("sample_08_memo.docx", "docx", 32_768),
    ("sample_09_minutes.docx", "docx", 524_288),
    ("sample_10_sales.csv", "csv", 20_480),
    ("sample_11_contacts.csv", "csv", 262_144),
    ("sample_12_inventory.csv", "csv", 2_097_152),
    ("sample_13_archive.txt", "text", 4_500_000),
    ("sample_14_readings.csv", "csv", 10_240),
    ("sample_15_portrait.jpg", "jpeg", 0),
]


def check_test_volume(root: Path) -> Path:
    """Require the marker setup_test_disk.ps1 writes to the VHDX volume."""
    marker = root / MARKER_NAME
    if not root.is_dir() or not marker.is_file():
        raise ValueError(f"{root} is not a marked test volume. Run setup_test_disk.ps1 and use its TEST DRIVE.")
    vhd_path = Path(marker.read_text(encoding="ascii").strip())
    expected = (SCRIPT_DIR / "testdisk.vhdx").resolve()
    if not vhd_path.is_absolute() or vhd_path.resolve() != expected or not expected.is_file():
        raise ValueError(f"Safety marker does not point to this folder's testdisk.vhdx: {marker}")
    return root


def sized_text(seed: str, target_size: int) -> bytes:
    data = (seed + "\n").encode("utf-8")
    repeats = (target_size + len(data) - 1) // len(data)
    return (data * repeats)[:target_size]


def write_pdf(path: Path, target_size: int) -> None:
    """Write a small valid PDF; harmless PDF comment padding sets its size."""
    stream = b"BT /F1 12 Tf 72 720 Td (Lost Data Retrieval test document) Tj ET\n"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    padding_size = max(0, target_size - 700)
    padding = b"%" + b"x" * max(0, padding_size - 3) + b"\n"
    content = stream + padding
    objects.append(b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n" + content + b"endstream")
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("ascii") + obj + b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii"))
    path.write_bytes(pdf)


def write_docx(path: Path, target_size: int) -> None:
    """Create a minimal valid OOXML Word document with padded document text."""
    rng = random.Random(path.name)
    text = "".join(rng.choices(string.ascii_letters + string.digits + " ", k=target_size))
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body><w:p><w:r><w:t xml:space="preserve">' + escape(text) +
        '</w:t></w:r></w:p><w:sectPr/></w:body></w:document>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '</Types>'
    )
    relationships = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '</Relationships>'
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", relationships)
        archive.writestr("word/document.xml", document_xml)


def write_csv(path: Path, target_size: int) -> None:
    header = "record_id,category,description,value\n"
    row = '"{index:06d}","sample","Synthetic recovery-test record {index}",{value}\n'
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(header)
        index = 0
        while handle.tell() < target_size:
            handle.write(row.format(index=index, value=(index * 17) % 10000))
            index += 1


def write_image(path: Path, kind: str, seed: int) -> None:
    random.seed(seed)
    if kind == "png":
        image = Image.effect_noise((1024, 1024), 90).convert("RGB")
        image.save(path, format="PNG", optimize=False)
    else:
        image = Image.effect_noise((512, 512), 85).convert("RGB")
        image.save(path, format="JPEG", quality=88)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Create 15 sample files on the marked test VHDX volume.")
    parser.add_argument("drive_root", help="The TEST DRIVE printed by setup_test_disk.ps1, for example X:\\")
    args = parser.parse_args()
    root = check_test_volume(Path(args.drive_root).resolve())
    print(f"Verified test-volume marker for {root}")
    print("Generating 15 synthetic text, image, PDF, DOCX, and CSV files...")
    manifest = []
    for index, (name, kind, size) in enumerate(FILES):
        path = root / name
        print(f"Creating {name} ({kind}) ...")
        if kind == "text":
            path.write_bytes(sized_text(f"Synthetic recovery test file: {name}", size))
        elif kind == "csv":
            write_csv(path, size)
        elif kind == "pdf":
            write_pdf(path, size)
        elif kind == "docx":
            write_docx(path, size)
        else:
            write_image(path, kind, index + 1)
        actual_size = path.stat().st_size
        if not 10_240 <= actual_size <= 5_000_000:
            raise RuntimeError(f"Generated size outside the requested range: {name} is {actual_size} bytes")
        manifest.append({"name": name, "size": actual_size, "sha256": sha256_file(path)})
        print(f"  {actual_size:,} bytes; SHA-256 {manifest[-1]['sha256']}")

    payload = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "test_volume": str(root),
        "files": manifest,
    }
    MANIFEST_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Manifest saved: {MANIFEST_PATH}")
    print(f"Created {len(manifest)} files. Leave this volume idle before attempting recovery.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
