import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json
import tempfile
from pathlib import Path
import pymupdf as fitz
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings
from PySide6.QtGui import QFontDatabase,QFont
from PySide6.QtPrintSupport import QPrinter,QPrintDialog
import postage_app
from postage_app import LabelApp,CustomSizeDialog,app_icon
from label_sizes import SizeStore,PRESETS,validate_size

def run_checks(report):
    report.parent.mkdir(parents=True,exist_ok=True)
    results=[]
    app=QApplication.instance() or QApplication([])
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    app.setFont(QFont('Segoe UI',10))
    app.setStyle('Fusion')
    try:
        with tempfile.TemporaryDirectory(prefix='postage-size-test-') as temp:
            settings=QSettings(str(Path(temp)/'sizes.ini'),QSettings.Format.IniFormat)
            store=SizeStore(settings)
            custom=store.add('My 3 by 5 labels',76.2,127)
            second=store.add('Wide parcel',150,100)
            assert store.add('Same dimensions',76.2,127)['id']==custom['id']
            settings2=QSettings(str(Path(temp)/'sizes.ini'),QSettings.Format.IniFormat)
            assert len(SizeStore(settings2).custom)==2
            results.append('Custom sizes persist across independent settings instances; duplicate dimensions reuse existing size.')
            for bad in [('',40,50),('Bad',0,40),('Bad',float('nan'),40),('Bad',40,1001)]:
                try:validate_size(*bad)
                except ValueError:pass
                else:raise AssertionError('Invalid size accepted')
            dialog=CustomSizeDialog()
            dialog.name.setText('Inches')
            dialog.units.setCurrentIndex(1)
            dialog.width.setValue(3);dialog.height.setValue(5)
            assert dialog.values()==('Inches',76.2,127)
            dialog.units.setCurrentIndex(0)
            assert dialog.values()==('Inches',76.2,127)
            dialog.show();app.processEvents();dialog.grab().save(str(report.parent/'Custom size dialog.png'));dialog.close()
            results.append('Inch/mm conversion and invalid dimensions checked.')
            window=LabelApp(settings2)
            window.show()
            doc=fitz.open();page=doc.new_page(width=288,height=432)
            page.draw_rect(fitz.Rect(12,12,276,420),color=(0,0,0))
            page.insert_text((30,60),'LABEL SIZE CHECK',fontsize=18)
            for x in range(30,250,8):page.draw_rect(fitz.Rect(x,260,x+3,360),fill=(0,0,0))
            window.doc=doc;window.page=doc[0];window.crop=page.rect;window.rotation=0
            window.path=Path(temp)/'sample.pdf'
            window.source.set_page(postage_app.page_image(page),page.rect,page.rect)
            window.enable_controls(True)
            assert not app_icon().isNull() and not window.windowIcon().isNull()
            class FilePrinter(QPrinter):
                def __init__(self,mode):
                    super().__init__(mode)
                    self.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
                    self.setOutputFileName(str(Path(temp)/'printed.pdf'))
            class AcceptDialog:
                DialogCode=QPrintDialog.DialogCode
                def __init__(self,*args):pass
                def setWindowTitle(self,text):pass
                def exec(self):return self.DialogCode.Accepted
            postage_app.QPrinter=FilePrinter;postage_app.QPrintDialog=AcceptDialog
            def fail_warning(*args):raise AssertionError(str(args))
            postage_app.QMessageBox.warning=fail_warning
            for index in range(window.size_combo.count()):
                window.size_combo.setCurrentIndex(index);window.size_changed()
                size=window.selected_size
                assert abs(window.output[0].rect.width-size['width']*72/25.4)<.01
                assert abs(window.output[0].rect.height-size['height']*72/25.4)<.01
                saved=Path(temp)/'exported.pdf'
                window.output.save(saved)
                with fitz.open(saved) as exported:
                    assert abs(exported[0].rect.width-size['width']*72/25.4)<.01
                window.print_label()
                with fitz.open(Path(temp)/'printed.pdf') as printed:
                    assert abs(printed[0].rect.width-size['width']*72/25.4)<1
                    assert abs(printed[0].rect.height-size['height']*72/25.4)<1
                results.append('PDF export and print: '+size['name'])
            selected=window.selected_size['id']
            restored=LabelApp(QSettings(str(Path(temp)/'sizes.ini'),QSettings.Format.IniFormat))
            assert restored.selected_size['id']==selected
            restored.close()
            app.processEvents();window.grab().save(str(report.parent/'Size options application.png'))
            window.remove_custom_size()
            assert len(SizeStore(QSettings(str(Path(temp)/'sizes.ini'),QSettings.Format.IniFormat)).custom)==1
            assert window.selected_size['id']=='4x6'
            results.append('Last selection restored, custom size removed, preset sizes preserved, application icon loaded.')
            window.close()
        report.write_text(json.dumps({'passed':True,'checks':results},indent=2),encoding='utf-8')
        return 0
    except Exception as exc:
        report.write_text(json.dumps({'passed':False,'checks':results,'error':repr(exc)},indent=2),encoding='utf-8')
        return 1

if __name__=='__main__':
    raise SystemExit(run_checks(Path('output/verification/sizes-source.json')))
