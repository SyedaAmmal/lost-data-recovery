# Performs ordinary filesystem deletion on exactly eight named test files.
# Requires the mounted testdisk.vhdx and its safety marker.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z]:?$')]
    [string]$DriveLetter
)

$ErrorActionPreference = 'Stop'
$VhdPath = Join-Path $PSScriptRoot 'testdisk.vhdx'
$MarkerName = '.lost-data-recovery-testdisk'
$letter = $DriveLetter.TrimEnd(':').ToUpperInvariant()
$driveRoot = "$letter`:\"
$logPath = Join-Path $PSScriptRoot 'deletion_log.csv'
$filesToDelete = @(
    'sample_01_notes.txt',
    'sample_04_photo.jpg',
    'sample_06_report.pdf',
    'sample_08_memo.docx',
    'sample_10_sales.csv',
    'sample_12_inventory.csv',
    'sample_13_archive.txt',
    'sample_15_portrait.jpg'
)

$principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Administrator privileges are required to verify the attached virtual disk. Re-run in an elevated PowerShell session.'
}
if (-not (Test-Path -LiteralPath $VhdPath -PathType Leaf)) {
    throw "Expected VHDX not found: $VhdPath. Refusing to delete any files."
}
$image = Get-DiskImage -ImagePath ([IO.Path]::GetFullPath($VhdPath))
if (-not $image.Attached) {
    throw 'The expected test VHDX is not attached. Refusing to delete any files.'
}
$disk = $image | Get-Disk
$expectedPath = [IO.Path]::GetFullPath($VhdPath)
$actualPath = if ($image.ImagePath) { [IO.Path]::GetFullPath($image.ImagePath) } else { '' }
if ($actualPath -ne $expectedPath -or
    $disk.BusType -ne 'File Backed Virtual' -or
    $disk.Size -lt 190MB -or $disk.Size -gt 210MB) {
    throw "Safety check failed: the VHDX-derived disk did not match the expected path, bus type, and approximately 200 MiB size (ImagePath=$actualPath, BusType=$($disk.BusType), Size=$($disk.Size)). Refusing to delete any files."
}
$partition = Get-Partition -DiskNumber $disk.Number | Where-Object { $_.DriveLetter -eq $letter }
if (-not $partition) {
    throw "Drive $driveRoot is not a partition on the attached test VHDX. Refusing to delete any files."
}
$markerPath = Join-Path $driveRoot $MarkerName
if (-not (Test-Path -LiteralPath $markerPath -PathType Leaf) -or
    (Get-Content -LiteralPath $markerPath -Raw).Trim() -ne $VhdPath) {
    throw 'Safety marker is missing or does not identify this script folder''s testdisk.vhdx. Refusing to delete any files.'
}

Write-Host "Safety check passed: $driveRoot maps to this folder's testdisk.vhdx."
Write-Host 'Deleting the selected files with normal Remove-Item (not secure erase).'
$deletedCount = 0
foreach ($name in $filesToDelete) {
    $target = Join-Path $driveRoot $name
    if (-not (Test-Path -LiteralPath $target -PathType Leaf)) {
        Write-Warning "Not found; leaving unchanged: $name"
        continue
    }
    Remove-Item -LiteralPath $target
    $timestamp = [DateTime]::UtcNow.ToString('o')
    [pscustomobject]@{
        FileName = $name
        DeletedAtUtc = $timestamp
        Status = 'DELETED'
        FullPath = $target
    } | Export-Csv -LiteralPath $logPath -NoTypeInformation -Append -Encoding UTF8
    $deletedCount++
    Write-Host "Deleted $name at $timestamp (UTC)"
}
Write-Host "Deletion complete: $deletedCount of $($filesToDelete.Count) selected files deleted."
Write-Host "Deletion log: $logPath"
Write-Host 'Stop writing to this volume now. Do not copy recovered files back onto it.'
