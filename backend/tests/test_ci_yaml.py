import yaml
import os

def test_ci_yaml_valid():
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

def test_build_yaml_valid():
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
