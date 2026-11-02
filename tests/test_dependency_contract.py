from pathlib import Path
import subprocess
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VERIFY_SCRIPT = PROJECT_ROOT / "scripts" / "verify-environment.ps1"

EXPECTED_REQUIREMENTS = {
    "cryptography==46.0.6",
    "fastapi==0.133.1",
    "httpx==0.28.1",
    "openpyxl==3.1.5",
    "pillow==12.2.0",
    "pydantic==2.12.5",
    "pyinstaller==6.19.0",
    "pypdf==6.10.0",
    "python-docx==1.2.0",
    "pywin32==311",
    "uvicorn==0.42.0",
}


def run_environment_check(*arguments):
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(VERIFY_SCRIPT),
            *map(str, arguments),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def output_contains_path(result, expected_path):
    combined_output = result.stdout + result.stderr
    output_without_wrapping = "".join(combined_output.split())
    path_without_wrapping = "".join(str(expected_path).split())
    return path_without_wrapping in output_without_wrapping


class DependencyContractTests(unittest.TestCase):
    def test_requirements_are_exactly_pinned(self):
        requirements_path = PROJECT_ROOT / "requirements.txt"
        self.assertTrue(requirements_path.is_file(), f"Missing dependency file: {requirements_path}")

        pinned_requirements = {
            line.strip()
            for line in requirements_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        self.assertEqual(EXPECTED_REQUIREMENTS, pinned_requirements)

    def test_environment_script_checks_all_boundaries(self):
        self.assertTrue(VERIFY_SCRIPT.is_file(), f"Missing environment script: {VERIFY_SCRIPT}")

        script = VERIFY_SCRIPT.read_text(encoding="utf-8")
        required_fragments = (
            "[string]$Python",
            "[string]$InnoSetup",
            "[string]$Requirements",
            "Python 3.13",
            "64-bit",
            "Test-Path -LiteralPath $Python",
            "Test-Path -LiteralPath $InnoSetup",
            "Test-Path -LiteralPath $Requirements",
            "importlib.metadata",
            "requirements.txt",
        )
        for fragment in required_fragments:
            self.assertIn(fragment, script, f"Environment script is missing check: {fragment}")

    def test_missing_python_error_includes_actual_path(self):
        missing_python = PROJECT_ROOT / "missing-python.exe"
        result = run_environment_check("-Python", missing_python)

        self.assertNotEqual(0, result.returncode)
        self.assertTrue(output_contains_path(result, missing_python))

    def test_missing_inno_setup_error_includes_actual_path(self):
        missing_inno_setup = PROJECT_ROOT / "missing-iscc.exe"
        result = run_environment_check(
            "-Python",
            sys.executable,
            "-InnoSetup",
            missing_inno_setup,
        )

        self.assertNotEqual(0, result.returncode)
        self.assertTrue(output_contains_path(result, missing_inno_setup))

    def test_missing_requirements_error_includes_actual_path(self):
        missing_requirements = PROJECT_ROOT / "missing-requirements.txt"
        result = run_environment_check(
            "-Python",
            sys.executable,
            "-InnoSetup",
            VERIFY_SCRIPT,
            "-Requirements",
            missing_requirements,
        )

        self.assertNotEqual(0, result.returncode)
        self.assertTrue(output_contains_path(result, missing_requirements))


if __name__ == "__main__":
    unittest.main()
