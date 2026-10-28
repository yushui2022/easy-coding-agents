"""Citable text out of documents the model could not otherwise read.

A PDF that reaches the model as an image is a picture of text: it cannot be
quoted, diffed or checked later. These extractors turn a document into plain
text at the attachment boundary, so what the model read is what the transcript
shows and what the user can search. Every extractor is bounded — a document that
is too large is truncated with an explicit marker, never silently cut.
"""
import io
import zipfile
from xml.etree import ElementTree as ET

MAX_DOC = 8 * 1024 * 1024
MAX_CHARS = 120_000
MAX_ZIP_BYTES = 60 * 1024 * 1024
MAX_PAGES = 400
MAX_ROWS = 2_000

PDF_MIME = 'application/pdf'
DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
PPTX_MIME = 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
MIMES = {PDF_MIME: 'pdf', DOCX_MIME: 'docx', XLSX_MIME: 'xlsx', PPTX_MIME: 'pptx'}
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
S = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'


def kind_of(mime):
    return MIMES.get(mime)


def sniff(raw, kind):
    """Check the real bytes, so a renamed file is refused instead of half-read."""
    if kind == 'pdf':
        if not raw.startswith(b'%PDF-'):
            raise ValueError('这个文件不是有效的 PDF。')
        return
    if not raw.startswith(b'PK\x03\x04'):
        raise ValueError('这个文件不是有效的 Office 文档（应当是一个 zip 容器）。')
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = set(archive.namelist())
    except zipfile.BadZipFile:
        raise ValueError('这个 Office 文档已损坏，无法读取。') from None
    expected = {'docx': 'word/document.xml', 'xlsx': 'xl/workbook.xml', 'pptx': 'ppt/presentation.xml'}[kind]
    if expected not in names:
        raise ValueError(f'文件扩展名是 {kind}，但内容不像 {kind}；请确认文件没有改过后缀。')


def _bounded(text, limit):
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def _finish(chunks, note, limit=MAX_CHARS):
    text = '\n'.join(chunk for chunk in chunks if chunk.strip())
    text, cut = _bounded(text, limit)
    if cut:
        text += f'\n[已截断：只保留前 {limit} 个字符，其余内容未包含]'
    if note:
        text = note + '\n' + text
    return text


def _read_zip_text(raw, name):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        info = archive.getinfo(name)
        if info.file_size > MAX_ZIP_BYTES:
            raise ValueError(f'文档内部的 {name} 过大，无法安全读取。')
        return archive.read(name)


def pdf_text(raw, limit=MAX_CHARS):
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError
    try:
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted:
            raise ValueError('这个 PDF 有密码保护，先解密再添加。')
        pages = len(reader.pages)
        chunks = [f'[PDF：{pages} 页]']
        for number, page in enumerate(reader.pages[:MAX_PAGES], start=1):
            try:
                body = page.extract_text() or ''
            except (KeyError, ValueError, TypeError):
                body = ''
            body = '\n'.join(line.rstrip() for line in body.splitlines() if line.strip())
            if body:
                chunks.append(f'[第 {number} 页]\n{body}')
        text = _finish(chunks, '')
    except PdfReadError:
        raise ValueError('这个 PDF 无法解析，可能已损坏或是少见编码。') from None
    if 'extract_text' in text or len(text.strip()) <= len('[PDF：') + 12:
        text += ('\n[提示：这一页没有可抽取的文本层，可能是扫描件；扫描件请改用图片并选择支持看图的模型]')
    return text


def docx_text(raw, limit=MAX_CHARS):
    root = ET.fromstring(_read_zip_text(raw, 'word/document.xml'))
    lines = []
    for paragraph in root.iter(f'{W}p'):
        line = ''.join(node.text or '' for node in paragraph.iter(f'{W}t'))
        if line.strip():
            lines.append(line.strip())
        if len(lines) > MAX_ROWS * 20:
            break
    if not lines:
        raise ValueError('这个 Word 文档没有可抽取的文字（可能全是图片）。')
    return _finish(['[Word 文档]'] + lines, '')


def xlsx_text(raw, limit=MAX_CHARS):
    shared = []
    try:
        strings = ET.fromstring(_read_zip_text(raw, 'xl/sharedStrings.xml'))
        for item in strings.iter(f'{S}si'):
            shared.append(''.join(node.text or '' for node in item.iter(f'{S}t')))
    except KeyError:
        shared = []
    workbook = ET.fromstring(_read_zip_text(raw, 'xl/workbook.xml'))
    names = [sheet.get('name') or f'Sheet{index}'
             for index, sheet in enumerate(workbook.iter(f'{S}sheet'), start=1)]
    chunks = [f'[Excel 工作簿：{len(names)} 个工作表]']
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        sheets = sorted(name for name in archive.namelist()
                        if name.startswith('xl/worksheets/sheet') and name.endswith('.xml'))
        for position, name in enumerate(sheets[:20]):
            sheet = ET.fromstring(_read_zip_text(raw, name))
            rows = []
            for row in sheet.iter(f'{S}row'):
                cells = []
                for cell in row.iter(f'{S}c'):
                    value = cell.find(f'{S}v')
                    inline = cell.find(f'{S}is')
                    if value is not None and value.text is not None:
                        text = value.text
                        if cell.get('t') == 's' and text.isdigit() and int(text) < len(shared):
                            text = shared[int(text)]
                        cells.append(text)
                    elif inline is not None:
                        cells.append(''.join(node.text or '' for node in inline.iter(f'{S}t')))
                if any(part.strip() for part in cells):
                    rows.append('\t'.join(cell.replace('\n', ' ') for cell in cells))
                if len(rows) >= MAX_ROWS:
                    rows.append(f'[已截断：只保留前 {MAX_ROWS} 行]')
                    break
            title = names[position] if position < len(names) else name
            if rows:
                chunks.append(f'[工作表 {title}]\n' + '\n'.join(rows))
    if len(chunks) == 1:
        raise ValueError('这个 Excel 工作簿没有可抽取的单元格文本。')
    return _finish(chunks, '')


def pptx_text(raw, limit=MAX_CHARS):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        slides = [name for name in archive.namelist()
                  if name.startswith('ppt/slides/slide') and name.endswith('.xml')]
    slides.sort(key=lambda name: int(''.join(filter(str.isdigit, name.rsplit('/', 1)[-1])) or 0))
    chunks = [f'[PowerPoint：{len(slides)} 页幻灯片]']
    for number, name in enumerate(slides[:MAX_PAGES], start=1):
        slide = ET.fromstring(_read_zip_text(raw, name))
        lines = []
        for paragraph in slide.iter(f'{A}p'):
            line = ''.join(node.text or '' for node in paragraph.iter(f'{A}t'))
            if line.strip():
                lines.append(line.strip())
        if lines:
            chunks.append(f'[第 {number} 页]\n' + '\n'.join(lines))
    if len(chunks) == 1:
        raise ValueError('这份幻灯片没有可抽取的文字。')
    return _finish(chunks, '')


EXTRACT = {'pdf': pdf_text, 'docx': docx_text, 'xlsx': xlsx_text, 'pptx': pptx_text}


def extract(raw, kind, limit=MAX_CHARS):
    """Return citable text plus what the caller should tell the user about it."""
    if kind not in EXTRACT:
        raise ValueError(f'暂不支持这种文档：{kind}')
    if len(raw) > MAX_DOC:
        raise ValueError(f'文档最大 {MAX_DOC // (1024 * 1024)} MB，请拆分或另存一份摘要。')
    sniff(raw, kind)
    text = EXTRACT[kind](raw, limit)
    return {'kind': kind, 'text': text, 'chars': len(text),
            'truncated': '已截断' in text}
