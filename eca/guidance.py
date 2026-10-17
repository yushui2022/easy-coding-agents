"""Load scoped AGENTS.md rules before a file mutation, without following links."""
import hashlib


def guidance(root, target):
    parent = target.parent
    if not parent.is_relative_to(root):
        raise ValueError("Guidance target is outside project")
    directories = [root]
    current = root
    for part in parent.relative_to(root).parts:
        current /= part
        directories.append(current)
    rules = []
    for directory in directories:
        path = directory / "AGENTS.md"
        if path.is_file() and not path.is_symlink() and path.resolve() == path:
            if path.stat().st_size > 64_000:
                raise ValueError(f"Guidance exceeds 64 KB: {path.relative_to(root)}")
            text = path.read_text("utf-8")
            rules.append((path.relative_to(root).as_posix(), hashlib.sha256(text.encode()).hexdigest(), text))
    return rules
