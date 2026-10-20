"""User-initiated, memory-only screen selection."""
import math
import pymupdf as fitz
from PySide6.QtCore import QTimer, QBuffer, QIODevice
from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QLabel,
                              QDialogButtonBox, QInputDialog)


def image_png(image):
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, 'PNG'):
        raise ValueError('Unable to read the captured image.')
    return bytes(buffer.data())


def crop_image(image, rect):
    bounds = fitz.Rect(0, 0, image.width(), image.height())
    rect = fitz.Rect(rect) & bounds
    if rect.width < 2 or rect.height < 2:
        raise ValueError('Drag around a larger area of the screen.')
    x, y = math.floor(rect.x0), math.floor(rect.y0)
    return image.copy(x, y, math.ceil(rect.x1)-x, math.ceil(rect.y1)-y)


class CaptureDialog(QDialog):
    def __init__(self, parent, image, canvas_type):
        super().__init__(parent)
        self.setWindowTitle('Select an area of your screen')
        self.resize(1000, 720)
        self.original = image
        self.result_image = None
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Drag around the label or QR codes you want to use.'))
        self.canvas = canvas_type(True)
        bounds = fitz.Rect(0, 0, image.width(), image.height())
        self.canvas.set_page(image, bounds, bounds)
        layout.addWidget(self.canvas, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Use selection')
        buttons.accepted.connect(self.use_selection)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def use_selection(self):
        try:
            self.result_image = crop_image(self.original, self.canvas.crop)
        except ValueError as exc:
            self.parent().error(exc)
            return
        self.accept()


def capture_screen(owner, canvas_type, callback):
    if getattr(owner, '_capture_pending', False):
        return
    screens = QApplication.screens()
    if not screens:
        owner.error('No display is available to capture.')
        return
    names = [f'Display {i+1} · {s.name()} · {s.size().width()} × {s.size().height()}'
             for i, s in enumerate(screens)]
    index = 0
    if len(screens) > 1:
        choice, accepted = QInputDialog.getItem(owner, 'Capture screen',
                                                'Choose a display', names, 0, False)
        if not accepted:
            return
        index = names.index(choice)
    screen = screens[index]
    owner._capture_pending = True
    was_maximized = owner.isMaximized()
    owner.hide()

    def grab():
        try:
            image = screen.grabWindow(0).toImage()
            # Coordinates in the selection canvas represent physical image pixels.
            image.setDevicePixelRatio(1.0)
            if image.isNull():
                raise ValueError('This display could not be captured. Try opening a saved image instead.')
            owner.showMaximized() if was_maximized else owner.showNormal()
            owner.activateWindow()
            dialog = CaptureDialog(owner, image, canvas_type)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                callback(dialog.result_image)
        except Exception as exc:
            owner.error(exc)
        finally:
            owner._capture_pending = False
            if not owner.isVisible():
                owner.showMaximized() if was_maximized else owner.showNormal()

    QTimer.singleShot(450, grab)
