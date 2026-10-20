from pathlib import Path
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QListWidget, QPlainTextEdit, QSpinBox, QFileDialog, QSplitter)
from qr_engine import scan_image, scan_file, create_sheets, sheet_stock
from screen_capture import capture_screen


class ScanWorker(QThread):
    found = Signal(object, str)

    def __init__(self, paths=None, image=None, parent=None):
        super().__init__(parent)
        self.paths, self.image = paths or [], image

    def run(self):
        items, messages = [], []
        try:
            if self.image is not None:
                items.extend(scan_image(self.image))
            for path in self.paths:
                try:
                    found = scan_file(path)
                    items.extend(found)
                    if not found:
                        messages.append(f'{Path(path).name}: no readable QR codes.')
                except Exception as exc:
                    messages.append(f'{Path(path).name}: {exc}')
            if not items and not messages:
                messages.append('No readable QR codes found. Try a closer, sharper view with the entire code visible.')
        except Exception as exc:
            messages.append(str(exc))
        self.image = None
        self.found.emit(items, '\n'.join(messages))


class QRPanel(QWidget):
    def __init__(self, owner, canvas_type, page_image):
        super().__init__()
        self.owner, self.canvas_type, self.page_image = owner, canvas_type, page_image
        self.items, self.output, self.worker = [], None, None
        root = QVBoxLayout(self)
        title = QLabel('QR labels'); title.setObjectName('heading'); root.addWidget(title)
        hint = QLabel('Collect QR codes from your screen or files, then print them together. Captures and codes stay in this session.')
        hint.setWordWrap(True); root.addWidget(hint)
        toolbar = QHBoxLayout()
        self.capture = QPushButton('Capture screen…'); self.capture.clicked.connect(self.capture_codes)
        self.open = QPushButton('Add files…'); self.open.clicked.connect(self.choose_files)
        toolbar.addWidget(self.capture); toolbar.addWidget(self.open); toolbar.addStretch()
        root.addLayout(toolbar)
        settings = QHBoxLayout()
        settings.addWidget(QLabel('Paper'))
        self.stock = QComboBox(); self.stock.setMinimumWidth(220); settings.addWidget(self.stock, 1)
        self.layout_combo = QComboBox()
        for name, count in [('Full page · 1 code', 1), ('Quarter page · 4 codes', 4),
                            ('Third page landscape · 3 codes', 3)]:
            self.layout_combo.addItem(name, count)
        settings.addWidget(self.layout_combo)
        custom = QPushButton('Custom paper…'); custom.clicked.connect(owner.add_custom_size)
        settings.addWidget(custom); root.addLayout(settings)
        split = QSplitter(); root.addWidget(split, 1)
        left = QWidget(); left.setObjectName('glass'); col = QVBoxLayout(left)
        self.count = QLabel('Print queue · 0 codes'); col.addWidget(self.count)
        self.queue = QListWidget(); col.addWidget(self.queue, 1)
        actions = QHBoxLayout()
        for text, callback in [('Remove', self.remove), ('Duplicate', self.duplicate), ('Clear', self.clear)]:
            button = QPushButton(text); button.clicked.connect(callback); actions.addWidget(button)
        col.addLayout(actions); col.addWidget(QLabel('Data printed below the selected code'))
        self.data = QPlainTextEdit(); self.data.setReadOnly(True); self.data.setMaximumHeight(120)
        col.addWidget(self.data); split.addWidget(left)
        right = QWidget(); right.setObjectName('glass'); preview_layout = QVBoxLayout(right)
        self.preview = canvas_type(); preview_layout.addWidget(self.preview, 1)
        pagebar = QHBoxLayout(); pagebar.addWidget(QLabel('Preview page'))
        self.page = QSpinBox(); self.page.setRange(1, 1); pagebar.addWidget(self.page)
        self.pages = QLabel('of 0'); pagebar.addWidget(self.pages); pagebar.addStretch()
        preview_layout.addLayout(pagebar); split.addWidget(right); split.setSizes([380, 650])
        self.status = QLabel('Add codes to begin. You can add more before printing.')
        self.status.setWordWrap(True); root.addWidget(self.status)
        footer = QHBoxLayout(); footer.addStretch()
        self.save = QPushButton('Save QR sheets PDF…'); self.save.clicked.connect(self.save_pdf)
        self.print = QPushButton('Print QR sheets…'); self.print.setObjectName('primary')
        self.print.clicked.connect(self.print_sheets)
        footer.addWidget(self.save); footer.addWidget(self.print); root.addLayout(footer)
        self.queue.currentRowChanged.connect(self.show_data)
        self.page.valueChanged.connect(self.show_page)
        self.stock.currentIndexChanged.connect(self.refresh)
        self.layout_combo.currentIndexChanged.connect(self.refresh)
        self.sync_sizes()

    def sync_sizes(self):
        selected = (self.stock.currentData() or {}).get('id', 'a4-sheet')
        self.stock.blockSignals(True); self.stock.clear()
        sizes = [dict(id='a4-sheet', name='A4', width=210, height=297),
                 dict(id='letter-sheet', name='US Letter', width=215.9, height=279.4)]
        sizes += self.owner.size_store.sizes
        for stock in sizes:
            self.stock.addItem(stock['name'], stock)
        self.stock.setCurrentIndex(next((i for i, s in enumerate(sizes) if s['id']==selected), 0))
        self.stock.blockSignals(False)
        self.refresh()

    def choose_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, 'Add QR codes from files', '',
            'PDF and images (*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp *.gif *.webp)')
        if paths:
            self.add_files(paths)

    def capture_codes(self):
        if self.worker and self.worker.isRunning():
            return
        capture_screen(self.owner, self.canvas_type, lambda image: self.start_scan(image=image))

    def add_files(self, paths):
        self.start_scan(paths=paths)

    def start_scan(self, paths=None, image=None):
        if self.worker and self.worker.isRunning():
            self.status.setText('Please wait for the current scan, then add more files.')
            return
        self.capture.setEnabled(False); self.open.setEnabled(False)
        self.status.setText('Looking for QR codes…')
        if self.worker is not None:
            self.worker.deleteLater()
        self.worker = ScanWorker(paths, image, self)
        self.worker.found.connect(self.add_results)
        self.worker.finished.connect(self.scan_finished)
        self.worker.start()

    def scan_finished(self):
        self.capture.setEnabled(True); self.open.setEnabled(True)

    def add_results(self, items, message=''):
        self.items.extend(items)
        self.rebuild_queue()
        if self.output is not None or not self.items:
            self.status.setText(f'Added {len(items)} code(s). {len(self.items)} in the queue.'+
                               (' '+message if message else ' Add more or print when ready.'))
        elif message:
            self.status.setText(self.status.text()+' '+message)

    def rebuild_queue(self):
        selected = self.queue.currentRow()
        self.queue.clear()
        for index, item in enumerate(self.items):
            summary = ' '.join(item.text.split())[:100] or '(binary data)'
            self.queue.addItem(f'{index+1}. {summary}\n{item.source}')
        if self.items:
            self.queue.setCurrentRow(max(0, min(selected, len(self.items)-1)))
        self.count.setText(f'Print queue · {len(self.items)} code(s)')
        self.refresh()

    def show_data(self, index):
        self.data.setPlainText(self.items[index].text if 0 <= index < len(self.items) else '')

    def remove(self):
        row = self.queue.currentRow()
        if row >= 0:
            self.items.pop(row); self.rebuild_queue()

    def duplicate(self):
        row = self.queue.currentRow()
        if row >= 0:
            self.items.insert(row+1, self.items[row]); self.rebuild_queue()

    def clear(self):
        self.items.clear(); self.rebuild_queue()

    def refresh(self):
        if self.output is not None:
            self.output.close(); self.output = None
        if self.items:
            try:
                self.output = create_sheets(self.items, self.stock.currentData(), self.layout_combo.currentData())
                self.status.setText(f'{len(self.items)} code(s) on {len(self.output)} page(s). Add more or print when ready.')
            except Exception as exc:
                self.status.setText(str(exc))
        count = len(self.output) if self.output is not None else 0
        self.save.setEnabled(count > 0); self.print.setEnabled(count > 0)
        self.page.setMaximum(max(1, count)); self.pages.setText(f'of {count}')
        self.show_page()

    def show_page(self):
        if self.output is not None:
            page = self.output[self.page.value()-1]
            self.preview.set_page(self.page_image(page), page.rect)
        else:
            self.preview.image = None; self.preview.update()

    def save_pdf(self):
        if self.output is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Save QR sheets', 'QR sheets.pdf', 'PDF (*.pdf)')
        if path:
            try:
                self.output.save(path, garbage=4, deflate=True)
                self.status.setText('Saved QR sheets.')
            except Exception as exc:
                self.owner.error(exc)

    def print_sheets(self):
        if self.output is not None:
            stock = sheet_stock(self.stock.currentData(), self.layout_combo.currentData())
            if self.owner.print_document(self.output, stock):
                self.status.setText('QR sheets sent to the printer. The queue is available to print again.')

    def dispose(self):
        if self.output is not None:
            self.output.close(); self.output = None
