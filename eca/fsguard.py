"""Filesystem failures described in words a user can act on.

``[Errno 28] No space left on device: 'G:\\\\Projects\\\\x\\\\.eca\\\\sessions.sqlite3'``
is technically accurate and practically useless: it does not say whether the
project is damaged, what to free, or that the disk — not the task — is the
problem. These helpers keep the path, drop the traceback wording, and name the
next action. Nothing here retries or hides a failure.
"""
import errno

ADVICE = {
    errno.ENOSPC: ('磁盘空间不足', '释放所在磁盘的空间（临时目录与构建缓存通常最占地方），或把项目移到另一个磁盘后重试'),
    errno.EDQUOT: ('超出磁盘配额', '清理配额占用，或请管理员提高这个账户的配额'),
    errno.EACCES: ('没有权限', '检查该目录的写入权限；不要用管理员身份硬跑，先确认文件没有被占用或设为只读'),
    errno.EPERM: ('操作被系统拒绝', '文件可能被标记为只读或被安全软件锁定，确认后重试'),
    errno.EROFS: ('所在磁盘是只读的', '把项目放到可写磁盘上；只读挂载点无法保存会话和快照'),
    errno.ENOENT: ('路径不存在', '上级目录可能已被移动或删除，重新打开项目后再试'),
    errno.ENOTDIR: ('路径中间有一段不是目录', '确认路径没有被同名文件占用'),
    errno.EISDIR: ('目标是目录而不是文件', '确认路径拼写，或先移除同名目录'),
    errno.EMFILE: ('进程打开的文件过多', '关闭一些标签或重启应用后再试'),
    errno.ENFILE: ('系统打开的文件过多', '关闭其他程序后再试'),
    errno.EBUSY: ('文件正被占用', '先结束占用该文件的程序再重试'),
    errno.ENAMETOOLONG: ('路径太长', '把项目移到更短的路径下'),
    errno.EXDEV: ('跨磁盘操作不被允许', '把临时目录与目标放在同一个磁盘上'),
}


def describe(error, action='写入', target=None):
    """One actionable sentence for a filesystem exception."""
    code = getattr(error, 'errno', None)
    label, advice = ADVICE.get(code, (None, None))
    where = ''
    if target is not None:
        where = f'：{target}'
    elif getattr(error, 'filename', None):
        where = f'：{error.filename}'
    if label is None:
        detail = str(error).strip() or error.__class__.__name__
        return f'{action}失败{where}。系统报告：{detail}。这不是模型或任务的问题。'
    return f'{action}失败{where}。{label}——{advice}。'


def space(path):
    """Free bytes on the volume holding ``path``, or None when unknown."""
    import shutil
    try:
        return shutil.disk_usage(str(path)).free
    except OSError:
        return None


def check_target(path, action='写入', minimum=1):
    """Refuse early with a readable message when the volume is obviously full."""
    free = space(path)
    if free is not None and free < minimum:
        free_mb = free / (1024 * 1024)
        raise ValueError(f'{action}失败：{path} 所在磁盘只剩 {free_mb:.1f} MB，'
                         '空间不足——先释放磁盘空间，再重试。这不是模型或任务的问题。')


def unsymlinked(path, root):
    """True when ``path`` sits under ``root`` without a symlink at or below it.

    Comparing ``path.resolve()`` with ``path`` looks like the same check but is
    wrong on macOS, where /var and /tmp are symlinks to /private/var and
    /private/tmp: every project inside a temporary directory was rejected even
    though nothing in the project itself was linked. Resolving both sides against
    the project root keeps the guarantee — a link at the state directory or below
    it still fails — without depending on where the volume is mounted.
    """
    from pathlib import Path

    path, root = Path(path), Path(root)
    if path.is_symlink():
        return False
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    try:
        return path.resolve() == root.resolve() / relative
    except OSError:
        return False
