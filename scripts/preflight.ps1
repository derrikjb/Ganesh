$HardMissing = $false

Write-Host "Ganesh AI Assistant - Environment Preflight Check"
Write-Host "================================================"

function Check-Version {
    param (
        [string]$Name,
        [string]$Cmd,
        [string]$MinVer,
        [bool]$Hard
    )

    $currentVer = $null
    try {
        if ($Cmd -eq "python3") {
            $currentVer = & python --version 2>&1
        } else {
            $currentVer = & $Cmd --version 2>&1
        }
        
        if ($currentVer -match '(\d+\.\d+\.\d+)') {
            $currentVer = $Matches[1]
        } else {
            throw "Version not found"
        }
    } catch {
        if ($Hard) {
            Write-Host "[FAIL] $Name is missing (Required >= $MinVer)" -ForegroundColor Red
            $global:HardMissing = $true
        } else {
            Write-Host "[WARN] $Name is missing (Optional)" -ForegroundColor Yellow
        }
        return
    }

    $major = [int]($currentVer.Split('.')[0])
    $minMajor = [int]($MinVer.Split('.')[0])

    if ($major -lt $minMajor) {
        if ($Hard) {
            Write-Host "[FAIL] $Name version $currentVer < $MinVer" -ForegroundColor Red
            $global:HardMissing = $true
        } else {
            Write-Host "[WARN] $Name version $currentVer < $MinVer" -ForegroundColor Yellow
        }
    } else {
        Write-Host "[PASS] $Name $currentVer" -ForegroundColor Green
    }
}

Check-Version -Name "Python" -Cmd "python3" -MinVer "3.11.0" -Hard $true
Check-Version -Name "Node.js" -Cmd "node" -MinVer "20.0.0" -Hard $true
Check-Version -Name "npm" -Cmd "npm" -MinVer "10.0.0" -Hard $true

try {
    $rustVer = & rustc --version
    if ($rustVer -match 'rustc (\d+\.\d+\.\d+)') {
        Write-Host "[PASS] Rust $($Matches[1])" -ForegroundColor Green
    }
} catch {
    Write-Host "[FAIL] Rust (cargo) is missing. Install from https://rustup.rs/" -ForegroundColor Red
    $global:HardMissing = $true
}

try {
    $tauriVer = & cargo tauri --version
    if ($tauriVer -match '(\d+\.\d+\.\d+)') {
        Write-Host "[PASS] Tauri CLI $($Matches[1])" -ForegroundColor Green
    }
} catch {
    Write-Host "[WARN] Tauri CLI is missing. Install with: cargo install tauri-cli --version '^2.0.0-beta'" -ForegroundColor Yellow
}

$drive = Get-PSDrive C
$freeSpaceGB = [math]::Round($drive.Free / 1GB, 2)
if ($freeSpaceGB -lt 5) {
    Write-Host "[WARN] Low disk space: $($freeSpaceGB)GB free (Recommended >= 5GB)" -ForegroundColor Yellow
} else {
    Write-Host "[PASS] Disk space: $($freeSpaceGB)GB free" -ForegroundColor Green
}

Write-Host "------------------------------------------------"
if ($global:HardMissing) {
    Write-Host "Preflight check failed. Please install missing requirements." -ForegroundColor Red
    exit 1
} else {
    Write-Host "Preflight check passed!" -ForegroundColor Green
    exit 0
}
