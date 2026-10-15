import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QPainter
from PySide6.QtCore import Qt
from PySide6.QtSvg import QSvgRenderer
from PIL import Image
app=QApplication([])
image=QImage(512,512,QImage.Format.Format_ARGB32)
image.fill(Qt.GlobalColor.transparent)
painter=QPainter(image)
QSvgRenderer('assets/postage-studio.svg').render(painter)
painter.end()
image.save('assets/postage-studio.png')
Image.open('assets/postage-studio.png').save('assets/postage-studio.ico',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
