from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.widgets.tool_card import ToolCard

CARD_MIN_WIDTH = 230
CARD_SPACING = 20
MAX_COLUMNS = 6

# (title, description, icon, route name or None if not implemented yet)
TOOLS = [
    ("Merge PDF", "Combine multiple PDF files into one document.", "app/assets/home/merge.svg", None),
    ("Split PDF", "Split PDFs into multiple documents.", "app/assets/home/split.svg", None),
    ("Compress", "Reduce PDF size while preserving quality.", "app/assets/home/compress.svg", "compress"),
    ("Rotate", "Rotate one or more PDF pages.", "app/assets/home/rotate.svg", None),
    ("Images → PDF", "Convert JPG and PNG images into PDF.", "app/assets/home/image_to_pdf.svg", "image_to_pdf"),
    ("PDF → Images", "Export PDF pages as images.", "app/assets/home/pdf_to_image.svg", "pdf_to_images"),
    ("Protect", "Encrypt your PDF with a password.", "app/assets/home/lock.svg", None),
    ("Watermark", "Add text or image watermarks.", "app/assets/home/watermark.svg", "watermark"),
    ("PDF → Word", "Convert PDFs into editable Word documents.", "app/assets/home/pdf_to_word.svg", None),
    ("Translate PDF", "Translate a PDF's text into another language.", "app/assets/home/translate.svg", None),
    ("AI Summarizer", "Generate a quick AI summary of a PDF.", "app/assets/home/ai_summarizer.svg", "ai_summarizer"),
]


class HomePage(QWidget):

    def __init__(self, router):
        super().__init__()

        self.router = router
        self._cards = []
        self._columns = 0

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(50, 40, 50, 40)
        root.setSpacing(25)

        title = QLabel("Simple PDF")
        title.setObjectName("pageTitle")

        subtitle = QLabel("Free • Offline • Open Source PDF Toolkit")
        subtitle.setObjectName("pageSubtitle")

        sectionLabel = QLabel("PDF Tools")
        sectionLabel.setObjectName("sectionLabel")

        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(CARD_SPACING)
        self.grid.setVerticalSpacing(CARD_SPACING)

        for titleText, desc, icon, route in TOOLS:
            card = ToolCard(titleText, desc, icon, enabled=route is not None)
            if route:
                card.clicked.connect(lambda route=route: self.router.go_to(route))
            self._cards.append(card)

        root.addWidget(title)
        root.addWidget(subtitle)
        root.addSpacing(20)
        root.addWidget(sectionLabel)
        root.addLayout(self.grid)
        root.addStretch()

        scroll.setWidget(content)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self._relayout(force=True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self, force=False):
        available = max(self.width() - 100, CARD_MIN_WIDTH)
        columns = max(1, available // (CARD_MIN_WIDTH + CARD_SPACING))
        columns = min(columns, len(self._cards), MAX_COLUMNS)

        if columns == self._columns and not force:
            return
        self._columns = columns

        for col in range(MAX_COLUMNS):
            self.grid.setColumnStretch(col, 0)

        for index, card in enumerate(self._cards):
            self.grid.removeWidget(card)
            self.grid.addWidget(card, index // columns, index % columns)

        for col in range(columns):
            self.grid.setColumnStretch(col, 1)
