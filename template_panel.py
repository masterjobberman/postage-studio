"""Template browser, editor, local imports and print preview."""
from pathlib import Path
import json
import pymupdf as fitz
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QListWidget,QListWidgetItem,QLineEdit,QPlainTextEdit,QSplitter,QFileDialog,QSpinBox)
from templates import DESIGNS,defaults,render_template,TemplateLibrary
from label_engine import make_label


class TemplatePanel(QWidget):
    def __init__(self, owner, canvas_type, image_function, folder):
        super().__init__()
        self.owner=owner;self.image_function=image_function
        self.library=TemplateLibrary(folder)
        self.current=None;self.output=None;self.document=None;self.loading=False
        layout=QVBoxLayout(self)
        intro=QLabel('Choose a design, edit its text, then preview and print. Imports are saved on this computer only.')
        intro.setWordWrap(True);layout.addWidget(intro)
        split=QSplitter();layout.addWidget(split,1)
        left=QWidget();col=QVBoxLayout(left)
        self.list=QListWidget();self.list.setMinimumWidth(205);col.addWidget(self.list,1)
        button=QPushButton('Import my template…');button.clicked.connect(self.choose_import);col.addWidget(button)
        self.remove=QPushButton('Remove imported template');self.remove.clicked.connect(self.remove_import);col.addWidget(self.remove)
        split.addWidget(left)
        editor=QWidget();form=QVBoxLayout(editor)
        form.addWidget(QLabel('Title'))
        self.title=QLineEdit();self.title.setMaxLength(100);form.addWidget(self.title)
        form.addWidget(QLabel('Details / subtitle'))
        self.subtitle=QLineEdit();self.subtitle.setMaxLength(150);form.addWidget(self.subtitle)
        self.help=QLabel();self.help.setWordWrap(True);form.addWidget(self.help)
        self.rows=QPlainTextEdit();form.addWidget(self.rows,1)
        self.qr_label=QLabel('Optional QR code: website or text')
        form.addWidget(self.qr_label);self.qr=QLineEdit();self.qr.setMaxLength(300);form.addWidget(self.qr)
        self.reset=QPushButton('Reset this design');self.reset.clicked.connect(self.reset_design);form.addWidget(self.reset)
        self.page_label=QLabel('Imported page to print')
        form.addWidget(self.page_label);self.page=QSpinBox();self.page.setMinimum(1);form.addWidget(self.page)
        split.addWidget(editor)
        self.preview=canvas_type();split.addWidget(self.preview);split.setSizes([220,300,430])
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        bottom=QHBoxLayout()
        self.note=QLabel('');self.note.setWordWrap(True);bottom.addWidget(self.note,1)
        self.save_button=QPushButton('Save template PDF…');self.save_button.clicked.connect(self.save);bottom.addWidget(self.save_button)
        self.print_button=QPushButton('Print template…');self.print_button.clicked.connect(self.print_template);bottom.addWidget(self.print_button)
        layout.addLayout(bottom)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(200);self.timer.timeout.connect(self.refresh)
        for field in (self.title,self.subtitle,self.rows,self.qr):field.textChanged.connect(self.edited)
        self.page.valueChanged.connect(self.refresh)
        self.list.currentItemChanged.connect(self.select)
        self.populate()

    def populate(self, selected=None):
        self.list.blockSignals(True);self.list.clear()
        chosen=None
        for heading,items in [('BUILT-IN DESIGNS',DESIGNS),('MY TEMPLATES',self.library.items())]:
            header=QListWidgetItem(heading);header.setFlags(Qt.ItemFlag.NoItemFlags);self.list.addItem(header)
            for row in items:
                item=QListWidgetItem(row['name']);item.setData(Qt.ItemDataRole.UserRole,row);self.list.addItem(item)
                if row['id']==selected or chosen is None:chosen=item
        self.list.blockSignals(False)
        self.list.setCurrentItem(chosen)

    def select(self, item, previous=None):
        self.timer.stop()
        self.current=item.data(Qt.ItemDataRole.UserRole) if item else None
        if not self.current:return
        if self.document:self.document.close();self.document=None
        custom=self.current.get('custom',False)
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

    def import_file(self, path):
        try:
            row=self.library.add(path);self.populate(row['id'])
        except Exception as exc:self.owner.error(exc)

    def remove_import(self):
        if not self.current or not self.current.get('custom'):return
        try:
            if self.document:self.document.close();self.document=None
            self.clear_output('Removing imported template…')
            self.library.remove(self.current['id']);self.populate()
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
        self.timer.stop()
        if self.output:self.output.close();self.output=None
        if self.document:self.document.close();self.document=None
