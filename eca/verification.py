"""Conservative hints from retained runner output, never a proof of correctness."""
import re


def no_tests_found(command, output):
    if not re.match(r"^(?:python(?:3)?\s+(?:-B\s+)?-m\s+(?:pytest|unittest)\b|pytest\b|uv\s+run\s+pytest\b)", command.strip()):
        return False
    text = "\n".join(str(output.get(key, "")) for key in ("stdout", "stderr"))
    return bool(re.search(r"(?m)^\s*Ran 0 tests? in .+$|^\s*(?:=+\s*)?no tests (?:ran|collected)\b", text))
