import os
from io import BytesIO
from pathlib import Path

import img2pdf
from PIL import Image
from PySide6.QtCore import QObject, QSize, Qt, QThread, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.widgets.drop_zone import DropZone
from app.widgets.toggle_group import ToggleGroup

ALLOWED_EXTENSIONS = [".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"]

PAGE_SIZES_MM = {
    "a4": (210, 297),
    "letter": (215.9, 279.4),
}


def normalize_image(path):
    """Load an image and return lossless PNG bytes in RGB (alpha flattened
    onto white), preserving DPI so 'original size' layout stays accurate."""
    with Image.open(path) as img:
        dpi = img.info.get("dpi", (96, 96))

        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            rgba = img.convert("RGBA")
            background = Image.new("RGB", rgba.size, (255, 255, 255))
            background.paste(rgba, mask=rgba.split()[-1])
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

        buf = BytesIO()
        img.save(buf, format="PNG", dpi=dpi)
        return buf.getvalue()


def build_layout_fun(page_size, orientation):
    if page_size == "original":
        return None

    w_mm, h_mm = PAGE_SIZES_MM[page_size]
    if orientation == "landscape":
        w_mm, h_mm = max(w_mm, h_mm), min(w_mm, h_mm)
    else:
        w_mm, h_mm = min(w_mm, h_mm), max(w_mm, h_mm)

    pagesize = (img2pdf.mm_to_pt(w_mm), img2pdf.mm_to_pt(h_mm))
    auto_orient = orientation == "auto"
    return img2pdf.get_layout_fun(pagesize=pagesize, fit=img2pdf.FitMode.into, auto_orient=auto_orient)


class ConversionWorker(QObject):
    progress = Signal(int, int)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, image_paths, output_path, page_size, orientation):
        super().__init__()
        self.image_paths = image_paths
        self.output_path = output_path
        self.page_size = page_size
        self.orientation = orientation

    def run(self):
        try:
            total = len(self.image_paths)
            normalized = []
            for i, path in enumerate(self.image_paths):
                normalized.append(normalize_image(path))
                self.progress.emit(i + 1, total)

            layout_fun = build_layout_fun(self.page_size, self.orientation)
            kwargs = {"layout_fun": layout_fun} if layout_fun else {}
            pdf_bytes = img2pdf.convert(normalized, **kwargs)

            Path(self.output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(self.output_path, "wb") as f:
                f.write(pdf_bytes)

            self.finished.emit(self.output_path)
        except Exception as exc:
            self.error.emit(str(exc))


class ImageToPdfPage(QWidget):

    def __init__(self, router):
        super().__init__()

        self.router = router
        self.image_paths = []
        self.output_path = None
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

        subtitle = QLabel("Combine JPG and PNG images into a single PDF document.")
        subtitle.setObjectName("pageSubtitle")
        root.addWidget(subtitle)

        self.dropZone = DropZone(
            extensions=ALLOWED_EXTENSIONS,
            file_filter="Images (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff)",
            prompt="Drag & drop images here, or click to browse",
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
        self.fileList.setIconSize(QSize(40, 40))
        self.fileList.setDragDropMode(QAbstractItemView.InternalMove)
        self.fileList.model().rowsMoved.connect(self._sync_order_from_list)
        outer.addWidget(self.fileList)

        hint = QLabel("Drag rows to reorder — pages follow this order.")
        hint.setObjectName("mutedLabel")
        outer.addWidget(hint)

        return panel

    def _build_options_panel(self):
        panel = QFrame()
        panel.setObjectName("panel")

        self.optionsForm = QFormLayout(panel)
        self.optionsForm.setContentsMargins(20, 20, 20, 20)
        self.optionsForm.setSpacing(14)
        self.optionsForm.setLabelAlignment(Qt.AlignLeft)

        self.pageSizeToggle = ToggleGroup(
            [("original", "Original size"), ("a4", "A4"), ("letter", "US Letter")],
            default="original",
        )
        self.pageSizeToggle.currentChanged.connect(self._on_page_size_changed)
        self.optionsForm.addRow(self._fieldLabel("Page size"), self.pageSizeToggle)

        self.orientationToggle = ToggleGroup(
            [("auto", "Auto"), ("portrait", "Portrait"), ("landscape", "Landscape")],
            default="auto",
        )
        self.optionsForm.addRow(self._fieldLabel("Orientation"), self.orientationToggle)
        self.optionsForm.setRowVisible(self.orientationToggle, False)

        outputRow = QHBoxLayout()
        self.outputPathEdit = QLineEdit()
        self.outputPathEdit.setReadOnly(True)
        browseButton = QPushButton("Browse…")
        browseButton.setProperty("flat", True)
        browseButton.clicked.connect(self._browse_for_output_pdf)
        outputRow.addWidget(self.outputPathEdit)
        outputRow.addWidget(browseButton)
        self.optionsForm.addRow(self._fieldLabel("Save PDF as"), outputRow)

        return panel

    def _fieldLabel(self, text):
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        return label

    def _on_page_size_changed(self, value):
        self.optionsForm.setRowVisible(self.orientationToggle, value != "original")

    # ---- File selection ----

    def _browse_for_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select images", "", "Images (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff)"
        )
        if paths:
            self._on_files_selected(paths)

    def _on_files_selected(self, paths):
        added = []
        errors = []

        for path in paths:
            if Path(path).suffix.lower() not in ALLOWED_EXTENSIONS:
                errors.append(f"{Path(path).name}: unsupported format")
                continue
            try:
                with Image.open(path) as img:
                    img.verify()
                added.append(path)
            except Exception as exc:
                errors.append(f"{Path(path).name}: {exc}")

        if errors:
            QMessageBox.warning(self, "Some files were skipped", "\n".join(errors))

        if not added:
            return

        self.image_paths.extend(added)
        self._refresh_file_list_ui()
        self._update_default_output_path()

        self.fileListPanel.setVisible(True)
        self.optionsPanel.setVisible(True)
        self.convertButton.setEnabled(True)
        self.statusLabel.setText("")
        self.dropZone.setPrompt("Drag & drop more images here, or click to browse")

    def _refresh_file_list_ui(self):
        self.fileList.blockSignals(True)
        self.fileList.clear()

        for path in self.image_paths:
            item = QListWidgetItem(Path(path).name)
            item.setData(Qt.UserRole, path)

            pixmap = QPixmap(path)
            if not pixmap.isNull():
                item.setIcon(QIcon(pixmap.scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation)))

            self.fileList.addItem(item)

        self.fileList.blockSignals(False)

        count = len(self.image_paths)
        self.fileListHeaderLabel.setText(f"{count} image{'s' if count != 1 else ''} selected")

    def _sync_order_from_list(self, *args):
        self.image_paths = [
            self.fileList.item(i).data(Qt.UserRole) for i in range(self.fileList.count())
        ]

    def _remove_selected(self):
        rows = sorted({index.row() for index in self.fileList.selectedIndexes()}, reverse=True)
        if not rows:
            return
        for row in rows:
            del self.image_paths[row]
        self._refresh_file_list_ui()
        if not self.image_paths:
            self._reset_selection()

    def _reset_selection(self):
        self.image_paths = []
        self.output_path = None
        self.fileList.clear()
        self.fileListPanel.setVisible(False)
        self.optionsPanel.setVisible(False)
        self.convertButton.setEnabled(False)
        self.statusLabel.setText("")
        self.dropZone.setPrompt("Drag & drop images here, or click to browse")

    # ---- Output path ----

    def _update_default_output_path(self):
        if not self.image_paths:
            return
        parent = str(Path(self.image_paths[0]).parent)
        self.output_path = str(Path(parent) / "images.pdf")
        self.outputPathEdit.setText(self.output_path)

    def _browse_for_output_pdf(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save PDF as", self.output_path or "", "PDF files (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        self.output_path = path
        self.outputPathEdit.setText(path)

    # ---- Conversion ----

    def _start_conversion(self):
        if not self.image_paths or not self.output_path:
            return

        page_size = self.pageSizeToggle.value()
        orientation = self.orientationToggle.value()

        self._set_running(True)

        self.thread = QThread(self)
        self.worker = ConversionWorker(list(self.image_paths), self.output_path, page_size, orientation)
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
        self.fileListPanel.setEnabled(not running)
        self.optionsPanel.setEnabled(not running)
        self.progressBar.setVisible(running)
        self.progressBar.setValue(0)
        self.statusLabel.setText("Converting…" if running else "")

    def _on_progress(self, current, total):
        self.progressBar.setMaximum(total)
        self.progressBar.setValue(current)
        self.statusLabel.setText(f"Processing image {current} of {total}…")

    def _on_finished(self, output_path):
        self._set_running(False)
        self.convertButton.setEnabled(True)
        self.statusLabel.setText(f"Done — saved {output_path}")
        self._offer_open_folder(output_path)

    def _on_error(self, message):
        self._set_running(False)
        self.convertButton.setEnabled(True)
        QMessageBox.critical(self, "Conversion failed", message)
        self.statusLabel.setText("Conversion failed.")

    def _offer_open_folder(self, output_path):
        reply = QMessageBox.question(
            self,
            "Conversion complete",
            "PDF created successfully. Open the containing folder?",
        )
        if reply == QMessageBox.Yes:
            os.startfile(str(Path(output_path).parent))

    def _cleanup_thread(self):
        self.thread = None
        self.worker = None
