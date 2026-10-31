from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen


class StartupSplash(QSplashScreen):
    def __init__(self, logo_path: Path):
        splash_image = QPixmap(460, 240)
        splash_image.fill(QColor("#f3f6fa"))

        painter = QPainter(splash_image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ffffff"))
        painter.drawRoundedRect(QRectF(8, 8, 444, 224), 18, 18)
        painter.setBrush(QColor("#173b5e"))
        painter.drawRoundedRect(QRectF(8, 8, 8, 224), 4, 4)

        logo = QIcon(str(logo_path)).pixmap(68, 68)
        painter.drawPixmap(42, 48, logo)
        painter.setPen(QColor("#173b5e"))
        painter.setFont(QFont("Segoe UI", 24, QFont.Weight.DemiBold))
        painter.drawText(QRectF(126, 48, 280, 40), Qt.AlignmentFlag.AlignVCenter, "EduTrack")
        painter.setPen(QColor("#667085"))
        painter.setFont(QFont("Segoe UI", 11))
        painter.drawText(
            QRectF(128, 88, 280, 28),
            Qt.AlignmentFlag.AlignVCenter,
            "Gestión educativa",
        )
        painter.setPen(QColor("#e1e8f0"))
        painter.drawLine(42, 140, 418, 140)
        painter.setPen(QColor("#173b5e"))
        painter.setFont(QFont("Segoe UI", 10))
        painter.drawText(
            QRectF(42, 159, 325, 32),
            Qt.AlignmentFlag.AlignVCenter,
            "Preparando el espacio de trabajo…",
        )
        painter.end()

        super().__init__(
            splash_image,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        screen = QApplication.primaryScreen()
        if screen is not None:
            self.move(screen.availableGeometry().center() - self.rect().center())

        self._spinner_angle = 0
        self._animation_timer = QTimer(self)
        self._animation_timer.setInterval(40)
        self._animation_timer.timeout.connect(self._advance_spinner)
        self._animation_timer.start()

    def drawContents(self, painter: QPainter) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#00897b"), 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(
            QRectF(386, 161, 28, 28),
            self._spinner_angle * 16,
            275 * 16,
        )
        painter.restore()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        event.accept()

    def close_splash(self) -> None:
        self._animation_timer.stop()
        self.close()

    def _advance_spinner(self) -> None:
        self._spinner_angle = (self._spinner_angle + 24) % 360
        self.repaint()
