# Creates and formats only the testdisk.vhdx located beside this script.
# Run from an elevated PowerShell session.
[CmdletBinding()]
param(
    [ValidateSet('NTFS', 'FAT32')]
    [string]$FileSystem = 'NTFS'
)

$ErrorActionPreference = 'Stop'
$VhdPath = Join-Path $PSScriptRoot 'testdisk.vhdx'
$MarkerName = '.lost-data-recovery-testdisk'

$principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Administrator privileges are required. Open PowerShell as Administrator and run this script again.'
}

if (Test-Path -LiteralPath $VhdPath) {
    try {
        $existingImage = Get-DiskImage -ImagePath $VhdPath -ErrorAction Stop
        if ($existingImage.Attached) {
            Dismount-DiskImage -ImagePath $VhdPath -ErrorAction Stop
        }
    }
    catch {
        throw "Found an existing testdisk.vhdx at $VhdPath but could not safely inspect or detach it. Remove it manually before rerunning setup. Details: $($_.Exception.Message)"
    }
    throw "Found an existing testdisk.vhdx at $VhdPath. It has been detached if it was attached. Remove the file manually before rerunning setup."
}

Write-Host "Creating a 200 MB expandable VHDX at $VhdPath ..."
$diskpartScript = Join-Path $env:TEMP ("ldr-create-{0}.txt" -f [guid]::NewGuid())
try {
    @(
        "create vdisk file=`"$VhdPath`" maximum=200 type=expandable",
        'attach vdisk',
        'exit'
    ) | Set-Content -LiteralPath $diskpartScript -Encoding ASCII
    & diskpart.exe /s $diskpartScript
    if ($LASTEXITCODE -ne 0) {
        throw "DiskPart failed with exit code $LASTEXITCODE. No disk initialization or formatting was attempted."
    }
}
finally {
    Remove-Item -LiteralPath $diskpartScript -Force -ErrorAction SilentlyContinue
}

$image = Get-DiskImage -ImagePath ([IO.Path]::GetFullPath($VhdPath))
if (-not $image.Attached) {
    throw 'The newly created VHDX is not attached. Refusing to initialize or format any disk.'
}
$disk = $image | Get-Disk
$expectedPath = [IO.Path]::GetFullPath($VhdPath)
$actualPath = if ($image.ImagePath) { [IO.Path]::GetFullPath($image.ImagePath) } else { '' }
if ($actualPath -ne $expectedPath -or
    $disk.BusType -ne 'File Backed Virtual' -or
    $disk.Size -lt 190MB -or $disk.Size -gt 210MB) {
    throw "Safety check failed: the VHDX-derived disk did not match the expected path, bus type, and approximately 200 MiB size (ImagePath=$actualPath, BusType=$($disk.BusType), Size=$($disk.Size)). Refusing to continue."
}

Write-Host "Safety check passed: disk $($disk.Number) is the attached file-backed virtual disk at $VhdPath."
Write-Host "Initializing as GPT and creating one $FileSystem partition ..."
$disk | Initialize-Disk -PartitionStyle GPT -PassThru | Out-Null
$partition = New-Partition -DiskNumber $disk.Number -UseMaximumSize -AssignDriveLetter
$volume = Format-Volume -Partition $partition -FileSystem $FileSystem -NewFileSystemLabel 'LDR_TEST' -Confirm:$false -Force
$driveRoot = "$($volume.DriveLetter):\"
Set-Content -LiteralPath (Join-Path $driveRoot $MarkerName) -Value $VhdPath -Encoding ASCII

Write-Host "Formatted test volume as $FileSystem."
Write-Host "TEST DRIVE: $driveRoot"
Write-Host 'Safety marker written to the test volume. Use only this drive for the exercise.'
