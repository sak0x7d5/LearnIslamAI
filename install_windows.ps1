[CmdletBinding()]
param(
    [switch] $Launch,
    [switch] $Dev,
    [ValidateRange(1, 65535)]
    [int] $Port = 8000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$UvVersion = "0.11.29"
$PythonVersion = "3.12"
$ProjectRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)

if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -ne "AMD64") {
    throw "IslamAI v0.1 supports 64-bit x86 Windows only."
}

$ConfiguredRuntimeRoot = $env:ISLAMAI_HOME
if ([string]::IsNullOrWhiteSpace($ConfiguredRuntimeRoot)) {
    $LocalAppData = [Environment]::GetFolderPath("LocalApplicationData")
    if ([string]::IsNullOrWhiteSpace($LocalAppData)) {
        throw "Windows did not provide a LocalAppData directory."
    }
    $RuntimeRoot = Join-Path $LocalAppData "IslamAI"
}
else {
    if (-not [System.IO.Path]::IsPathRooted($ConfiguredRuntimeRoot)) {
        throw "ISLAMAI_HOME must be an absolute Windows path."
    }
    $RuntimeRoot = [System.IO.Path]::GetFullPath($ConfiguredRuntimeRoot)
    $PathRoot = [System.IO.Path]::GetPathRoot($RuntimeRoot)
    if ($RuntimeRoot.TrimEnd('\') -eq $PathRoot.TrimEnd('\')) {
        throw "ISLAMAI_HOME cannot be the root of a drive."
    }
}

$UvInstallDir = Join-Path $RuntimeRoot "tools\uv"
$ManagedUv = Join-Path $UvInstallDir "uv.exe"
$PythonInstallDir = Join-Path $RuntimeRoot "tools\python"
$VenvPath = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvPath "Scripts\python.exe"
$ChainlitRuntimeRoot = $null

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string] $FilePath,
        [Parameter(Mandatory = $true)]
        [string[]] $Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

function Get-UvVersion {
    param([Parameter(Mandatory = $true)][string] $Candidate)

    if (-not (Test-Path -LiteralPath $Candidate -PathType Leaf)) {
        return $null
    }

    try {
        $versionOutput = & $Candidate --version 2>$null
        if ($LASTEXITCODE -eq 0 -and $versionOutput -match '^uv\s+([0-9]+\.[0-9]+\.[0-9]+)') {
            return $Matches[1]
        }
    }
    catch {
        return $null
    }

    return $null
}

function Install-PinnedUv {
    New-Item -ItemType Directory -Path $UvInstallDir -Force | Out-Null
    $installerUrl = "https://astral.sh/uv/$UvVersion/install.ps1"

    Write-Host "Installing uv $UvVersion for IslamAI..."
    try {
        $installerResponse = Invoke-WebRequest -UseBasicParsing -Uri $installerUrl
        if ($installerResponse.Content -is [byte[]]) {
            $installer = [Text.Encoding]::UTF8.GetString($installerResponse.Content)
        }
        else {
            $installer = [string]$installerResponse.Content
        }
    }
    catch {
        throw "Could not download the pinned uv installer from $installerUrl. Check your connection and try again. $($_.Exception.Message)"
    }

    if ([string]::IsNullOrWhiteSpace($installer)) {
        throw "The pinned uv installer download was empty."
    }

    $previousUnmanagedInstall = $env:UV_UNMANAGED_INSTALL
    $previousNoModifyPath = $env:UV_NO_MODIFY_PATH
    try {
        $env:UV_UNMANAGED_INSTALL = $UvInstallDir
        $env:UV_NO_MODIFY_PATH = "1"
        Invoke-Expression $installer
    }
    finally {
        $env:UV_UNMANAGED_INSTALL = $previousUnmanagedInstall
        $env:UV_NO_MODIFY_PATH = $previousNoModifyPath
    }

    if ((Get-UvVersion -Candidate $ManagedUv) -ne $UvVersion) {
        throw "uv $UvVersion was not installed at the expected path: $ManagedUv"
    }

    return $ManagedUv
}

function Find-PinnedUv {
    if ((Get-UvVersion -Candidate $ManagedUv) -eq $UvVersion) {
        return $ManagedUv
    }

    $systemUv = Get-Command "uv.exe" -ErrorAction SilentlyContinue
    if ($null -ne $systemUv -and (Get-UvVersion -Candidate $systemUv.Source) -eq $UvVersion) {
        return $systemUv.Source
    }

    return (Install-PinnedUv)
}

function Test-VenvPython312 {
    if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
        return $false
    }

    try {
        & $VenvPython -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" 2>$null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

function Reset-InvalidVenv {
    param([Parameter(Mandatory = $true)][string] $UvPath)

    if (-not (Test-Path -LiteralPath $VenvPath)) {
        return
    }

    if (Test-VenvPython312) {
        return
    }

    $resolvedVenv = [System.IO.Path]::GetFullPath($VenvPath)
    $expectedVenv = [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot ".venv"))
    if (-not $resolvedVenv.Equals($expectedVenv, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to reset an unexpected virtual environment path: $resolvedVenv"
    }

    Write-Host "Replacing an invalid or broken .venv with Python $PythonVersion..."
    Invoke-CheckedCommand -FilePath $UvPath -Arguments @(
        "venv", "--clear", "--force", "--python", $PythonVersion, $VenvPath
    )
}

function Set-IslamAiRuntimeEnvironment {
    $cacheRoot = Join-Path $RuntimeRoot "cache"
    $modelRoot = Join-Path $RuntimeRoot "models"
    $directories = @(
        $RuntimeRoot,
        $cacheRoot,
        (Join-Path $cacheRoot "uv"),
        $modelRoot,
        (Join-Path $modelRoot "embedding_models"),
        (Join-Path $modelRoot "huggingface"),
        (Join-Path $RuntimeRoot "vector_indices"),
        (Join-Path $RuntimeRoot "corpus\versions"),
        (Join-Path $RuntimeRoot "corpus\staging"),
        (Join-Path $RuntimeRoot "state"),
        $PythonInstallDir
    )
    foreach ($directory in $directories) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }

    $env:ISLAMAI_HOME = $RuntimeRoot
    $env:HF_HOME = Join-Path $modelRoot "huggingface"
    $env:SENTENCE_TRANSFORMERS_HOME = Join-Path $modelRoot "embedding_models"
    $env:UV_CACHE_DIR = Join-Path $cacheRoot "uv"
    $env:UV_PYTHON_INSTALL_DIR = $PythonInstallDir
    $env:CHAINLIT_HOST = "127.0.0.1"
    $env:CHAINLIT_PORT = $Port.ToString([System.Globalization.CultureInfo]::InvariantCulture)
}

function Get-LoopbackServiceState {
    param([Parameter(Mandatory = $true)][int] $CandidatePort)

    try {
        $existing = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$CandidatePort" -TimeoutSec 2
        if ($existing.Content -match '<title>IslamAI</title>') {
            return "IslamAI"
        }
    }
    catch {
        # Fall through to a TCP probe so a non-HTTP or erroring service is not
        # mistaken for a free port.
    }

    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $connect = $client.ConnectAsync("127.0.0.1", $CandidatePort)
        if ($connect.Wait(1000) -and $client.Connected) {
            return "Occupied"
        }
        return "Free"
    }
    catch {
        return "Free"
    }
    finally {
        $client.Dispose()
    }
}

function Get-ChainlitRuntimeConfig {
    param(
        [Parameter(Mandatory = $true)][string] $ConfigText,
        [Parameter(Mandatory = $true)][int] $CandidatePort
    )

    $originPattern = '(?m)^[ \t]*allow_origins[ \t]*=[^\r\n]*'
    $originMatches = [regex]::Matches($ConfigText, $originPattern)
    if ($originMatches.Count -ne 1) {
        throw "Expected exactly one Chainlit origin allowlist entry."
    }

    $originLine = 'allow_origins = ["http://127.0.0.1:{0}", "http://localhost:{0}"]' -f $CandidatePort
    return [regex]::Replace($ConfigText, $originPattern, $originLine)
}

function New-ChainlitRuntimeRoot {
    param([Parameter(Mandatory = $true)][int] $CandidatePort)

    $runtimeParent = Join-Path $RuntimeRoot "runtime"
    New-Item -ItemType Directory -Path $runtimeParent -Force | Out-Null
    $runtimeName = "chainlit-$PID-$([Guid]::NewGuid().ToString('N'))"
    $runtimeApp = Join-Path $runtimeParent $runtimeName
    $runtimeConfigDir = Join-Path $runtimeApp ".chainlit"
    New-Item -ItemType Directory -Path $runtimeConfigDir -Force | Out-Null

    $sourceConfig = Join-Path $ProjectRoot ".chainlit\config.toml"
    $runtimeConfig = Join-Path $runtimeConfigDir "config.toml"
    $configText = [System.IO.File]::ReadAllText($sourceConfig)
    $updatedConfig = Get-ChainlitRuntimeConfig -ConfigText $configText -CandidatePort $CandidatePort
    [System.IO.File]::WriteAllText(
        $runtimeConfig,
        $updatedConfig,
        [System.Text.UTF8Encoding]::new($false)
    )

    # Chainlit reads UI strings from <app root>/.chainlit/translations and fills
    # in its own defaults when the folder is missing, which would drop the
    # project's customized footer disclaimer.
    Copy-Item -LiteralPath (Join-Path $ProjectRoot ".chainlit\translations") -Destination $runtimeConfigDir -Recurse
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "public") -Destination $runtimeApp -Recurse
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "chainlit.md") -Destination $runtimeApp
    return $runtimeApp
}

function Remove-ChainlitRuntimeRoot {
    param([Parameter(Mandatory = $true)][string] $RuntimeApp)

    $resolved = [System.IO.Path]::GetFullPath($RuntimeApp)
    $expectedParent = [System.IO.Path]::GetFullPath((Join-Path $RuntimeRoot "runtime"))
    if (-not [System.IO.Path]::GetDirectoryName($resolved).Equals(
        $expectedParent,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Refusing to remove an unexpected Chainlit runtime path: $resolved"
    }
    if (Test-Path -LiteralPath $resolved) {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}

try {
    if ($Launch) {
        $loopbackState = Get-LoopbackServiceState -CandidatePort $Port
        if ($loopbackState -eq "IslamAI") {
            Write-Host "IslamAI is already available at http://127.0.0.1:$Port."
            Write-Host "Open that address instead of starting a duplicate server."
            return
        }
        if ($loopbackState -eq "Occupied") {
            throw "Port $Port is already used by another local service. Choose a free -Port value."
        }
    }

    Set-IslamAiRuntimeEnvironment
    $uv = Find-PinnedUv

    Write-Host "Preparing managed Python $PythonVersion..."
    Invoke-CheckedCommand -FilePath $uv -Arguments @(
        "python", "install", $PythonVersion, "--install-dir", $PythonInstallDir,
        "--no-bin", "--no-registry", "--no-progress"
    )

    Reset-InvalidVenv -UvPath $uv

    $syncArguments = @("sync", "--locked", "--python", $PythonVersion)
    if ($Dev) {
        Write-Host "Synchronizing the locked CPU-only runtime and development tools..."
        $syncArguments += @("--group", "dev")
    }
    else {
        Write-Host "Synchronizing the locked CPU-only runtime..."
        $syncArguments += "--no-dev"
    }
    $syncArguments += @("--project", $ProjectRoot, "--no-progress")
    Invoke-CheckedCommand -FilePath $uv -Arguments $syncArguments

    if (-not (Test-VenvPython312)) {
        throw "The environment did not produce a working Python 3.12 interpreter."
    }

    Invoke-CheckedCommand -FilePath $VenvPython -Arguments @(
        "-c",
        "import faiss, torch; import sentence_transformers; import langchain_huggingface"
    )

    Write-Host "IslamAI runtime is ready at $VenvPath"
    Write-Host "Application data will be stored at $RuntimeRoot"

    if ($Launch) {
        $ChainlitRuntimeRoot = New-ChainlitRuntimeRoot -CandidatePort $Port
        $env:CHAINLIT_APP_ROOT = $ChainlitRuntimeRoot
        Write-Host "Opening IslamAI at http://127.0.0.1:$Port"
        Invoke-CheckedCommand -FilePath $uv -Arguments @(
            "run", "--no-sync", "--project", $ProjectRoot,
            "chainlit", "run", (Join-Path $ProjectRoot "src\app.py"),
            "--host", "127.0.0.1", "--port", $Port.ToString()
        )
    }
}
catch {
    Write-Error $_
    exit 1
}
finally {
    if ($null -ne $ChainlitRuntimeRoot) {
        Remove-ChainlitRuntimeRoot -RuntimeApp $ChainlitRuntimeRoot
    }
}
