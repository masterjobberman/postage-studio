"""Synthetic template regressions. Never uses customer documents or printers."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import tempfile
import json
import pymupdf as fitz
import cv2
import numpy as np
from PIL import Image
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase,QFont
from PySide6.QtPrintSupport import QPrinter,QPrintDialog
import postage_app
from postage_app import LabelApp
from templates import DESIGNS,defaults,render_template,TemplateLibrary


def run():
    output=Path('output/verification/templates');output.mkdir(parents=True,exist_ok=True)
    app=QApplication.instance() or QApplication([])
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    app.setFont(QFont('Segoe UI',10))
    app.setStyle('Fusion')
    with tempfile.TemporaryDirectory() as temp, fitz.open() as gallery:
        folder=Path(temp)
        settings=QSettings(str(folder/'settings.ini'),QSettings.Format.IniFormat)
        window=LabelApp(settings);window.show();window.tabs.setCurrentIndex(1)
        def fail(message):raise AssertionError(str(message))
        window.error=fail
        panel=window.templates
        assert len(DESIGNS)==15
        for index,item in enumerate(DESIGNS):
            panel.list.setCurrentRow(index+1)
            assert panel.output is not None,(item['id'],panel.status.text())
            assert item['name'] in panel.output[0].get_text().replace('\n',' ')
            gallery.insert_pdf(panel.output)
            panel.output.save(output/(item['id']+'.pdf'))
        # Unicode text is preserved and markup is treated literally.
        values=defaults(DESIGNS[0]);values['title']='Café & <test>'
        with render_template(DESIGNS[0],values,101.6,152.4) as doc:
            assert 'Café & <test>' in doc[0].get_text()
        # Typed QR payload is faithfully encoded and decodable.
        values=defaults(DESIGNS[-1]);values['qr']='https://example.org/test'
        with render_template(DESIGNS[-1],values,101.6,152.4) as doc:
            pix=doc[0].get_pixmap(matrix=fitz.Matrix(3,3),alpha=False)
            array=np.frombuffer(pix.samples,np.uint8).reshape(pix.height,pix.width,3)
            decoded,_,_=cv2.QRCodeDetector().detectAndDecode(array)
            assert decoded==values['qr']
        # Edits persist per design, reset works and invalid drafts cannot print.
        panel.list.setCurrentRow(1);panel.title.setText('My checklist')
        assert not panel.print_button.isEnabled()
        panel.refresh();assert panel.output is not None
        panel.list.setCurrentRow(2);panel.list.setCurrentRow(1)
        assert panel.title.text()=='My checklist'
        panel.rows.setPlainText('\n'.join(['too many']*40));panel.refresh()
        assert panel.output is None and not panel.print_button.isEnabled()
        panel.reset_design();assert panel.output is not None
        # Import, restart library, source deletion, page selection and removal.
        source=folder/'synthetic.pdf'
        with fitz.open() as doc:
            for value in ['FIRST PAGE','SECOND PAGE']:
                page=doc.new_page(width=288,height=432);page.insert_text((30,50),value)
                page.insert_link({'kind':fitz.LINK_URI,'from':fitz.Rect(20,20,100,80),'uri':'https://example.org'})
            doc.embfile_add('private.txt',b'not copied')
            doc.save(source)
        panel.import_file(source);identifier=panel.current['id'];source.unlink()
        assert TemplateLibrary(panel.library.folder).items()[0]['id']==identifier
        assert panel.page.maximum()==2
        panel.page.setValue(2);assert 'SECOND PAGE' in panel.output[0].get_text()
        with fitz.open(panel.library.path(identifier)) as doc:
            assert doc.embfile_count()==0 and not doc[0].get_links()
        panel.remove_import();assert not panel.library.items()
        image=folder/'synthetic.png';Image.new('RGB',(200,300),'white').save(image)
        panel.import_file(image);assert panel.output is not None
        panel.remove_import()
        try:panel.library.path('../escape')
        except ValueError:pass
        else:raise AssertionError('Library path escaped')
        # Shared print path: selected page at the selected paper size.
        class FilePrinter(QPrinter):
            def __init__(self,mode):
                super().__init__(mode);self.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
                self.setOutputFileName(str(folder/'printed.pdf'))
        class AcceptDialog:
            DialogCode=QPrintDialog.DialogCode
            def __init__(self,*args):pass
            def setWindowTitle(self,*args):pass
            def exec(self):return self.DialogCode.Accepted
        postage_app.QPrinter=FilePrinter;postage_app.QPrintDialog=AcceptDialog
        for index in [0,4,6]:
            window.size_combo.setCurrentIndex(index);panel.print_template()
            with fitz.open(folder/'printed.pdf') as printed:
                assert abs(printed[0].rect.width-window.selected_size['width']*72/25.4)<1
                assert abs(printed[0].rect.height-window.selected_size['height']*72/25.4)<1
        window.size_combo.setCurrentIndex(0);panel.list.setCurrentRow(1)
        app.processEvents();window.grab().save(str(output/'templates-tab.png'))
        window.close()
        gallery.save(output/'all-templates.pdf')
    print('PASS: 15 designs, Unicode, QR, draft validation, persistence, imports, page selection and PDF printing.')


if __name__=='__main__':run()
