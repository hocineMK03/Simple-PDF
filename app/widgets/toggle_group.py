from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QPushButton, QWidget


class ToggleGroup(QWidget):
    """A row of mutually exclusive pill buttons (segmented control) with a
    clear checked color and hover state, used instead of native radio
    buttons which don't read well against the dark theme."""

    currentChanged = Signal(str)

    def __init__(self, options, default=None):
        super().__init__()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons = {}

        for value, label in options:
            button = QPushButton(label)
            button.setObjectName("toggleChip")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            self.group.addButton(button)
            self.buttons[value] = button
            layout.addWidget(button)

        layout.addStretch()

        default_value = default if default is not None else options[0][0]
        self.buttons[default_value].setChecked(True)

        self.group.buttonToggled.connect(self._on_toggled)

    def _on_toggled(self, button, checked):
        if checked:
            self.currentChanged.emit(self.value())

    def value(self):
        for value, button in self.buttons.items():
            if button.isChecked():
                return value
        return None

    def setValue(self, value):
        if value in self.buttons:
            self.buttons[value].setChecked(True)
