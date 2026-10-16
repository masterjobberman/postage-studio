"""Template browser, editor, local imports and print preview."""
from pathlib import Path
import json
import pymupdf as fitz
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QListWidget,QListWidgetItem,QLineEdit,QPlainTextEdit,QSplitter,QFileDialog,QSpinBox,QScrollArea,QComboBox,QButtonGroup,QSizePolicy)
from templates import DESIGNS,defaults,render_template,TemplateLibrary
from label_engine import make_label
from studio_theme import TemplateGallery


class TemplatePanel(QWidget):
    def __init__(self, owner, canvas_type, image_function, folder):
        super().__init__()
        self.setAcceptDrops(True)
        self.owner=owner;self.image_function=image_function
        self.library=TemplateLibrary(folder)
        self.current=None;self.output=None;self.document=None;self.loading=False
        self.thumbnail_cache={};self.thumbnail_queue=[]
        self.thumbnail_timer=QTimer(self);self.thumbnail_timer.setInterval(25)
        self.thumbnail_timer.timeout.connect(self.next_thumbnail)
        layout=QVBoxLayout(self);layout.setContentsMargins(0,8,0,0)
        split=QSplitter();layout.addWidget(split,1)
        left=QWidget();left.setObjectName('glass');col=QVBoxLayout(left)
        col.setContentsMargins(18,20,18,16);col.setSpacing(12)
        heading=QLabel('Choose a template');heading.setObjectName('heading');col.addWidget(heading)
        self.count=QLabel('15 designs');self.count.setObjectName('muted');col.addWidget(self.count)
        self.search=QLineEdit();self.search.setPlaceholderText('Search templates…')
        self.search.setClearButtonEnabled(True);self.search.setAccessibleName('Search templates');col.addWidget(self.search)
        filters=QHBoxLayout();self.filters=QButtonGroup(self);self.filters.setExclusive(True)
        for i,name in enumerate(['All templates','My templates']):
            button=QPushButton(name);button.setObjectName('filter');button.setCheckable(True)
            self.filters.addButton(button,i);filters.addWidget(button)
        self.filters.button(0).setChecked(True);filters.addStretch();col.addLayout(filters)
        self.list=TemplateGallery();col.addWidget(self.list,1)
        self.empty=QLabel('');self.empty.setWordWrap(True);self.empty.setObjectName('muted');col.addWidget(self.empty)
        button=QPushButton('Import template…');button.clicked.connect(self.choose_import)
        button.setToolTip('Save a private copy of a PDF or image in My templates');col.addWidget(button)
        split.addWidget(left)
        right=QWidget();right.setObjectName('glass');right_col=QVBoxLayout(right)
        right_col.setContentsMargins(18,20,18,16);right_col.setSpacing(12)
        self.selection_heading=QLabel('Daily checklist');self.selection_heading.setObjectName('heading')
        self.selection_heading.setWordWrap(True);right_col.addWidget(self.selection_heading)
        content=QSplitter();right_col.addWidget(content,1)
        self.preview=canvas_type();content.addWidget(self.preview)
        editor=QWidget();form=QVBoxLayout(editor);form.setContentsMargins(8,0,6,0);form.setSpacing(9)
        form.addWidget(QLabel('Title'))
        self.title=QLineEdit();self.title.setMaxLength(100);form.addWidget(self.title)
        form.addWidget(QLabel('Details'))
        self.subtitle=QLineEdit();self.subtitle.setMaxLength(150);form.addWidget(self.subtitle)
        self.rows_label=QLabel('Tasks / content');form.addWidget(self.rows_label)
        self.rows=QPlainTextEdit();self.rows.setMinimumHeight(130);self.rows.setMaximumHeight(230);form.addWidget(self.rows,1)
        self.help=QLabel();self.help.setWordWrap(True);self.help.setObjectName('muted');form.addWidget(self.help)
        self.qr_label=QLabel('QR code: website or text')
        form.addWidget(self.qr_label);self.qr=QLineEdit();self.qr.setMaxLength(300);form.addWidget(self.qr)
        self.page_label=QLabel('Page to print')
        form.addWidget(self.page_label);self.page=QSpinBox();self.page.setMinimum(1);form.addWidget(self.page)
        form.addWidget(QLabel('Label size'))
        self.stock=QComboBox();self.stock.setAccessibleName('Template label size')
        self.stock.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.stock.setMinimumContentsLength(10);form.addWidget(self.stock)
        custom=QPushButton('Custom size…');custom.clicked.connect(owner.add_custom_size);form.addWidget(custom)
        self.delete_size=QPushButton('Remove saved size');self.delete_size.clicked.connect(owner.remove_custom_size);form.addWidget(self.delete_size)
        self.reset=QPushButton('Reset design');self.reset.clicked.connect(self.reset_design);form.addWidget(self.reset)
        self.remove=QPushButton('Remove import');self.remove.clicked.connect(self.remove_import)
        self.remove.setToolTip('Remove only the saved copy; your original file is kept');form.addWidget(self.remove)
        form.addStretch()
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(editor);scroll.setMinimumWidth(235)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.viewport().setAutoFillBackground(False);editor.setAutoFillBackground(False)
        editor.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        content.addWidget(scroll);content.setSizes([380,250]);content.setChildrenCollapsible(False)
        self.status=QLabel();self.status.setWordWrap(True);self.status.setObjectName('muted');right_col.addWidget(self.status)
        self.note=QLabel('');self.note.setWordWrap(True);self.note.setObjectName('muted');right_col.addWidget(self.note)
        bottom=QHBoxLayout();bottom.addStretch()
        self.save_button=QPushButton('Save PDF…');self.save_button.clicked.connect(self.save);bottom.addWidget(self.save_button)
        self.print_button=QPushButton('Print…');self.print_button.setObjectName('primary')
        self.print_button.clicked.connect(self.print_template);bottom.addWidget(self.print_button)
        right_col.addLayout(bottom);split.addWidget(right)
        split.setSizes([500,790]);split.setChildrenCollapsible(False)
        self.stock.currentIndexChanged.connect(lambda index: owner.size_combo.setCurrentIndex(index) if index>=0 else None)
        self.search.textChanged.connect(self.filter_items)
        self.filters.idClicked.connect(self.filter_items)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(200);self.timer.timeout.connect(self.refresh)
        for field in (self.title,self.subtitle,self.rows,self.qr):
            field.setAcceptDrops(False)
            field.textChanged.connect(self.edited)
        self.page.valueChanged.connect(self.refresh)
        self.list.currentItemChanged.connect(self.select)
        self.populate()

    def populate(self, selected=None):
        self.thumbnail_timer.stop();self.thumbnail_queue=[]
        self.list.blockSignals(True);self.list.clear()
        chosen=None
        for heading,items in [('BUILT-IN DESIGNS',DESIGNS),('MY TEMPLATES',self.library.items())]:
            header=QListWidgetItem(heading);header.setFlags(Qt.ItemFlag.NoItemFlags);self.list.addItem(header)
            for row in items:
                item=QListWidgetItem(row['name']);item.setData(Qt.ItemDataRole.UserRole,row);self.list.addItem(item)
                if row['id']==selected or chosen is None:chosen=item
        self.list.blockSignals(False)
        self.list.setCurrentItem(chosen)
        self.filter_items()
        self.thumbnail_queue=[self.list.item(i) for i in range(self.list.count()) if self.list.item(i).data(Qt.ItemDataRole.UserRole)]
        self.thumbnail_timer.start()

    def sync_stock(self):
        self.stock.blockSignals(True);self.stock.clear()
        for i in range(self.owner.size_combo.count()):
            self.stock.addItem(self.owner.size_combo.itemText(i))
        self.stock.setCurrentIndex(self.owner.size_combo.currentIndex());self.stock.blockSignals(False)
        self.delete_size.setVisible(bool(self.owner.selected_size.get('custom')))

    def filter_items(self,*args):
        query=self.search.text().strip().casefold();visible=[]
        for i in range(self.list.count()):
            item=self.list.item(i);row=item.data(Qt.ItemDataRole.UserRole)
            match=bool(row and query in row['name'].casefold() and
                       (self.filters.checkedId()==0 or row.get('custom')))
            item.setHidden(not match)
            if match:visible.append(item)
        self.count.setText(f"{len(visible)} templates" if self.filters.checkedId()==0 else f"{len(visible)} saved imports")
        self.empty.setText('No matching templates. Try another search.' if query else 'Import a PDF or image to start your own collection.')
        self.empty.setVisible(not visible)
        if visible and (not self.list.currentItem() or self.list.currentItem().isHidden()):
            self.list.setCurrentItem(visible[0])
        elif visible and self.current is None:
            self.select(self.list.currentItem())
        elif not visible:
            self.current=None;self.clear_output('Choose a template to preview and print.')
            self.selection_heading.setText('Choose a template')
            for widget in (self.title,self.subtitle,self.rows,self.reset,self.remove):widget.setEnabled(False)

    def next_thumbnail(self):
        if not self.thumbnail_queue:
            self.thumbnail_timer.stop();return
        item=self.thumbnail_queue.pop(0);row=item.data(Qt.ItemDataRole.UserRole)
        try:
            if row['id'] not in self.thumbnail_cache:
                if row.get('custom'):
                    with fitz.open(stream=self.library.path(row['id']).read_bytes(),filetype='pdf') as doc:
                        image=self.image_function(doc[0],60)
                else:
                    with render_template(row,defaults(row),101.6,152.4) as doc:
                        image=self.image_function(doc[0],60)
                self.thumbnail_cache[row['id']]=image.scaled(240,320,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
            item.setData(Qt.ItemDataRole.DecorationRole,self.thumbnail_cache[row['id']])
        except Exception:
            pass  # Selecting an unreadable import presents the full error.

    def select(self, item, previous=None):
        self.timer.stop()
        self.current=item.data(Qt.ItemDataRole.UserRole) if item else None
        if not self.current:return
        if self.document:self.document.close();self.document=None
        custom=self.current.get('custom',False)
        self.selection_heading.setText(self.current['name'])
        self.remove.setVisible(custom);self.reset.setVisible(not custom)
        for field in (self.title,self.subtitle,self.rows,self.rows_label):field.setVisible(not custom)
        self.loading=True
        try:
            values=defaults(self.current) if not custom else dict(title=self.current['name'],subtitle='',rows='',qr='')
            if not custom:
                try:
                    saved=json.loads(self.owner.settings.value('template-drafts/'+self.current['id'],'{}'))
                    values.update({key:value for key,value in saved.items() if key in values and isinstance(value,str)})
                except (ValueError,TypeError,AttributeError):pass
            self.title.setText(values['title']);self.subtitle.setText(values['subtitle'])
            self.rows.setPlainText(values['rows']);self.qr.setText(values['qr'])
            for field in (self.title,self.subtitle,self.rows,self.reset):field.setEnabled(not custom)
            self.remove.setEnabled(custom)
            qr=not custom and self.current['kind']=='thanks'
            self.qr.setVisible(qr);self.qr_label.setVisible(qr)
            self.page.setVisible(custom);self.page_label.setVisible(custom)
            if custom:
                self.document=fitz.open(stream=self.library.path(self.current['id']).read_bytes(),filetype='pdf')
                self.page.setMaximum(len(self.document));self.page.setValue(1)
                self.help.setText('Imported artwork is printed as provided, fitted without stretching. Select one page to print. Edit the original file and import it again to change its contents.')
            else:
                kind=self.current['kind']
                detail='Use | between columns.' if kind=='stock' else ('Use Label | Your text on each line.' if kind in ('fields','week') else 'One item per line. Blank lines leave writing space.')
                self.help.setText(detail+' Changes are saved locally for this design.')
        except Exception as exc:
            self.clear_output(str(exc));return
        finally:self.loading=False
        self.refresh()

    def values(self):
        return dict(title=self.title.text(),subtitle=self.subtitle.text(),rows=self.rows.toPlainText(),qr=self.qr.text())

    def edited(self):
        if self.loading or not self.current:return
        # Disable printing immediately so it never sends an out-of-date preview.
        self.save_button.setEnabled(False);self.print_button.setEnabled(False)
        if not self.current.get('custom'):
            self.owner.settings.setValue('template-drafts/'+self.current['id'],json.dumps(self.values()))
            self.owner.settings.sync()
        self.timer.start()

    def clear_output(self, message):
        if self.output:self.output.close()
        self.output=None;self.preview.image=None;self.preview.update()
        self.save_button.setEnabled(False);self.print_button.setEnabled(False);self.status.setText(message)

    def refresh(self, *args):
        if self.loading or not self.current:return
        self.timer.stop()
        try:
            self.sync_stock()
            size=self.owner.selected_size
            if self.current.get('custom'):
                if self.document is None:raise ValueError('Import could not be opened. Remove it and import it again.')
                page=self.document[self.page.value()-1]
                result=make_label(self.document,page.number,page.rect,0,size['width'],size['height'])
            else:result=render_template(self.current,self.values(),size['width'],size['height'])
            if self.output:self.output.close()
            self.output=result
            self.preview.set_page(self.image_function(result[0]),result[0].rect)
            self.save_button.setEnabled(True);self.print_button.setEnabled(True)
            self.status.setText('Ready: '+self.current['name'])
            self.note.setText('One page per print. Best at 4 × 6 inches or larger.'+
                (' Small stock shrinks text and QR codes; check readability.' if min(size['width']/101.6,size['height']/152.4)<.8 else ''))
        except Exception as exc:self.clear_output(str(exc))

    def reset_design(self):
        if not self.current or self.current.get('custom'):return
        self.owner.settings.remove('template-drafts/'+self.current['id']);self.owner.settings.sync()
        self.select(self.list.currentItem())

    def choose_import(self):
        path,_=QFileDialog.getOpenFileName(self,'Import a template','','PDF and images (*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp *.gif *.webp)')
        if path:self.import_file(path)

    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls() and event.mimeData().urls()[0].isLocalFile():
            event.acceptProposedAction()

    def dropEvent(self,event):
        if event.mimeData().hasUrls() and event.mimeData().urls()[0].isLocalFile():
            self.import_file(event.mimeData().urls()[0].toLocalFile())
            event.acceptProposedAction()

    def import_file(self, path):
        try:
            row=self.library.add(path);self.search.clear();self.filters.button(1).setChecked(True);self.populate(row['id'])
        except Exception as exc:self.owner.error(exc)

    def remove_import(self):
        if not self.current or not self.current.get('custom'):return
        try:
            if self.document:self.document.close();self.document=None
            self.clear_output('Removing imported template…')
            self.library.remove(self.current['id']);self.filters.button(0).setChecked(True);self.search.clear();self.populate()
        except Exception as exc:self.owner.error(exc)

    def save(self):
        self.refresh()
        if self.output is None:return
        path,_=QFileDialog.getSaveFileName(self,'Save template PDF','template.pdf','PDF (*.pdf)')
        if path:
            try:
                destination=Path(path).resolve()
                if destination.is_relative_to(self.library.folder.resolve()):
                    raise ValueError('Save exported PDFs outside the private template library.')
                self.output.save(path,garbage=4,deflate=True);self.status.setText('Template PDF saved.')
            except Exception as exc:self.owner.error(exc)

    def print_template(self):
        self.refresh()
        if self.output is not None:
            if self.owner.print_document(self.output,self.owner.selected_size):self.status.setText('Template sent to the selected printer.')

    def dispose(self):
        self.timer.stop();self.thumbnail_timer.stop();self.thumbnail_queue=[]
        if self.output:self.output.close();self.output=None
        if self.document:self.document.close();self.document=None
