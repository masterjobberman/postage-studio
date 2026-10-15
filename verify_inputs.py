"""Synthetic-only input and label-detection regression checks."""
import tempfile
from pathlib import Path
import pymupdf as fitz
from PIL import Image
from label_engine import open_document, detect_label, make_label

with tempfile.TemporaryDirectory() as temporary:
    folder = Path(temporary)
    # Unsupported formats must not select arbitrary Pillow decoders.
    unsupported = folder / 'unsupported.png'
    Image.new('RGB', (20, 20), 'white').save(unsupported, format='PPM')
    try:
        open_document(unsupported)
    except ValueError:
        pass
    else:
        raise AssertionError('Unsupported image content accepted')
    for format_name, suffix in [('PNG', 'png'), ('JPEG', 'jpg'), ('TIFF', 'tif'),
                                ('BMP', 'bmp'), ('GIF', 'gif'), ('WEBP', 'webp')]:
        image_path = folder / ('test.' + suffix)
        Image.new('RGB', (200, 300), 'white').save(image_path, format=format_name)
        with open_document(image_path) as document:
            assert len(document) == 1
    # Identical synthetic label in five positions on an A4 page.
    for x, y in [(25, 25), (280, 25), (25, 400), (280, 400), (155, 215)]:
        document = fitz.open()
        page = document.new_page(width=595, height=842)
        expected = fitz.Rect(x, y, x + 250, y + 375)
        page.draw_rect(expected, color=(0, 0, 0), width=2)
        page.insert_text((x + 20, y + 40), 'SYNTHETIC SHIPPING LABEL', fontsize=10)
        page.insert_text((x + 20, y + 65), 'TEST ONLY - NOT VALID POSTAGE', fontsize=10)
        page.insert_text((x + 20, y + 95), 'Recipient: TEST RECIPIENT', fontsize=10)
        for offset in range(20, 230, 7):
            page.draw_rect(fitz.Rect(x + offset, y + 240, x + offset + 3, y + 320), fill=(0, 0, 0))
        crop, rotation, _ = detect_label(page)
        assert (crop & expected).get_area() / expected.get_area() > .95
        with make_label(document, 0, crop, rotation) as output:
            assert abs(output[0].rect.width - 288) < .01
            assert abs(output[0].rect.height - 432) < .01
        document.close()
print('Supported formats, rejected content and five synthetic label positions passed.')
