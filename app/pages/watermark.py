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
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.widgets.drop_zone import DropZone
from app.widgets.toggle_group import ToggleGroup

IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".bmp", ".webp"]

TEXT_COLOR = (0.55, 0.55, 0.55)
TILE_MARGIN = 20


def format_size(num_bytes):
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if unit == "B":
            if size < 1024:
                return f"{int(size)} B"
        elif size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024


def grid_positions(rect, placement, spacing_x, spacing_y):
    """Points at which to stamp one watermark instance."""
    if placement == "center":
        return [fitz.Point((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)]

    spacing_x = max(spacing_x, 1)
    spacing_y = max(spacing_y, 1)

    points = []
    y = rect.y0 + TILE_MARGIN + spacing_y / 2
    row = 0
    while y < rect.y1 - TILE_MARGIN:
        offset = spacing_x / 2 if row % 2 else 0
        x = rect.x0 + TILE_MARGIN + offset
        while x < rect.x1 - TILE_MARGIN:
            points.append(fitz.Point(x, y))
            x += spacing_x
        y += spacing_y
        row += 1

    return points or [fitz.Point((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)]


class WatermarkWorker(QObject):
    """Stamps a text or image watermark onto every page of one or more PDFs."""

    progress = Signal(int, int)
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, jobs, config):
        super().__init__()
        self.jobs = jobs  # list of (input_path, output_path)
        self.config = config

    def run(self):
        try:
            total = len(self.jobs)
            results = []

            for i, (input_path, output_path) in enumerate(self.jobs):
                orig_size = os.path.getsize(input_path)

                doc = fitz.open(input_path)
                try:
                    for page in doc:
                        if self.config["type"] == "text":
                            self._stamp_text(page)
                        else:
                            self._stamp_image(page)

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

    def _stamp_text(self, page):
        text = self.config["text"]
        fontsize = self.config["font_size"]
        opacity = self.config["opacity"]
        angle = self.config["rotation"]

        text_len = fitz.get_text_length(text, fontname="helv", fontsize=fontsize)
        positions = grid_positions(
            page.rect,
            self.config["placement"],
            spacing_x=text_len * 1.8,
            spacing_y=fontsize * 4,
        )

        for point in positions:
            morph = (point, fitz.Matrix(1, 1).prerotate(angle))
            page.insert_text(
                (point.x - text_len / 2, point.y + fontsize / 3),
                text,
                fontsize=fontsize,
                fontname="helv",
                color=TEXT_COLOR,
                fill_opacity=opacity,
                morph=morph,
                overlay=True,
            )

    def _stamp_image(self, page):
        opacity = self.config["opacity"]
        angle = self.config["rotation"]

        with Image.open(self.config["image_path"]) as source:
            img = source.convert("RGBA")

        if opacity < 1:
            alpha = img.split()[-1].point(lambda a: int(a * opacity))
            img.putalpha(alpha)

        if angle:
            img = img.rotate(angle, expand=True, resample=Image.BICUBIC)

        target_w = page.rect.width * (self.config["image_scale"] / 100)
        target_h = img.height * (target_w / img.width)

        buf = BytesIO()
        img.save(buf, format="PNG")
        data = buf.getvalue()

        positions = grid_positions(
            page.rect,
            self.config["placement"],
            spacing_x=target_w * 1.6,
            spacing_y=target_h * 1.6,
        )

        for point in positions:
            img_rect = fitz.Rect(
                point.x - target_w / 2,
                point.y - target_h / 2,
                point.x + target_w / 2,
                point.y + target_h / 2,
            )
            page.insert_image(img_rect, stream=data, keep_proportion=True, overlay=True)


class WatermarkPage(QWidget):

    def __init__(self, router):
        super().__init__()

        self.router = router
        self.pdf_files = []  # list of (path, pages, size)
        self.image_path = None
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

        subtitle = QLabel("Stamp a text or image watermark onto every page of one or more PDFs.")
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
        self.watermarkButton = QPushButton("Add Watermark")
        self.watermarkButton.setEnabled(False)
        self.watermarkButton.clicked.connect(self._start_watermarking)
        actionRow.addWidget(self.watermarkButton)
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

        self.typeToggle = ToggleGroup(
            [("text", "Text"), ("image", "Image")],
            default="text",
        )
        self.typeToggle.currentChanged.connect(self._on_type_changed)
        self.optionsForm.addRow(self._fieldLabel("Watermark"), self.typeToggle)

        self.textEdit = QLineEdit()
        self.textEdit.setText("CONFIDENTIAL")
        self.textEdit.setPlaceholderText("Watermark text")
        self.textRow = self._fieldLabel("Text")
        self.optionsForm.addRow(self.textRow, self.textEdit)

        self.fontSizeSpin = QSpinBox()
        self.fontSizeSpin.setRange(8, 300)
        self.fontSizeSpin.setValue(60)
        self.fontSizeSpin.setSuffix(" pt")
        self.fontSizeRow = self._fieldLabel("Font size")
        self.optionsForm.addRow(self.fontSizeRow, self.fontSizeSpin)

        imageRow = QHBoxLayout()
        self.imagePathEdit = QLineEdit()
        self.imagePathEdit.setReadOnly(True)
        self.imagePathEdit.setPlaceholderText("Choose a PNG or JPEG image")
        imageBrowseButton = QPushButton("Browse…")
        imageBrowseButton.setProperty("flat", True)
        imageBrowseButton.clicked.connect(self._browse_for_image)
        imageRow.addWidget(self.imagePathEdit)
        imageRow.addWidget(imageBrowseButton)
        self.imageRow = self._fieldLabel("Image")
        self.optionsForm.addRow(self.imageRow, imageRow)

        self.imageScaleSpin = QSpinBox()
        self.imageScaleSpin.setRange(5, 100)
        self.imageScaleSpin.setValue(30)
        self.imageScaleSpin.setSuffix("% of page width")
        self.imageScaleRow = self._fieldLabel("Image size")
        self.optionsForm.addRow(self.imageScaleRow, self.imageScaleSpin)

        self.opacitySpin = QSpinBox()
        self.opacitySpin.setRange(1, 100)
        self.opacitySpin.setValue(35)
        self.opacitySpin.setSuffix("%")
        self.optionsForm.addRow(self._fieldLabel("Opacity"), self.opacitySpin)

        self.rotationSpin = QSpinBox()
        self.rotationSpin.setRange(-180, 180)
        self.rotationSpin.setValue(45)
        self.rotationSpin.setSuffix("°")
        self.optionsForm.addRow(self._fieldLabel("Rotation"), self.rotationSpin)

        self.placementToggle = ToggleGroup(
            [("tile", "Tiled"), ("center", "Centered")],
            default="tile",
        )
        self.optionsForm.addRow(self._fieldLabel("Placement"), self.placementToggle)

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

        self._on_type_changed(self.typeToggle.value())

        return panel

    def _fieldLabel(self, text):
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        return label

    def _on_type_changed(self, value):
        is_text = value == "text"
        self.optionsForm.setRowVisible(self.textRow, is_text)
        self.optionsForm.setRowVisible(self.fontSizeRow, is_text)
        self.optionsForm.setRowVisible(self.imageRow, not is_text)
        self.optionsForm.setRowVisible(self.imageScaleRow, not is_text)

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
        self.watermarkButton.setEnabled(True)
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
        self.watermarkButton.setEnabled(False)
        self.statusLabel.setText("")
        self.dropZone.setPrompt("Drag & drop PDFs here, or click to browse")

    # ---- Watermark image selection ----

    def _browse_for_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select watermark image", "", "Images (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if not path:
            return
        if Path(path).suffix.lower() not in IMAGE_EXTENSIONS:
            QMessageBox.warning(self, "Unsupported image", f"{Path(path).name}: unsupported format")
            return
        self.image_path = path
        self.imagePathEdit.setText(path)

    # ---- Output path ----

    def _update_default_output_path(self):
        if not self.pdf_files:
            return
        first_path = self.pdf_files[0][0]
        parent = Path(first_path).parent
        if len(self.pdf_files) == 1:
            self.output_target = str(parent / f"{Path(first_path).stem}_watermarked.pdf")
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

    # ---- Watermarking ----

    def _build_jobs(self):
        if len(self.pdf_files) == 1:
            return [(self.pdf_files[0][0], self.output_target)]
        output_dir = Path(self.output_target)
        return [
            (path, str(output_dir / f"{Path(path).stem}_watermarked.pdf"))
            for path, _, _ in self.pdf_files
        ]

    def _start_watermarking(self):
        if not self.pdf_files or not self.output_target:
            return

        watermark_type = self.typeToggle.value()
        if watermark_type == "text" and not self.textEdit.text().strip():
            QMessageBox.warning(self, "Missing text", "Enter the watermark text.")
            return
        if watermark_type == "image" and not self.image_path:
            QMessageBox.warning(self, "Missing image", "Choose a watermark image.")
            return

        config = {
            "type": watermark_type,
            "text": self.textEdit.text().strip(),
            "font_size": self.fontSizeSpin.value(),
            "image_path": self.image_path,
            "image_scale": self.imageScaleSpin.value(),
            "opacity": self.opacitySpin.value() / 100,
            "rotation": self.rotationSpin.value(),
            "placement": self.placementToggle.value(),
        }
        jobs = self._build_jobs()

        self._set_running(True)

        self.thread = QThread(self)
        self.worker = WatermarkWorker(jobs, config)
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
        self.watermarkButton.setEnabled(not running)
        self.dropZone.setEnabled(not running)
        self.fileListPanel.setEnabled(not running)
        self.optionsPanel.setEnabled(not running)
        self.progressBar.setVisible(running)
        self.progressBar.setValue(0)
        self.statusLabel.setText("Applying watermark…" if running else "")

    def _on_progress(self, current, total):
        self.progressBar.setMaximum(total)
        self.progressBar.setValue(current)
        self.statusLabel.setText(f"Watermarking file {current} of {total}…")

    def _on_finished(self, results):
        self._set_running(False)
        self.watermarkButton.setEnabled(True)

        if len(results) == 1:
            _, output_path, _, _ = results[0]
            self.statusLabel.setText(f"Done — saved {output_path}")
            open_target = str(Path(output_path).parent)
        else:
            self.statusLabel.setText(f"Done — watermarked {len(results)} files")
            open_target = str(Path(results[0][1]).parent)

        self._offer_open_folder(open_target)

    def _on_error(self, message):
        self._set_running(False)
        self.watermarkButton.setEnabled(True)
        QMessageBox.critical(self, "Watermarking failed", message)
        self.statusLabel.setText("Watermarking failed.")

    def _offer_open_folder(self, folder_path):
        reply = QMessageBox.question(
            self,
            "Watermarking complete",
            "PDF watermarked successfully. Open the containing folder?",
        )
        if reply == QMessageBox.Yes:
            os.startfile(folder_path)

    def _cleanup_thread(self):
        self.thread = None
        self.worker = None
