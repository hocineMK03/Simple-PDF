import os
import shutil
import tempfile
from pathlib import Path

import fitz
from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
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
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.widgets.drop_zone import DropZone
from app.widgets.toggle_group import ToggleGroup


def parse_page_range(text, total_pages):
    """Parse a string like '1-3, 5, 8' into a sorted list of 0-based page indices."""
    text = text.strip()
    if not text:
        raise ValueError("Enter a page range, e.g. 1-3, 5, 8")

    indices = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue

        if "-" in part:
            start_s, _, end_s = part.partition("-")
            try:
                start, end = int(start_s), int(end_s)
            except ValueError:
                raise ValueError(f"Invalid range '{part}'")
            if start < 1 or end > total_pages or start > end:
                raise ValueError(f"Range '{part}' is out of bounds (1-{total_pages})")
            indices.update(range(start - 1, end))
        else:
            try:
                page = int(part)
            except ValueError:
                raise ValueError(f"Invalid page number '{part}'")
            if page < 1 or page > total_pages:
                raise ValueError(f"Page {page} is out of bounds (1-{total_pages})")
            indices.add(page - 1)

    if not indices:
        raise ValueError("No valid pages found")

    return sorted(indices)


class ConversionWorker(QObject):
    """Renders pages from one or more PDFs into a single zip. The zip always
    contains one top-level folder, which contains one subfolder per PDF
    (even when there's only one), each holding that PDF's page images."""

    progress = Signal(int, int)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, pdf_paths, zip_path, fmt, dpi, page_indices):
        super().__init__()
        self.pdf_paths = pdf_paths
        self.zip_path = zip_path
        self.fmt = fmt
        self.dpi = dpi
        self.page_indices = page_indices  # only applied when there's exactly one pdf

    def run(self):
        try:
            zoom = self.dpi / 72
            matrix = fitz.Matrix(zoom, zoom)

            with tempfile.TemporaryDirectory() as tmp_dir:
                export_name = Path(self.zip_path).stem
                export_root = Path(tmp_dir) / export_name
                export_root.mkdir(parents=True, exist_ok=True)

                docs = [fitz.open(p) for p in self.pdf_paths]
                try:
                    if len(docs) == 1 and self.page_indices is not None:
                        page_plan = [self.page_indices]
                    else:
                        page_plan = [range(len(doc)) for doc in docs]

                    total = sum(len(indices) for indices in page_plan)
                    done = 0

                    for doc, pdf_path, indices in zip(docs, self.pdf_paths, page_plan):
                        out_dir = export_root / Path(pdf_path).stem
                        out_dir.mkdir(parents=True, exist_ok=True)

                        for page_index in indices:
                            page = doc.load_page(page_index)
                            pix = page.get_pixmap(matrix=matrix, alpha=(self.fmt == "png"))
                            out_path = out_dir / f"page_{page_index + 1}.{self.fmt}"
                            pix.save(str(out_path), jpg_quality=92)
                            done += 1
                            self.progress.emit(done, total)
                finally:
                    for doc in docs:
                        doc.close()

                zip_base = str(Path(self.zip_path).with_suffix(""))
                produced = shutil.make_archive(zip_base, "zip", root_dir=tmp_dir)
                if produced != self.zip_path:
                    Path(self.zip_path).parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(produced, self.zip_path)

            self.finished.emit(self.zip_path)
        except Exception as exc:
            self.error.emit(str(exc))


class PdfToImagesPage(QWidget):

    def __init__(self, router):
        super().__init__()

        self.router = router
        self.selected_files = []  # list of (path, page_count)
        self.zip_path = None
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

        subtitle = QLabel("Export PDF pages as PNG or JPEG images, packaged into a zip.")
        subtitle.setObjectName("pageSubtitle")
        root.addWidget(subtitle)

        root.addLayout(self._build_mode_row())

        self.dropZone = DropZone(
            extensions=[".pdf"],
            file_filter="PDF files (*.pdf)",
            prompt="Drag & drop a PDF here, or click to browse",
        )
        self.dropZone.filesSelected.connect(self._on_files_selected)
        root.addWidget(self.dropZone)

        self.fileListPanel = self._build_file_list_panel()
        self.fileListPanel.setVisible(False)
        root.addWidget(self.fileListPanel)

        self.optionsPanel = self._build_options_panel()
        self.optionsPanel.setVisible(False)
        root.addWidget(self.optionsPanel)

        actionRow = QHBoxLayout()
        self.convertButton = QPushButton("Convert")
        self.convertButton.setEnabled(False)
        self.convertButton.clicked.connect(self._start_conversion)
        actionRow.addWidget(self.convertButton)
        actionRow.addStretch()
        root.addLayout(actionRow)

        self.progressBar = QProgressBar()
        self.progressBar.setVisible(False)
        root.addWidget(self.progressBar)

        self.statusLabel = QLabel("")
        self.statusLabel.setObjectName("mutedLabel")
        self.statusLabel.setWordWrap(True)
        root.addWidget(self.statusLabel)

        root.addStretch()

        scroll.setWidget(content)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ---- UI builders ----

    def _build_mode_row(self):
        row = QHBoxLayout()
        row.setSpacing(14)

        self.modeToggle = ToggleGroup(
            [("single", "One PDF"), ("multi", "Multiple PDFs")],
            default="single",
        )
        self.modeToggle.currentChanged.connect(self._on_mode_changed)

        row.addWidget(self._fieldLabel("Convert"))
        row.addWidget(self.modeToggle)
        row.addStretch()

        return row

    def _build_file_list_panel(self):
        panel = QFrame()
        panel.setObjectName("panel")

        outer = QVBoxLayout(panel)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(10)

        header = QHBoxLayout()
        self.fileListHeaderLabel = QLabel("")
        self.fileListHeaderLabel.setObjectName("cardTitle")
        changeButton = QPushButton("Change files")
        changeButton.setProperty("flat", True)
        changeButton.clicked.connect(self._browse_for_files)
        header.addWidget(self.fileListHeaderLabel)
        header.addStretch()
        header.addWidget(changeButton)
        outer.addLayout(header)

        self.fileListRows = QVBoxLayout()
        self.fileListRows.setSpacing(4)
        outer.addLayout(self.fileListRows)

        return panel

    def _build_options_panel(self):
        panel = QFrame()
        panel.setObjectName("panel")

        self.optionsForm = QFormLayout(panel)
        self.optionsForm.setContentsMargins(20, 20, 20, 20)
        self.optionsForm.setSpacing(14)
        self.optionsForm.setLabelAlignment(Qt.AlignLeft)

        self.formatCombo = QComboBox()
        self.formatCombo.addItems(["PNG", "JPEG"])
        self.optionsForm.addRow(self._fieldLabel("Format"), self.formatCombo)

        self.dpiSpin = QSpinBox()
        self.dpiSpin.setRange(72, 600)
        self.dpiSpin.setSingleStep(50)
        self.dpiSpin.setValue(200)
        self.dpiSpin.setSuffix(" DPI")
        self.optionsForm.addRow(self._fieldLabel("Resolution"), self.dpiSpin)

        self.pagesWidget = QWidget()
        pagesLayout = QVBoxLayout(self.pagesWidget)
        pagesLayout.setContentsMargins(0, 0, 0, 0)
        pagesLayout.setSpacing(6)

        self.pagesToggle = ToggleGroup(
            [("all", "All pages"), ("custom", "Custom range")],
            default="all",
        )
        self.pagesToggle.currentChanged.connect(self._on_pages_mode_changed)

        self.pageRangeEdit = QLineEdit()
        self.pageRangeEdit.setPlaceholderText("e.g. 1-3, 5, 8")
        self.pageRangeEdit.setEnabled(False)

        pagesLayout.addWidget(self.pagesToggle)
        pagesLayout.addWidget(self.pageRangeEdit)

        self.optionsForm.addRow(self._fieldLabel("Pages"), self.pagesWidget)

        outputRow = QHBoxLayout()
        self.outputPathEdit = QLineEdit()
        self.outputPathEdit.setReadOnly(True)
        browseButton = QPushButton("Browse…")
        browseButton.setProperty("flat", True)
        browseButton.clicked.connect(self._browse_for_output_zip)
        outputRow.addWidget(self.outputPathEdit)
        outputRow.addWidget(browseButton)
        self.optionsForm.addRow(self._fieldLabel("Save zip as"), outputRow)

        return panel

    def _fieldLabel(self, text):
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        return label

    # ---- Mode handling ----

    def _on_mode_changed(self, value):
        self._reset_selection()
        is_multi = value == "multi"
        self.dropZone.setMultiple(is_multi)
        self.dropZone.setPrompt(
            "Drag & drop PDFs here, or click to browse"
            if is_multi
            else "Drag & drop a PDF here, or click to browse"
        )

    def _on_pages_mode_changed(self, value):
        self.pageRangeEdit.setEnabled(value == "custom")

    def _reset_selection(self):
        self.selected_files = []
        self.zip_path = None
        self.fileListPanel.setVisible(False)
        self.optionsPanel.setVisible(False)
        self.convertButton.setEnabled(False)
        self.statusLabel.setText("")

    # ---- File selection ----

    def _browse_for_files(self):
        if self.modeToggle.value() == "multi":
            paths, _ = QFileDialog.getOpenFileNames(self, "Select PDFs", "", "PDF files (*.pdf)")
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Select PDF", "", "PDF files (*.pdf)")
            paths = [path] if path else []
        if paths:
            self._on_files_selected(paths)

    def _on_files_selected(self, paths):
        if self.modeToggle.value() == "single":
            paths = paths[:1]

        valid_files = []
        errors = []
        for path in paths:
            try:
                doc = fitz.open(path)
                valid_files.append((path, len(doc)))
                doc.close()
            except Exception as exc:
                errors.append(f"{Path(path).name}: {exc}")

        if errors:
            QMessageBox.warning(self, "Some files were skipped", "\n".join(errors))

        if not valid_files:
            return

        self.selected_files = valid_files
        self._refresh_file_list_ui()
        self._update_default_output_path()

        self.fileListPanel.setVisible(True)
        self.optionsPanel.setVisible(True)
        self.convertButton.setEnabled(True)
        self.statusLabel.setText("")

        single_file = len(self.selected_files) == 1
        self.optionsForm.setRowVisible(self.pagesWidget, single_file)
        if not single_file:
            self.pagesToggle.setValue("all")

    def _refresh_file_list_ui(self):
        while self.fileListRows.count():
            item = self.fileListRows.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        count = len(self.selected_files)
        self.fileListHeaderLabel.setText(f"{count} file{'s' if count != 1 else ''} selected")

        for path, pages in self.selected_files:
            row = QLabel(f"{Path(path).name}  —  {pages} page{'s' if pages != 1 else ''}")
            row.setObjectName("mutedLabel")
            self.fileListRows.addWidget(row)

    # ---- Output path ----

    def _update_default_output_path(self):
        if not self.selected_files:
            return
        first_path = self.selected_files[0][0]
        parent = str(Path(first_path).parent)
        if len(self.selected_files) == 1:
            default_name = f"{Path(first_path).stem}_images.zip"
        else:
            default_name = "pdf_images.zip"
        self.zip_path = str(Path(parent) / default_name)
        self.outputPathEdit.setText(self.zip_path)

    def _browse_for_output_zip(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save zip as", self.zip_path or "", "Zip files (*.zip)")
        if not path:
            return
        if not path.lower().endswith(".zip"):
            path += ".zip"
        self.zip_path = path
        self.outputPathEdit.setText(path)

    # ---- Conversion ----

    def _start_conversion(self):
        if not self.selected_files or not self.zip_path:
            return

        page_indices = None
        if len(self.selected_files) == 1 and self.pagesToggle.value() == "custom":
            try:
                page_indices = parse_page_range(self.pageRangeEdit.text(), self.selected_files[0][1])
            except ValueError as exc:
                QMessageBox.warning(self, "Invalid page range", str(exc))
                return

        fmt = "png" if self.formatCombo.currentText() == "PNG" else "jpg"
        dpi = self.dpiSpin.value()
        pdf_paths = [path for path, _ in self.selected_files]

        self._set_running(True)

        self.thread = QThread(self)
        self.worker = ConversionWorker(pdf_paths, self.zip_path, fmt, dpi, page_indices)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.error.connect(self.thread.quit)
        self.thread.finished.connect(self._cleanup_thread)

        self.thread.start()

    def _set_running(self, running):
        self.convertButton.setEnabled(not running)
        self.dropZone.setEnabled(not running)
        self.optionsPanel.setEnabled(not running)
        self.modeToggle.setEnabled(not running)
        self.progressBar.setVisible(running)
        self.progressBar.setValue(0)
        self.statusLabel.setText("Converting…" if running else "")

    def _on_progress(self, current, total):
        self.progressBar.setMaximum(total)
        self.progressBar.setValue(current)
        self.statusLabel.setText(f"Converting page {current} of {total}…")

    def _on_finished(self, zip_path):
        self._set_running(False)
        self.convertButton.setEnabled(True)
        self.statusLabel.setText(f"Done — saved {zip_path}")
        self._offer_open_folder(zip_path)

    def _on_error(self, message):
        self._set_running(False)
        self.convertButton.setEnabled(True)
        QMessageBox.critical(self, "Conversion failed", message)
        self.statusLabel.setText("Conversion failed.")

    def _offer_open_folder(self, zip_path):
        reply = QMessageBox.question(
            self,
            "Conversion complete",
            "Images exported successfully. Open the containing folder?",
        )
        if reply == QMessageBox.Yes:
            os.startfile(str(Path(zip_path).parent))

    def _cleanup_thread(self):
        self.thread = None
        self.worker = None
