import re
import os
from pathlib import Path

def test_no_hardcoded_ports_in_frontend():
    """Verify no hardcoded ports (localhost:1234, etc.) in frontend source files."""
    frontend_src = Path(__file__).parent.parent.parent / "frontend" / "src"
    # Regex: (localhost|127.0.0.1|0.0.0.0):\d{2,5}
    # Matches localhost:8080, 127.0.0.1:3000, etc.
    # Does NOT match 127.0.0.1 without a port.
    port_pattern = re.compile(r"(localhost|127\.0\.0\.1|0\.0\.0\.0):\d{2,5}")
    
    matches = []
    for root, _, files in os.walk(frontend_src):
        for file in files:
            if file.endswith((".ts", ".tsx")):
                path = Path(root) / file
                content = path.read_text(encoding="utf-8")
                if port_pattern.search(content):
                    # Find all matches for better error reporting
                    for match in port_pattern.finditer(content):
                        matches.append(f"{path.relative_to(frontend_src.parent)}: {match.group(0)}")
    
    if matches:
        error_msg = "Found hardcoded ports in frontend source files:\n" + "\n".join(matches)
        error_msg += "\n\nAll ports must be ephemeral. Use discovery or configuration instead."
        raise AssertionError(error_msg)
