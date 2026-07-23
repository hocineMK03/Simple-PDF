import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.theme import apply_theme
from app.navigation import Router
from app.pages.ai_summarizer import AiSummarizerPage
from app.pages.compress import CompressPage
from app.pages.home import HomePage
from app.pages.image_to_pdf import ImageToPdfPage
from app.pages.pdf_to_images import PdfToImagesPage
from app.pages.watermark import WatermarkPage


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Simple PDF")
        self.resize(1300, 800)

        central = QWidget()
        rootLayout = QVBoxLayout(central)
        rootLayout.setContentsMargins(0, 0, 0, 0)
        rootLayout.setSpacing(0)

        self.topBar = self._build_top_bar()
        rootLayout.addWidget(self.topBar)

        self.stack = QStackedWidget()
        rootLayout.addWidget(self.stack)

        self.setCentralWidget(central)

        self.router = Router(self.stack)
        self.router.pageChanged.connect(self._on_page_changed)

        self.router.register("home", HomePage(self.router), "Simple PDF")
        self.router.register(
            "pdf_to_images", PdfToImagesPage(self.router), "PDF → Images"
        )
        self.router.register(
            "image_to_pdf", ImageToPdfPage(self.router), "Images → PDF"
        )
        self.router.register(
            "compress", CompressPage(self.router), "Compress PDF"
        )
        self.router.register(
            "watermark", WatermarkPage(self.router), "Watermark PDF"
        )
        self.router.register(
            "ai_summarizer", AiSummarizerPage(self.router), "AI Summarizer"
        )

        self.router.go_to("home")

    def _build_top_bar(self):
        bar = QWidget()
        bar.setObjectName("topBar")
        bar.setFixedHeight(56)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(14)

        self.backButton = QPushButton("← Back")
        self.backButton.setObjectName("backButton")
        self.backButton.setCursor(Qt.PointingHandCursor)
        self.backButton.clicked.connect(self._go_back)

        self.topBarTitle = QLabel("")
        self.topBarTitle.setObjectName("topBarTitle")

        layout.addWidget(self.backButton)
        layout.addWidget(self.topBarTitle)
        layout.addStretch()

        return bar

    def _go_back(self):
        self.router.go_back()

    def _on_page_changed(self, name):
        is_home = name != "home"
        self.topBar.setVisible(is_home)
        self.topBarTitle.setText(self.router.titles.get(name, ""))


app = QApplication(sys.argv)

apply_theme(app)

window = MainWindow()
window.show()

sys.exit(app.exec())
