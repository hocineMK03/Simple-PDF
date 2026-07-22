from PySide6.QtCore import QObject, Signal


class Router(QObject):
    """Thin wrapper around a QStackedWidget with back-navigation history."""

    pageChanged = Signal(str)

    def __init__(self, stack):
        super().__init__()
        self.stack = stack
        self.pages = {}
        self.titles = {}
        self.history = []

    def register(self, name, widget, title):
        self.pages[name] = widget
        self.titles[name] = title
        self.stack.addWidget(widget)

    def go_to(self, name):
        if name not in self.pages:
            raise ValueError(f"No page registered for '{name}'")
        if self.history and self.history[-1] == name:
            return
        self.history.append(name)
        self.stack.setCurrentWidget(self.pages[name])
        self.pageChanged.emit(name)

    def go_back(self):
        if len(self.history) <= 1:
            return
        self.history.pop()
        previous = self.history[-1]
        self.stack.setCurrentWidget(self.pages[previous])
        self.pageChanged.emit(previous)

    @property
    def current(self):
        return self.history[-1] if self.history else None
