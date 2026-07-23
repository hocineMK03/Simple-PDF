import json
import urllib.error
import urllib.request
from pathlib import Path

import fitz
from PySide6.QtCore import QObject, QSettings, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.widgets.drop_zone import DropZone
from app.widgets.toggle_group import ToggleGroup

MAX_CHARS = 15000

LENGTH_PROMPTS = {
    "short": "Summarize the document in 3-5 concise bullet points.",
    "medium": "Summarize the document in 2-3 short paragraphs covering the key points.",
    "detailed": "Write a detailed, well-structured summary covering all major sections, arguments, and conclusions.",
}


def extract_text(path):
    doc = fitz.open(path)
    try:
        text = "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()
    truncated = len(text) > MAX_CHARS
    return text[:MAX_CHARS], truncated


class SummarizeWorker(QObject):
    """Sends extracted PDF text to an OpenAI-compatible chat completions
    endpoint and returns the generated summary."""

    finished = Signal(str, bool)
    error = Signal(str)

    def __init__(self, base_url, api_key, model, text, truncated, length):
        super().__init__()
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.text = text
        self.truncated = truncated
        self.length = length

    def run(self):
        try:
            instruction = LENGTH_PROMPTS[self.length]
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an assistant that writes clear, accurate summaries of documents.",
                    },
                    {"role": "user", "content": f"{instruction}\n\nDocument:\n{self.text}"},
                ],
                "temperature": 0.3,
            }
            data = json.dumps(payload).encode("utf-8")
            request = urllib.request.Request(
                f"{self.base_url}/chat/completions",
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=120) as response:
                body = json.loads(response.read().decode("utf-8"))

            summary = body["choices"][0]["message"]["content"].strip()
            self.finished.emit(summary, self.truncated)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            self.error.emit(f"HTTP {exc.code}: {detail[:300]}")
        except Exception as exc:
            self.error.emit(str(exc))


class AiSummarizerPage(QWidget):

    def __init__(self, router):
        super().__init__()

        self.router = router
        self.settings = QSettings("OpenPDFStudio", "AISummarizer")
        self.pdf_path = None
        self.thread = None
        self.worker = None

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(50, 40, 50, 40)
        root.setSpacing(20)
        root.setAlignment(Qt.AlignTop)

        subtitle = QLabel("Generate a quick AI-written summary of a PDF using your own LLM API.")
        subtitle.setObjectName("pageSubtitle")
        root.addWidget(subtitle)

        self.settingsPanel = self._build_settings_panel()
        root.addWidget(self.settingsPanel)

        self.gateLabel = QLabel("Add your LLM API details above, then click Save to start summarizing.")
        self.gateLabel.setObjectName("mutedLabel")
        self.gateLabel.setWordWrap(True)
        root.addWidget(self.gateLabel)

        self.workArea = self._build_work_area()
        root.addWidget(self.workArea)

        root.addStretch()

        scroll.setWidget(content)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self._load_settings()
        self._update_gate()

    # ---- UI builders ----

    def _build_settings_panel(self):
        panel = QFrame()
        panel.setObjectName("panel")

        form = QFormLayout(panel)
        form.setContentsMargins(20, 20, 20, 20)
        form.setSpacing(14)
        form.setLabelAlignment(Qt.AlignLeft)

        self.baseUrlEdit = QLineEdit()
        self.baseUrlEdit.setPlaceholderText("https://api.openai.com/v1")
        form.addRow(self._fieldLabel("API base URL"), self.baseUrlEdit)

        self.apiKeyEdit = QLineEdit()
        self.apiKeyEdit.setEchoMode(QLineEdit.Password)
        self.apiKeyEdit.setPlaceholderText("sk-…")
        form.addRow(self._fieldLabel("API key"), self.apiKeyEdit)

        self.modelEdit = QLineEdit()
        self.modelEdit.setPlaceholderText("gpt-4o-mini")
        form.addRow(self._fieldLabel("Model"), self.modelEdit)

        saveRow = QHBoxLayout()
        self.saveSettingsButton = QPushButton("Save")
        self.saveSettingsButton.clicked.connect(self._save_settings)
        self.settingsStatusLabel = QLabel("")
        self.settingsStatusLabel.setObjectName("mutedLabel")
        saveRow.addWidget(self.saveSettingsButton)
        saveRow.addWidget(self.settingsStatusLabel)
        saveRow.addStretch()
        form.addRow(self._fieldLabel(""), saveRow)

        return panel

    def _build_work_area(self):
        area = QWidget()
        layout = QVBoxLayout(area)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)

        self.dropZone = DropZone(
            extensions=[".pdf"],
            file_filter="PDF files (*.pdf)",
            prompt="Drag & drop a PDF here, or click to browse",
        )
        self.dropZone.filesSelected.connect(self._on_file_selected)
        layout.addWidget(self.dropZone)

        self.optionsPanel = self._build_options_panel()
        layout.addWidget(self.optionsPanel)

        actionRow = QHBoxLayout()
        self.summarizeButton = QPushButton("Summarize")
        self.summarizeButton.setEnabled(False)
        self.summarizeButton.clicked.connect(self._start_summarizing)
        actionRow.addWidget(self.summarizeButton)
        actionRow.addStretch()
        layout.addLayout(actionRow)

        self.progressBar = QProgressBar()
        self.progressBar.setRange(0, 0)
        self.progressBar.setVisible(False)
        layout.addWidget(self.progressBar)

        self.statusLabel = QLabel("")
        self.statusLabel.setObjectName("mutedLabel")
        self.statusLabel.setWordWrap(True)
        layout.addWidget(self.statusLabel)

        self.resultPanel = self._build_result_panel()
        self.resultPanel.setVisible(False)
        layout.addWidget(self.resultPanel)

        return area

    def _build_options_panel(self):
        panel = QFrame()
        panel.setObjectName("panel")

        form = QFormLayout(panel)
        form.setContentsMargins(20, 20, 20, 20)
        form.setSpacing(14)
        form.setLabelAlignment(Qt.AlignLeft)

        self.lengthToggle = ToggleGroup(
            [("short", "Short"), ("medium", "Medium"), ("detailed", "Detailed")],
            default="medium",
        )
        form.addRow(self._fieldLabel("Summary length"), self.lengthToggle)

        return panel

    def _build_result_panel(self):
        panel = QFrame()
        panel.setObjectName("panel")

        outer = QVBoxLayout(panel)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Summary")
        title.setObjectName("cardTitle")

        copyButton = QPushButton("Copy")
        copyButton.setProperty("flat", True)
        copyButton.clicked.connect(self._copy_summary)

        saveButton = QPushButton("Save as .txt")
        saveButton.setProperty("flat", True)
        saveButton.clicked.connect(self._save_summary)

        header.addWidget(title)
        header.addStretch()
        header.addWidget(copyButton)
        header.addWidget(saveButton)
        outer.addLayout(header)

        self.summaryText = QTextEdit()
        self.summaryText.setReadOnly(True)
        self.summaryText.setMinimumHeight(220)
        outer.addWidget(self.summaryText)

        return panel

    def _fieldLabel(self, text):
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        return label

    # ---- Settings ----

    def _load_settings(self):
        self.baseUrlEdit.setText(self.settings.value("base_url", ""))
        self.apiKeyEdit.setText(self.settings.value("api_key", ""))
        self.modelEdit.setText(self.settings.value("model", "gpt-4o-mini"))

    def _save_settings(self):
        base_url = self.baseUrlEdit.text().strip()
        api_key = self.apiKeyEdit.text().strip()
        model = self.modelEdit.text().strip() or "gpt-4o-mini"

        if not base_url or not api_key:
            QMessageBox.warning(self, "Missing details", "Enter both an API base URL and an API key.")
            return

        self.settings.setValue("base_url", base_url)
        self.settings.setValue("api_key", api_key)
        self.settings.setValue("model", model)
        self.modelEdit.setText(model)

        self.settingsStatusLabel.setText("Saved")
        self._update_gate()

    def _is_configured(self):
        return bool(self.settings.value("base_url", "")) and bool(self.settings.value("api_key", ""))

    def _update_gate(self):
        configured = self._is_configured()
        self.gateLabel.setVisible(not configured)
        self.workArea.setVisible(configured)

    # ---- File selection ----

    def _on_file_selected(self, paths):
        if not paths:
            return
        path = paths[0]
        try:
            doc = fitz.open(path)
            doc.close()
        except Exception as exc:
            QMessageBox.warning(self, "Could not open file", f"{Path(path).name}: {exc}")
            return

        self.pdf_path = path
        self.dropZone.setPrompt(f"Selected: {Path(path).name} — click to choose a different PDF")
        self.summarizeButton.setEnabled(True)
        self.statusLabel.setText("")
        self.resultPanel.setVisible(False)

    # ---- Summarizing ----

    def _start_summarizing(self):
        if not self.pdf_path:
            return

        base_url = self.settings.value("base_url", "")
        api_key = self.settings.value("api_key", "")
        model = self.settings.value("model", "gpt-4o-mini")

        try:
            text, truncated = extract_text(self.pdf_path)
        except Exception as exc:
            QMessageBox.critical(self, "Could not read PDF", str(exc))
            return

        if not text.strip():
            QMessageBox.warning(self, "Empty document", "No extractable text was found in this PDF.")
            return

        length = self.lengthToggle.value()

        self._set_running(True)

        self.thread = QThread(self)
        self.worker = SummarizeWorker(base_url, api_key, model, text, truncated, length)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.error.connect(self.thread.quit)
        self.thread.finished.connect(self._cleanup_thread)

        self.thread.start()

    def _set_running(self, running):
        self.summarizeButton.setEnabled(not running)
        self.dropZone.setEnabled(not running)
        self.optionsPanel.setEnabled(not running)
        self.settingsPanel.setEnabled(not running)
        self.progressBar.setVisible(running)
        self.statusLabel.setText("Summarizing…" if running else "")

    def _on_finished(self, summary, truncated):
        self._set_running(False)
        self.summarizeButton.setEnabled(True)

        self.summaryText.setPlainText(summary)
        self.resultPanel.setVisible(True)

        note = " (document was truncated to fit the model's context window)" if truncated else ""
        self.statusLabel.setText(f"Done{note}.")

    def _on_error(self, message):
        self._set_running(False)
        self.summarizeButton.setEnabled(True)
        QMessageBox.critical(self, "Summarization failed", message)
        self.statusLabel.setText("Summarization failed.")

    def _cleanup_thread(self):
        self.thread = None
        self.worker = None

    # ---- Result actions ----

    def _copy_summary(self):
        QApplication.clipboard().setText(self.summaryText.toPlainText())

    def _save_summary(self):
        if not self.pdf_path:
            return
        default = str(Path(self.pdf_path).with_name(f"{Path(self.pdf_path).stem}_summary.txt"))
        path, _ = QFileDialog.getSaveFileName(self, "Save summary as", default, "Text files (*.txt)")
        if not path:
            return
        Path(path).write_text(self.summaryText.toPlainText(), encoding="utf-8")
