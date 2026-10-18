"""Read-only repository navigation benchmark; private index/output in --output.

No repository imports, dependency installation, models, or source edits. Expected
paths are a small hand-selected recall sample, not exhaustive semantic truth.
"""
import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eca.code_index import CodeIndex
from eca.config import Settings
from eca.tools import Tools


@dataclass
class BenchmarkSettings(Settings):
    cache_dir: Path = Path('.')

    @property
    def state_dir(self):
        return self.cache_dir


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--manifest', type=Path, default=Path(__file__).resolve().parents[1]/'benchmark/repository-navigation.json')
    args = parser.parse_args()
    root, output = args.root.resolve(), args.output.resolve()
    if output.is_relative_to(root):
        parser.error('--output must be outside the measured repository')
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(args.manifest.read_text('utf-8'))
    def git(*argv):
        return subprocess.run(['git', *argv], cwd=root, check=True, capture_output=True, timeout=20).stdout
    revision = git('rev-parse', 'HEAD').decode().strip()
    # Refuse to silently measure a different fixture revision.
    if revision != manifest['revision']:
        parser.error('Repository revision does not match the benchmark manifest')
    before = git('status', '--porcelain', '-uno')
    fixture_paths = sorted({p for task in manifest['tasks'] for p in task['expected']})
    def fingerprints():
        return {p: hashlib.sha256((root/p).read_bytes()).hexdigest() for p in fixture_paths}
    source_hashes = fingerprints()
    tracked = len(git('ls-files', '-z').split(b'\0')) - 1
    cache = output / ('index-' + str(time.time_ns()))
    cache.mkdir()
    settings = BenchmarkSettings(root=root, cache_dir=cache)
    tools = Tools(settings, {}, None, None, lambda *_: None)
    index = CodeIndex(tools)
    cold = json.loads(index.query(manifest['tasks'][0]['symbol'], limit=20, related=True))
    print('Cold index:', json.dumps(cold['index']), flush=True)
    measurements = []
    for task in manifest['tasks']:
        symbol, expected = task['symbol'], set(task['expected'])
        runs = {}
        for mode in ('text', 'relations'):
            result = json.loads(index.query(symbol, limit=20, related=mode == 'relations'))
            found = {r['path'] for r in result['results']}
            runs[mode] = {'expected_recall': len(found & expected) / len(expected),
                          'missing': sorted(expected - found), 'result_count': len(found), **result}
        measurements.append({'symbol': symbol, 'expected': sorted(expected), 'runs': runs})
    after = git('status', '--porcelain', '-uno')
    report = {'repository': manifest['repository'], 'revision': revision,
              'tracked_files': tracked, 'python': sys.version.split()[0],
              'source_status_unchanged': before == after, 'tracked_changes_before': bool(before),
              'expected_source_sha256': source_hashes, 'expected_source_unchanged': source_hashes == fingerprints(),
              'manifest_sha256': hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
              'cold_index': cold['index'], 'tasks': measurements,
              'limitations': 'Three navigation tasks only; no model-driven edits, repository tests or semantic precision measurement. Warm queries still enumerate/stat source files. Per-file structure caps apply.'}
    (output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'tasks'}, ensure_ascii=False))
    for task in measurements:
        print(task['symbol'], json.dumps({m: {'recall': r['expected_recall'], 'missing': r['missing'],
              'read': r['index']['files_read'], 'ms': r['index']['elapsed_ms']} for m, r in task['runs'].items()}))
    return 0 if before == after and report['expected_source_unchanged'] and all(not t['runs']['relations']['missing'] for t in measurements) else 1


if __name__ == '__main__':
    raise SystemExit(main())
