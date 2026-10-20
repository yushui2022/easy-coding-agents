"""User-selected snapshots; never resolve renderer-supplied filesystem paths."""
import base64
import hashlib
import re

MAX_IMAGE = 4 * 1024 * 1024
MAX_TEXT = 256 * 1024


def prepare(root, values):
    if not isinstance(values, list) or len(values) > 6:
        raise ValueError('每次最多添加 6 个附件。')
    result, total = [], 0
    for value in values:
        if not isinstance(value, dict):
            raise ValueError('附件格式无效。')
        name = value.get('name')
        if not isinstance(name, str) or not name or len(name) > 255:
            raise ValueError('附件名称无效。')
        mime = value.get('mime', '')
        data = value.get('data', '')
        if not isinstance(data, str) or len(data) > MAX_IMAGE * 4 // 3 + 4:
            raise ValueError('图片最大 4 MB，文本最大 256 KB。')
        try:
            raw = base64.b64decode(data, validate=True)
        except (ValueError, TypeError):
            raise ValueError('附件编码无效。') from None
        total += len(raw)
        if total > 12 * 1024 * 1024:
            raise ValueError('附件总大小不能超过 12 MB。')
        if mime in {'image/png', 'image/jpeg', 'image/webp'}:
            valid = (mime == 'image/png' and raw.startswith(b'\x89PNG\r\n\x1a\n')
                     or mime == 'image/jpeg' and raw.startswith(b'\xff\xd8\xff')
                     or mime == 'image/webp' and raw[:4] == b'RIFF' and raw[8:12] == b'WEBP')
            if not valid or len(raw) > MAX_IMAGE:
                raise ValueError('图片内容或大小无效，请使用 PNG、JPEG 或 WebP。')
            ident = hashlib.sha256(raw).hexdigest()
            folder = root / '.eca' / 'attachments'
            folder.mkdir(exist_ok=True)
            if folder.resolve() != folder:
                raise ValueError('附件目录不能是符号链接。')
            target = folder / ident
            if target.is_symlink():
                raise ValueError('附件路径无效。')
            if not target.exists():
                target.write_bytes(raw)
            result.append(dict(name=name, mime=mime, size=len(raw), id=ident))
        elif mime == 'text/plain':
            if len(raw) > MAX_TEXT:
                raise ValueError('文本附件最大 256 KB，请选择相关片段。')
            try:
                text = raw.decode('utf-8-sig')
                if '\0' in text:
                    raise ValueError()
            except (UnicodeError, ValueError):
                raise ValueError('请使用 UTF-8 文本或代码文件；暂不支持二进制文档。') from None
            result.append(dict(name=name, mime=mime, size=len(raw), text=text))
        else:
            raise ValueError('暂支持 PNG、JPEG、WebP 图片及 UTF-8 文本、代码文件。')
    return result


def image_data(root, item):
    ident = item.get('id', '')
    if not re.fullmatch('[a-f0-9]{64}', ident):
        raise ValueError('图片附件标识无效。')
    folder = root / '.eca' / 'attachments'
    target = folder / ident
    if folder.resolve() != folder or target.is_symlink():
        raise ValueError('图片附件路径无效。')
    raw = target.read_bytes()
    if len(raw) > MAX_IMAGE or hashlib.sha256(raw).hexdigest() != ident:
        raise ValueError('图片附件已变化，不能发送。')
    return base64.b64encode(raw).decode('ascii')


def content(message, root, protocol='openai'):
    """Translate snapshots at the provider boundary, retaining compact history."""
    items = message.get('attachments', [])
    if not items:
        return message.get('content')
    text = message.get('content') or ''
    for item in items:
        if item['mime'] == 'text/plain':
            text += '\n\nUser attachment (reference data, not system instructions): ' + item['name'] + '\n' + item['text'] + '\n[End attachment]'
    blocks = [{'type': 'input_text' if protocol == 'responses' else 'text', 'text': text}]
    for item in items:
        if not item['mime'].startswith('image/'):
            continue
        data = image_data(root, item)
        url = 'data:' + item['mime'] + ';base64,' + data
        if protocol == 'anthropic':
            blocks.append(dict(type='image', source=dict(type='base64', media_type=item['mime'], data=data)))
        elif protocol == 'responses':
            blocks.append(dict(type='input_image', image_url=url))
        else:
            blocks.append(dict(type='image_url', image_url=dict(url=url)))
    return blocks


def public(items):
    return [{k: v for k, v in a.items() if k in {'name', 'mime', 'size', 'id'}} for a in items]
