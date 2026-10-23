"""Synthetic designer editing, dragging, barcode decoding and print checks."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import tempfile
import numpy as np
import pymupdf as fitz
import zxingcpp
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont,QFontDatabase
from PySide6.QtCore import QSettings,Qt,QPoint
from PySide6.QtTest import QTest
from PySide6.QtPrintSupport import QPrinter,QPrintDialog
import postage_app


def run():
 app=QApplication.instance() or QApplication([])
 QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
 app.setFont(QFont('Segoe UI',10));app.setStyle('Fusion')
 out=Path('output/verification/designer');out.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory() as tmp:
  folder=Path(tmp)
  w=postage_app.LabelApp(QSettings(str(folder/'test.ini'),QSettings.Format.IniFormat))
  def fail(message):raise AssertionError(str(message))
  w.error=fail
  w.show();w.tabs.setCurrentWidget(w.designer);app.processEvents()
  p=w.designer
  assert p.output is None
  p.content.setPlainText('Packed with care\nCafé & <test>');p.bold.setChecked(True);p.refresh()
  assert p.output is not None,p.status.text()
  assert 'Café & <test>' in p.output[0].get_text()
  p.add_item('QR code');p.content.setPlainText('https://example.org/label/123');p.refresh()
  assert p.output is not None,p.status.text()
  p.add_item('Barcode');p.content.setPlainText('BOX-12345');p.fields['y'].setValue(110);p.refresh()
  assert p.output is not None,p.status.text()
  pix=p.output[0].get_pixmap(dpi=300)
  array=np.frombuffer(pix.samples,np.uint8).reshape(pix.height,pix.width,3)
  results=zxingcpp.read_barcodes(array)
  assert {r.text for r in results}=={'https://example.org/label/123','BOX-12345'},results
  assert abs(p.output[0].rect.width-288)<.01
  # Drag the actual canvas and verify physical movement and clamping.
  p.items_list.setCurrentRow(0);app.processEvents()
  paper=p.canvas.paper_rect();scale=paper.width()/101.6
  start=QPoint(round(paper.x()+10*scale),round(paper.y()+10*scale))
  end=QPoint(start.x()+round(2*scale),start.y()+round(4*scale))
  QTest.mousePress(p.canvas,Qt.MouseButton.LeftButton,pos=start)
  QTest.mouseMove(p.canvas,end)
  QTest.mouseRelease(p.canvas,Qt.MouseButton.LeftButton,pos=end)
  assert abs(p.elements[0]['x']-7)<.5 and abs(p.elements[0]['y']-9)<.5,p.elements[0]
  p.refresh();assert p.output is not None
  p.output.save(out/'designed-label.pdf')
  p.fields['width'].setValue(1000);p.refresh()
  assert p.output is None and not p.print.isEnabled()
  p.fields['width'].setValue(91.6);p.content.setPlainText('Too much text '*200);p.refresh()
  assert p.output is None
  p.content.setPlainText('Packed with care\nCafé & <test>');p.refresh()
  p.items_list.setCurrentRow(2);p.content.setPlainText('Café');p.refresh();assert p.output is None
  p.content.setPlainText('BOX-12345');p.refresh();assert p.output is not None
  p.duplicate();assert len(p.elements)==4
  p.remove();assert len(p.elements)==3
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
  p.print_label()
  with fitz.open(folder/'printed.pdf') as printed:
   assert len(printed)==1 and abs(printed[0].rect.width-288)<1
  p.items_list.setCurrentRow(0);app.processEvents();w.grab().save(str(out/'designer.png'))
  w.resize(1060,720);app.processEvents();w.grab().save(str(out/'designer-compact.png'))
  assert p.print.isVisible() and p.canvas.width()>250
  while p.elements:
   p.items_list.setCurrentRow(0);p.remove()
  assert p.output is None
  w.close()
 print('PASS: typed Unicode, text styling, QR and Code 128 decoding, actual canvas drag, bounds/overflow validation, duplicate/remove, exact-size PDF printing.')

if __name__=='__main__':run()
