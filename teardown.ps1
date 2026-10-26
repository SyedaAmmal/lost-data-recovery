# Dismounts and deletes only this folder's marked testdisk.vhdx.
# Run from an elevated PowerShell session after recovery work is complete.
$ErrorActionPreference = 'Stop'
$VhdPath = Join-Path $PSScriptRoot 'testdisk.vhdx'
$MarkerName = '.lost-data-recovery-testdisk'

$principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Administrator privileges are required. Open PowerShell as Administrator and run this script again.'
}
if (-not (Test-Path -LiteralPath $VhdPath -PathType Leaf)) {
    Write-Host "Nothing to remove; VHDX not found at $VhdPath."
    return
}

$image = Get-DiskImage -ImagePath $VhdPath
$mountedByTeardown = $false
if (-not $image.Attached) {
    Write-Host 'Temporarily mounting the VHDX read-only to verify its safety marker...'
    $image = Mount-DiskImage -ImagePath $VhdPath -Access ReadOnly -PassThru
    $mountedByTeardown = $true
}

try {
    if (-not $image.Attached) {
        throw 'The expected VHDX could not be attached. Refusing to remove it.'
    }
    $image = Get-DiskImage -ImagePath ([IO.Path]::GetFullPath($VhdPath))
    $disk = $image | Get-Disk
    $expectedPath = [IO.Path]::GetFullPath($VhdPath)
    $actualPath = if ($image.ImagePath) { [IO.Path]::GetFullPath($image.ImagePath) } else { '' }
    if ($actualPath -ne $expectedPath -or
        $disk.BusType -ne 'File Backed Virtual' -or
        $disk.Size -lt 190MB -or $disk.Size -gt 210MB) {
        throw "Safety check failed: the VHDX-derived disk did not match the expected path, bus type, and approximately 200 MiB size (ImagePath=$actualPath, BusType=$($disk.BusType), Size=$($disk.Size)). Refusing to remove it."
    }
    $partitions = Get-Partition -DiskNumber $disk.Number
    $markerFound = $false
    foreach ($partition in $partitions) {
        if (-not $partition.DriveLetter) { continue }
        $markerPath = Join-Path "$($partition.DriveLetter):\" $MarkerName
        if (Test-Path -LiteralPath $markerPath -PathType Leaf) {
            $markerValue = (Get-Content -LiteralPath $markerPath -Raw).Trim()
            if ($markerValue -eq $VhdPath) {
                $markerFound = $true
                break
            }
        }
    }
    if (-not $markerFound) {
        throw "Safety marker not found or did not match $VhdPath. Refusing to delete the VHDX."
    }

    Write-Host "Safety check passed: the attached virtual disk contains this folder's marker."
}
catch {
    if ($mountedByTeardown) {
        Dismount-DiskImage -ImagePath $VhdPath -ErrorAction SilentlyContinue
    }
    throw
}

Write-Host 'Dismounting the verified test VHDX...'
Dismount-DiskImage -ImagePath $VhdPath
Write-Host 'Deleting the verified test VHDX file...'
Remove-Item -LiteralPath $VhdPath
Write-Host 'Teardown complete. Only testdisk.vhdx was removed; scripts, manifest, and logs were kept.'
