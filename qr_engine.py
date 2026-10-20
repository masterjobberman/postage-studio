"""Decode QR images and create printable, paginated QR sheets locally."""
from dataclasses import dataclass
import html
import math
import textwrap
import pymupdf as fitz
import qrcode
import zxingcpp
from label_engine import open_document


@dataclass(frozen=True)
class QRItem:
    data: bytes
    text: str
    source: str = ''


def scan_image(image, source='Screen selection'):
    results = zxingcpp.read_barcodes(image, formats=zxingcpp.BarcodeFormat.QRCode,
                                    text_mode=zxingcpp.TextMode.Plain)
    results = sorted(results, key=lambda r: (r.position.top_left.y, r.position.top_left.x))
    return [QRItem(bytes(r.bytes), r.text, source) for r in results if r.valid]


def scan_file(path):
    from PIL import Image
    from pathlib import Path
    items = []
    with open_document(path) as document:
        for number, page in enumerate(document):
            # Bound memory while retaining enough detail for small QR codes.
            scale = min(3, math.sqrt(24_000_000 / (page.rect.width * page.rect.height)))
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
            items.extend(scan_image(image, f'{Path(path).name} · page {number+1}'))
    return items


def sheet_stock(stock, layout):
    result = dict(stock)
    if layout == 3:
        result['width'], result['height'] = max(stock['width'], stock['height']), min(stock['width'], stock['height'])
    return result


def create_sheets(items, stock, layout):
    if layout not in (1, 4, 3):
        raise ValueError('Choose one, four or three QR codes per page.')
    if not items:
        raise ValueError('Add a QR code first.')
    stock = sheet_stock(stock, layout)
    width, height = stock['width']*72/25.4, stock['height']*72/25.4
    columns, rows = (2, 2) if layout == 4 else ((3, 1) if layout == 3 else (1, 1))
    margin, gap = 14.2, 11.4
    cw, ch = (width-2*margin-gap*(columns-1))/columns, (height-2*margin-gap*(rows-1))/rows
    doc = fitz.open()
    try:
        for index, item in enumerate(items):
            if index % layout == 0:
                page = doc.new_page(width=width, height=height)
            slot = index % layout
            x, y = margin+(slot % columns)*(cw+gap), margin+(slot // columns)*(ch+gap)
            qr = qrcode.QRCode(border=4, error_correction=qrcode.constants.ERROR_CORRECT_M)
            qr.add_data(item.data, optimize=0)
            qr.make(fit=True)
            matrix = qr.get_matrix()
            text_height = min(ch*.38, max(32, ch*.2))
            size = min(cw, ch-text_height-8)
            module = size/len(matrix)
            if module < .7:
                raise ValueError(f'Code {index+1} is too dense for this paper/layout. Choose larger paper or fewer codes per page.')
            left = x+(cw-size)/2
            shape = page.new_shape()
            for row, cells in enumerate(matrix):
                for col, dark in enumerate(cells):
                    if dark:
                        shape.draw_rect(fitz.Rect(left+col*module, y+row*module,
                                                  left+(col+1)*module, y+(row+1)*module))
            shape.finish(color=None, fill=(0, 0, 0))
            shape.commit()
            rect = fitz.Rect(x, y+size+8, x+cw, y+ch)
            # Explicit wrapping handles long URLs without changing the QR bytes.
            display = ''.join(c if c.isprintable() or c in '\n\t' else f'\\x{ord(c):02x}'
                              for c in item.text)
            lines = []
            for line in display.split('\n'):
                lines.extend(textwrap.wrap(line, width=max(8, int(cw/6.6)),
                                           replace_whitespace=False) or [''])
            content = '<br>'.join(html.escape(line) for line in lines) or '(empty QR data)'
            spare, scale = page.insert_htmlbox(rect, f'<div>{content}</div>',
                css='div {font-family:sans-serif; font-size:11pt; text-align:center;}',
                scale_low=7/11)
            if spare < 0:
                raise ValueError(f'The data below code {index+1} will not fit legibly. Choose larger paper or fewer codes per page.')
        return doc
    except Exception:
        doc.close()
        raise
