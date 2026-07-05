import os
from pathlib import Path

def test_project_directories_exist():
    root = Path(__file__).parent.parent.parent
    directories = [
        "backend",
        "frontend",
        "src-tauri",
        ".github/workflows",
        "docs",
    ]
    for dir_name in directories:
        assert (root / dir_name).is_dir(), f"Directory {dir_name} missing"

def test_critical_files_exist():
    root = Path(__file__).parent.parent.parent
    files = [
        "backend/main.py",
        "backend/pyproject.toml",
        "frontend/index.html",
        "frontend/package.json",
        "frontend/vite.config.ts",
        "src-tauri/tauri.conf.json",
        "src-tauri/Cargo.toml",
        "LICENSE",
        "README.md",
    ]
    for file_path in files:
        assert (root / file_path).is_file(), f"File {file_path} missing"
