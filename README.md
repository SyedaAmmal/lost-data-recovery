# Lost Data Retrieval Lab

A safe, repeatable lab for simulating accidental file deletion and testing recovery tools on NTFS and FAT32. Built for Month 2 of the Cyber Security internship at Arch Technologies.

> Everything runs on a 200 MB virtual disk (VHDX) created by the scripts. Use it only in a safe, authorized test environment. Never point these scripts or a recovery tool at a real drive, partition or someone else's data.

## What it does

1. `setup_test_disk.ps1` creates the virtual disk, formats it as NTFS or FAT32 and writes a safety marker.
2. `generate_samples.py` creates 15 synthetic files (text, JPEG, PNG, PDF, DOCX, CSV) and saves their SHA-256 hashes in `manifest_before.json`.
3. `delete_files.ps1` deletes 8 of them with ordinary deletion (not secure erase) and logs the times in `deletion_log.csv`. The other 7 are untouched control files.
4. You scan the virtual drive with Recuva or TestDisk and recover to a folder on a different drive.
5. `verify_recovery.py` compares the recovered files with the manifest by SHA-256 and reports FULLY RECOVERED, CORRUPTED/PARTIAL or NOT RECOVERED, with a recovery rate and a `recovery_report.csv`.
6. `teardown.ps1` dismounts and deletes only the test VHDX.

## Safety design

- Every script operates only on the `testdisk.vhdx` next to it.
- Each script finds the disk through the image path, requires bus type "File Backed Virtual" and a size of about 200 MB, and checks a marker file on the volume before acting.
- Setup refuses to run if an old image exists. Administrator rights are required.
- Recovered files must always go to a folder on another drive, never back onto the test volume.

## Results

Same experiment on both file systems, 8 deleted files each:

| File system | Tool | Fully recovered | Corrupted/partial | Not recovered | Recovery rate |
|---|---|---|---|---|---|
| NTFS | Recuva | 8 | 0 | 0 | 100.0% |
| NTFS | TestDisk | 8 | 0 | 0 | 100.0% |
| FAT32 | Recuva | 0 | 8 | 0 | 0.0% |
| FAT32 | TestDisk | 0 | 8 | 0 | 0.0% |

On NTFS both tools restored every file byte for byte (hashes matched). On FAT32 both tools found all 8 file names and sizes, but none of the recovered files matched the original hashes.

A byte-level check of the 8 FAT32 files recovered by TestDisk showed that most contents were missing (share of non-zero bytes): sample_01_notes.txt 3.13%, sample_04_photo.jpg 5.35%, and 0.00% for sample_06_report.pdf, sample_08_memo.docx, sample_10_sales.csv, sample_12_inventory.csv, sample_13_archive.txt and sample_15_portrait.jpg. The 7 control files measured 99.56% to 100% non-zero, so the measurement is valid.

The cause of the FAT32 result was not determined. Possible factors, none of them tested: how FAT32 releases the cluster chain on delete, the virtual disk layer, and discard/TRIM behaviour on the host.

`results/` holds the manifests, deletion logs and verification reports from each run. `results/ntfs` contains only the TestDisk report: the Recuva NTFS verification output was not archived as a file (the 8/8 result is documented in the project report). Windows user paths in the reports were replaced with `<user>`.

## Requirements

- Windows 10/11, an elevated (Administrator) PowerShell
- Python 3.10+ and Pillow (`python -m pip install Pillow`)
- [Recuva](https://www.ccleaner.com/recuva) and [TestDisk](https://www.cgsecurity.org/wiki/TestDisk) from their official sites

Tested with Windows 11, Python 3.13, Pillow 12.3.0, Recuva 1.55.133 and TestDisk 7.3-WIP.

## Run order

Run in an Administrator PowerShell, in this folder:

```powershell
.\setup_test_disk.ps1 -FileSystem NTFS      # or FAT32; note the TEST DRIVE letter it prints
python .\generate_samples.py D:\            # use the printed drive letter
.\delete_files.ps1 -DriveLetter D
# Scan the test drive with Recuva or TestDisk and recover to a folder on C:
python .\verify_recovery.py "C:\path\to\recovered-folder"
.\teardown.ps1
```

Archive the manifest, log and report from each run before starting the next file system, since the scripts overwrite them.

## Notes

Built with an AI coding agent under my review, then run and checked by me. Synthetic data only.
