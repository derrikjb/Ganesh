import yaml
import os

def test_ci_yaml_valid() -> None:
    ci_path = os.path.join(os.path.dirname(__file__), "../../.github/workflows/ci.yml")
    with open(ci_path, "r") as f:
        data = yaml.safe_load(f)
    assert data["name"] == "CI"
    assert "jobs" in data
    assert "test" in data["jobs"]
    assert "strategy" in data["jobs"]["test"]
    assert "matrix" in data["jobs"]["test"]["strategy"]
    assert "os" in data["jobs"]["test"]["strategy"]["matrix"]
    assert "windows-latest" in data["jobs"]["test"]["strategy"]["matrix"]["os"]
    assert "ubuntu-latest" in data["jobs"]["test"]["strategy"]["matrix"]["os"]
    
    # Task 41: Assert new CI steps exist
    steps = [step.get("name", "") for step in data["jobs"]["test"]["steps"]]
    assert any("Lint Python" in s and "ruff" in s.lower() for s in steps)
    assert any("Type Check Python" in s and "mypy" in s.lower() for s in steps)
    assert any("Lint TypeScript" in s and "eslint" in s.lower() for s in steps)
    assert any("Type Check TypeScript" in s and "tsc" in s.lower() for s in steps)
    assert any("Port Scan" in s for s in steps)
    assert any("Bundle Size Check" in s for s in steps)

def test_build_yaml_valid() -> None:
    build_path = os.path.join(os.path.dirname(__file__), "../../.github/workflows/build.yml")
    with open(build_path, "r") as f:
        data = yaml.safe_load(f)
    assert data["name"] == "Build"
    assert "jobs" in data
    # Task 38: build.yml defines build-minimal and build-full jobs
    # (matrix: OS × variant) for Windows + Linux release artifacts.
    assert "build-minimal" in data["jobs"]
    assert "build-full" in data["jobs"]
    for job_name in ("build-minimal", "build-full"):
        job = data["jobs"][job_name]
        assert "strategy" in job
        assert "matrix" in job["strategy"]
        assert "os" in job["strategy"]["matrix"]
        assert "windows-latest" in job["strategy"]["matrix"]["os"]
        assert "ubuntu-latest" in job["strategy"]["matrix"]["os"]
        
        # Task 41: Assert bundle size check exists in build.yml
        step_names = [step.get("name", "") for step in job["steps"]]
        assert any("bundle size" in name.lower() for name in step_names)

def test_ci_steps_exist() -> None:
    ci_path = os.path.join(os.path.dirname(__file__), "../../.github/workflows/ci.yml")
    with open(ci_path, "r") as f:
        data = yaml.safe_load(f)
    
    steps = data["jobs"]["test"]["steps"]
    step_names = [step.get("name", "").lower() for step in steps]
    
    assert any("ruff" in name for name in step_names)
    assert any("mypy" in name for name in step_names)
    assert any("eslint" in name or "lint typescript" in name for name in step_names)
    assert any("tsc" in name or "type check typescript" in name for name in step_names)
    assert any("port scan" in name for name in step_names)
    assert any("bundle size" in name for name in step_names)
