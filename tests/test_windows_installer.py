"""Run the Windows installer with fake native commands; no pip or database access."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell installer")
ROOT = Path(__file__).resolve().parents[1]
STAGES = ["venv", "version", "pip", "application", "init"]

STUB = r"""
using System;
using System.IO;
using System.Reflection;
class InstallerStub {
    static int Main(string[] args) {
        string command = String.Join(" ", args);
        string stage = command.StartsWith("-m venv ") ? "venv" :
            command.StartsWith("-c ") ? "version" :
            command.StartsWith("-m pip install --upgrade ") ? "pip" :
            command.StartsWith("-m pip install --no-build-isolation ") ? "application" :
            command == "init" ? "init" : "unexpected";
        File.AppendAllText("commands.log", stage + "\n");
        if (stage == "unexpected") return 99;
        if (Environment.GetEnvironmentVariable("CLASSIFIRE_TEST_FAIL_STAGE") == stage) return 42;
        if (stage == "venv") {
            string scripts = Path.Combine(".venv", "Scripts");
            Directory.CreateDirectory(scripts);
            string source = Assembly.GetExecutingAssembly().Location;
            File.Copy(source, Path.Combine(scripts, "python.exe"));
            File.Copy(source, Path.Combine(scripts, "classifire.exe"));
        }
        return 0;
    }
}
"""


@pytest.fixture(scope="module")
def native_stub(tmp_path_factory):
    folder = tmp_path_factory.mktemp("installer-native-stub")
    source = folder / "stub.cs"
    source.write_text(STUB, encoding="utf-8")
    compiler = Path(os.environ["WINDIR"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    assert compiler.is_file(), "Windows installer checks require the system C# compiler"
    binary = folder / "py.exe"
    subprocess.run(  # noqa: S603 - fixed compiler and synthetic temporary source
        [str(compiler), "/nologo", "/target:exe", f"/out:{binary}", str(source)],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return binary


def run_installer(tmp_path, native_stub, *, failure="", existing_venv=True, existing_env=False):
    checkout = tmp_path / "synthetic installation with spaces"
    checkout.mkdir()
    shutil.copyfile(ROOT / "install.ps1", checkout / "install.ps1")
    example = b"SYNTHETIC_EXAMPLE=1\n"
    (checkout / ".env.example").write_bytes(example)
    if existing_env:
        (checkout / ".env").write_bytes(b"SYNTHETIC_EXISTING=1\n")
    if existing_venv:
        scripts = checkout / ".venv/Scripts"
        scripts.mkdir(parents=True)
        for name in ("python.exe", "classifire.exe"):
            shutil.copyfile(native_stub, scripts / name)
    shell = Path(os.environ["WINDIR"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    assert shell.is_file()
    env = dict(os.environ)
    env["PATH"] = str(native_stub.parent) + os.pathsep + env["PATH"]
    env["CLASSIFIRE_TEST_FAIL_STAGE"] = failure
    result = subprocess.run(  # noqa: S603 - owned copy and fake commands, no real install
        [
            str(shell),
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(checkout / "install.ps1"),
        ],
        cwd=checkout,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    commands = (checkout / "commands.log").read_text().splitlines()
    return checkout, result, commands


@pytest.mark.parametrize("failure", STAGES)
def test_failed_native_step_stops_installation(tmp_path, native_stub, failure):
    checkout, result, commands = run_installer(
        tmp_path, native_stub, failure=failure, existing_venv=failure != "venv"
    )
    expected = STAGES if failure == "venv" else STAGES[1:]
    assert commands == expected[: expected.index(failure) + 1], "No downstream command may run"
    assert result.returncode != 0, result.stdout + result.stderr
    assert "exit code 42" in result.stdout + result.stderr
    assert "QUANTIFIRE installed." not in result.stdout
    assert (checkout / ".env").exists() is (failure == "init")


@pytest.mark.parametrize("existing_venv", [False, True])
@pytest.mark.parametrize("existing_env", [False, True])
def test_successful_install_preserves_existing_configuration(
    tmp_path, native_stub, existing_venv, existing_env
):
    checkout, result, commands = run_installer(
        tmp_path, native_stub, existing_venv=existing_venv, existing_env=existing_env
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert commands == (STAGES[1:] if existing_venv else STAGES)
    assert "QUANTIFIRE installed." in result.stdout
    expected = b"SYNTHETIC_EXISTING=1\n" if existing_env else b"SYNTHETIC_EXAMPLE=1\n"
    assert (checkout / ".env").read_bytes() == expected
