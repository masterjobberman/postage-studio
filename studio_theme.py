"""Soft translucent surfaces over a quiet, painted pastel background."""
from PySide6.QtCore import Qt, QRectF, QSize
from PySide6.QtGui import QColor, QPainter, QLinearGradient, QRadialGradient, QPen
from PySide6.QtWidgets import QWidget, QListWidget, QListView, QStyledItemDelegate, QStyle


class StudioBackground(QWidget):
    def paintEvent(self,event):
        painter=QPainter(self)
        painter.fillRect(self.rect(),QColor('#f5f7fb'))
        for x,y,rgb in [(.12,.18,(196,215,245)),(.85,.3,(218,208,241)),(.45,.95,(196,227,217))]:
            gradient=QRadialGradient(self.width()*x,self.height()*y,self.width()*.65)
            gradient.setColorAt(0,QColor(*rgb,85));gradient.setColorAt(1,QColor(*rgb,0))
            painter.fillRect(self.rect(),gradient)


class TemplateGallery(QListWidget):
    def __init__(self):
        super().__init__()
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setMovement(QListView.Movement.Static)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setWrapping(True);self.setWordWrap(True);self.setSpacing(6)
        self.setUniformItemSizes(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.setMinimumWidth(330)
        self.setItemDelegate(TemplateCard(self))
        self.setAccessibleName('Template gallery')

    def resizeEvent(self,event):
        super().resizeEvent(event)
        columns=max(1,self.viewport().width()//170)
        columns=min(2,columns)
        self.setGridSize(QSize(max(150,(self.viewport().width()-18)//columns),230))


class TemplateCard(QStyledItemDelegate):
    def sizeHint(self,option,index):
        return QSize(max(150,self.parent().gridSize().width()-10),230)

    def paint(self,painter,option,index):
        row=index.data(Qt.ItemDataRole.UserRole)
        if not row:return
        painter.save();painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect=QRectF(option.rect).adjusted(5,5,-5,-5)
        selected=bool(option.state & QStyle.StateFlag.State_Selected)
        hover=bool(option.state & QStyle.StateFlag.State_MouseOver)
        colours=['#f1f5fc','#f5f2fa','#f0f7f4']
        painter.setBrush(QColor('#eaf1fd' if selected else colours[index.row()%3]))
        painter.setPen(QPen(QColor('#507cc8' if selected else '#dfe5ee'),2 if selected else 1))
        painter.drawRoundedRect(rect,12,12)
        if hover and not selected:
            painter.setBrush(QColor(255,255,255,65));painter.drawRoundedRect(rect,12,12)
        image=index.data(Qt.ItemDataRole.DecorationRole)
        if image is not None:
            available=QSize(int(rect.width()-30),int(rect.height()-55))
            size=image.size().scaled(available,Qt.AspectRatioMode.KeepAspectRatio)
            paper=QRectF(rect.center().x()-size.width()/2,rect.y()+12,size.width(),size.height())
            painter.fillRect(paper.translated(1,2),QColor(35,52,74,16))
            painter.fillRect(paper,Qt.GlobalColor.white);painter.drawImage(paper,image)
        else:
            painter.setPen(QColor('#64748b'))
            painter.drawText(rect.adjusted(12,12,-12,-45),Qt.AlignmentFlag.AlignCenter,'Preparing preview…')
        painter.setPen(QColor('#1e304a'))
        painter.drawText(rect.adjusted(8,rect.height()-43,-8,-6),
                         Qt.AlignmentFlag.AlignHCenter|Qt.AlignmentFlag.AlignVCenter|Qt.TextFlag.TextWordWrap,row['name'])
        if option.state & QStyle.StateFlag.State_HasFocus:
            painter.setPen(QPen(QColor('#315ea8'),1,Qt.PenStyle.DotLine));painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(4,4,-4,-4),9,9)
        painter.restore()


STYLE = '''
QMainWindow { background:#f5f7fb; }
QWidget { font-family:"Segoe UI"; font-size:13px; color:#26364e; }
QLabel { background:transparent; }
QLabel#brand {font-size:22px;font-weight:700;color:#172943;}
QLabel#heading {font-size:23px;font-weight:700;color:#172943;}
QLabel#section {font-size:15px;font-weight:600;}
QLabel#muted {color:#65758c;font-size:12px;}
QWidget#glass {background:rgba(255,255,255,165);border:1px solid rgba(255,255,255,220);border-radius:14px;}
QWidget#header {background:rgba(255,255,255,175);border:1px solid #e4e9f1;border-radius:12px;}
QTabWidget::pane {border:0;background:transparent;}
QPushButton {padding:9px 13px;border:1px solid #d5deeb;border-radius:8px;background:rgba(255,255,255,210);font-weight:500;}
QPushButton:hover {background:#edf3fc;border-color:#a8bde1;}
QPushButton:pressed {background:#dce8fa;}
QPushButton:focus {border:2px solid #648bce;}
QPushButton:disabled {color:#9ca8b8;background:rgba(247,249,252,170);border-color:#e2e7ef;}
QPushButton#primary {background:#426eb9;color:white;border:1px solid #426eb9;font-weight:600;padding:10px 26px;}
QPushButton#primary:hover {background:#345eaa;}
QPushButton#primary:disabled {background:#b3c4df;border-color:#b3c4df;color:#f5f7fc;}
QPushButton#nav {border:0;background:transparent;padding:11px 20px;}
QPushButton#nav:checked {background:#e7effc;color:#315fa9;font-weight:600;}
QPushButton#filter {border:0;background:transparent;border-radius:16px;padding:8px 14px;}
QPushButton#filter:checked {background:#e7effc;color:#315fa9;}
QLineEdit,QPlainTextEdit,QComboBox,QSpinBox,QDoubleSpinBox {background:rgba(255,255,255,225);border:1px solid #d3ddea;border-radius:7px;padding:8px;selection-background-color:#dbe8fd;selection-color:#182b48;}
QLineEdit:focus,QPlainTextEdit:focus,QComboBox:focus {border-color:#6d93cf;}
QLineEdit:disabled,QPlainTextEdit:disabled {color:#77849a;background:#f1f4f8;}
QListWidget {background:transparent;border:0;outline:0;}
QScrollArea {background:transparent;border:0;}
QScrollBar:vertical {background:transparent;width:10px;margin:2px;}
QScrollBar::handle:vertical {background:#c9d3e2;border-radius:4px;min-height:30px;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {height:0;}
QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical {background:transparent;}
QSplitter::handle {background:transparent;width:8px;}
QToolTip {background:#fff;color:#26364e;border:1px solid #c9d3e2;padding:5px;}
'''
