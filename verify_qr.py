"""Synthetic QR, capture-selection and multipage-print regressions."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import pymupdf as fitz
import qrcode
from PIL import Image
from PySide6.QtCore import QSettings
from PySide6.QtGui import QImage, QFontDatabase, QFont
from PySide6.QtWidgets import QApplication
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
import postage_app
from qr_engine import QRItem, scan_image, scan_file, create_sheets, sheet_stock
from screen_capture import crop_image, CaptureDialog


def run():
    output = Path('output/verification/qr'); output.mkdir(parents=True, exist_ok=True)
    stock = dict(name='A4', width=210, height=297)
    payloads = ['https://example.org/parcel/123', 'Café & <test>', 'Checklist 03',
                'Item 04', 'Item 05', 'Item 06', 'Item 07']
    items = [QRItem(s.encode('utf-8'), s, 'Synthetic test') for s in payloads]
    image = Image.new('RGB', (900, 500), 'white')
    for x, item in zip([20, 480], items):
        image.paste(qrcode.make(item.data).convert('RGB').resize((360, 360)), (x, 40))
    found = scan_image(image)
    assert {i.data for i in found} == {i.data for i in items[:2]}
    assert len(scan_image(image.rotate(90, expand=True))) == 2
    binary = b'\x00\xff\x80ABC'
    assert scan_image(qrcode.make(binary).get_image())[0].data == binary
    for layout, expected in [(1, 7), (4, 2), (3, 3)]:
        with create_sheets(items, stock, layout) as doc:
            assert len(doc) == expected
            size = sheet_stock(stock, layout)
            assert abs(doc[0].rect.width-size['width']*72/25.4) < .01
            assert abs(doc[0].rect.height-size['height']*72/25.4) < .01
            text = ''.join(p.get_text() for p in doc).replace('\u200b', '').replace('\n', '')
            for payload in payloads:
                assert payload in text, (payload, text)
            decoded = []
            for page in doc:
                pix = page.get_pixmap(dpi=150)
                decoded.extend(scan_image(Image.frombytes('RGB', (pix.width, pix.height), pix.samples)))
            assert [i.data for i in decoded] == [i.data for i in items]
            doc.save(output/f'layout-{layout}.pdf')
    assert len(scan_file(output/'layout-4.pdf')) == 7
    try:
        create_sheets(items, dict(width=10, height=10), 4)
    except ValueError:
        pass
    else:
        raise AssertionError('Tiny paper must block printing')
    app = QApplication.instance() or QApplication([])
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    app.setFont(QFont('Segoe UI', 10)); app.setStyle('Fusion')
    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)
        window = postage_app.LabelApp(QSettings(str(folder/'test.ini'), QSettings.Format.IniFormat))
        def fail(message): raise AssertionError(str(message))
        window.error = fail
        window.show(); window.tabs.setCurrentWidget(window.qr); app.processEvents()
        panel = window.qr
        image.save(folder/'screen.png')
        panel.start_scan(image=QImage(str(folder/'screen.png')))
        assert panel.worker.wait(10000)
        app.processEvents()
        assert len(panel.items) == 2 and panel.capture.isEnabled()
        panel.clear()
        panel.add_results(items[:2]); panel.add_results(items[2:])
        assert len(panel.items) == 7
        panel.layout_combo.setCurrentIndex(1)
        assert len(panel.output) == 2
        panel.queue.setCurrentRow(0); panel.duplicate(); assert len(panel.items) == 8
        panel.remove(); assert len(panel.items) == 7
        panel.clear(); assert panel.output is None and not panel.print.isEnabled()
        panel.add_results(items)
        panel.page.setValue(2); assert panel.page.value() == 2
        shot = QImage(800, 600, QImage.Format.Format_RGB32); shot.fill(0xffffffff)
        shot.setDevicePixelRatio(2)
        cropped = crop_image(shot, fitz.Rect(100, 50, 500, 350))
        assert (cropped.width(), cropped.height()) == (400, 300)
        dialog = CaptureDialog(window, shot, postage_app.PageCanvas)
        dialog.canvas.crop = fitz.Rect(100, 50, 500, 350); dialog.use_selection()
        assert dialog.result_image.width() == 400
        cancelled = CaptureDialog(window, shot, postage_app.PageCanvas); cancelled.reject()
        assert cancelled.result_image is None
        # The label capture integration works with a synthetic screen image.
        original_auto_crop = window.auto_crop
        window.auto_crop = lambda: None
        window.open_capture(shot)
        window.crop = window.page.rect; window.refresh()
        assert len(window.doc) == 1 and window.output is not None
        assert window.filename.text().startswith('Screen capture')
        window.auto_crop = original_auto_crop
        class FilePrinter(QPrinter):
            def __init__(self, mode):
                super().__init__(mode)
                self.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
                self.setOutputFileName(str(folder/'printed.pdf'))
        class AcceptDialog:
            DialogCode = QPrintDialog.DialogCode
            def __init__(self, *args): pass
            def setWindowTitle(self, *args): pass
            def exec(self): return self.DialogCode.Accepted
        postage_app.QPrinter = FilePrinter; postage_app.QPrintDialog = AcceptDialog
        panel.print_sheets()
        with fitz.open(folder/'printed.pdf') as printed:
            assert len(printed) == 2
            assert abs(printed[0].rect.width-210*72/25.4) < 1
        panel.page.setValue(1); app.processEvents()
        window.grab().save(str(output/'qr-tab.png'))
        window.resize(1060, 720); app.processEvents()
        window.grab().save(str(output/'qr-compact.png'))
        assert panel.print.isVisible()
        window.close()
    print('PASS: multiple/rotated/binary QR codes, captions, all layouts, pagination, queue, crop, cancellation, multipage PDF printing.')


if __name__ == '__main__':
    run()
