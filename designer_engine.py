"""Physical-size, local label artwork shared by the editor and PDF output."""
import html
import numpy as np
import pymupdf as fitz
import zxingcpp

PT = 72 / 25.4


def render_design(elements, stock):
    doc = fitz.open()
    page = doc.new_page(width=stock['width']*PT, height=stock['height']*PT)
    errors = []
    for index, item in enumerate(elements):
        rect = fitz.Rect(item['x']*PT, item['y']*PT,
                         (item['x']+item['width'])*PT, (item['y']+item['height'])*PT)
        try:
            if not item['text'].strip():
                raise ValueError('Enter some text or code data.')
            if rect.width <= 0 or rect.height <= 0 or not page.rect.contains(rect):
                raise ValueError('Move or resize this item to fit inside the label.')
            if item['kind'] == 'Text':
                content = html.escape(item['text']).replace('\n', '<br>')
                css = ('body {margin:0;} div {font-family:sans-serif; '
                       f"font-size:{item['font']}pt; text-align:{item['align']}; "
                       f"font-weight:{'bold' if item['bold'] else 'normal'};"+'}')
                spare, _ = page.insert_htmlbox(rect, '<div>'+content+'</div>', css=css, scale_low=1)
                if spare < 0:
                    raise ValueError('Text does not fit. Enlarge the box or reduce the text size.')
            else:
                qr = item['kind'] == 'QR code'
                if not qr and (not item['text'].isascii() or not item['text'].isprintable()):
                    raise ValueError('Code 128 needs printable ASCII text. Use a QR code for other characters.')
                code = zxingcpp.create_barcode(item['text'],
                    zxingcpp.BarcodeFormat.QRCode if qr else zxingcpp.BarcodeFormat.Code128)
                matrix = np.asarray(zxingcpp.write_barcode_to_image(code, add_quiet_zones=True))
                caption_height = 24 if item['caption'] else 0
                available = rect.height-caption_height
                if available < 8:
                    raise ValueError('Increase the height to make room for the code and caption.')
                h, w = matrix.shape
                if qr:
                    size = min(rect.width, available)
                    box = fitz.Rect(rect.x0+(rect.width-size)/2, rect.y0,
                                    rect.x0+(rect.width+size)/2, rect.y0+size)
                else:
                    box = fitz.Rect(rect.x0, rect.y0, rect.x1, rect.y0+available)
                if box.width/w < .7 or (qr and box.height/h < .7):
                    raise ValueError('Code is too dense at this size. Make it wider or shorten its data.')
                shape = page.new_shape()
                # Merge adjacent modules into horizontal runs for compact vector PDF artwork.
                for row in range(h):
                    dark = np.r_[False, matrix[row] < 128, False]
                    edges = np.flatnonzero(dark[1:] != dark[:-1])
                    for start, end in zip(edges[::2], edges[1::2]):
                        shape.draw_rect(fitz.Rect(box.x0+start*box.width/w, box.y0+row*box.height/h,
                                                box.x0+end*box.width/w, box.y0+(row+1)*box.height/h))
                shape.finish(color=None, fill=(0, 0, 0)); shape.commit()
                if item['caption']:
                    caption = fitz.Rect(rect.x0, box.y1+3, rect.x1, rect.y1)
                    spare, _ = page.insert_htmlbox(caption, '<div>'+html.escape(item['text']).replace('\n','<br>')+'</div>',
                        css='body {margin:0;} div {font:9pt sans-serif; text-align:center;}', scale_low=1)
                    if spare < 0:
                        raise ValueError('Code caption does not fit. Enlarge the box or turn off the caption.')
        except Exception as exc:
            errors.append(f'Item {index+1}: {exc}')
            visible = rect & page.rect
            if not visible.is_empty:
                page.draw_rect(visible, color=(.8, .15, .15), width=.8)
    return doc, errors
