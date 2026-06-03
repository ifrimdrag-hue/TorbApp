<#
.SYNOPSIS
    Porneste Torb Logistic local. Configureaza mediul automat la prima rulare,
    inclusiv descarcarea si instalarea Python daca lipseste.
.DESCRIPTION
    1. Verifica daca Python 3.11+ este instalat (il descarca automat daca lipseste).
    2. Creaza un mediu virtual Python daca nu exista.
    3. Instaleaza toate dependentele la prima rulare (sau cu -Install).
    4. Creaza .env din .env.example si genereaza automat FLASK_SECRET_KEY.
    5. Porneste serverul Flask si deschide browserul automat.
.PARAMETER Install
    Forteaza reinstalarea pachetelor pip (foloseste dupa git pull).
.EXAMPLE
    .\tools\Start-Hub.ps1
.EXAMPLE
    .\tools\Start-Hub.ps1 -Install
#>
param(
    [switch]$Install
)

Set-StrictMode -Off

# -- Paths ------------------------------------------------------------------
$Root    = Split-Path $PSScriptRoot -Parent
$Venv    = Join-Path $Root ".venv"
$Pip     = Join-Path $Venv "Scripts\pip.exe"
$Flask   = Join-Path $Venv "Scripts\flask.exe"
$Python  = Join-Path $Venv "Scripts\python.exe"
$EnvFile = Join-Path $Root ".env"
$EnvEx   = Join-Path $Root ".env.example"
$Req     = Join-Path $Root "requirements.txt"
$Port    = 5000
$Url     = "http://127.0.0.1:$Port/"
$MinPyMajor = 3
$MinPyMinor = 11

Write-Host ""
Write-Host "  Torb Logistic" -ForegroundColor Cyan
Write-Host "  --------------------------------" -ForegroundColor DarkGray

# -- Helpers ----------------------------------------------------------------

function Get-PythonVersion {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $cmd) { return $null }
    try {
        $ver = & python -c "import sys; print(sys.version_info.major, sys.version_info.minor)" 2>$null
        if ($ver -match '^(\d+)\s+(\d+)$') {
            return @{ Major = [int]$Matches[1]; Minor = [int]$Matches[2] }
        }
    } catch {}
    return $null
}

function Update-SessionPath {
    $machine = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $user    = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = ($machine, $user | Where-Object { $_ }) -join ";"
}

function Install-Python {
    Write-Host ""
    Write-Host "  Python $MinPyMajor.$MinPyMinor+ nu a fost gasit. Instalare automata..." -ForegroundColor Cyan

    # -- Try winget first (Windows 10 1709+ si Windows 11) ------------------
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Host "  Folosind winget..." -ForegroundColor DarkGray
        winget install --id Python.Python.3 --silent --scope user `
            --accept-package-agreements --accept-source-agreements
        Update-SessionPath
        $v = Get-PythonVersion
        if ($v -and ($v.Major -gt $MinPyMajor -or ($v.Major -eq $MinPyMajor -and $v.Minor -ge $MinPyMinor))) {
            Write-Host "  Python $($v.Major).$($v.Minor) instalat." -ForegroundColor Green
            return
        }
        Write-Host "  winget a terminat, dar Python nu a fost detectat. Se incearca descarcarea directa." -ForegroundColor Yellow
    }

    # -- Fallback: descarcare direct de la python.org -----------------------
    Write-Host "  Se cauta ultima versiune Python de pe python.org..." -ForegroundColor DarkGray
    $installerVersion = $null
    try {
        $page = Invoke-WebRequest -Uri "https://www.python.org/downloads/windows/" `
                    -UseBasicParsing -TimeoutSec 15
        $match = [regex]::Match($page.Content, 'python-(\d+\.\d+\.\d+)-amd64\.exe')
        if ($match.Success) { $installerVersion = $match.Groups[1].Value }
    } catch {}

    if (-not $installerVersion) {
        Write-Host ""
        Write-Host "  EROARE: Nu s-a putut determina ultima versiune Python." -ForegroundColor Red
        Write-Host "  Instaleaza Python $MinPyMajor.$MinPyMinor+ manual:" -ForegroundColor Yellow
        Write-Host "    https://www.python.org/downloads/" -ForegroundColor White
        Write-Host "  La instalare, bifeaza: Add Python to PATH" -ForegroundColor Yellow
        Write-Host ""
        exit 1
    }

    $installerUrl  = "https://www.python.org/ftp/python/$installerVersion/python-$installerVersion-amd64.exe"
    $installerPath = Join-Path $env:TEMP "python-$installerVersion-amd64.exe"

    Write-Host "  Descarcare Python $installerVersion..." -ForegroundColor DarkGray
    try {
        Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath -UseBasicParsing
    } catch {
        Write-Host "  EROARE: Descarcarea a esuat: $_" -ForegroundColor Red
        exit 1
    }

    Write-Host "  Instalare Python $installerVersion (per-user, fara drepturi de administrator)..." -ForegroundColor DarkGray
    $proc = Start-Process -FilePath $installerPath `
                -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_test=0" `
                -Wait -PassThru
    Remove-Item $installerPath -ErrorAction SilentlyContinue

    if ($proc.ExitCode -ne 0) {
        Write-Host "  EROARE: Instalatorul Python a iesit cu codul $($proc.ExitCode)." -ForegroundColor Red
        exit 1
    }

    Update-SessionPath
    $v = Get-PythonVersion
    if ($v -and ($v.Major -gt $MinPyMajor -or ($v.Major -eq $MinPyMajor -and $v.Minor -ge $MinPyMinor))) {
        Write-Host "  Python $($v.Major).$($v.Minor) instalat." -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "  Python a fost instalat, dar nu este inca disponibil in aceasta sesiune." -ForegroundColor Yellow
        Write-Host "  Inchide aceasta fereastra, deschide un PowerShell nou si ruleaza din nou." -ForegroundColor Yellow
        Write-Host ""
        exit 0
    }
}

# -- Python check -----------------------------------------------------------
$pyVer = Get-PythonVersion
$pyOk  = $pyVer -and ($pyVer.Major -gt $MinPyMajor -or
                      ($pyVer.Major -eq $MinPyMajor -and $pyVer.Minor -ge $MinPyMinor))

if (-not $pyOk) {
    Install-Python
}

# -- Virtual environment ----------------------------------------------------
if (-not (Test-Path $Venv)) {
    Write-Host ""
    Write-Host "  Creare mediu virtual Python..." -ForegroundColor Cyan
    python -m venv $Venv
    if (-not $?) {
        Write-Host "  EROARE: Nu s-a putut crea mediul virtual." -ForegroundColor Red
        exit 1
    }
    Write-Host "  Mediu virtual creat." -ForegroundColor Green
    $Install = $true
}

# -- Dependencies -----------------------------------------------------------
if ($Install -or -not (Test-Path $Flask)) {
    Write-Host ""
    Write-Host "  Instalare dependente (poate dura cateva minute la prima rulare)..." -ForegroundColor Cyan
    & $Pip install -r $Req --prefer-binary --quiet
    if (-not $?) {
        Write-Host "  EROARE: pip install a esuat. Verifica conexiunea la internet si incearca din nou." -ForegroundColor Red
        exit 1
    }
    Write-Host "  Dependente instalate." -ForegroundColor Green
}

# -- Credentials / .env -----------------------------------------------------
if (-not (Test-Path $EnvFile)) {
    if (Test-Path $EnvEx) {
        Copy-Item $EnvEx $EnvFile
    }

    # Auto-generate FLASK_SECRET_KEY so sessions work out of the box
    $secretKey = & $Python -c "import secrets; print(secrets.token_hex(32))"
    if ($secretKey) {
        (Get-Content $EnvFile) -replace 'change-me-generate-with-secrets-token-hex-32', $secretKey |
            Set-Content $EnvFile -Encoding utf8
        Write-Host ""
        Write-Host "  Fisierul .env a fost creat si FLASK_SECRET_KEY generat automat." -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "  Fisierul .env a fost creat din .env.example." -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "  Aplicatia porneste, dar unele functii necesita credentiale." -ForegroundColor Yellow
    Write-Host "  Completeaza optionalele in: $EnvFile" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "    ANTHROPIC_API_KEY    - pentru functii AI (console.anthropic.com)" -ForegroundColor DarkGray
    Write-Host "    EMAG_USERNAME        - pentru sincronizare stoc eMAG" -ForegroundColor DarkGray
    Write-Host "    EMAG_PASSWORD        - pentru sincronizare stoc eMAG" -ForegroundColor DarkGray
    Write-Host "    SHOPIFY_SHOP         - pentru sincronizare stoc Shopify" -ForegroundColor DarkGray
    Write-Host "    SHOPIFY_ACCESS_TOKEN - pentru sincronizare stoc Shopify" -ForegroundColor DarkGray
    Write-Host ""
}

# -- Stop any existing server on the same port ------------------------------
$existing = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
if ($existing) {
    $ownPids = $existing | Select-Object -ExpandProperty OwningProcess | Sort-Object -Unique
    foreach ($ownPid in $ownPids) {
        $proc = Get-Process -Id $ownPid -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host "  Oprire server existent (PID $ownPid)..." -ForegroundColor Yellow
            Stop-Process -Id $ownPid -Force -ErrorAction SilentlyContinue
        }
    }
    Start-Sleep -Seconds 1
}

# -- Start ------------------------------------------------------------------
Write-Host ""
Write-Host "  Pornire server la $Url" -ForegroundColor Green
Write-Host "  Apasa Ctrl+C pentru a opri." -ForegroundColor DarkGray
Write-Host ""

# Deschide browserul dupa ce Flask raspunde (polling pana la 30 sec)
$null = Start-Job -ScriptBlock {
    param($u)
    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 1
        try {
            $r = Invoke-WebRequest -Uri $u -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
            if ($r.StatusCode -lt 500) { break }
        } catch {}
    }
    Start-Process $u
} -ArgumentList $Url

Set-Location $Root
& $Python app\app.py
