import os
from pathlib import Path

def test_directories_exist():
    root = Path(__file__).parent.parent.parent
    assert (root / "backend").is_dir()
    assert (root / "frontend").is_dir()
    assert (root / "src-tauri").is_dir()
    assert (root / ".github/workflows").is_dir()
    assert (root / "docs").is_dir()

def test_backend_files_exist():
    backend = Path(__file__).parent.parent
    assert (backend / "main.py").is_file()
    assert (backend / "pyproject.toml").is_file()
