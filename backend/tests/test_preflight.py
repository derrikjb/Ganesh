import subprocess
import os

def test_preflight_detects_missing_rust():
    env = os.environ.copy()
    path_dirs = env.get("PATH", "").split(os.pathsep)
    
    new_path_dirs = [d for d in path_dirs if not os.path.exists(os.path.join(d, "cargo")) and not os.path.exists(os.path.join(d, "rustc"))]
    env["PATH"] = os.pathsep.join(new_path_dirs)
    
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../scripts/preflight.sh"))
    
    result = subprocess.run(["bash", script_path], env=env, capture_output=True, text=True)
    
    assert result.returncode == 1
    assert "Rust (cargo) is missing" in result.stdout
    assert "https://rustup.rs/" in result.stdout
