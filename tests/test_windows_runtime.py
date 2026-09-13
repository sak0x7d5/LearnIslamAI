from __future__ import annotations

import re
import subprocess
import tomllib
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"
LOCK_PATH = PROJECT_ROOT / "uv.lock"
INSTALLER_PATH = PROJECT_ROOT / "install_windows.ps1"
LAUNCHER_PATH = PROJECT_ROOT / "start_windows.bat"

REQUIRED_RUNTIME_PACKAGES = {
    "chainlit",
    "faiss-cpu",
    "langchain-huggingface",
    "platformdirs",
    "pydantic",
    "sentence-transformers",
    "torch",
}
BANNED_PACKAGES = {
    "faiss-gpu",
    "nvidia-cublas-cu12",
    "nvidia-cuda-runtime-cu12",
    "torchaudio",
    "torchvision",
}
DEV_PACKAGES = {"pytest", "pytest-asyncio", "pytest-mock", "ruff"}


def _dependency_names(dependencies: list[str]) -> set[str]:
    return {
        re.split(r"[<>=!~;\s\[]", dependency, maxsplit=1)[0].lower() for dependency in dependencies
    }


def _load_pyproject() -> dict:
    with PYPROJECT_PATH.open("rb") as pyproject_file:
        return tomllib.load(pyproject_file)


def test_runtime_is_pinned_to_python_312_and_uv() -> None:
    config = _load_pyproject()

    assert config["project"]["requires-python"] == "==3.12.*"
    assert config["tool"]["uv"]["required-version"] == "==0.11.29"
    assert config["tool"]["uv"]["package"] is False
    assert (PROJECT_ROOT / ".python-version").read_text(encoding="utf-8").strip() == "3.12"


def test_end_user_dependencies_are_cpu_only_and_minimal() -> None:
    config = _load_pyproject()
    runtime_dependencies = config["project"]["dependencies"]
    runtime_names = _dependency_names(runtime_dependencies)

    assert REQUIRED_RUNTIME_PACKAGES <= runtime_names
    assert DEV_PACKAGES.isdisjoint(runtime_names)
    assert BANNED_PACKAGES.isdisjoint(runtime_names)
    assert "langchain-huggingface" in runtime_names
    assert "sentence-transformers" in runtime_names


def test_torch_uses_explicit_cpu_index() -> None:
    config = _load_pyproject()

    assert config["tool"]["uv"]["sources"]["torch"] == {"index": "pytorch-cpu"}
    cpu_index = next(
        index for index in config["tool"]["uv"]["index"] if index["name"] == "pytorch-cpu"
    )
    assert cpu_index["url"] == "https://download.pytorch.org/whl/cpu"
    assert cpu_index["explicit"] is True


def test_developer_tools_are_isolated_in_dev_group() -> None:
    config = _load_pyproject()
    dev_names = _dependency_names(config["dependency-groups"]["dev"])

    assert dev_names == DEV_PACKAGES
    assert config["tool"]["uv"]["default-groups"] == []


def test_lock_is_python_312_cpu_only() -> None:
    lock_content = LOCK_PATH.read_text(encoding="utf-8").lower()

    assert 'requires-python = "==3.12.*"' in lock_content
    assert 'name = "torch"' in lock_content
    assert "https://download.pytorch.org/whl/cpu" in lock_content
    for package in BANNED_PACKAGES:
        assert f'name = "{package}"' not in lock_content


def test_installer_bootstraps_without_python_and_syncs_locked_runtime() -> None:
    installer = INSTALLER_PATH.read_text(encoding="utf-8")
    lowered = installer.lower()

    assert "https://astral.sh/uv/$UvVersion/install.ps1" in installer
    assert '"python", "install", $PythonVersion' in installer
    assert '$syncArguments = @("sync", "--locked", "--python", $PythonVersion)' in installer
    assert '$syncArguments += "--no-dev"' in installer
    assert '$syncArguments += @("--group", "dev")' in installer
    assert "pip install" not in lowered
    assert "nvidia-smi" not in lowered
    assert "nvcc" not in lowered
    assert "cuda" not in lowered


def test_installer_handles_broken_venv_and_uses_local_app_data() -> None:
    installer = INSTALLER_PATH.read_text(encoding="utf-8")

    assert "Test-VenvPython312" in installer
    assert '"venv", "--clear", "--force", "--python", $PythonVersion, $VenvPath' in installer
    assert '[Environment]::GetFolderPath("LocalApplicationData")' in installer
    assert "$ConfiguredRuntimeRoot = $env:ISLAMAI_HOME" in installer
    assert "ISLAMAI_HOME must be an absolute Windows path" in installer
    assert "ISLAMAI_HOME cannot be the root of a drive" in installer
    for variable in (
        "ISLAMAI_HOME",
        "HF_HOME",
        "SENTENCE_TRANSFORMERS_HOME",
        "UV_CACHE_DIR",
        "UV_PYTHON_INSTALL_DIR",
        "CHAINLIT_HOST",
        "CHAINLIT_PORT",
    ):
        assert f"$env:{variable}" in installer


def test_launcher_is_space_safe_and_loopback_only() -> None:
    installer = INSTALLER_PATH.read_text(encoding="utf-8")
    launcher = LAUNCHER_PATH.read_text(encoding="utf-8")

    assert 'pushd "%~dp0"' in launcher
    assert '-File "%~dp0install_windows.ps1" -Launch' in launcher
    assert '"--host", "127.0.0.1"' in installer
    assert '"--port", $Port.ToString()' in installer
    assert "[int] $Port = 8000" in installer
    assert "instead of starting a duplicate server" in installer
    assert 'return "Occupied"' in installer
    assert "already used by another local service" in installer
    assert "<title>IslamAI</title>" in installer
    assert "/project/settings" not in installer
    assert "New-ChainlitRuntimeRoot" in installer
    assert "allow_origins" in installer
    assert "$env:CHAINLIT_APP_ROOT = $ChainlitRuntimeRoot" in installer
    assert '"--no-sync", "--project", $ProjectRoot' in installer


def test_runtime_origin_rewrite_accepts_default_and_custom_ports() -> None:
    escaped_path = str(INSTALLER_PATH).replace("'", "''")
    powershell_test = (
        "$tokens=$null; $errors=$null; "
        f"$ast=[System.Management.Automation.Language.Parser]::ParseFile('{escaped_path}', "
        "[ref]$tokens, [ref]$errors); "
        "$function=$ast.Find({ param($node) "
        "$node -is [System.Management.Automation.Language.FunctionDefinitionAst] "
        "-and $node.Name -eq 'Get-ChainlitRuntimeConfig' }, $true); "
        "if ($null -eq $function) { throw 'Config helper not found.' }; "
        "Invoke-Expression $function.Extent.Text; "
        "$config=('[project]', "
        '\'allow_origins = ["http://127.0.0.1:8000", "http://localhost:8000"]\', '
        "'') -join [Environment]::NewLine; "
        "$default=Get-ChainlitRuntimeConfig -ConfigText $config -CandidatePort 8000; "
        "if ($default -ne $config) { throw 'Default-port config changed unexpectedly.' }; "
        "$custom=Get-ChainlitRuntimeConfig -ConfigText $config -CandidatePort 8123; "
        "if (-not $custom.Contains('127.0.0.1:8123') -or "
        "-not $custom.Contains('localhost:8123')) { throw 'Custom port was not applied.' }; "
        "$missingThrew=$false; try { Get-ChainlitRuntimeConfig "
        "-ConfigText (('[project]', 'cache = false', '') -join [Environment]::NewLine) "
        "-CandidatePort 8000 } "
        "catch { $missingThrew=$true }; "
        "if (-not $missingThrew) { throw 'Missing allowlist was accepted.' }; "
        "$duplicateThrew=$false; try { Get-ChainlitRuntimeConfig "
        "-ConfigText ($config + $config) -CandidatePort 8000 } "
        "catch { $duplicateThrew=$true }; "
        "if (-not $duplicateThrew) { throw 'Duplicate allowlists were accepted.' }"
    )
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            powershell_test,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def _installer_function_prelude(function_name: str) -> str:
    escaped_path = str(INSTALLER_PATH).replace("'", "''")
    return (
        "$tokens=$null; $errors=$null; "
        f"$ast=[System.Management.Automation.Language.Parser]::ParseFile('{escaped_path}', "
        "[ref]$tokens, [ref]$errors); "
        "$function=$ast.Find({ param($node) "
        "$node -is [System.Management.Automation.Language.FunctionDefinitionAst] "
        f"-and $node.Name -eq '{function_name}' }}, $true); "
        f"if ($null -eq $function) {{ throw '{function_name} not found.' }}; "
        "Invoke-Expression $function.Extent.Text; "
    )


def test_launch_port_falls_back_only_when_not_explicit() -> None:
    powershell_test = _installer_function_prelude("Resolve-LaunchPort") + (
        "$busyBelow8002={ param($p) if ($p -lt 8002) { 'Occupied' } else { 'Free' } }; "
        "$free={ param($p) 'Free' }; "
        "$runningAt8001={ param($p) if ($p -eq 8000) { 'Occupied' } "
        "elseif ($p -eq 8001) { 'IslamAI' } else { 'Free' } }; "
        "$allBusy={ param($p) 'Occupied' }; "
        "$r=Resolve-LaunchPort -RequestedPort 8000 -Explicit $false -Probe $free; "
        "if ($r.Port -ne 8000 -or $r.State -ne 'Free') { throw 'Free default port was not kept.' }; "
        "$r=Resolve-LaunchPort -RequestedPort 8000 -Explicit $false -Probe $busyBelow8002; "
        "if ($r.Port -ne 8002 -or $r.State -ne 'Free') { throw 'Did not skip to the next free port.' }; "
        "$r=Resolve-LaunchPort -RequestedPort 8000 -Explicit $false -Probe $runningAt8001; "
        "if ($r.Port -ne 8001 -or $r.State -ne 'IslamAI') { throw 'Running instance was not detected.' }; "
        "$explicitThrew=$false; try { Resolve-LaunchPort -RequestedPort 8000 -Explicit $true "
        "-Probe $busyBelow8002 } catch { $explicitThrew=$_.ToString() }; "
        "if (-not $explicitThrew -or -not $explicitThrew.Contains('Choose a free -Port value')) "
        "{ throw 'Explicit occupied port did not fail loudly.' }; "
        "$exhaustedThrew=$false; try { Resolve-LaunchPort -RequestedPort 8000 -Explicit $false "
        "-Probe $allBusy -MaxAttempts 3 } catch { $exhaustedThrew=$_.ToString() }; "
        "if (-not $exhaustedThrew -or -not $exhaustedThrew.Contains('No free loopback port')) "
        "{ throw 'Exhausted scan did not fail.' }"
    )
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            powershell_test,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_launcher_uses_resolved_port_before_configuring_runtime() -> None:
    installer = INSTALLER_PATH.read_text(encoding="utf-8")

    resolve = installer.index('-Explicit $PSBoundParameters.ContainsKey("Port")')
    reassign = installer.index("$Port = $resolved.Port")
    runtime_env = installer.index("Set-IslamAiRuntimeEnvironment\n")
    runtime_root = installer.index("New-ChainlitRuntimeRoot -CandidatePort $Port")
    assert resolve < reassign < runtime_env < runtime_root
    assert "IslamAI will use free port" in installer


def test_powershell_installer_parses() -> None:
    escaped_path = str(INSTALLER_PATH).replace("'", "''")
    parse_command = (
        "$errors=$null; "
        f"[System.Management.Automation.Language.Parser]::ParseFile('{escaped_path}', "
        "[ref]$null, [ref]$errors) > $null; "
        "if ($errors.Count -gt 0) { $errors | ForEach-Object { Write-Error $_ }; exit 1 }"
    )
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            parse_command,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_default_app_home_does_not_duplicate_application_name(monkeypatch) -> None:
    import core.config as config

    captured = {}

    def fake_user_data_path(**kwargs):
        captured.update(kwargs)
        return Path("C:/Users/example/AppData/Local/IslamAI")

    monkeypatch.setattr(config, "user_data_path", fake_user_data_path)

    assert config.default_app_home() == Path("C:/Users/example/AppData/Local/IslamAI")
    assert captured == {"appname": "IslamAI", "appauthor": False, "roaming": False}


def test_chainlit_session_files_use_the_mutable_app_home() -> None:
    import core.config as config

    assert config.CHAINLIT_FILES_DIR == config.APP_HOME / "runtime_files"
    assert config.ROOT_DIR not in config.CHAINLIT_FILES_DIR.parents


def test_direct_runtime_rejects_unsafe_app_home_values() -> None:
    import core.config as config

    with pytest.raises(RuntimeError, match="absolute"):
        config.resolve_app_home("relative/runtime")
    with pytest.raises(RuntimeError, match="root of a drive"):
        config.resolve_app_home(Path.cwd().anchor)

    safe = Path.cwd() / "path with spaces" / "IslamAI"
    assert config.resolve_app_home(safe) == safe.resolve()
