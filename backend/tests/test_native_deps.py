import subprocess
import sys
import os

def test_native_deps_import():
    # GIVEN: The list of required native dependencies
    deps = ["fastapi", "uvicorn", "litellm", "pydantic", "keyring"]
    
    # WHEN: We try to import each dependency
    for dep in deps:
        # THEN: The import should succeed
        result = subprocess.run(
            [sys.executable, "-c", f"import {dep}"],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"Failed to import {dep}: {result.stderr}"

def test_main_check_imports_flag():
    # GIVEN: The backend main.py script
    main_path = os.path.join(os.path.dirname(__file__), "..", "main.py")
    
    # WHEN: We run it with the --check-imports flag
    result = subprocess.run(
        [sys.executable, main_path, "--check-imports"],
        capture_output=True,
        text=True
    )
    
    # THEN: It should exit with code 0 and print success message
    assert result.returncode == 0
    assert "All native dependencies imported successfully" in result.stdout
