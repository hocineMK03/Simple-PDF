from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QCursor
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
)


class ToolCard(QFrame):

    clicked = Signal()

    def __init__(self, title, description, icon_path, enabled=True):
        super().__init__()

        self._enabled = enabled

        self.setObjectName("toolCard")
        self.setCursor(QCursor(Qt.PointingHandCursor if enabled else Qt.ArrowCursor))
        self.setMinimumWidth(230)
        self.setFixedHeight(180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        icon = QSvgWidget(icon_path)
        icon.setFixedSize(QSize(44, 44))
        icon.setAttribute(Qt.WA_TranslucentBackground)

        titleLabel = QLabel(title)
        titleLabel.setObjectName("cardTitle")

        descLabel = QLabel(description)
        descLabel.setObjectName("cardDescription")
        descLabel.setWordWrap(True)

        arrow = QLabel("→" if enabled else "Soon")
        arrow.setObjectName("cardArrow")
        arrow.setAlignment(Qt.AlignRight)

        layout.addWidget(icon)
        layout.addWidget(titleLabel)
        layout.addWidget(descLabel)
        layout.addStretch()
        layout.addWidget(arrow)

        if not enabled:
            self.setProperty("disabledCard", True)

    def mouseReleaseEvent(self, event):
        if self._enabled and self.rect().contains(event.pos()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)
