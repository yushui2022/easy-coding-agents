"""Conservative hints from retained runner output, never a proof of correctness."""
import re
import json
import hashlib


def failure_signature(command, result):
    """Hash exact retained diagnostics; never normalize away meaningful differences."""
    if not repair_allowed(result):
        return None
    output = json.loads(result)
    evidence = {key: output.get(key) for key in ('exit_code', 'stdout', 'stderr', 'test_status')}
    return hashlib.sha256(json.dumps([command, evidence], sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def repair_allowed(result):
    """Do not rerun denied, timed-out, interrupted or unknown-outcome commands."""
    try:
        output = json.loads(result)
        return (isinstance(output, dict) and output.get('timed_out') is False and
                type(output.get('exit_code')) is int and output['exit_code'] >= 0)
    except (TypeError, ValueError):
        return False


def command_status(command, result):
    """Successful command evidence only; never infer tests passed from prose."""
    try:
        output = json.loads(result)
        if not isinstance(output, dict):
            return 'failed'
        if no_tests_found(command, output) or output.get('test_status') == 'no_tests':
            return 'no_tests'
        if type(output.get('exit_code')) is int and output['exit_code'] == 0 and output.get('timed_out') is False:
            return 'passed'
    except (TypeError, ValueError):
        pass
    return 'failed'


def no_tests_found(command, output):
    if not re.match(r"^(?:python(?:3)?\s+(?:-B\s+)?-m\s+(?:pytest|unittest)\b|pytest\b|uv\s+run\s+pytest\b)", command.strip()):
        return False
    text = "\n".join(str(output.get(key, "")) for key in ("stdout", "stderr"))
    return bool(re.search(r"(?m)^\s*Ran 0 tests? in .+$|^\s*(?:=+\s*)?no tests (?:ran|collected)\b", text))
