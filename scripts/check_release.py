"""Offline artifact gate: versions, archive allowlist, wheel metadata and digest."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tomllib
import zipfile


def check(archive, root):
    package = json.loads((root/'package.json').read_text('utf-8'))
    version = package['version']
    assert json.loads((root/'desktop/package.json').read_text('utf-8'))['version'] == version
    assert tomllib.loads((root/'pyproject.toml').read_text('utf-8'))['project']['version'] == version
    assert f'__version__ = "{version}"' in (root/'eca/__init__.py').read_text('utf-8')
    with tarfile.open(archive, 'r:gz') as tar:
        members = tar.getmembers()
        allowed = {'package/package.json', 'package/README.md', 'package/bin/ecs.cjs',
                   'package/docs/NPM_INSTALL.md', 'package/vendor/runtime.json',
                   f'package/vendor/easy_coding_agent-{version}-py3-none-any.whl'}
        assert {m.name for m in members} == allowed, 'Unexpected/missing npm archive files'
        assert all(m.isfile() for m in members), 'Only regular files allowed'
        def read(name):
            return tar.extractfile(name).read()
        packed = json.loads(read('package/package.json'))
        assert packed['version'] == version
        assert packed['bin'] == {'eca': 'bin/ecs.cjs', 'ecs': 'bin/ecs.cjs'}
        manifest = json.loads(read('package/vendor/runtime.json'))
        wheel = read('package/vendor/'+manifest['wheel'])
        assert manifest['version'] == version
        assert hashlib.sha256(wheel).hexdigest() == manifest['sha256']
        with zipfile.ZipFile(io.BytesIO(wheel)) as zipped:
            names = zipped.namelist()
            assert all(n.startswith(('eca/', 'agent_memory_core/', f'easy_coding_agent-{version}.dist-info/')) for n in names)
            for module in ('skills', 'refactor', 'budget', 'acceptance', 'background', 'web', 'snapshot', 'runtime', 'desktop_rpc', 'impact'):
                assert f'eca/{module}.py' in names, f'Missing {module}'
            assert f'__version__ = "{version}"' in zipped.read('eca/__init__.py').decode()
    return {'version': version, 'archive': str(archive.resolve()), 'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
            'archive_bytes': archive.stat().st_size, 'artifact_checks': 'passed'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('archive', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = check(args.archive, Path(__file__).resolve().parents[1])
    if args.report:
        args.report.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
