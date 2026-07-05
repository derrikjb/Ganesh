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
    assert "build" in data["jobs"]
    assert "strategy" in data["jobs"]["build"]
    assert "matrix" in data["jobs"]["build"]["strategy"]
    assert "os" in data["jobs"]["build"]["strategy"]["matrix"]
    assert "windows-latest" in data["jobs"]["build"]["strategy"]["matrix"]["os"]
    assert "ubuntu-latest" in data["jobs"]["build"]["strategy"]["matrix"]["os"]
