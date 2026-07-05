import os
import json
import tomllib
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

def test_frontend_config():
    root = Path(__file__).parent.parent.parent
    package_json_path = root / "frontend" / "package.json"
    assert package_json_path.exists()
    
    with open(package_json_path, "r") as f:
        data = json.load(f)
        dev_deps = data.get("devDependencies", {})
        assert "tailwindcss" in dev_deps
        assert dev_deps["tailwindcss"].startswith("^4")
        assert "@tailwindcss/vite" in dev_deps
        assert "@testing-library/react" in dev_deps

def test_tauri_config():
    root = Path(__file__).parent.parent.parent
    cargo_toml_path = root / "src-tauri" / "Cargo.toml"
    assert cargo_toml_path.exists()
    
    with open(cargo_toml_path, "rb") as f:
        data = tomllib.load(f)
        deps = data.get("dependencies", {})
        tauri_ver = deps.get("tauri")
        if isinstance(tauri_ver, dict):
            tauri_ver = tauri_ver.get("version")
        assert tauri_ver == "2.11.5"
        assert "tauri-plugin-global-shortcut" in deps
        assert "tauri-plugin-single-instance" in deps

def test_backend_config():
    root = Path(__file__).parent.parent.parent
    pyproject_toml_path = root / "backend" / "pyproject.toml"
    assert pyproject_toml_path.exists()
    
    with open(pyproject_toml_path, "rb") as f:
        data = tomllib.load(f)
        project = data.get("project", {})
        deps = project.get("dependencies", [])
        assert "python-multipart" in deps
        
        optional_deps = project.get("optional-dependencies", {})
        dev_deps = optional_deps.get("dev", [])
        assert "pytest-asyncio" in dev_deps
        assert "httpx" in dev_deps

def test_license_polyform():
    root = Path(__file__).parent.parent.parent
    license_path = root / "LICENSE"
    assert license_path.exists()
    
    with open(license_path, "r") as f:
        first_line = f.readline().strip()
        assert first_line == "# PolyForm Noncommercial License 1.0.0"
