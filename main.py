"""DRViewer Dng Raw Viewer"""

import sys
from pathlib import Path
from collections import OrderedDict

from PySide6.QtCore import Qt, QSize, QObject, QRunnable, QThreadPool, Signal, QTimer
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFileDialog,
    QSlider,
    QTabBar,
    QListWidget,
    QListWidgetItem,
    QListView,
    QStyledItemDelegate,
    QStackedWidget,
    QFrame,
    QScrollArea,
    QGraphicsView,
    QGraphicsScene,
)

from imaging import DETAIL_FIELDS, category, decode, metadata


class Signals(QObject):
    done = Signal(object, object, object, object)


class Job(QRunnable):
    def __init__(self, key, function):
        super().__init__()
        self.key, self.function, self.signals = key, function, Signals()

    def run(self):
        try:
            result = self.function()
            self.signals.done.emit(self.key, result, None, self)
        except Exception as error:
            self.signals.done.emit(self.key, None, str(error), self)


def load_image(path, preview):
    image, details = decode(path, preview)
    data = image.tobytes()
    return (
        QImage(
            data,
            image.width,
            image.height,
            image.width * 3,
            QImage.Format.Format_RGB888,
        ).copy(),
        details,
    )


class PhotoDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        path = index.data(Qt.ItemDataRole.UserRole)
        window = self.parent().window()
        pixmap = window.thumbnails.get(path)
        rect = option.rect.adjusted(7, 7, -7, -7)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#24272c"))
        painter.drawRoundedRect(rect, 8, 8)
        photo = rect.adjusted(10, 10, -10, -34)
        if pixmap:
            scaled = pixmap.size().scaled(
                photo.size(), Qt.AspectRatioMode.KeepAspectRatio
            )
            target = photo.__class__(0, 0, scaled.width(), scaled.height())
            target.moveCenter(photo.center())
            painter.drawPixmap(target, pixmap)
        else:
            painter.setPen(QColor("#7c838d"))
            painter.drawText(
                photo,
                Qt.AlignmentFlag.AlignCenter,
                "Preview unavailable" if path in window.errors else "Loading…",
            )
        painter.setPen(QColor("#c7cbd1"))
        label = painter.fontMetrics().elidedText(
            Path(path).name, Qt.TextElideMode.ElideMiddle, rect.width() - 20
        )
        painter.drawText(
            rect.adjusted(10, rect.height() - 28, -10, -4),
            Qt.AlignmentFlag.AlignVCenter,
            label,
        )
        painter.restore()


class Grid(QListWidget):
    def __init__(self):
        super().__init__()
        self.columns = 4
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setMovement(QListView.Movement.Static)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setWrapping(True)
        self.setUniformItemSizes(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.setItemDelegate(PhotoDelegate(self))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reflow()

    def reflow(self):
        width = max(1, self.viewport().width() // self.columns)
        size = QSize(width, max(90, int(width * 0.72) + 36))
        self.setGridSize(size)
        for i in range(self.count()):
            self.item(i).setSizeHint(size)


class PhotoView(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.fitted = True

    def set_photo(self, image):
        self.scene().clear()
        self.scene().addPixmap(QPixmap.fromImage(image))
        self.scene().setSceneRect(self.scene().itemsBoundingRect())
        self.fit()

    def fit(self):
        self.fitted = True
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.fitted:
            self.fit()

    def wheelEvent(self, event):
        factor = 1.2 if event.angleDelta().y() > 0 else 1 / 1.2
        scale = self.transform().m11() * factor
        if 0.01 < scale < 16:
            self.fitted = False
            self.scale(factor, factor)

    def mouseDoubleClickEvent(self, event):
        self.fit()


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DRViewer · DNG / RAW Viewer")
        self.resize(1180, 820)
        self.setMinimumSize(640, 480)
        self.setAcceptDrops(True)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self.jobs = set()
        self.files, self.thumbnails, self.errors = [], OrderedDict(), {}
        self.developed = OrderedDict()
        self.developing = set()
        self.pending = set()
        self.current = None
        self.scan_id = 0
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        library = QWidget()
        layout = QVBoxLayout(library)
        layout.setContentsMargins(28, 24, 28, 16)
        header = QHBoxLayout()
        title = QLabel("DRViewer")
        title.setStyleSheet("font-size: 24px; font-weight: 700; letter-spacing: 5px;")
        header.addWidget(title)
        header.addStretch()
        open_button = QPushButton("＋  Open folder")
        open_button.clicked.connect(self.pick_folder)
        header.addWidget(open_button)
        layout.addLayout(header)
        self.location = QLabel("A little space for the bigger picture.")
        self.location.setStyleSheet("color: #858e99; padding: 12px 0;")
        layout.addWidget(self.location)
        toolbar = QHBoxLayout()
        self.tabs = QTabBar()
        self.tabs.addTab("DNG  ·  0")
        self.tabs.addTab("RAW  ·  0")
        self.tabs.currentChanged.connect(self.populate)
        toolbar.addWidget(self.tabs)
        toolbar.addStretch()
        toolbar.addWidget(QLabel("Small"))
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(1, 10)
        self.slider.setValue(7)
        self.slider.setFixedWidth(140)
        self.slider.setAccessibleName("Photo size: 10 columns to 1 column")
        self.slider.valueChanged.connect(self.change_size)
        toolbar.addWidget(self.slider)
        toolbar.addWidget(QLabel("Large"))
        self.column_label = QLabel("4 columns")
        self.column_label.setFixedWidth(78)
        toolbar.addWidget(self.column_label)
        layout.addLayout(toolbar)
        self.library_stack = QStackedWidget()
        self.grid = Grid()
        self.grid.itemClicked.connect(self.open_photo)
        self.grid.verticalScrollBar().valueChanged.connect(self.schedule_visible)
        self.library_stack.addWidget(self.grid)
        empty = QWidget()
        empty_layout = QVBoxLayout(empty)
        empty_layout.addStretch()
        self.empty_title = QLabel("Your photos, in their original light.")
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_title.setStyleSheet("font-size: 24px; color: #dce0e6;")
        empty_layout.addWidget(self.empty_title)
        self.empty_help = QLabel(
            "Open a folder or drop files here to start browsing.\nDNG and camera RAW files are automatically separated."
        )
        self.empty_help.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_help.setStyleSheet("color: #858e99; padding: 16px;")
        empty_layout.addWidget(self.empty_help)
        empty_layout.addStretch()
        self.library_stack.addWidget(empty)
        layout.addWidget(self.library_stack)
        self.status = QLabel("LOCAL FILES  ·  Originals are never modified")
        layout.addWidget(self.status)
        self.stack.addWidget(library)
        viewer = QWidget()
        viewer_layout = QVBoxLayout(viewer)
        bar = QHBoxLayout()
        close = QPushButton("✕")
        close.setAccessibleName("Close photo")
        close.setToolTip("Close photo (Esc)")
        close.clicked.connect(self.close_photo)
        bar.addWidget(close)
        self.photo_title = QLabel()
        bar.addWidget(self.photo_title)
        bar.addStretch()
        self.format_switch = QPushButton()
        self.format_switch.clicked.connect(self.switch_format)
        self.format_switch.hide()
        bar.addWidget(self.format_switch)
        self.info = QPushButton("ⓘ")
        self.info.setAccessibleName("Show detail")
        self.info.setToolTip("Show detail (I)")
        self.info.setCheckable(True)
        self.info.toggled.connect(lambda shown: self.details_panel.setVisible(shown))
        bar.addWidget(self.info)
        viewer_layout.addLayout(bar)
        body = QHBoxLayout()
        self.photo = PhotoView()
        body.addWidget(self.photo, 1)
        self.details_panel = QScrollArea()
        self.details_panel.setFixedWidth(280)
        self.details_panel.setWidgetResizable(True)
        self.details_panel.setFrameShape(QFrame.Shape.NoFrame)
        self.details_panel.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        detail_content = QWidget()
        self.details_panel.setWidget(detail_content)
        detail_layout = QVBoxLayout(detail_content)
        detail_layout.addWidget(QLabel("PHOTO DETAILS"))
        self.detail_labels = {}
        for field in DETAIL_FIELDS:
            heading = QLabel(field.upper())
            heading.setStyleSheet("color: #858e99; font-size: 10px; margin-top: 18px;")
            detail_layout.addWidget(heading)
            value = QLabel("N/A")
            value.setWordWrap(True)
            value.setTextFormat(Qt.TextFormat.PlainText)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            detail_layout.addWidget(value)
            self.detail_labels[field] = value
        detail_layout.addStretch()
        body.addWidget(self.details_panel)
        self.details_panel.hide()
        viewer_layout.addLayout(body, 1)
        self.viewer_status = QLabel(
            "Scroll to zoom  ·  Drag to pan  ·  Double-click to fit  ·  ← → to browse"
        )
        viewer_layout.addWidget(self.viewer_status)
        self.stack.addWidget(viewer)
        for key, action in [
            ("Escape", self.close_photo),
            ("I", self.info.click),
            ("Right", lambda: self.navigate(1)),
            ("Left", lambda: self.navigate(-1)),
        ]:
            QShortcut(QKeySequence(key), self, activated=action)
        QShortcut(QKeySequence.StandardKey.Open, self, activated=self.pick_folder)
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.schedule_visible)
        self.timer.start()
        self.populate()

    def submit(self, key, function, callback, priority=0):
        job = Job(key, function)
        self.jobs.add(job)
        job.signals.done.connect(callback)
        self.pool.start(job, priority)

    def pick_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Open photo folder")
        if folder:
            self.import_paths([Path(folder)])

    def import_paths(self, paths):
        self.close_photo()
        self.scan_id += 1
        self.developed.clear()
        token = self.scan_id
        self.location.setText("Scanning folders…")

        def scan():
            found = set()
            for path in paths:
                if path.is_dir():
                    found.update(
                        str(p.resolve())
                        for p in path.rglob("*")
                        if p.is_file() and category(p)
                    )
                elif path.is_file() and category(path):
                    found.add(str(path.resolve()))
            return sorted(found, key=str.casefold)

        self.submit(token, scan, self.scanned)

    def scanned(self, token, files, error, job):
        self.jobs.discard(job)
        if token != self.scan_id:
            return
        self.files = files or []
        self.thumbnails.clear()
        self.errors.clear()
        self.location.setText(
            f"{len(self.files)} photos · {Path(self.files[0]).parent}"
            if self.files
            else "No supported photos found"
        )
        self.location.setToolTip(error or self.location.text())
        for i, name in enumerate(("DNG", "RAW")):
            self.tabs.setTabText(
                i, f"{name}  ·  {sum(category(p) == name for p in self.files)}"
            )
        self.populate()
        if error:
            self.status.setText(f"Could not scan folder: {error}")

    def populate(self):
        self.grid.clear()
        name = ("DNG", "RAW")[self.tabs.currentIndex()]
        for path in self.files:
            if category(path) == name:
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, path)
                item.setToolTip(path)
                self.grid.addItem(item)
        self.grid.reflow()
        self.library_stack.setCurrentIndex(0 if self.grid.count() else 1)
        self.empty_title.setText(
            f"No {name} photos in this selection."
            if self.files
            else "Your photos, in their original light."
        )
        self.status.setText(
            f"{self.grid.count()} {name} photos  ·  Originals are never modified"
        )

    def change_size(self, value):
        self.grid.columns = 11 - value
        self.column_label.setText(
            f"{self.grid.columns} column" + ("s" if self.grid.columns != 1 else "")
        )
        self.grid.reflow()

    def schedule_visible(self):
        if self.stack.currentIndex() != 0 or self.library_stack.currentIndex() != 0:
            return
        rect = self.grid.viewport().rect()
        for i in range(self.grid.count()):
            if len(self.pending) >= 4:
                break
            item = self.grid.item(i)
            path = item.data(Qt.ItemDataRole.UserRole)
            key = (self.scan_id, path)
            if (
                self.grid.visualItemRect(item).intersects(rect)
                and path not in self.thumbnails
                and path not in self.errors
                and key not in self.pending
            ):
                self.pending.add(key)
                self.submit(
                    key, lambda p=path: load_image(p, True), self.thumbnail_loaded
                )

    def thumbnail_loaded(self, key, result, error, job):
        self.jobs.discard(job)
        self.pending.discard(key)
        token, path = key
        if token != self.scan_id:
            return
        if error:
            self.errors[path] = error
        else:
            self.thumbnails[path] = QPixmap.fromImage(result[0])
            while len(self.thumbnails) > 160:
                self.thumbnails.popitem(last=False)
        self.grid.viewport().update()

    def open_photo(self, item):
        path = item.data(Qt.ItemDataRole.UserRole)
        self.current = path
        counterpart = self.matching_format()
        self.format_switch.setVisible(counterpart is not None)
        if counterpart:
            self.format_switch.setText(f"Switch to {category(counterpart)}")
            self.format_switch.setToolTip(Path(counterpart).name)
        self.photo_title.setText(Path(path).name)
        self.photo_title.setTextFormat(Qt.TextFormat.PlainText)
        self.photo.scene().clear()
        self.stack.setCurrentIndex(1)
        pair = Path(path).with_suffix("")
        versions = self.developed.setdefault(pair, {})
        cached = versions.get(path)
        # Viewing either format refreshes the whole pair; late workers do not.
        self.developed.move_to_end(pair)
        while len(self.developed) > 20:
            self.developed.popitem(last=False)
        if cached is not None:
            self.show_developed(cached)
            return
        self.set_details(metadata(path, {}))
        if path in self.thumbnails:
            self.photo.set_photo(self.thumbnails[path].toImage())
        self.viewer_status.setText("Developing photo…")
        self.viewer_status.setToolTip("")
        key = (self.scan_id, path)
        if key not in self.developing:
            self.developing.add(key)
            self.submit(key, lambda: load_image(path, False), self.photo_loaded, 1)

    def matching_format(self):
        if not self.current:
            return None
        current = Path(self.current)
        matches = [path for path in self.files
                   if Path(path).parent == current.parent
                   and Path(path).stem == current.stem
                   and category(path) != category(current)]
        return matches[0] if len(matches) == 1 else None

    def switch_format(self):
        counterpart = self.matching_format()
        if counterpart is None:
            return
        self.tabs.setCurrentIndex(0 if category(counterpart) == "DNG" else 1)
        for index in range(self.grid.count()):
            item = self.grid.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == counterpart:
                self.open_photo(item)
                self.grid.scrollToItem(item)
                break

    def photo_loaded(self, key, result, error, job):
        self.jobs.discard(job)
        self.developing.discard(key)
        token, path = key
        if token != self.scan_id:
            return
        pair = Path(path).with_suffix("")
        if not error and pair in self.developed:
            self.developed[pair][path] = result
        if self.current != path:
            return
        if error:
            self.viewer_status.setText(
                "Could not decode this photo. The file may be unsupported or damaged."
            )
            self.viewer_status.setToolTip(error)
            self.set_details(metadata(path))
        else:
            self.show_developed(result)

    def show_developed(self, result):
        self.photo.set_photo(result[0])
        self.set_details(result[1])
        self.viewer_status.setText(
            "Scroll to zoom  ·  Drag to pan  ·  Double-click to fit  ·  ← → to browse"
        )
        self.viewer_status.setToolTip("")

    def set_details(self, details):
        for field, label in self.detail_labels.items():
            label.setText(details.get(field) or "N/A")

    def close_photo(self):
        self.current = None
        self.stack.setCurrentIndex(0)
        self.photo.scene().clear()
        self.info.setChecked(False)

    def navigate(self, offset):
        if self.current:
            paths = [
                self.grid.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self.grid.count())
            ]
            if self.current in paths:
                index = paths.index(self.current) + offset
                if 0 <= index < len(paths):
                    self.open_photo(self.grid.item(index))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.import_paths(
            [
                Path(url.toLocalFile())
                for url in event.mimeData().urls()
                if url.isLocalFile()
            ]
        )
        event.acceptProposedAction()

    def closeEvent(self, event):
        self.timer.stop()
        self.pool.clear()
        self.pool.waitForDone()
        event.accept()


STYLE = """
QWidget { background: #191b1f; color: #dce0e6; font-family: Helvetica, Arial; font-size: 12px; }
QPushButton { background: #2e343b; border: 1px solid #404751; border-radius: 6px; padding: 9px 15px; }
QPushButton:hover { background: #424b56; }
QPushButton:checked { background: #536859; }
QTabBar::tab { padding: 12px 24px; color: #858e99; border-bottom: 2px solid #30353c; }
QTabBar::tab:selected { color: #c3dec9; border-bottom: 2px solid #b9d5bc; }
QListWidget, QGraphicsView { border: none; background: #191b1f; }
QSlider::groove:horizontal { height: 3px; background: #424951; }
QSlider::handle:horizontal { background: #c3dec9; width: 12px; margin: -5px 0; border-radius: 6px; }
QScrollBar:vertical { width: 10px; background: #191b1f; }
QScrollBar::handle:vertical { background: #424951; min-height: 30px; border-radius: 5px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { background: #30353c; color: #ffffff; border: none; }
"""


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = Window()
    window.show()
    if len(sys.argv) > 1:
        window.import_paths([Path(arg) for arg in sys.argv[1:]])
    sys.exit(app.exec())
