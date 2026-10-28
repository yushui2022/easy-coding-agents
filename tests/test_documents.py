"""Document extraction: what the model reads must be quotable text, not a picture."""
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile

from eca import attachments, documents


def build_pdf(text='Hello evidence'):
    """A real one-page PDF with a correct xref table, so pypdf accepts it."""
    stream = f'BT /F1 12 Tf 20 100 Td ({text}) Tj ET'.encode()
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Contents 4 0 R '
        b'/Resources << /Font << /F1 5 0 R >> >> >>',
        b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    ]
    out = bytearray(b'%PDF-1.4\n')
    offsets = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f'{index} 0 obj\n'.encode() + body + b'\nendobj\n'
    xref = len(out)
    out += f'xref\n0 {len(objects) + 1}\n'.encode()
    out += b'0000000000 65535 f \n'
    for offset in offsets:
        out += f'{offset:010d} 00000 n \n'.encode()
    out += (f'trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n').encode()
    return bytes(out)


def build_pdf_without_text():
    return build_pdf(text='')


def build_docx(paragraphs):
    body = ''.join(f'<w:p><w:r><w:t>{text}</w:t></w:r></w:p>' for text in paragraphs)
    xml = ('<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
           f'wordprocessingml/2006/main"><w:body>{body}</w:body></w:document>')
    return zip_bytes({'word/document.xml': xml})


def build_xlsx(rows):
    shared = sorted({cell for row in rows for cell in row if not cell.replace('.', '').isdigit()})
    strings = ('<?xml version="1.0" encoding="UTF-8"?><sst xmlns="http://schemas.openxmlformats.org/'
               'spreadsheetml/2006/main">' + ''.join(f'<si><t>{value}</t></si>' for value in shared) + '</sst>')
    sheet_rows = ''
    for number, row in enumerate(rows, start=1):
        cells = ''
        for column, value in enumerate(row):
            reference = f'{"ABCDEFGH"[column]}{number}'
            if value.replace('.', '').isdigit():
                cells += f'<c r="{reference}"><v>{value}</v></c>'
            else:
                cells += f'<c r="{reference}" t="s"><v>{shared.index(value)}</v></c>'
        sheet_rows += f'<row r="{number}">{cells}</row>'
    sheet = ('<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/'
             'spreadsheetml/2006/main"><sheetData>' + sheet_rows + '</sheetData></worksheet>')
    workbook = ('<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/'
                'spreadsheetml/2006/main"><sheets><sheet name="Scores" sheetId="1"/></sheets></workbook>')
    return zip_bytes({'xl/workbook.xml': workbook, 'xl/sharedStrings.xml': strings,
                      'xl/worksheets/sheet1.xml': sheet})


def build_pptx(slides):
    files = {'ppt/presentation.xml': '<?xml version="1.0"?><p:presentation xmlns:p="x"/>'}
    for number, lines in enumerate(slides, start=1):
        body = ''.join(f'<a:p><a:r><a:t>{line}</a:t></a:r></a:p>' for line in lines)
        files[f'ppt/slides/slide{number}.xml'] = (
            '<?xml version="1.0" encoding="UTF-8"?><p:sld xmlns:p="http://schemas.openxmlformats.org/'
            f'presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
            f'<a:txBody>{body}</a:txBody></p:sld>')
    return zip_bytes(files)


def zip_bytes(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for name, body in files.items():
            archive.writestr(name, body)
    return buffer.getvalue()


class Extractors(unittest.TestCase):
    def test_pdf_text_keeps_page_markers(self):
        found = documents.extract(build_pdf('Hello evidence'), 'pdf')
        self.assertEqual(found['kind'], 'pdf')
        self.assertIn('Hello evidence', found['text'])
        self.assertIn('[第 1 页]', found['text'])
        self.assertFalse(found['truncated'])

    def test_a_pdf_without_a_text_layer_says_it_is_probably_a_scan(self):
        found = documents.extract(build_pdf_without_text(), 'pdf')
        self.assertIn('扫描件', found['text'])

    def test_docx_paragraphs(self):
        found = documents.extract(build_docx(['第一章 引言', '结论：符号检验不成立']), 'docx')
        self.assertIn('第一章 引言', found['text'])
        self.assertIn('符号检验不成立', found['text'])

    def test_xlsx_cells_keep_sheet_and_shared_strings(self):
        found = documents.extract(build_xlsx([['模型', '准确率'], ['baseline', '78.1']]), 'xlsx')
        self.assertIn('[工作表 Scores]', found['text'])
        self.assertIn('baseline\t78.1', found['text'])

    def test_pptx_slides_in_order(self):
        found = documents.extract(build_pptx([['研究问题'], ['方法', '结果']]), 'pptx')
        self.assertIn('[第 1 页]\n研究问题', found['text'])
        self.assertIn('[第 2 页]\n方法\n结果', found['text'])

    def test_a_renamed_file_is_refused_instead_of_half_read(self):
        with self.assertRaisesRegex(ValueError, '不是有效的 PDF'):
            documents.extract(b'PK\x03\x04docx bytes', 'pdf')
        with self.assertRaisesRegex(ValueError, '内容不像 docx'):
            documents.extract(zip_bytes({'xl/workbook.xml': '<x/>'}), 'docx')

    def test_a_corrupt_zip_is_named(self):
        with self.assertRaisesRegex(ValueError, '损坏'):
            documents.extract(b'PK\x03\x04' + b'not a zip', 'docx')

    def test_too_large_documents_are_refused_not_truncated_silently(self):
        with self.assertRaisesRegex(ValueError, '文档最大 8 MB'):
            documents.extract(b'%PDF-' + b'0' * (documents.MAX_DOC + 1), 'pdf')

    def test_long_documents_are_cut_with_a_visible_marker(self):
        found = documents.extract(build_docx(['x' * 400] * 400), 'docx', limit=1200)
        self.assertTrue(found['truncated'])
        self.assertIn('已截断', found['text'])


class Attachments(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get('ECA_TEST_TMP', tempfile.gettempdir()))
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def wrap(self, raw, mime, name):
        import base64
        return [{'name': name, 'mime': mime, 'data': base64.b64encode(raw).decode()}]

    def test_a_document_attachment_becomes_text_not_an_image(self):
        items = attachments.prepare(self.root, self.wrap(build_pdf('Attention is all you need'),
                                                         documents.PDF_MIME, 'paper.pdf'))
        self.assertEqual(items[0]['doc'], 'pdf')
        self.assertIn('Attention is all you need', items[0]['text'])
        content = attachments.content({'content': 'summarise', 'attachments': items}, self.root)
        self.assertEqual(content[0]['type'], 'text')
        self.assertIn('pdf 文档', content[0]['text'])
        self.assertIn('[End attachment]', content[0]['text'])
        self.assertEqual(len(content), 1, 'a document must not add an image block')

    def test_a_renamed_document_is_refused_at_the_boundary(self):
        with self.assertRaisesRegex(ValueError, '不是有效的 PDF'):
            attachments.prepare(self.root, self.wrap(b'%NOTPDF', documents.PDF_MIME, 'x.pdf'))

    def test_an_unsupported_type_lists_what_is_supported(self):
        with self.assertRaisesRegex(ValueError, 'PDF'):
            attachments.prepare(self.root, self.wrap(b'%PDF-1.4', 'application/x-7z-compressed', 'x.7z'))


if __name__ == '__main__':
    unittest.main()
