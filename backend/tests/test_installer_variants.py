"""Tests for installer variants (Task 38): minimal vs full PyInstaller specs.

Verifies:
- Both PyInstaller spec files exist and have the correct structure.
- ``test_minimal_no_models``: minimal spec excludes ``.onnx`` / ``.bin``
  model weight files from the bundle.
- ``test_full_has_models``: full spec bundles the three required models
  (stt.bin, tts.onnx, embeddings.bin) into ``dist/models/``.
- Build scripts exist for both Windows (.ps1) and Linux (.sh) and reference
  the correct spec files.
- CI workflow defines ``build-minimal`` and ``build-full`` jobs with
  OS matrix (Windows + Linux, no macOS).
- Full variant does NOT download models during the build.
"""
import os
import ast
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent.parent
BACKEND = ROOT / "backend"
SCRIPTS = ROOT / "scripts"
WORKFLOWS = ROOT / ".github" / "workflows"

MINIMAL_SPEC = BACKEND / "pyinstaller-minimal.spec"
FULL_SPEC = BACKEND / "pyinstaller-full.spec"

MODEL_EXTENSIONS = (".onnx", ".bin")
REQUIRED_MODEL_FILES = ("stt.bin", "tts.onnx", "embeddings.bin")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Spec file existence and structure
# ---------------------------------------------------------------------------


def test_minimal_spec_exists():
    assert MINIMAL_SPEC.is_file(), f"Missing {MINIMAL_SPEC}"


def test_full_spec_exists():
    assert FULL_SPEC.is_file(), f"Missing {FULL_SPEC}"


def test_minimal_spec_is_pyinstaller_spec():
    text = _read(MINIMAL_SPEC)
    assert "Analysis(" in text
    assert "EXE(" in text
    assert "PYZ(" in text
    assert "ganesh-backend" in text


def test_full_spec_is_pyinstaller_spec():
    text = _read(FULL_SPEC)
    assert "Analysis(" in text
    assert "EXE(" in text
    assert "PYZ(" in text
    assert "ganesh-backend" in text


def test_minimal_spec_is_valid_python():
    ast.parse(_read(MINIMAL_SPEC))


def test_full_spec_is_valid_python():
    ast.parse(_read(FULL_SPEC))


# ---------------------------------------------------------------------------
# test_minimal_no_models: no .onnx/.bin model files in minimal dist
# ---------------------------------------------------------------------------


def test_minimal_spec_declares_excludes():
    text = _read(MINIMAL_SPEC)
    assert "MINIMAL_EXCLUDES" in text
    assert ".onnx" in text
    assert ".bin" in text


def test_minimal_spec_filters_model_weights():
    text = _read(MINIMAL_SPEC)
    assert "_is_model_weight" in text
    assert "datas = [(src, dst) for src, dst in datas if not _is_model_weight(src)]" in text
    assert "binaries = [(src, dst) for src, dst in binaries if not _is_model_weight(src)]" in text


def test_minimal_spec_does_not_bundle_models():
    text = _read(MINIMAL_SPEC)
    assert "BUNDLED_MODELS" not in text, "minimal spec must not declare BUNDLED_MODELS"
    assert "prebuilt_models" not in text, "minimal spec must not reference prebuilt_models"
    assert '"models"' not in text, "minimal spec must not add datas with 'models' destination"


def test_minimal_no_models():
    """No .onnx/.bin model files should end up in the minimal dist.

    Since we cannot run PyInstaller in the unit-test environment, we
    verify the contract by asserting the minimal spec actively filters
    out model weight extensions from ``datas`` and ``binaries``.
    """
    text = _read(MINIMAL_SPEC)
    assert "MINIMAL_EXCLUDES" in text
    assert ".onnx" in text and ".bin" in text
    assert "_is_model_weight" in text
    assert "datas = [(src, dst) for src, dst in datas if not _is_model_weight(src)]" in text
    assert "binaries = [(src, dst) for src, dst in binaries if not _is_model_weight(src)]" in text


# ---------------------------------------------------------------------------
# test_full_has_models: models present in dist/models/
# ---------------------------------------------------------------------------


def test_full_spec_declares_bundled_models():
    text = _read(FULL_SPEC)
    assert "BUNDLED_MODELS" in text
    for model in REQUIRED_MODEL_FILES:
        assert model in text, f"full spec must reference {model}"


def test_full_spec_uses_models_destination():
    text = _read(FULL_SPEC)
    assert '"models"' in text or "'models'" in text, (
        "full spec must add model datas with destination 'models'"
    )


def test_full_spec_supports_models_src_env():
    text = _read(FULL_SPEC)
    assert "GANESH_MODELS_SRC" in text, (
        "full spec must read GANESH_MODELS_SRC env var for pre-downloaded models"
    )


def test_full_spec_does_not_download_models():
    text = _read(FULL_SPEC)
    assert "download_model" not in text, (
        "full spec must NOT download models during build"
    )
    assert "httpx" not in text, "full spec must not import httpx for downloads"


def test_full_has_models():
    """Models present in dist/models/ for the full variant.

    We verify the contract by asserting the full spec adds each required
    model file to ``datas`` with destination ``models`` when the file
    exists in ``GANESH_MODELS_SRC``.
    """
    text = _read(FULL_SPEC)
    assert "BUNDLED_MODELS" in text
    for model in REQUIRED_MODEL_FILES:
        assert model in text, f"full spec must reference {model}"
    assert '"models"' in text or "'models'" in text
    assert "GANESH_MODELS_SRC" in text


# ---------------------------------------------------------------------------
# Build scripts
# ---------------------------------------------------------------------------


def _build_scripts():
    return {
        "minimal_sh": SCRIPTS / "build-minimal.sh",
        "minimal_ps1": SCRIPTS / "build-minimal.ps1",
        "full_sh": SCRIPTS / "build-full.sh",
        "full_ps1": SCRIPTS / "build-full.ps1",
    }


def test_build_scripts_exist():
    for name, path in _build_scripts().items():
        assert path.is_file(), f"Missing {name}: {path}"


def test_build_minimal_sh_references_minimal_spec():
    text = _read(SCRIPTS / "build-minimal.sh")
    assert "pyinstaller-minimal.spec" in text
    assert "ganesh-backend" in text
    assert "--check-imports" in text


def test_build_minimal_ps1_references_minimal_spec():
    text = _read(SCRIPTS / "build-minimal.ps1")
    assert "pyinstaller-minimal.spec" in text
    assert "ganesh-backend" in text
    assert "--check-imports" in text


def test_build_full_sh_references_full_spec():
    text = _read(SCRIPTS / "build-full.sh")
    assert "pyinstaller-full.spec" in text
    assert "GANESH_MODELS_SRC" in text
    assert "dist/models" in text or "dist/models/" in text
    assert "stt.bin" in text
    assert "tts.onnx" in text
    assert "embeddings.bin" in text


def test_build_full_ps1_references_full_spec():
    text = _read(SCRIPTS / "build-full.ps1")
    assert "pyinstaller-full.spec" in text
    assert "GANESH_MODELS_SRC" in text
    assert "dist\\models" in text or "dist/models" in text
    assert "stt.bin" in text
    assert "tts.onnx" in text
    assert "embeddings.bin" in text


def test_build_full_sh_does_not_download_models():
    text = _read(SCRIPTS / "build-full.sh")
    assert "download_model" not in text, (
        "build-full.sh must NOT download models during build"
    )
    assert "httpx" not in text, "build-full.sh must not use httpx for downloads"


def test_build_full_ps1_does_not_download_models():
    text = _read(SCRIPTS / "build-full.ps1")
    assert "download_model" not in text, (
        "build-full.ps1 must NOT download models during build"
    )
    assert "httpx" not in text, "build-full.ps1 must not use httpx for downloads"


def test_build_full_sh_references_pre_bundled_models():
    text = _read(SCRIPTS / "build-full.sh")
    assert "pre-bundled" in text.lower() or "pre-downloaded" in text.lower(), (
        "build-full.sh should reference pre-bundled/pre-downloaded models"
    )


def test_build_full_ps1_references_pre_bundled_models():
    text = _read(SCRIPTS / "build-full.ps1")
    assert "pre-bundled" in text.lower() or "pre-downloaded" in text.lower(), (
        "build-full.ps1 should reference pre-bundled/pre-downloaded models"
    )


def test_build_minimal_sh_executable():
    if os.name == "posix":
        stat = (SCRIPTS / "build-minimal.sh").stat()
        assert stat.st_mode & 0o100, "build-minimal.sh should be executable"


def test_build_full_sh_executable():
    if os.name == "posix":
        stat = (SCRIPTS / "build-full.sh").stat()
        assert stat.st_mode & 0o100, "build-full.sh should be executable"


# ---------------------------------------------------------------------------
# CI workflow: build-minimal and build-full jobs (Task 38)
# ---------------------------------------------------------------------------


def test_build_yaml_has_variant_jobs():
    build_path = WORKFLOWS / "build.yml"
    with open(build_path, "r") as f:
        data = yaml.safe_load(f)
    assert "jobs" in data
    assert "build-minimal" in data["jobs"], (
        "build.yml must define a build-minimal job (Task 38)"
    )
    assert "build-full" in data["jobs"], (
        "build.yml must define a build-full job (Task 38)"
    )


def test_build_yaml_variant_jobs_have_os_matrix():
    build_path = WORKFLOWS / "build.yml"
    with open(build_path, "r") as f:
        data = yaml.safe_load(f)
    for job_name in ("build-minimal", "build-full"):
        job = data["jobs"][job_name]
        assert "strategy" in job, f"{job_name} should have a strategy"
        matrix = job["strategy"]["matrix"]
        assert "os" in matrix, f"{job_name} should have os in matrix"
        assert "windows-latest" in matrix["os"], (
            f"{job_name} should build on Windows"
        )
        assert "ubuntu-latest" in matrix["os"], (
            f"{job_name} should build on Linux"
        )


def test_build_yaml_no_macos():
    build_path = WORKFLOWS / "build.yml"
    with open(build_path, "r") as f:
        data = yaml.safe_load(f)
    for job_name, job in data["jobs"].items():
        if "strategy" in job and "matrix" in job["strategy"]:
            os_list = job["strategy"]["matrix"].get("os", [])
            for entry in os_list:
                assert "macos" not in str(entry).lower(), (
                    f"Job {job_name} must not include macOS builds (Task 38 constraint)"
                )


def test_build_yaml_uploads_separate_artifacts():
    build_path = WORKFLOWS / "build.yml"
    with open(build_path, "r") as f:
        data = yaml.safe_load(f)
    for job_name in ("build-minimal", "build-full"):
        job = data["jobs"][job_name]
        steps = job.get("steps", [])
        upload_steps = [
            s for s in steps
            if "uses" in s and "upload-artifact" in s.get("uses", "")
        ]
        assert len(upload_steps) > 0, (
            f"{job_name} should have an upload-artifact step"
        )
        for step in upload_steps:
            with_name = step.get("with", {}).get("name", "")
            assert "minimal" in with_name or "full" in with_name, (
                f"{job_name} upload-artifact name should include variant: "
                f"got '{with_name}'"
            )


def test_build_yaml_full_job_caches_models():
    build_path = WORKFLOWS / "build.yml"
    with open(build_path, "r") as f:
        data = yaml.safe_load(f)
    full_job = data["jobs"]["build-full"]
    steps = full_job.get("steps", [])
    cache_steps = [
        s for s in steps
        if "uses" in s and "actions/cache" in s.get("uses", "")
    ]
    assert len(cache_steps) > 0, (
        "build-full job should cache pre-bundled models (no download during build)"
    )


def test_ci_yaml_no_macos():
    ci_path = WORKFLOWS / "ci.yml"
    with open(ci_path, "r") as f:
        data = yaml.safe_load(f)
    for job_name, job in data["jobs"].items():
        if "strategy" in job and "matrix" in job["strategy"]:
            os_list = job["strategy"]["matrix"].get("os", [])
            for entry in os_list:
                assert "macos" not in str(entry).lower(), (
                    f"Job {job_name} must not include macOS builds"
                )
