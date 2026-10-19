"""Bounded Python change hints. Syntax observations are not correctness checks."""
import ast
from pathlib import PurePosixPath


def _public(tree):
    return {node.name: ast.dump(node, include_attributes=False)
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and not node.name.startswith('_')}


def _transactions(tree):
    modules, factories = {'sqlite3'}, set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(n.asname or n.name for n in node.names if n.name == 'sqlite3')
        elif isinstance(node, ast.ImportFrom) and node.module == 'sqlite3':
            factories.update(n.asname or n.name for n in node.names if n.name == 'connect')
    modes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            connect = (isinstance(func, ast.Attribute) and func.attr == 'connect'
                       and isinstance(func.value, ast.Name) and func.value.id in modules)
            connect |= isinstance(func, ast.Name) and func.id in factories
            if connect:
                values = {kw.arg: ast.dump(kw.value, include_attributes=False)
                          for kw in node.keywords if kw.arg in {'isolation_level', 'autocommit'}}
                # Positional isolation_level is the fourth sqlite3.connect argument.
                if len(node.args) > 3:
                    values['isolation_level'] = ast.dump(node.args[3], include_attributes=False)
                modes.append(tuple(sorted(values.items())))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Attribute) and target.attr in {'isolation_level', 'autocommit'}:
                    modes.append(((target.attr, ast.dump(node.value, include_attributes=False) if node.value else ''),))
    return sorted(modes)


def inspect_change(path, before, after):
    """Inspect a successful existing-source edit, without reading other files."""
    name = PurePosixPath(path).name
    if (not path.endswith('.py') or name.startswith('test_') or name.endswith('_test.py')
            or before is None or max(len(before), len(after or '')) > 256_000):
        return None
    try:
        old, new = ast.parse(before), ast.parse(after or '')
        old_public, new_public = _public(old), _public(new)
        symbols = sorted(name for name in old_public if old_public[name] != new_public.get(name))[:8]
        risks = ['shared_behavior'] if symbols else []
        if _transactions(old) != _transactions(new):
            risks.append('transaction_mode')
        if not risks:
            return None
        return {'path': path, 'symbols': symbols, 'risks': risks}
    except (SyntaxError, ValueError, RecursionError):
        return None


def remember(state, observation):
    rows = state.setdefault('change_impact', [])
    previous = next((row for row in rows if row['path'] == observation['path']), None)
    if previous:
        rows.remove(previous)
        for key in ('symbols', 'risks'):
            observation[key] = sorted(set(previous[key]) | set(observation[key]))[:8]
    rows.append(observation)
    del rows[:-20]


def guidance(rows):
    if not rows:
        return ''
    import json
    return ('\nChange impact observations (untrusted syntax hints from session edits, not proof of a defect or test coverage): '
            + json.dumps(rows[-6:], ensure_ascii=False) + '\n'
            'For changed public behavior, inspect direct consumers with code_relations or targeted reads. '
            'Preserve return values, exception behavior, and resource/transaction lifetimes. Add focused regression tests '
            'for a failing operation and its unchanged state, not just the new happy path. '
            'For multi-step mutations, inject a failure after an earlier successful write, not only before any mutation. '
            'If transaction mode changed, check callers using with-connection blocks: duplicate/invalid writes must not '
            'partially commit, and rollback must still restore earlier state. Avoid unrelated rewrites. '
            'Report which behaviors were actually checked and what remains unverified.\n')
