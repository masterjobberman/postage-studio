import sys
from pathlib import Path
import pymupdf as fitz
from PySide6.QtCore import Qt, QRectF, QSizeF, Signal, QThread, QSettings, QStandardPaths
from PySide6.QtGui import QPixmap, QImage, QPainter, QColor, QPen, QPageSize, QPageLayout, QIcon
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QFileDialog, QMessageBox, QSplitter, QSpinBox, QFrame,
    QComboBox, QDialog, QFormLayout, QLineEdit, QDoubleSpinBox, QDialogButtonBox)
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from label_engine import open_document, detect_label, make_label
from label_sizes import SizeStore, dimensions_text, validate_size

def app_icon():
    return QIcon(str(Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'assets'/'postage-studio.ico'))

class CustomSizeDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setWindowTitle('Add custom label size')
        self.setMinimumWidth(380)
        form=QFormLayout(self)
        self.name=QLineEdit()
        self.name.setMaxLength(60)
        self.name.setPlaceholderText('e.g. My parcel labels')
        self.units=QComboBox()
        self.units.addItems(['Millimetres','Inches'])
        self.width=QDoubleSpinBox(); self.height=QDoubleSpinBox()
        for field,value in [(self.width,100),(self.height,150)]:
            field.setDecimals(3); field.setRange(10,1000); field.setValue(value)
            field.setSuffix(' mm')
        self.old_factor=1.
        self.units.currentIndexChanged.connect(self.change_units)
        form.addRow('Name',self.name)
        form.addRow('Units',self.units)
        form.addRow('Width',self.width)
        form.addRow('Height',self.height)
        hint=QLabel('Saved sizes will appear in the dropdown next time you open the app.')
        hint.setWordWrap(True); form.addRow(hint)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def change_units(self,index):
        factor=25.4 if index else 1.
        values=[field.value()*self.old_factor/factor for field in (self.width,self.height)]
        for field,value in zip((self.width,self.height),values):
            field.setDecimals(4 if index else 3)
            field.setRange(10/factor,1000/factor)
            field.setSuffix(' in' if index else ' mm');field.setValue(value)
        self.old_factor=factor

    def values(self):
        return validate_size(self.name.text(),self.width.value()*self.old_factor,self.height.value()*self.old_factor)

    def accept(self):
        try:
            self.values()
        except ValueError as exc:
            QMessageBox.warning(self,'Check label size',str(exc));return
        super().accept()


class DetectionWorker(QThread):
    detected = Signal(object, int, str)
    failed = Signal(str)

    def __init__(self, data, number, parent):
        super().__init__(parent)
        self.data, self.number = data, number

    def run(self):
        try:
            with fitz.open(stream=self.data, filetype='pdf') as doc:
                crop, angle, message = detect_label(doc[self.number])
                self.detected.emit(tuple(crop), angle, message)
        except Exception as exc:
            self.failed.emit(str(exc))


def page_image(page, dpi=140):
    # Bound raster memory for unusually large custom paper sizes.
    dpi=max(1,min(dpi,int((24_000_000/(page.rect.width*page.rect.height/72**2))**.5)))
    p = page.get_pixmap(dpi=dpi, alpha=False)
    return QImage(p.samples, p.width, p.height, p.stride, QImage.Format.Format_RGB888).copy()


class PageCanvas(QWidget):
    selected = Signal(object)
    def __init__(self, editable=False):
        super().__init__()
        self.editable = editable
        self.image = None
        self.crop = None
        self.start = None
        self.setMinimumSize(240, 300)
        if editable:
            self.setCursor(Qt.CursorShape.CrossCursor)

    def set_page(self, image, bounds, crop=None):
        self.image, self.bounds, self.crop = image, bounds, crop
        self.update()

    def display_rect(self):
        size = self.image.size().scaled(self.width()-36, self.height()-36, Qt.AspectRatioMode.KeepAspectRatio)
        return QRectF((self.width()-size.width())/2, (self.height()-size.height())/2, size.width(), size.height())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#e9eef3'))
        if self.image is None:
            painter.setPen(QColor('#64748b'))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, 'Drop a PDF or image here' if self.editable else 'Your label will appear here')
            return
        r = self.display_rect()
        painter.drawImage(r, self.image)
        if self.editable and self.crop:
            c = self.crop
            selection = QRectF(r.x()+c.x0/self.bounds.width*r.width(), r.y()+c.y0/self.bounds.height*r.height(), c.width/self.bounds.width*r.width(), c.height/self.bounds.height*r.height())
            painter.fillRect(selection, QColor(0, 150, 136, 30))
            painter.setPen(QPen(QColor('#008577'), 2))
            painter.drawRect(selection)

    def point(self, pos):
        r = self.display_rect()
        return (max(0, min(self.bounds.width, (pos.x()-r.x())/r.width()*self.bounds.width)), max(0, min(self.bounds.height, (pos.y()-r.y())/r.height()*self.bounds.height)))

    def mousePressEvent(self, event):
        if self.editable and self.image is not None and event.button() == Qt.MouseButton.LeftButton:
            self.start = self.point(event.position())

    def mouseMoveEvent(self, event):
        if self.start:
            x, y = self.point(event.position())
            a, b = self.start
            self.crop = fitz.Rect(min(a,x), min(b,y), max(a,x), max(b,y))
            self.update()

    def mouseReleaseEvent(self, event):
        if self.start:
            self.mouseMoveEvent(event)
            self.start = None
            self.selected.emit(self.crop)


class LabelApp(QMainWindow):
    def __init__(self, settings=None):
        super().__init__()
        self.doc = None
        self.output = None
        self.rotation = 0
        self.worker = None
        if settings is None:
            settings_dir=Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation))/'Postage Studio'
            settings_dir.mkdir(parents=True,exist_ok=True)
            settings=QSettings(str(settings_dir/'label-sizes.ini'),QSettings.Format.IniFormat)
        self.settings=settings
        self.size_store=SizeStore(settings)
        self.setWindowTitle('Postage Studio 1.2.1 • Label printing')
        self.setWindowIcon(app_icon())
        self.resize(1150, 820)
        self.setAcceptDrops(True)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 24, 28, 20)
        title = QLabel('Postage Studio')
        title.setStyleSheet('font-size:28px; font-weight:700; color:#102d3a')
        layout.addWidget(title)
        layout.addWidget(QLabel('A page in. A parcel-ready label out.   •   Everything stays on this computer.'))
        bar = QHBoxLayout()
        self.open_button = QPushButton('Open file…')
        self.open_button.clicked.connect(self.choose)
        bar.addWidget(self.open_button)
        bar.addStretch()
        bar.addWidget(QLabel('Page'))
        self.page_number = QSpinBox()
        self.page_number.setMinimum(1)
        self.page_number.valueChanged.connect(self.load_page)
        bar.addWidget(self.page_number)
        self.auto_button = QPushButton('Detect label')
        self.auto_button.clicked.connect(self.auto_crop)
        bar.addWidget(self.auto_button)
        self.full_button = QPushButton('Whole page')
        self.full_button.clicked.connect(self.full_page)
        bar.addWidget(self.full_button)
        self.rotate_button = QPushButton('Rotate 90°')
        self.rotate_button.clicked.connect(self.rotate)
        bar.addWidget(self.rotate_button)
        layout.addLayout(bar)
        sizebar=QHBoxLayout()
        sizebar.addWidget(QLabel('Label size'))
        self.size_combo=QComboBox()
        self.size_combo.setMinimumWidth(330)
        sizebar.addWidget(self.size_combo,1)
        self.add_size_button=QPushButton('Add custom size…')
        self.add_size_button.clicked.connect(self.add_custom_size)
        sizebar.addWidget(self.add_size_button)
        self.remove_size_button=QPushButton('Remove saved size')
        self.remove_size_button.clicked.connect(self.remove_custom_size)
        sizebar.addWidget(self.remove_size_button)
        layout.addLayout(sizebar)
        self.size_note=QLabel()
        self.size_note.setWordWrap(True)
        layout.addWidget(self.size_note)
        self.filename = QLabel('PDF, PNG, JPG, TIFF, BMP, GIF and WebP • Drag and drop supported')
        layout.addWidget(self.filename)
        split = QSplitter()
        self.source = PageCanvas(True)
        self.preview = PageCanvas()
        self.preview_heading=QLabel('2  PRINT PREVIEW')
        for heading, widget in [(QLabel('1  SOURCE  •  Drag to adjust the crop'), self.source), (self.preview_heading, self.preview)]:
            pane = QWidget()
            col = QVBoxLayout(pane)
            col.setContentsMargins(0, 8, 0, 8)
            col.addWidget(heading)
            col.addWidget(widget, 1)
            split.addWidget(pane)
        layout.addWidget(split, 1)
        self.source.selected.connect(self.set_crop)
        self.status = QLabel('Open a file to begin. You can choose the printer before anything prints.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        bottom = QHBoxLayout()
        bottom.addWidget(QLabel('Actual size • No stretching • Small safety margin'))
        bottom.addStretch()
        self.save_button = QPushButton('Save label PDF…')
        self.save_button.clicked.connect(self.save)
        bottom.addWidget(self.save_button)
        self.print_button = QPushButton('Print label…')
        self.print_button.setStyleSheet('background:#087e73;color:white;font-weight:700')
        self.print_button.clicked.connect(self.print_label)
        bottom.addWidget(self.print_button)
        layout.addLayout(bottom)
        self.setStyleSheet('QMainWindow{background:#f8fafc} QLabel{color:#334155;font-size:13px} QPushButton{padding:10px 16px;border:1px solid #cbd5e1;border-radius:6px;background:white;font-size:13px} QPushButton:disabled{color:#a0aab6;background:#f1f5f9} QSpinBox,QComboBox,QDoubleSpinBox,QLineEdit{padding:8px}')
        self.populate_sizes(self.settings.value('selected_size','4x6'))
        self.size_combo.currentIndexChanged.connect(self.size_changed)
        self.enable_controls(False)

    @property
    def selected_size(self):
        return self.size_combo.currentData()

    def populate_sizes(self,selected='4x6'):
        self.size_combo.blockSignals(True)
        self.size_combo.clear()
        for size in self.size_store.sizes:
            text=size['name']+(f" · {dimensions_text(size)}" if size.get('custom') else '')
            self.size_combo.addItem(text,size)
        index=next((i for i in range(self.size_combo.count()) if self.size_combo.itemData(i)['id']==selected),0)
        self.size_combo.setCurrentIndex(index)
        self.size_combo.blockSignals(False)
        self.size_changed()

    def size_changed(self):
        size=self.selected_size
        self.settings.setValue('selected_size',size['id']);self.settings.sync()
        self.remove_size_button.setEnabled(bool(size.get('custom')))
        self.preview_heading.setText('2  PRINT PREVIEW  •  '+dimensions_text(size))
        text='Width × height: '+dimensions_text(size)+'. One label per page; artwork keeps its proportions.'
        if size['width']*size['height'] < 100*145:
            text+=' Small stock reduces barcode size; check readability before using postage.'
        self.size_note.setText(text)
        if self.doc and hasattr(self,'crop'):
            self.refresh()

    def add_custom_size(self):
        dialog=CustomSizeDialog(self)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            try:
                size=self.size_store.add(*dialog.values())
                self.populate_sizes(size['id'])
            except ValueError as exc:
                self.error(exc)

    def remove_custom_size(self):
        if self.selected_size.get('custom'):
            self.size_store.remove(self.selected_size['id'])
            self.populate_sizes()

    def enable_controls(self, enabled):
        self.source.setEnabled(enabled)
        for w in [self.page_number,self.auto_button,self.full_button,self.rotate_button,self.save_button,self.print_button]:
            w.setEnabled(enabled)

    def error(self, exc):
        QMessageBox.warning(self, 'Unable to complete that action', str(exc))

    def choose(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Open postage file', '', 'Postage files (*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp *.gif *.webp);;All files (*)')
        if path:
            self.open_file(path)

    def open_file(self, path):
        if self.worker and self.worker.isRunning():
            return
        try:
            doc = open_document(path)
            if not len(doc):
                raise ValueError('This file has no pages.')
            if self.doc:
                self.doc.close()
            self.doc, self.path = doc, Path(path)
            self.filename.setText(self.path.name)
            self.page_number.blockSignals(True)
            self.page_number.setMaximum(len(doc))
            self.page_number.setValue(1)
            self.page_number.blockSignals(False)
            self.enable_controls(True)
            self.load_page()
        except Exception as exc:
            self.error(exc)

    def load_page(self):
        if self.doc:
            self.page = self.doc[self.page_number.value()-1]
            if self.page.rotation:
                self.page.remove_rotation()
            self.source.set_page(page_image(self.page), self.page.rect)
            self.auto_crop()

    def auto_crop(self):
        if self.worker and self.worker.isRunning():
            return
        self.enable_controls(False)
        self.open_button.setEnabled(False)
        self.size_combo.setEnabled(False)
        self.add_size_button.setEnabled(False)
        self.remove_size_button.setEnabled(False)
        self.status.setText('Finding the complete label and checking orientation…')
        self.worker = DetectionWorker(self.doc.tobytes(), self.page_number.value()-1, self)
        self.worker.detected.connect(self.apply_detection)
        self.worker.failed.connect(self.detection_failed)
        self.worker.finished.connect(self.detection_finished)
        self.worker.start()

    def apply_detection(self, crop, rotation, message):
        self.crop, self.rotation = fitz.Rect(crop), rotation
        self.status.setText(message)
        self.refresh()

    def detection_failed(self, message):
        self.crop, self.rotation = self.page.rect, 0
        self.refresh()
        self.status.setText('Automatic detection failed. Drag around the label to select it. '+message)

    def detection_finished(self):
        self.enable_controls(True)
        self.open_button.setEnabled(True)
        self.size_combo.setEnabled(True)
        self.add_size_button.setEnabled(True)
        self.remove_size_button.setEnabled(bool(self.selected_size.get('custom')))

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.status.setText('Finishing label detection. Please close the window in a moment.')
            event.ignore()
        else:
            event.accept()

    def full_page(self):
        self.crop = self.page.rect
        self.refresh()

    def set_crop(self, crop):
        if crop.width < 3 or crop.height < 3:
            self.source.crop = self.crop
            self.source.update()
            return
        self.crop = crop
        self.status.setText('Custom crop selected. Check that no label text or barcode is cut off.')
        self.refresh()

    def rotate(self):
        self.rotation = (self.rotation + 90) % 360
        self.refresh()

    def refresh(self):
        try:
            if self.output:
                self.output.close()
            size=self.selected_size
            self.output = make_label(self.doc, self.page_number.value()-1, self.crop, self.rotation,size['width'],size['height'])
            self.preview.set_page(page_image(self.output[0]), self.output[0].rect)
            self.source.crop = self.crop
            self.source.update()
        except Exception as exc:
            self.output = None
            self.error(exc)

    def save(self):
        if self.output is None:
            return
        size=self.selected_size
        suffix=f"-{size['width']:g}x{size['height']:g}mm.pdf"
        path, _ = QFileDialog.getSaveFileName(self, 'Save label PDF', str(self.path.with_name(self.path.stem+suffix)), 'PDF (*.pdf)')
        if path:
            try:
                if Path(path).resolve() == self.path.resolve():
                    raise ValueError('Choose a different filename to preserve your original file.')
                self.output.save(path, garbage=4, deflate=True)
                self.status.setText('Saved: '+path)
            except Exception as exc:
                self.error(exc)

    def print_label(self):
        if self.output is None:
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        stock=self.selected_size
        width,height=stock['width'],stock['height']
        printer.setPageSize(QPageSize(QSizeF(min(width,height),max(width,height)),QPageSize.Unit.Millimeter,stock['name'],QPageSize.SizeMatchPolicy.ExactMatch))
        printer.setPageOrientation(QPageLayout.Orientation.Landscape if width>height else QPageLayout.Orientation.Portrait)
        printer.setFullPage(True)
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle('Print label • '+dimensions_text(stock))
        if dialog.exec() != QPrintDialog.DialogCode.Accepted:
            return
        size = printer.pageLayout().fullRect(QPageLayout.Unit.Millimeter)
        if abs(size.width()-width)>.8 or abs(size.height()-height)>.8:
            QMessageBox.warning(self,'Check printer paper size','Select '+dimensions_text(stock)+' (width × height) in printer properties. The driver currently reports '+f'{size.width():g} × {size.height():g} mm.')
            return
        painter = QPainter()
        try:
            if not painter.begin(printer):
                raise ValueError('The printer could not start. Check its connection and settings.')
            dpi = min(printer.resolution(), 600)
            image = page_image(self.output[0], dpi)
            target = QRectF(0,0,printer.resolution()*width/25.4,printer.resolution()*height/25.4)
            painter.drawImage(target,image)
            painter.end()
            self.status.setText('Label sent to '+printer.printerName()+'. Check the printed label before use.')
        except Exception as exc:
            if painter.isActive():
                painter.end()
            self.error(exc)

    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self,event):
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            self.open_file(urls[0].toLocalFile())


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setWindowIcon(app_icon())
    window = LabelApp()
    window.show()
    if len(sys.argv)>1:
        window.open_file(sys.argv[1])
    sys.exit(app.exec())
