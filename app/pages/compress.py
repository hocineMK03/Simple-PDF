import os
import shutil
import tempfile
from io import BytesIO
from pathlib import Path

import fitz
from PIL import Image
from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.widgets.drop_zone import DropZone
from app.widgets.toggle_group import ToggleGroup

LEVELS = {
    "low": {
        "label": "Lossless",
        "description": "Rebuild the file structure only — no change to image quality.",
        "max_dim": None,
        "quality": None,
    },
    "medium": {
        "label": "Recommended",
        "description": "Downscale oversized images — a good balance of size and quality.",
        "max_dim": 1600,
        "quality": 75,
    },
    "high": {
        "label": "Maximum",
        "description": "Aggressively shrink images for the smallest possible file size.",
        "max_dim": 1000,
        "quality": 40,
    },
}


def format_size(num_bytes):
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if unit == "B":
            if size < 1024:
                return f"{int(size)} B"
        elif size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024


class CompressWorker(QObject):
    """Compresses one or more PDFs by deflating streams and, for lossy
    levels, downscaling and re-encoding embedded images in place."""

    progress = Signal(int, int)
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, jobs, level):
        super().__init__()
        self.jobs = jobs  # list of (input_path, output_path)
        self.level = level

    def run(self):
        try:
            total = len(self.jobs)
            results = []

            for i, (input_path, output_path) in enumerate(self.jobs):
                orig_size = os.path.getsize(input_path)

                doc = fitz.open(input_path)
                try:
                    if self.level != "low":
                        self._compress_images(doc)

                    out_dir = Path(output_path).parent
                    out_dir.mkdir(parents=True, exist_ok=True)

                    with tempfile.NamedTemporaryFile(
                        suffix=".pdf", delete=False, dir=str(out_dir)
                    ) as tmp:
                        tmp_path = tmp.name
                    doc.save(tmp_path, garbage=4, deflate=True, clean=True)
                finally:
                    doc.close()

                shutil.move(tmp_path, output_path)
                new_size = os.path.getsize(output_path)
                results.append((input_path, output_path, orig_size, new_size))

                self.progress.emit(i + 1, total)

            self.finished.emit(results)
        except Exception as exc:
            self.error.emit(str(exc))

    def _compress_images(self, doc):
        max_dim = LEVELS[self.level]["max_dim"]
        quality = LEVELS[self.level]["quality"]
        seen_xrefs = set()

        for page in doc:
            for img in page.get_images(full=True):
                xref = img[0]
                if xref in seen_xrefs:
                    continue
                seen_xrefs.add(xref)
                try:
                    self._recompress_image(doc, page, xref, max_dim, quality)
                except Exception:
                    continue

    def _recompress_image(self, doc, page, xref, max_dim, quality):
        raw = doc.extract_image(xref)["image"]
        img = Image.open(BytesIO(raw))

        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            rgba = img.convert("RGBA")
            background = Image.new("RGB", rgba.size, (255, 255, 255))
            background.paste(rgba, mask=rgba.split()[-1])
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

        if max(img.size) > max_dim:
            ratio = max_dim / max(img.size)
            new_size = (max(1, round(img.width * ratio)), max(1, round(img.height * ratio)))
            img = img.resize(new_size, Image.LANCZOS)

        buf = BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        new_bytes = buf.getvalue()

        if len(new_bytes) < len(raw):
            page.replace_image(xref, stream=new_bytes)


class CompressPage(QWidget):

    def __init__(self, router):
        super().__init__()

        self.router = router
        self.pdf_files = []  # list of (path, pages, size)
        self.output_target = None
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

        subtitle = QLabel("Shrink PDF file size by optimizing embedded images and structure.")
        subtitle.setObjectName("pageSubtitle")
        root.addWidget(subtitle)

        self.dropZone = DropZone(
            extensions=[".pdf"],
            file_filter="PDF files (*.pdf)",
            prompt="Drag & drop PDFs here, or click to browse",
            multiple=True,
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
        self.compressButton = QPushButton("Compress")
        self.compressButton.setEnabled(False)
        self.compressButton.clicked.connect(self._start_compression)
        actionRow.addWidget(self.compressButton)
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

    def _build_file_list_panel(self):
        panel = QFrame()
        panel.setObjectName("panel")

        outer = QVBoxLayout(panel)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(10)

        header = QHBoxLayout()
        self.fileListHeaderLabel = QLabel("")
        self.fileListHeaderLabel.setObjectName("cardTitle")

        addButton = QPushButton("Add more")
        addButton.setProperty("flat", True)
        addButton.clicked.connect(self._browse_for_files)

        removeButton = QPushButton("Remove selected")
        removeButton.setProperty("flat", True)
        removeButton.clicked.connect(self._remove_selected)

        clearButton = QPushButton("Clear")
        clearButton.setProperty("flat", True)
        clearButton.clicked.connect(self._reset_selection)

        header.addWidget(self.fileListHeaderLabel)
        header.addStretch()
        header.addWidget(addButton)
        header.addWidget(removeButton)
        header.addWidget(clearButton)
        outer.addLayout(header)

        self.fileList = QListWidget()
        outer.addWidget(self.fileList)

        return panel

    def _build_options_panel(self):
        panel = QFrame()
        panel.setObjectName("panel")

        self.optionsForm = QFormLayout(panel)
        self.optionsForm.setContentsMargins(20, 20, 20, 20)
        self.optionsForm.setSpacing(14)
        self.optionsForm.setLabelAlignment(Qt.AlignLeft)

        levelColumn = QVBoxLayout()
        levelColumn.setContentsMargins(0, 0, 0, 0)
        levelColumn.setSpacing(6)

        self.levelToggle = ToggleGroup(
            [("low", "Lossless"), ("medium", "Recommended"), ("high", "Maximum")],
            default="medium",
        )
        self.levelToggle.currentChanged.connect(self._on_level_changed)

        self.levelDescription = QLabel("")
        self.levelDescription.setObjectName("mutedLabel")
        self.levelDescription.setWordWrap(True)

        levelColumn.addWidget(self.levelToggle)
        levelColumn.addWidget(self.levelDescription)

        levelWidget = QWidget()
        levelWidget.setLayout(levelColumn)
        self.optionsForm.addRow(self._fieldLabel("Compression"), levelWidget)

        outputRow = QHBoxLayout()
        self.outputPathEdit = QLineEdit()
        self.outputPathEdit.setReadOnly(True)
        browseButton = QPushButton("Browse…")
        browseButton.setProperty("flat", True)
        browseButton.clicked.connect(self._browse_for_output)
        outputRow.addWidget(self.outputPathEdit)
        outputRow.addWidget(browseButton)

        self.outputFieldLabel = self._fieldLabel("Save PDF as")
        self.optionsForm.addRow(self.outputFieldLabel, outputRow)

        self._on_level_changed(self.levelToggle.value())

        return panel

    def _fieldLabel(self, text):
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        return label

    def _on_level_changed(self, value):
        self.levelDescription.setText(LEVELS[value]["description"])

    # ---- File selection ----

    def _browse_for_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Select PDFs", "", "PDF files (*.pdf)")
        if paths:
            self._on_files_selected(paths)

    def _on_files_selected(self, paths):
        valid_files = []
        errors = []

        for path in paths:
            try:
                doc = fitz.open(path)
                pages = len(doc)
                doc.close()
                valid_files.append((path, pages, os.path.getsize(path)))
            except Exception as exc:
                errors.append(f"{Path(path).name}: {exc}")

        if errors:
            QMessageBox.warning(self, "Some files were skipped", "\n".join(errors))

        if not valid_files:
            return

        self.pdf_files.extend(valid_files)
        self._refresh_file_list_ui()
        self._update_default_output_path()

        self.fileListPanel.setVisible(True)
        self.optionsPanel.setVisible(True)
        self.compressButton.setEnabled(True)
        self.statusLabel.setText("")
        self.dropZone.setPrompt("Drag & drop more PDFs here, or click to browse")

    def _refresh_file_list_ui(self):
        self.fileList.clear()
        for path, pages, size in self.pdf_files:
            text = f"{Path(path).name}  —  {pages} page{'s' if pages != 1 else ''}, {format_size(size)}"
            self.fileList.addItem(text)

        count = len(self.pdf_files)
        self.fileListHeaderLabel.setText(f"{count} file{'s' if count != 1 else ''} selected")
        self.outputFieldLabel.setText("Save PDF as" if count == 1 else "Save to folder")

    def _remove_selected(self):
        rows = sorted({index.row() for index in self.fileList.selectedIndexes()}, reverse=True)
        if not rows:
            return
        for row in rows:
            del self.pdf_files[row]

        if not self.pdf_files:
            self._reset_selection()
            return

        self._refresh_file_list_ui()
        self._update_default_output_path()

    def _reset_selection(self):
        self.pdf_files = []
        self.output_target = None
        self.fileList.clear()
        self.fileListPanel.setVisible(False)
        self.optionsPanel.setVisible(False)
        self.compressButton.setEnabled(False)
        self.statusLabel.setText("")
        self.dropZone.setPrompt("Drag & drop PDFs here, or click to browse")

    # ---- Output path ----

    def _update_default_output_path(self):
        if not self.pdf_files:
            return
        first_path = self.pdf_files[0][0]
        parent = Path(first_path).parent
        if len(self.pdf_files) == 1:
            self.output_target = str(parent / f"{Path(first_path).stem}_compressed.pdf")
        else:
            self.output_target = str(parent)
        self.outputPathEdit.setText(self.output_target)

    def _browse_for_output(self):
        if len(self.pdf_files) == 1:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save PDF as", self.output_target or "", "PDF files (*.pdf)"
            )
            if not path:
                return
            if not path.lower().endswith(".pdf"):
                path += ".pdf"
        else:
            path = QFileDialog.getExistingDirectory(self, "Select output folder", self.output_target or "")
            if not path:
                return

        self.output_target = path
        self.outputPathEdit.setText(path)

    # ---- Compression ----

    def _build_jobs(self):
        if len(self.pdf_files) == 1:
            return [(self.pdf_files[0][0], self.output_target)]
        output_dir = Path(self.output_target)
        return [
            (path, str(output_dir / f"{Path(path).stem}_compressed.pdf"))
            for path, _, _ in self.pdf_files
        ]

    def _start_compression(self):
        if not self.pdf_files or not self.output_target:
            return

        level = self.levelToggle.value()
        jobs = self._build_jobs()

        self._set_running(True)

        self.thread = QThread(self)
        self.worker = CompressWorker(jobs, level)
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
        self.compressButton.setEnabled(not running)
        self.dropZone.setEnabled(not running)
        self.fileListPanel.setEnabled(not running)
        self.optionsPanel.setEnabled(not running)
        self.progressBar.setVisible(running)
        self.progressBar.setValue(0)
        self.statusLabel.setText("Compressing…" if running else "")

    def _on_progress(self, current, total):
        self.progressBar.setMaximum(total)
        self.progressBar.setValue(current)
        self.statusLabel.setText(f"Compressing file {current} of {total}…")

    def _on_finished(self, results):
        self._set_running(False)
        self.compressButton.setEnabled(True)

        total_orig = sum(r[2] for r in results)
        total_new = sum(r[3] for r in results)
        saved_pct = max(0, (1 - total_new / total_orig) * 100) if total_orig else 0

        if len(results) == 1:
            _, output_path, orig, new = results[0]
            self.statusLabel.setText(
                f"Done — {format_size(orig)} → {format_size(new)} ({saved_pct:.0f}% smaller). Saved {output_path}"
            )
            open_target = str(Path(output_path).parent)
        else:
            self.statusLabel.setText(
                f"Done — compressed {len(results)} files: "
                f"{format_size(total_orig)} → {format_size(total_new)} ({saved_pct:.0f}% smaller)"
            )
            open_target = str(Path(results[0][1]).parent)

        self._offer_open_folder(open_target)

    def _on_error(self, message):
        self._set_running(False)
        self.compressButton.setEnabled(True)
        QMessageBox.critical(self, "Compression failed", message)
        self.statusLabel.setText("Compression failed.")

    def _offer_open_folder(self, folder_path):
        reply = QMessageBox.question(
            self,
            "Compression complete",
            "PDF compressed successfully. Open the containing folder?",
        )
        if reply == QMessageBox.Yes:
            os.startfile(folder_path)

    def _cleanup_thread(self):
        self.thread = None
        self.worker = None
