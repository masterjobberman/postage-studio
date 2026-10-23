from PySide6.QtCore import Qt, QRectF, Signal, QTimer
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QListWidget, QPlainTextEdit, QDoubleSpinBox, QCheckBox, QFormLayout,
    QFileDialog, QSplitter, QScrollArea)
from designer_engine import render_design


class DesignCanvas(QWidget):
    selected = Signal(int)
    moved = Signal()

    def __init__(self, panel):
        super().__init__()
        self.panel = panel
        self.image = None
        self.drag = None
        self.setMinimumSize(260, 300)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def paper_rect(self):
        stock = self.panel.stock.currentData()
        scale = min((self.width()-40)/stock['width'], (self.height()-40)/stock['height'])
        return QRectF((self.width()-stock['width']*scale)/2,
                      (self.height()-stock['height']*scale)/2,
                      stock['width']*scale, stock['height']*scale)

    def point(self, pos):
        paper = self.paper_rect(); stock = self.panel.stock.currentData()
        return ((pos.x()-paper.x())*stock['width']/paper.width(),
                (pos.y()-paper.y())*stock['height']/paper.height())

    def paintEvent(self, event):
        painter = QPainter(self)
        paper = self.paper_rect()
        painter.fillRect(paper, QColor('white'))
        if self.image is not None:
            painter.drawImage(paper, self.image)
        index = self.panel.items_list.currentRow()
        if 0 <= index < len(self.panel.elements):
            item = self.panel.elements[index]
            scale = paper.width()/self.panel.stock.currentData()['width']
            painter.setPen(QPen(QColor('#426eb9'), 1.5, Qt.PenStyle.DashLine))
            painter.drawRect(QRectF(paper.x()+item['x']*scale, paper.y()+item['y']*scale,
                                   item['width']*scale, item['height']*scale))

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        x, y = self.point(event.position())
        for index in reversed(range(len(self.panel.elements))):
            item = self.panel.elements[index]
            if item['x'] <= x <= item['x']+item['width'] and item['y'] <= y <= item['y']+item['height']:
                self.selected.emit(index)
                self.drag = (index, x-item['x'], y-item['y'])
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                return
        self.selected.emit(-1)

    def mouseMoveEvent(self, event):
        if self.drag is None:
            return
        index, dx, dy = self.drag
        x, y = self.point(event.position()); item = self.panel.elements[index]
        stock = self.panel.stock.currentData()
        item['x'] = round(max(0, min(stock['width']-item['width'], x-dx)), 2)
        item['y'] = round(max(0, min(stock['height']-item['height'], y-dy)), 2)
        self.panel.schedule_refresh()
        self.update()

    def mouseReleaseEvent(self, event):
        if self.drag is not None:
            self.mouseMoveEvent(event)
            self.drag = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self.moved.emit()

    def resizeEvent(self, event):
        self.update()


class DesignerPanel(QWidget):
    def __init__(self, owner, page_image):
        super().__init__()
        self.owner, self.page_image = owner, page_image
        self.elements, self.output = [], None
        self.loading = False
        root = QVBoxLayout(self)
        title = QLabel('Label designer'); title.setObjectName('heading'); root.addWidget(title)
        root.addWidget(QLabel('Type your label, add codes, then drag each item into place.'))
        toolbar = QHBoxLayout()
        for kind in ['Text', 'QR code', 'Barcode']:
            button = QPushButton('Add '+kind.lower())
            button.clicked.connect(lambda checked=False, k=kind: self.add_item(k))
            toolbar.addWidget(button)
        toolbar.addStretch(); toolbar.addWidget(QLabel('Label size'))
        self.stock = QComboBox(); toolbar.addWidget(self.stock)
        custom = QPushButton('Custom size…'); custom.clicked.connect(owner.add_custom_size)
        toolbar.addWidget(custom); root.addLayout(toolbar)
        split = QSplitter(); root.addWidget(split, 1)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setMinimumWidth(300)
        controls = QWidget(); controls.setObjectName('glass'); col = QVBoxLayout(controls)
        col.addWidget(QLabel('Items · select to edit'))
        self.items_list = QListWidget(); self.items_list.setMaximumHeight(110); col.addWidget(self.items_list)
        actions = QHBoxLayout()
        for name, callback in [('Remove', self.remove), ('Duplicate', self.duplicate)]:
            button = QPushButton(name); button.clicked.connect(callback); actions.addWidget(button)
        col.addLayout(actions)
        self.editor = QWidget(); form = QFormLayout(self.editor); form.setContentsMargins(0, 0, 0, 0)
        self.content = QPlainTextEdit(); self.content.setPlaceholderText('Type text or code data here…')
        self.content.setMinimumHeight(90); self.content.setMaximumHeight(140)
        form.addRow('Text / code data', self.content)
        self.fields = {}
        for key, label, low, high in [('x','Left (mm)',0,1000), ('y','Top (mm)',0,1000),
                                     ('width','Width (mm)',1,1000), ('height','Height (mm)',1,1000),
                                     ('font','Text size (pt)',6,144)]:
            field = QDoubleSpinBox(); field.setRange(low, high); field.setDecimals(2)
            self.fields[key] = field; form.addRow(label, field)
            field.valueChanged.connect(self.edit)
        self.bold = QCheckBox('Bold text'); form.addRow(self.bold)
        self.align = QComboBox(); self.align.addItems(['left','center','right']); form.addRow('Text alignment', self.align)
        self.caption = QCheckBox('Show code data underneath'); form.addRow(self.caption)
        col.addWidget(self.editor); col.addStretch(); scroll.setWidget(controls); split.addWidget(scroll)
        self.canvas = DesignCanvas(self); split.addWidget(self.canvas); split.setSizes([340, 700])
        self.status = QLabel(); self.status.setWordWrap(True); root.addWidget(self.status)
        bottom = QHBoxLayout(); bottom.addWidget(QLabel('Drag to position · Exact label size'))
        bottom.addStretch()
        self.save = QPushButton('Save label PDF…'); self.save.clicked.connect(self.save_pdf)
        self.print = QPushButton('Print label…'); self.print.setObjectName('primary'); self.print.clicked.connect(self.print_label)
        bottom.addWidget(self.save); bottom.addWidget(self.print); root.addLayout(bottom)
        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.setInterval(120)
        self.timer.timeout.connect(self.refresh)
        self.items_list.currentRowChanged.connect(self.select)
        self.canvas.selected.connect(self.items_list.setCurrentRow)
        self.canvas.moved.connect(lambda: self.select(self.items_list.currentRow()))
        self.content.textChanged.connect(self.edit); self.bold.toggled.connect(self.edit)
        self.caption.toggled.connect(self.edit); self.align.currentIndexChanged.connect(self.edit)
        self.stock.currentIndexChanged.connect(self.refresh)
        self.sync_sizes()
        self.add_item('Text')

    def sync_sizes(self):
        selected = (self.stock.currentData() or self.owner.selected_size)['id']
        self.stock.blockSignals(True); self.stock.clear()
        for size in self.owner.size_store.sizes:
            self.stock.addItem(size['name'], size)
        self.stock.setCurrentIndex(next((i for i in range(self.stock.count())
            if self.stock.itemData(i)['id']==selected), 0))
        self.stock.blockSignals(False)
        self.refresh()

    def add_item(self, kind):
        stock = self.stock.currentData()
        width = max(1, stock['width']-10) if kind != 'QR code' else min(45, stock['width']-4)
        height = min(30 if kind=='Text' else (55 if kind=='QR code' else 28), stock['height']-4)
        x = min(5, max(0, stock['width']-width))
        y = min(5+len(self.elements)*32, max(0, stock['height']-height))
        self.elements.append(dict(kind=kind, text='', x=x, y=y, width=width, height=height,
                                  font=16, bold=False, align='left', caption=kind!='Text'))
        self.items_list.addItem(kind); self.items_list.setCurrentRow(len(self.elements)-1)
        self.content.setFocus(); self.schedule_refresh()

    def select(self, index):
        self.loading = True
        valid = 0 <= index < len(self.elements); self.editor.setEnabled(valid)
        if valid:
            item = self.elements[index]; self.content.setPlainText(item['text'])
            for key, field in self.fields.items(): field.setValue(item[key])
            self.bold.setChecked(item['bold']); self.align.setCurrentText(item['align'])
            self.caption.setChecked(item['caption'])
            text = item['kind']=='Text'
            self.fields['font'].setEnabled(text); self.bold.setEnabled(text); self.align.setEnabled(text)
            self.caption.setEnabled(not text)
        self.loading = False; self.canvas.update()

    def edit(self):
        index = self.items_list.currentRow()
        if self.loading or index < 0: return
        item = self.elements[index]
        item.update(text=self.content.toPlainText(), bold=self.bold.isChecked(),
                    caption=self.caption.isChecked(), align=self.align.currentText())
        item.update({key: field.value() for key, field in self.fields.items()})
        self.items_list.item(index).setText(item['kind']+' · '+' '.join(item['text'].split())[:30])
        self.schedule_refresh()

    def schedule_refresh(self):
        self.save.setEnabled(False); self.print.setEnabled(False); self.timer.start()

    def refresh(self):
        self.timer.stop()
        if self.output is not None: self.output.close(); self.output = None
        try:
            doc, errors = render_design(self.elements, self.stock.currentData())
            self.canvas.image = self.page_image(doc[0]); self.canvas.update()
            if errors or not self.elements:
                doc.close(); self.status.setText(errors[0] if errors else 'Add text or a code to begin.')
            else:
                self.output = doc
                self.status.setText('Ready to print. Select an item to edit it, or drag it on the label.')
        except Exception as exc:
            self.status.setText(str(exc)); self.canvas.image = None; self.canvas.update()
        self.save.setEnabled(self.output is not None); self.print.setEnabled(self.output is not None)

    def remove(self):
        index = self.items_list.currentRow()
        if index < 0: return
        self.elements.pop(index)
        self.items_list.blockSignals(True); self.items_list.takeItem(index); self.items_list.blockSignals(False)
        self.select(self.items_list.currentRow()); self.refresh()

    def duplicate(self):
        index = self.items_list.currentRow()
        if index < 0: return
        self.elements.append(dict(self.elements[index]))
        self.items_list.addItem(self.elements[-1]['kind']); self.items_list.setCurrentRow(len(self.elements)-1)
        self.refresh()

    def save_pdf(self):
        self.refresh()
        if self.output is None: return
        path, _ = QFileDialog.getSaveFileName(self, 'Save designed label', 'My label.pdf', 'PDF (*.pdf)')
        if path:
            try: self.output.save(path, garbage=4, deflate=True)
            except Exception as exc: self.owner.error(exc)

    def print_label(self):
        self.refresh()
        if self.output is not None:
            self.owner.print_document(self.output, self.stock.currentData())

    def dispose(self):
        self.timer.stop()
        if self.output is not None: self.output.close(); self.output = None
