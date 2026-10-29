"""Read-only local readiness diagnostics. Never contacts a model or opens a store."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.parse import urlsplit

from . import __version__
from .config import Settings
from .fsguard import unsymlinked


def diagnose(root, **overrides):
    root = Path(root).resolve()
    report = {"version": __version__, "python": sys.version.split()[0], "project": str(root),
              "network_checked": False, "checks": []}
    def check(name, status, message):
        report["checks"].append({"name": name, "status": status, "message": message})
    check("python", "ok" if sys.version_info >= (3, 11) else "error", "Python 3.11 or newer is required.")
    if not root.is_dir():
        check("project", "error", "Project directory does not exist; correct --cwd.")
    else:
        check("project", "ok" if os.access(root, os.W_OK) else "warning", "Directory access checked; actual filesystem writes were not attempted.")
        state = root / ".eca"
        invalid = not unsymlinked(state, root) or (state.exists() and not state.is_dir())
        check("state_directory", "error" if invalid else "ok", "The .eca path must be a real directory, not a link or file.")
        try:
            settings = Settings.load(root, **overrides)
        except Exception as exc:
            # TOML/type errors may contain user input; report no raw configuration values.
            check("configuration", "error", f"Configuration could not be loaded ({type(exc).__name__}). Check TOML syntax, option names/types, model ID and endpoint; use eca.example.toml as reference.")
        else:
            check("configuration", "ok", "Configuration parsed and validated.")
            report['sandbox'] = settings.sandbox
            if settings.sandbox == 'docker':
                check('sandbox_backend', 'warning' if shutil.which('docker') else 'error',
                      'Docker CLI checked only; local Linux engine and preinstalled image are checked at execution. '
                      'On Windows, start Docker Desktop from the Start menu before using the sandbox. No host fallback.')
            check("api_key", "ok" if settings.api_key else "error", "API key configured (not tested)." if settings.api_key else "API key missing. Set the configured api_key_env, ECA_API_KEY or the selected provider's key variable.")
            url = urlsplit(settings.base_url)
            # Display origin only; custom paths can themselves contain credentials.
            report.update(model=settings.model.replace(settings.api_key, "[redacted]") if settings.api_key else settings.model,
                          api_format=settings.api_format, endpoint_origin=f"{url.scheme}://{url.netloc}",
                          api_key_configured=bool(settings.api_key), mode=settings.mode, permission=settings.permission,
                          state_dir=str(state))
    shell = (shutil.which("pwsh") or shutil.which("powershell")) if os.name == "nt" else shutil.which("sh")
    check("shell", "ok" if shell else "warning", "Shell available." if shell else "Shell unavailable; command tools cannot run. Install PowerShell or a POSIX shell.")
    git = shutil.which("git")
    if not git:
        check("git", "warning", "Git unavailable; Git diff and repository-aware indexing are unavailable.")
    elif root.is_dir():
        try:
            def run(*args):
                return subprocess.run([git, *args], cwd=root, stdin=subprocess.DEVNULL,
                                      capture_output=True, timeout=5,
                                      creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            inside = run("rev-parse", "--is-inside-work-tree")
            if inside.returncode != 0 or inside.stdout.strip() != b"true":
                check("git", "warning", "Directory is not a Git worktree; file-tool snapshots still work.")
            else:
                check("git", "ok", "Git worktree detected; no changes made.")
                for path in (".env", ".eca/"):
                    tracked = run("ls-files", "--", path).stdout.strip()
                    ignored = run("check-ignore", "-q", "--", path).returncode == 0
                    check("git_privacy_" + path, "warning" if tracked or not ignored else "ok",
                          f"{path} is tracked; review its history and remove it from the index if appropriate." if tracked else
                          f"Add {path} to this project's .gitignore." if not ignored else f"{path} is ignored by Git.")
        except (OSError, subprocess.TimeoutExpired):
            check("git", "warning", "Git diagnostics could not complete; no repository changes made.")
    report["ready"] = not any(item["status"] == "error" for item in report["checks"])
    return report
