"""Bounded, streaming content fingerprints for verification evidence.

Every included byte is hashed; large files are never silently skipped. Metadata
checks detect ordinary concurrent writes, but this is not an atomic filesystem
snapshot and does not defend against an actor restoring all metadata.
"""
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import time

MAX_FILES = 20_000
MAX_BYTES = 512 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024
MAX_SECONDS = 30


def _stamp(value):
    # Windows path stat synthesizes execute bits for .cmd/.exe names, whereas
    # fstat on the same open handle does not. Compare type and write/read bits.
    mode = value.st_mode & ~0o111 if os.name == 'nt' else value.st_mode
    return (value.st_dev, value.st_ino, mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns)


def _stat(path):
    try:
        value = path.stat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(value.st_mode):
        raise ValueError('Snapshot requires regular files')
    return _stamp(value)


def _hash_file(path, expected, deadline):
    digest, size = hashlib.sha256(), 0
    with path.open('rb') as stream:
        if _stamp(os.fstat(stream.fileno())) != expected:
            raise ValueError('File changed before read')
        while True:
            if time.monotonic() > deadline:
                raise ValueError('Snapshot time budget exhausted')
            data = stream.read(min(CHUNK_BYTES, expected[3] - size + 1))
            if not data:
                break
            size += len(data)
            if size > expected[3]:
                raise ValueError('File grew during read')
            digest.update(data)
        if size != expected[3] or _stamp(os.fstat(stream.fileno())) != expected or _stat(path) != expected:
            raise ValueError('File changed during read')
    return digest.digest()


def fingerprint(root, files, resolve, skip):
    deadline = time.monotonic() + MAX_SECONDS
    def inventory():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError('Snapshot time budget exhausted')
        result = subprocess.run(['git', '-c', 'core.fsmonitor=false', 'ls-files', '-co',
                                 '--exclude-standard', '-z'], cwd=root,
                                capture_output=True, timeout=min(5, remaining))
        paths = set()
        if result.returncode == 0:
            for raw in result.stdout.split(b'\0'):
                if not raw:
                    continue
                value = raw.decode('utf-8')
                if any(part.lower() in skip for part in value.split('/')):
                    continue
                try:
                    paths.add(resolve(value))
                except ValueError:
                    continue  # Existing secret and workspace boundary policy.
                if len(paths) > MAX_FILES:
                    raise ValueError('Snapshot file budget exhausted')
        else:
            # The navigation iterator may stop at its own scan limit. Never
            # mistake that truncated view for a complete verification snapshot.
            scanned = 0
            def walk_error(error):
                raise error
            for directory, dirs, names in os.walk(root, followlinks=False, onerror=walk_error):
                if time.monotonic() > deadline:
                    raise ValueError('Snapshot scan time budget exhausted')
                dirs[:] = [d for d in dirs if d.lower() not in skip and not (Path(directory)/d).is_symlink()]
                for name in names:
                    scanned += 1
                    if scanned > MAX_FILES or time.monotonic() > deadline:
                        raise ValueError('Snapshot scan budget exhausted')
                    try:
                        paths.add(resolve(str(Path(directory)/name)))
                    except ValueError:
                        continue
        listing, total = {}, 0
        for path in sorted(paths):
            if time.monotonic() > deadline:
                raise ValueError('Snapshot time budget exhausted')
            value = _stat(path)
            total += value[3] if value else 0
            if total > MAX_BYTES:
                raise ValueError('Snapshot byte budget exhausted')
            listing[path] = value
        return listing
    try:
        before = inventory()
        digest = hashlib.sha256(b'eca-snapshot-v2\0')
        for path, value in before.items():
            name = path.relative_to(root).as_posix().encode('utf-8')
            digest.update(len(name).to_bytes(8, 'big') + name)
            digest.update(b'M' if value is None else b'F' + _hash_file(path, value, deadline))
        # Re-enumerate additions/deletions/renames, and re-stat files hashed early
        # so edits during a later file's read cannot validate stale evidence.
        if inventory() != before:
            return None
        return digest.hexdigest()
    except (OSError, ValueError, UnicodeError, subprocess.TimeoutExpired):
        return None
