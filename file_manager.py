import sys
import os
import shutil
import datetime
import zipfile
import time
import json
import traceback
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                               QLineEdit, QPushButton, QTreeWidget, QTreeWidgetItem, 
                               QFileDialog, QLabel, QSplitter, QComboBox, QDateEdit, 
                               QCheckBox, QMessageBox, QFrame, QHeaderView,
                               QFileSystemModel, QFileIconProvider, QStatusBar, 
                               QStackedWidget, QSpinBox, QFormLayout, QGroupBox,
                               QProgressBar, QTableWidget, QTableWidgetItem, QAbstractItemView,
                               QInputDialog, QDialog, QDialogButtonBox, QTabWidget, QTextEdit,
                               QListWidget, QListWidgetItem, QColorDialog, QScrollArea)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QFileInfo, QSize, QSettings, QDate, QUrl
from PySide6.QtGui import QIcon, QColor, QAction, QPainter, QPixmap, QDesktopServices, QBrush, QPolygonF, QPen, QImage

# Try importing OpenCV for video thumbnails
try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False

# --- CONFIGURATION ---
PRESETS_FILE = "organizer_presets.json"
SETTINGS_FILE = "app_settings.json"

# --- DEFAULT THEME ---
DEFAULT_THEME = {
    "bg_main": "#282a36",
    "bg_sec": "#21222c",
    "fg_text": "#f8f8f2",
    "accent": "#bd93f9",
    "input_bg": "#44475a",
    "border": "#6272a4",
    "highlight": "#ff79c6"
}

# --- HELPER CLASSES ---

class ThumbnailWorker(QThread):
    """Generates thumbnails for images and videos in the background."""
    icon_ready = Signal(str, QIcon) # Path, Icon

    def __init__(self):
        super().__init__()
        self.queue = []
        self.running = True
        self.cache = {}

    def add_to_queue(self, path):
        if path not in self.cache and path not in self.queue:
            self.queue.append(path)

    def run(self):
        while self.running:
            if not self.queue:
                self.msleep(100)
                continue
            
            path = self.queue.pop(0)
            if path in self.cache:
                self.icon_ready.emit(path, self.cache[path])
                continue

            icon = self.generate_icon(path)
            if icon:
                self.cache[path] = icon
                self.icon_ready.emit(path, icon)

    def generate_icon(self, path):
        pixmap = QPixmap(128, 128)
        pixmap.fill(Qt.transparent)
        
        ext = os.path.splitext(path)[1].lower()
        is_video = ext in ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv']
        is_image = ext in ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp']

        try:
            final_pixmap = None
            
            # 1. Generate Base Image
            if is_image:
                original = QPixmap(path)
                if not original.isNull():
                    final_pixmap = original.scaled(128, 128, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            
            elif is_video and OPENCV_AVAILABLE:
                cap = cv2.VideoCapture(path)
                ret, frame = cap.read()
                cap.release()
                if ret:
                    # Convert BGR (OpenCV) to RGB (Qt)
                    height, width, channel = frame.shape
                    bytes_per_line = 3 * width
                    q_img = QImage(frame.data, width, height, bytes_per_line, QImage.Format_RGB888).rgbSwapped()
                    final_pixmap = QPixmap.fromImage(q_img).scaled(128, 128, Qt.KeepAspectRatio, Qt.SmoothTransformation)

            # 2. Apply Overlays
            if final_pixmap:
                # Create a canvas to draw on
                canvas = QPixmap(128, 128)
                canvas.fill(Qt.transparent)
                painter = QPainter(canvas)
                
                # Center the image
                x = (128 - final_pixmap.width()) // 2
                y = (128 - final_pixmap.height()) // 2
                painter.drawPixmap(x, y, final_pixmap)

                # Draw Video Indicator
                if is_video:
                    # Semi-transparent circle background
                    painter.setBrush(QBrush(QColor(0, 0, 0, 150)))
                    painter.setPen(Qt.NoPen)
                    painter.drawEllipse(44, 44, 40, 40)
                    
                    # White Play Triangle
                    painter.setBrush(QBrush(Qt.white))
                    triangle = QPolygonF([
                        QPointF(55, 55),
                        QPointF(55, 73),
                        QPointF(75, 64)
                    ])
                    painter.drawPolygon(triangle)

                painter.end()
                return QIcon(canvas)
                
        except Exception:
            pass # Fallback to default
        return None
    
    def stop(self):
        self.running = False
        self.wait()

from PySide6.QtCore import QPointF # Needed for the triangle drawing above

class LogDialog(QDialog):
    """Simple dialog to display execution logs."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Process Log")
        self.resize(700, 500)
        layout = QVBoxLayout(self)
        self.text_area = QTextEdit()
        self.text_area.setReadOnly(True)
        self.text_area.setStyleSheet("font-family: Consolas, monospace; font-size: 12px;")
        
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.hide)
        
        layout.addWidget(QLabel("Execution Details:"))
        layout.addWidget(self.text_area)
        layout.addWidget(btn_close)

    def log(self, message):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.text_area.append(f"[{timestamp}] {message}")
    
    def clear(self):
        self.text_area.clear()

class RuleEditDialog(QDialog):
    """Dialog to create or edit complex file sorting rules."""
    def __init__(self, parent=None, rule_data=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Smart Rule")
        self.resize(600, 600)
        self.layout = QVBoxLayout(self)
        self.rule_data = rule_data or {}

        # 1. Basic Info
        gb_basic = QGroupBox("General")
        form_basic = QFormLayout()
        self.inp_name = QLineEdit(self.rule_data.get("name", "New Rule"))
        form_basic.addRow("Rule Name:", self.inp_name)
        gb_basic.setLayout(form_basic)
        self.layout.addWidget(gb_basic)

        # 2. Criteria
        gb_criteria = QGroupBox("Match Criteria (Leave empty to ignore)")
        form_crit = QFormLayout()
        
        self.inp_contains = QLineEdit(self.rule_data.get("contains", ""))
        self.inp_contains.setPlaceholderText("File name contains (comma separated for OR)...")
        
        self.inp_exts = QLineEdit(self.rule_data.get("extensions", ""))
        self.inp_exts.setPlaceholderText("Comma separated (e.g. .jpg, .png)")

        # Size
        hbox_size = QHBoxLayout()
        self.spin_size_min = QSpinBox()
        self.spin_size_min.setRange(0, 999999)
        self.spin_size_min.setSuffix(" MB")
        self.spin_size_min.setValue(self.rule_data.get("size_min", 0))
        
        self.spin_size_max = QSpinBox()
        self.spin_size_max.setRange(0, 999999)
        self.spin_size_max.setSuffix(" MB")
        self.spin_size_max.setValue(self.rule_data.get("size_max", 0)) # 0 means no max
        
        hbox_size.addWidget(QLabel("Min:"))
        hbox_size.addWidget(self.spin_size_min)
        hbox_size.addWidget(QLabel("Max (0=Any):"))
        hbox_size.addWidget(self.spin_size_max)

        # Date
        hbox_date = QHBoxLayout()
        self.chk_date = QCheckBox("Modified After:")
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        
        saved_date = self.rule_data.get("date_after", None)
        if saved_date:
            self.chk_date.setChecked(True)
            self.date_edit.setDate(QDate.fromString(saved_date, "yyyy-MM-dd"))
        
        hbox_date.addWidget(self.chk_date)
        hbox_date.addWidget(self.date_edit)

        form_crit.addRow("Name Match:", self.inp_contains)
        form_crit.addRow("Extensions:", self.inp_exts)
        form_crit.addRow("File Size:", hbox_size)
        form_crit.addRow("Date:", hbox_date)
        gb_criteria.setLayout(form_crit)
        self.layout.addWidget(gb_criteria)

        # 3. Destination & Subfolders
        gb_dest = QGroupBox("Destination & Subfolder Structure")
        form_dest = QFormLayout()
        
        # Base Path
        dest_layout = QHBoxLayout()
        self.inp_dest = QLineEdit(self.rule_data.get("destination", ""))
        btn_browse = QPushButton("...")
        btn_browse.setObjectName("BrowseBtn")
        btn_browse.clicked.connect(self.browse_dest)
        dest_layout.addWidget(self.inp_dest)
        dest_layout.addWidget(btn_browse)

        # Subfolder Pattern Builder
        self.combo_pattern = QComboBox()
        self.combo_pattern.addItems([
            "Custom (Use Pattern Below)",
            "--- Date: 3 Levels (Deep) ---",
            "Year/Month/Day ({Year}/{Month}/{Day})",
            "--- Date: 2 Levels (Condensed) ---",
            "Daily Condensed ({Year}/{Day}d-{Month}m)",
            "Weekly Condensed ({Year}/Week{Week}-{Month}m)",
            "Monthly Standard ({Year}/{Month})",
            "--- Date: 1 Level (Flat) ---",
            "Flat Date ({Year}-{Month}-{Day})",
            "Flat Monthly ({Year}-{Month})",
            "Year Only ({Year})",
            "--- Attributes ---",
            "By Extension ({Ext})",
            "By Size ({Size_Tier})",
            "Alphabetical ({First_Letter})"
        ])
        self.combo_pattern.currentIndexChanged.connect(self.update_pattern_input)
        
        # Subname inputs
        subname_layout = QHBoxLayout()
        self.inp_prefix = QLineEdit(self.rule_data.get("prefix", ""))
        self.inp_prefix.setPlaceholderText("Prefix (e.g. Backup_)")
        self.inp_suffix = QLineEdit(self.rule_data.get("suffix", ""))
        self.inp_suffix.setPlaceholderText("Suffix (e.g. _Done)")
        subname_layout.addWidget(QLabel("Prefix:"))
        subname_layout.addWidget(self.inp_prefix)
        subname_layout.addWidget(QLabel("Suffix:"))
        subname_layout.addWidget(self.inp_suffix)

        self.inp_pattern = QLineEdit(self.rule_data.get("pattern", "{Year}/{Month}"))
        self.inp_pattern.setPlaceholderText("Ex: {Year}/{Month}/{Ext}")
        
        lbl_help = QLabel("Tags: {Year}, {Month}, {Day}, {Week}, {Ext}, {Name}, {Size_Tier}, {First_Letter}")
        lbl_help.setWordWrap(True)
        lbl_help.setStyleSheet("color: #6272a4; font-size: 11px;")

        form_dest.addRow("Base Folder:", dest_layout)
        form_dest.addRow("Auto-Subfolder:", self.combo_pattern)
        form_dest.addRow("Folder Pattern:", self.inp_pattern)
        form_dest.addRow("Extra Subname:", subname_layout)
        form_dest.addRow("", lbl_help)
        
        gb_dest.setLayout(form_dest)
        self.layout.addWidget(gb_dest)

        # Buttons
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        self.layout.addWidget(btns)

    def browse_dest(self):
        d = QFileDialog.getExistingDirectory(self, "Select Destination Base")
        if d: self.inp_dest.setText(d)

    def update_pattern_input(self):
        txt = self.combo_pattern.currentText()
        if "Custom" in txt or "---" in txt: return
        import re
        match = re.search(r'\((.*?)\)', txt)
        if match:
            self.inp_pattern.setText(match.group(1))

    def get_data(self):
        return {
            "name": self.inp_name.text(),
            "contains": self.inp_contains.text(),
            "extensions": self.inp_exts.text(),
            "size_min": self.spin_size_min.value(),
            "size_max": self.spin_size_max.value(),
            "date_after": self.date_edit.date().toString("yyyy-MM-dd") if self.chk_date.isChecked() else None,
            "destination": self.inp_dest.text(),
            "pattern": self.inp_pattern.text(),
            "prefix": self.inp_prefix.text(),
            "suffix": self.inp_suffix.text()
        }

# --- WORKER THREADS ---
class SearchWorker(QThread):
    batch_found = Signal(list) 
    finished = Signal(int, float)

    def __init__(self, root_dir, recursive, keywords, extensions, size_filter, date_filter, batch_size):
        super().__init__()
        self.root_dir = root_dir
        self.recursive = recursive
        self.keywords = keywords 
        self.extensions = extensions 
        self.size_filter = size_filter 
        self.date_filter = date_filter 
        self.batch_size = batch_size
        self.running = True

    def run(self):
        start_time = time.time()
        count = 0
        current_batch = []
        
        if not os.path.isdir(self.root_dir):
            self.finished.emit(0, 0)
            return

        if self.recursive:
            iterator = os.walk(self.root_dir)
        else:
            try:
                with os.scandir(self.root_dir) as entries:
                    files = [e.name for e in entries if e.is_file()]
                    iterator = [(self.root_dir, [], files)]
            except OSError:
                iterator = []

        for root, dirs, files in iterator:
            if not self.running: break
            for file in files:
                if not self.running: break
                if self.extensions and not any(file.lower().endswith(ext) for ext in self.extensions): continue
                if self.keywords and not any(k.lower() in file.lower() for k in self.keywords): continue

                file_path = os.path.join(root, file)
                try:
                    stats = os.stat(file_path)
                    if self.size_filter:
                        ftype, fsize = self.size_filter
                        if (ftype == 'gt' and stats.st_size <= fsize) or \
                           (ftype == 'lt' and stats.st_size >= fsize): continue
                    if self.date_filter:
                        dtype, ddate = self.date_filter
                        m_date = datetime.date.fromtimestamp(stats.st_mtime)
                        if dtype == 'modified' and m_date < ddate: continue

                    current_batch.append((file, file_path, stats.st_size, stats.st_mtime))
                    count += 1
                    if len(current_batch) >= self.batch_size:
                        self.batch_found.emit(current_batch)
                        current_batch = [] 
                except OSError: continue 

        if current_batch: self.batch_found.emit(current_batch)
        self.finished.emit(count, time.time() - start_time)

    def stop(self): self.running = False

class ActionWorker(QThread):
    progress = Signal(int, str) # Value, Status Message
    log_msg = Signal(str) # Detailed log signal
    finished = Signal(dict) # Returns summary stats

    def __init__(self, files, rules, default_action="copy"):
        super().__init__()
        self.files = files
        self.rules = rules
        self.default_action = default_action
        self.running = True

    def matches_rule(self, file_path, rule):
        fname = os.path.basename(file_path).lower()
        stats = os.stat(file_path)
        
        if rule.get("contains"):
            keywords = [k.strip().lower() for k in rule["contains"].split(',') if k.strip()]
            if keywords and not any(k in fname for k in keywords):
                return False
        
        if rule.get("extensions"):
            exts = [e.strip().lower() for e in rule["extensions"].split(',')]
            f_ext = os.path.splitext(fname)[1]
            if f_ext not in exts and f_ext.strip('.') not in exts: 
                return False
        
        size_mb = stats.st_size / (1024 * 1024)
        if rule.get("size_min") and size_mb < rule["size_min"]: return False
        if rule.get("size_max") and rule["size_max"] > 0 and size_mb > rule["size_max"]: return False
        
        if rule.get("date_after"):
            m_date = datetime.date.fromtimestamp(stats.st_mtime)
            rule_date = datetime.datetime.strptime(rule["date_after"], "%Y-%m-%d").date()
            if m_date <= rule_date: return False
        return True

    def get_size_tier(self, bytes_size):
        mb = bytes_size / (1024 * 1024)
        if mb < 1: return "Tiny"
        if mb < 10: return "Small"
        if mb < 100: return "Medium"
        if mb < 1024: return "Large"
        return "Huge"

    def run(self):
        total = len(self.files)
        results = {"success": 0, "skipped": 0, "errors": 0}
        self.log_msg.emit(f"STARTING OPERATION: {self.default_action.upper()} on {total} files.")
        
        for i, file_path in enumerate(self.files):
            if not self.running: break
            try:
                fname = os.path.basename(file_path)
                matched_rule = None
                
                # Rule Matching
                if self.rules:
                    for rule in self.rules:
                        if self.matches_rule(file_path, rule):
                            matched_rule = rule
                            break
                
                if self.rules and not matched_rule:
                    results["skipped"] += 1
                    self.log_msg.emit(f"SKIP: '{fname}' did not match any rule criteria.")
                    self.progress.emit(int((i / total) * 100), f"Skipped: {fname}")
                    continue
                
                dest_base = matched_rule["destination"] if matched_rule else None
                if dest_base:
                    dest_base = dest_base.strip().strip('"\'')
                    dest_base = os.path.normpath(dest_base)

                if not dest_base:
                    results["skipped"] += 1
                    self.log_msg.emit(f"SKIP: No destination folder defined for rule '{matched_rule['name']}'.")
                    continue

                pattern = matched_rule["pattern"] if matched_rule else ""
                prefix = matched_rule.get("prefix", "") if matched_rule else ""
                suffix = matched_rule.get("suffix", "") if matched_rule else ""
                
                stats = os.stat(file_path)
                dt_mod = datetime.datetime.fromtimestamp(stats.st_mtime)
                iso_week = dt_mod.isocalendar()[1]
                f_name, f_ext = os.path.splitext(os.path.basename(file_path))
                f_ext_clean = f_ext.lstrip('.')
                
                rel_path = pattern.replace("{Year}", str(dt_mod.year))\
                                  .replace("{Month}", f"{dt_mod.month:02d}")\
                                  .replace("{Day}", f"{dt_mod.day:02d}")\
                                  .replace("{Week}", f"{iso_week:02d}")\
                                  .replace("{Ext}", f_ext_clean)\
                                  .replace("{Name}", f_name)\
                                  .replace("{First_Letter}", f_name[0].upper() if f_name else "_")\
                                  .replace("{Size_Tier}", self.get_size_tier(stats.st_size))
                
                rel_path = rel_path.lstrip("/\\")
                path_parts = rel_path.replace("\\", "/").split("/")
                if path_parts:
                    path_parts[-1] = f"{prefix}{path_parts[-1]}{suffix}"
                    rel_path = os.path.join(*path_parts)

                # Final Normalize
                final_dir = os.path.normpath(os.path.join(dest_base, rel_path))
                final_path = os.path.join(final_dir, os.path.basename(file_path))
                
                self.log_msg.emit(f"ACTION: Dest dir='{final_dir}'")
                
                os.makedirs(final_dir, exist_ok=True)
                
                if self.default_action == "move":
                    shutil.move(file_path, final_path)
                    action_str = "Moved"
                else:
                    shutil.copy2(file_path, final_path)
                    action_str = "Copied"

                results["success"] += 1
                rule_name = matched_rule['name'] if matched_rule else 'Manual'
                self.progress.emit(int(((i + 1) / total) * 100), f"[{rule_name}] {action_str}: {fname}")
                self.log_msg.emit(f"SUCCESS: {action_str} '{fname}' to '{final_path}'")
                    
            except Exception as e:
                results["errors"] += 1
                self.log_msg.emit(f"ERROR: Failed to process '{file_path}'. Reason: {str(e)}")
        
        self.progress.emit(100, "Done.")
        self.finished.emit(results)

    def stop(self): self.running = False


# --- MAIN APPLICATION ---
class FileManagerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dracula File Manager Pro")
        
        # Default Settings
        self.batch_size = 100
        self.resize(1300, 850)
        self.auto_select_all = False 
        
        # Theme
        self.theme = DEFAULT_THEME.copy()
        self.update_stylesheet()

        # Data
        self.found_files = [] 
        self.organizer_files = [] 
        self.organizer_presets = {}
        self.load_presets()
        self.load_settings()

        # Threading
        self.search_thread = None
        self.org_search_thread = None
        self.action_thread = None
        self.thumb_worker = ThumbnailWorker()
        self.thumb_worker.icon_ready.connect(self.update_grid_icon)
        self.thumb_worker.start()
        
        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self.start_search)

        self.org_search_timer = QTimer()
        self.org_search_timer.setSingleShot(True)
        self.org_search_timer.timeout.connect(self.start_organizer_search)
        
        self.icon_provider = QFileIconProvider()
        
        # Log Dialog
        self.log_dialog = LogDialog(self)
        
        self.setup_ui()

    def update_stylesheet(self):
        """Generates stylesheet from current theme dict"""
        t = self.theme
        style = f"""
        QMainWindow {{ background-color: {t['bg_main']}; color: {t['fg_text']}; }}
        QWidget {{ background-color: {t['bg_main']}; color: {t['fg_text']}; font-family: 'Segoe UI', sans-serif; font-size: 14px; }}
        
        /* Sidebar */
        QFrame#Sidebar {{ background-color: {t['bg_sec']}; border-right: 1px solid {t['input_bg']}; }}
        QPushButton#SidebarBtn {{
            background-color: transparent; border: none; text-align: left; padding: 15px; color: {t['fg_text']}; font-weight: bold;
        }}
        QPushButton#SidebarBtn:hover {{ background-color: {t['input_bg']}; border-left: 4px solid {t['accent']}; }}
        QPushButton#SidebarBtn:checked {{ background-color: {t['input_bg']}; border-left: 4px solid {t['highlight']}; }}

        /* Inputs */
        QLineEdit, QComboBox, QDateEdit, QSpinBox, QTableWidget, QTextEdit, QListWidget {{
            background-color: {t['input_bg']}; border: 1px solid {t['border']}; border-radius: 5px; padding: 5px; color: {t['fg_text']};
        }}
        QLineEdit:focus, QSpinBox:focus, QTextEdit:focus, QListWidget:focus {{ border: 1px solid {t['accent']}; }}

        /* Dialogs */
        QDialog {{ background-color: {t['bg_main']}; }}

        /* Trees and Tables */
        QTreeWidget, QTableWidget, QListWidget {{
            background-color: {t['bg_main']}; border: 1px solid {t['input_bg']}; alternate-background-color: {t['bg_sec']};
        }}
        QHeaderView::section {{
            background-color: {t['bg_sec']}; color: {t['accent']}; padding: 5px; border: none; font-weight: bold;
        }}
        QTreeWidget::item:selected, QTableWidget::item:selected, QListWidget::item:selected {{ background-color: {t['input_bg']}; color: {t['highlight']}; }}

        /* Buttons */
        QPushButton#ActionBtn {{
            background-color: {t['accent']}; color: {t['bg_main']}; border-radius: 5px; padding: 8px 15px; font-weight: bold;
        }}
        QPushButton#ActionBtn:hover {{ background-color: {t['highlight']}; }}
        QPushButton#BrowseBtn, QPushButton#SaveBtn, QPushButton#TableBtn {{ 
            background-color: {t['border']}; border-radius: 5px; padding: 5px; 
        }}
        
        /* Group Box */
        QGroupBox {{ border: 1px solid {t['border']}; margin-top: 20px; border-radius: 5px; font-weight: bold; }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 5px; color: {t['accent']}; }}
        """
        self.setStyleSheet(style)

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # --- SIDEBAR ---
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(200)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 20, 0, 20)
        
        self.btn_home = QPushButton(" Search Files")
        self.btn_home.setIcon(QIcon.fromTheme("system-search"))
        self.btn_home.setObjectName("SidebarBtn")
        self.btn_home.setCheckable(True)
        self.btn_home.setChecked(True)
        self.btn_home.clicked.connect(lambda: self.switch_page(0))
        
        self.btn_organize = QPushButton(" Smart Organize")
        self.btn_organize.setIcon(QIcon.fromTheme("folder-new"))
        self.btn_organize.setObjectName("SidebarBtn")
        self.btn_organize.setCheckable(True)
        self.btn_organize.clicked.connect(lambda: self.switch_page(1))
        
        self.btn_settings = QPushButton(" Settings")
        self.btn_settings.setIcon(QIcon.fromTheme("preferences-system"))
        self.btn_settings.setObjectName("SidebarBtn")
        self.btn_settings.setCheckable(True)
        self.btn_settings.clicked.connect(lambda: self.switch_page(2))
        
        btn_exit = QPushButton(" Exit")
        btn_exit.setObjectName("SidebarBtn")
        btn_exit.clicked.connect(self.close)
        
        sidebar_layout.addWidget(self.btn_home)
        sidebar_layout.addWidget(self.btn_organize)
        sidebar_layout.addWidget(self.btn_settings)
        sidebar_layout.addStretch()
        sidebar_layout.addWidget(btn_exit)
        
        # --- STACKED PAGES ---
        self.stack = QStackedWidget()
        
        self.page_search = QWidget()
        self.setup_search_ui(self.page_search)
        self.stack.addWidget(self.page_search)
        
        self.page_organize = QWidget()
        self.setup_organize_ui(self.page_organize)
        self.stack.addWidget(self.page_organize)
        
        self.page_settings = QWidget()
        self.setup_settings_ui(self.page_settings)
        self.stack.addWidget(self.page_settings)
        
        main_layout.addWidget(sidebar)
        main_layout.addWidget(self.stack)

        # --- STATUS BAR ---
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        self.status_widget = QWidget()
        self.status_layout = QHBoxLayout(self.status_widget)
        self.status_layout.setContentsMargins(0, 0, 0, 0)
        
        self.status_label = QLabel("Ready.")
        self.status_label.setStyleSheet("padding-left: 10px; font-weight: bold;")
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(200)
        self.progress_bar.setVisible(False)
        
        self.btn_show_log = QPushButton("Show Log")
        self.btn_show_log.setFixedWidth(80)
        self.btn_show_log.clicked.connect(self.log_dialog.show)
        
        self.btn_cancel = QPushButton("Stop")
        self.btn_cancel.setFixedWidth(60)
        self.btn_cancel.setStyleSheet("background-color: #ff5555; color: white; border-radius: 3px;")
        self.btn_cancel.setVisible(False)
        self.btn_cancel.clicked.connect(self.stop_operations)
        
        self.status_layout.addWidget(self.status_label)
        self.status_layout.addStretch()
        self.status_layout.addWidget(self.progress_bar)
        self.status_layout.addWidget(self.btn_show_log)
        self.status_layout.addWidget(self.btn_cancel)
        
        self.status_bar.addWidget(self.status_widget, 1)

    # ==========================
    # PAGE 1: SEARCH DASHBOARD
    # ==========================
    def setup_search_ui(self, parent):
        layout = QVBoxLayout(parent)
        
        # 1. Filter Area
        filter_frame = QFrame()
        filter_layout = QVBoxLayout(filter_frame)

        # Directory
        dir_layout = QHBoxLayout()
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("Select root directory...")
        self.path_input.textChanged.connect(self.schedule_search)
        browse_btn = QPushButton("Browse")
        browse_btn.setObjectName("BrowseBtn")
        browse_btn.clicked.connect(lambda: self.browse_directory(self.path_input))
        self.recursive_chk = QCheckBox("Include Subfolders")
        self.recursive_chk.stateChanged.connect(self.schedule_search)

        dir_layout.addWidget(self.path_input)
        dir_layout.addWidget(browse_btn)
        dir_layout.addWidget(self.recursive_chk)
        filter_layout.addLayout(dir_layout)

        # Keywords
        key_layout = QHBoxLayout()
        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("Keywords (comma separated)...")
        self.keyword_input.textChanged.connect(self.schedule_search)
        self.ext_input = QLineEdit()
        self.ext_input.setPlaceholderText("Extensions (e.g. .py, .txt)...")
        self.ext_input.textChanged.connect(self.schedule_search)
        key_layout.addWidget(self.keyword_input)
        key_layout.addWidget(self.ext_input)
        filter_layout.addLayout(key_layout)

        # Advanced Filters
        adv_layout = QHBoxLayout()
        self.size_type = QComboBox()
        self.size_type.addItems(["Any Size", "Larger Than (MB)", "Smaller Than (MB)"])
        self.size_val = QLineEdit()
        self.size_val.setFixedWidth(80)
        self.date_type = QComboBox()
        self.date_type.addItems(["Any Date", "Modified After"])
        self.date_picker = QDateEdit()
        self.date_picker.setCalendarPopup(True)
        self.date_picker.setDate(datetime.date.today())

        adv_layout.addWidget(QLabel("Size:"))
        adv_layout.addWidget(self.size_type)
        adv_layout.addWidget(self.size_val)
        adv_layout.addWidget(QLabel("Date:"))
        adv_layout.addWidget(self.date_type)
        adv_layout.addWidget(self.date_picker)
        adv_layout.addStretch()
        
        # View Toggle
        self.btn_view_toggle = QPushButton(" Switch to Grid View")
        self.btn_view_toggle.setCheckable(True)
        self.btn_view_toggle.setObjectName("ActionBtn")
        self.btn_view_toggle.clicked.connect(self.toggle_view_mode)
        adv_layout.addWidget(self.btn_view_toggle)
        
        self.size_type.currentTextChanged.connect(self.schedule_search)
        self.size_val.textChanged.connect(self.schedule_search)
        self.date_type.currentTextChanged.connect(self.schedule_search)
        self.date_picker.dateChanged.connect(self.schedule_search)
        filter_layout.addLayout(adv_layout)

        # 2. Results (Stacked: List or Grid)
        self.results_stack = QStackedWidget()
        
        # View 1: Tree (List)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "Path", "Size", "Date", "Type"])
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.tree.setAlternatingRowColors(True)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.itemDoubleClicked.connect(self.on_tree_double_click)
        self.results_stack.addWidget(self.tree)
        
        # View 2: Grid (Thumbnails)
        self.grid = QListWidget()
        self.grid.setViewMode(QListWidget.IconMode)
        self.grid.setIconSize(QSize(120, 120))
        self.grid.setResizeMode(QListWidget.Adjust)
        self.grid.setSpacing(10)
        self.grid.setSelectionMode(QListWidget.ExtendedSelection)
        self.grid.itemDoubleClicked.connect(self.on_grid_double_click)
        self.results_stack.addWidget(self.grid)
        
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(filter_frame)
        splitter.addWidget(self.results_stack)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

        # 3. Actions
        act_layout = QHBoxLayout()
        btn_copy = QPushButton("Copy To...")
        btn_copy.setObjectName("ActionBtn")
        btn_copy.clicked.connect(self.action_copy)
        act_layout.addWidget(btn_copy)

        for name, func in [("Rename", self.action_rename), ("Move", self.action_move),
                           ("Zip", self.action_compress), ("Unzip", self.action_decompress)]:
            btn = QPushButton(name)
            btn.setObjectName("ActionBtn")
            btn.clicked.connect(func)
            act_layout.addWidget(btn)
        
        act_layout.addStretch()
        btn_del = QPushButton("Delete")
        btn_del.setObjectName("ActionBtn")
        btn_del.setStyleSheet("background-color: #ff5555; color: white;")
        btn_del.clicked.connect(self.action_delete)
        act_layout.addWidget(btn_del)
        layout.addLayout(act_layout)

    # ==========================
    # PAGE 2: SMART ORGANIZER
    # ==========================
    def setup_organize_ui(self, parent):
        layout = QHBoxLayout(parent)
        
        # --- LEFT SIDE: LIVE VIEW (SEARCH REPLICATED) ---
        left_frame = QFrame()
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(0,0,5,0)
        
        # Live Filters
        gb_live = QGroupBox("1. Filter Source Files (Live View)")
        f_layout = QVBoxLayout()
        
        # Path
        h_path = QHBoxLayout()
        self.org_path_input = QLineEdit()
        self.org_path_input.setPlaceholderText("Select Root Folder...")
        self.org_path_input.textChanged.connect(self.schedule_organizer_search)
        btn_org_browse = QPushButton("...")
        btn_org_browse.setObjectName("BrowseBtn")
        btn_org_browse.clicked.connect(lambda: self.browse_directory(self.org_path_input))
        h_path.addWidget(self.org_path_input)
        h_path.addWidget(btn_org_browse)
        
        # Criteria
        self.org_keyword = QLineEdit()
        self.org_keyword.setPlaceholderText("Name contains...")
        self.org_keyword.textChanged.connect(self.schedule_organizer_search)
        
        self.org_ext = QLineEdit()
        self.org_ext.setPlaceholderText("Extensions (.jpg, .png)...")
        self.org_ext.textChanged.connect(self.schedule_organizer_search)
        
        # Date
        h_date = QHBoxLayout()
        self.org_date_chk = QCheckBox("Modified After:")
        self.org_date_chk.stateChanged.connect(self.schedule_organizer_search)
        self.org_date = QDateEdit(QDate.currentDate())
        self.org_date.setCalendarPopup(True)
        self.org_date.dateChanged.connect(self.schedule_organizer_search)
        h_date.addWidget(self.org_date_chk)
        h_date.addWidget(self.org_date)
        
        f_layout.addLayout(h_path)
        f_layout.addWidget(self.org_keyword)
        f_layout.addWidget(self.org_ext)
        f_layout.addLayout(h_date)
        gb_live.setLayout(f_layout)
        
        # Tree
        self.org_tree = QTreeWidget()
        self.org_tree.setHeaderLabels(["File Name", "Size", "Date"])
        self.org_tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.org_tree.setAlternatingRowColors(True)
        
        left_layout.addWidget(gb_live)
        left_layout.addWidget(QLabel("Matching Files Preview:"))
        left_layout.addWidget(self.org_tree)
        
        # --- RIGHT SIDE: RULES & EXECUTION ---
        right_frame = QFrame()
        right_layout = QVBoxLayout(right_frame)
        
        # Presets
        gb_presets = QGroupBox("2. Rules & Profiles")
        preset_layout = QVBoxLayout()
        
        h_preset = QHBoxLayout()
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("Select a Profile...")
        self.preset_combo.addItems(self.organizer_presets.keys())
        self.preset_combo.currentTextChanged.connect(self.load_selected_preset)
        
        btn_save_p = QPushButton("Save")
        btn_save_p.clicked.connect(self.save_current_preset)
        btn_del_p = QPushButton("Del")
        btn_del_p.clicked.connect(self.delete_preset)
        h_preset.addWidget(self.preset_combo)
        h_preset.addWidget(btn_save_p)
        h_preset.addWidget(btn_del_p)
        
        preset_layout.addLayout(h_preset)
        
        # Rule Table
        self.rule_table = QTableWidget(0, 2)
        self.rule_table.setHorizontalHeaderLabels(["Rule Name", "Target Pattern"])
        self.rule_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.rule_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.rule_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.rule_table.doubleClicked.connect(self.edit_rule)
        self.rule_table.itemClicked.connect(self.preview_rule)
        
        btn_add_from_filter = QPushButton(" Create Rule from Filters")
        btn_add_from_filter.setObjectName("ActionBtn")
        btn_add_from_filter.setIcon(QIcon.fromTheme("list-add"))
        btn_add_from_filter.clicked.connect(self.add_rule_from_filters)
        
        btn_edit = QPushButton("Edit Rule")
        btn_edit.clicked.connect(self.edit_rule)
        btn_rem = QPushButton("Remove Rule")
        btn_rem.clicked.connect(self.remove_rule)
        
        h_btns = QHBoxLayout()
        h_btns.addWidget(btn_edit)
        h_btns.addWidget(btn_rem)
        
        preset_layout.addWidget(self.rule_table)
        preset_layout.addWidget(btn_add_from_filter)
        preset_layout.addLayout(h_btns)
        gb_presets.setLayout(preset_layout)
        
        # Execution
        gb_exec = QGroupBox("3. Execute")
        exec_layout = QVBoxLayout()
        
        self.org_source_mode = QComboBox()
        self.org_source_mode.addItems(["Process All Files in Preview", "Process Selected Files Only"])
        
        self.org_action_mode = QComboBox()
        self.org_action_mode.addItems(["Copy Files", "Move Files"])
        
        btn_run = QPushButton("START SORTING")
        btn_run.setObjectName("ActionBtn")
        btn_run.setStyleSheet("background-color: #50fa7b; color: #282a36; font-weight: bold; padding: 15px;")
        btn_run.clicked.connect(self.run_organizer)
        
        exec_layout.addWidget(QLabel("Source:"))
        exec_layout.addWidget(self.org_source_mode)
        exec_layout.addWidget(QLabel("Action:"))
        exec_layout.addWidget(self.org_action_mode)
        exec_layout.addWidget(btn_run)
        gb_exec.setLayout(exec_layout)
        
        right_layout.addWidget(gb_presets)
        right_layout.addWidget(gb_exec)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_frame)
        splitter.addWidget(right_frame)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

    # ==========================
    # SETTINGS & UTILS
    # ==========================
    def setup_settings_ui(self, parent):
        layout = QVBoxLayout(parent)
        
        # Performance
        perf_group = QGroupBox("Performance")
        perf_layout = QFormLayout()
        self.batch_spin = QSpinBox()
        self.batch_spin.setRange(1, 5000)
        self.batch_spin.setValue(self.batch_size)
        perf_layout.addRow("Search Batch Size:", self.batch_spin)
        perf_group.setLayout(perf_layout)
        
        # Personalization
        theme_group = QGroupBox("Personalization")
        theme_layout = QVBoxLayout()
        
        grid_l = QHBoxLayout()
        btn_bg = QPushButton("Main Background")
        btn_bg.clicked.connect(lambda: self.pick_color("bg_main"))
        btn_acc = QPushButton("Accent Color")
        btn_acc.clicked.connect(lambda: self.pick_color("accent"))
        btn_fg = QPushButton("Text Color")
        btn_fg.clicked.connect(lambda: self.pick_color("fg_text"))
        
        grid_l.addWidget(btn_bg)
        grid_l.addWidget(btn_acc)
        grid_l.addWidget(btn_fg)
        
        btn_reset_theme = QPushButton("Reset Theme")
        btn_reset_theme.clicked.connect(self.reset_theme)
        
        theme_layout.addLayout(grid_l)
        theme_layout.addWidget(btn_reset_theme)
        theme_group.setLayout(theme_layout)
        
        save_btn = QPushButton("Save All Preferences")
        save_btn.setObjectName("ActionBtn")
        save_btn.clicked.connect(self.save_global_settings)
        
        layout.addWidget(perf_group)
        layout.addWidget(theme_group)
        layout.addWidget(save_btn)
        layout.addStretch()

    def pick_color(self, key):
        c = QColorDialog.getColor(QColor(self.theme[key]), self, f"Select {key}")
        if c.isValid():
            self.theme[key] = c.name()
            self.update_stylesheet()

    def reset_theme(self):
        self.theme = DEFAULT_THEME.copy()
        self.update_stylesheet()

    def switch_page(self, index):
        self.stack.setCurrentIndex(index)
        self.btn_home.setChecked(index == 0)
        self.btn_organize.setChecked(index == 1)
        self.btn_settings.setChecked(index == 2)

    def load_presets(self):
        if os.path.exists(PRESETS_FILE):
            try:
                with open(PRESETS_FILE, 'r') as f:
                    self.organizer_presets = json.load(f)
            except: self.organizer_presets = {}

    def save_presets_to_file(self):
        with open(PRESETS_FILE, 'w') as f:
            json.dump(self.organizer_presets, f, indent=4)
    
    def load_settings(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r') as f:
                    data = json.load(f)
                    self.batch_size = data.get("batch_size", 100)
                    self.theme.update(data.get("theme", {}))
                    self.update_stylesheet()
            except: pass

    def save_global_settings(self):
        self.batch_size = self.batch_spin.value()
        data = {"batch_size": self.batch_size, "theme": self.theme}
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(data, f, indent=4)
        QMessageBox.information(self, "Saved", "Settings updated.")

    def stop_operations(self):
        if self.search_thread and self.search_thread.isRunning(): self.search_thread.stop()
        if self.org_search_thread and self.org_search_thread.isRunning(): self.org_search_thread.stop()
        if self.action_thread and self.action_thread.isRunning(): self.action_thread.stop()
        self.status_label.setText("Stopped by user.")
        self.progress_bar.setVisible(False)
        self.btn_cancel.setVisible(False)
        self.log_dialog.log("User stopped operations manually.")

    def browse_directory(self, input_field):
        d = QFileDialog.getExistingDirectory(self, "Select Directory")
        if d: input_field.setText(d)

    # ==========================
    # LOGIC: SEARCH & VIEW
    # ==========================
    def toggle_view_mode(self):
        is_grid = self.btn_view_toggle.isChecked()
        self.results_stack.setCurrentIndex(1 if is_grid else 0)
        self.btn_view_toggle.setText(" Switch to List View" if is_grid else " Switch to Grid View")

    def schedule_search(self): self.search_timer.start(500)

    def start_search(self):
        root = self.path_input.text().strip()
        if not root or not os.path.isdir(root): return
        if self.search_thread and self.search_thread.isRunning(): self.search_thread.stop()

        self.tree.clear()
        self.grid.clear()
        self.found_files = [] 
        self.status_label.setText(f"Searching {root}...")
        self.progress_bar.setVisible(True)
        self.btn_cancel.setVisible(True)
        
        keywords = [k.strip() for k in self.keyword_input.text().split(',') if k.strip()]
        exts = [e.strip() if e.strip().startswith('.') else f'.{e.strip()}' 
                for e in self.ext_input.text().split(',') if e.strip()]
        
        s_idx = self.size_type.currentIndex()
        s_val = int(self.size_val.text()) * 1048576 if (s_idx > 0 and self.size_val.text().isdigit()) else None
        size_filter = ('gt' if s_idx == 1 else 'lt', s_val) if s_val else None
        
        d_idx = self.date_type.currentIndex()
        date_filter = ('modified', self.date_picker.date().toPython()) if d_idx > 0 else None

        self.search_thread = SearchWorker(root, self.recursive_chk.isChecked(), keywords, exts, 
                                          size_filter, date_filter, self.batch_size)
        self.search_thread.batch_found.connect(self.add_batch_to_views)
        self.search_thread.finished.connect(lambda c, d: self.finish_search(c, d, self.tree))
        self.search_thread.start()

    def add_batch_to_views(self, batch_list):
        self.tree.setUpdatesEnabled(False)
        # self.grid.setUpdatesEnabled(False) # Keep enabled for smoother partial loading
        
        tree_items = []
        
        for name, path, size, timestamp in batch_list:
            self.found_files.append(path)
            
            # 1. Tree Item
            t_item = QTreeWidgetItem()
            t_item.setText(0, name)
            t_item.setText(1, path)
            t_item.setText(2, f"{size / 1024:.2f} KB")
            t_item.setText(3, datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M"))
            t_item.setText(4, os.path.splitext(name)[1])
            t_item.setIcon(0, self.icon_provider.icon(QFileInfo(path)))
            tree_items.append(t_item)
            
            # 2. Grid Item
            g_item = QListWidgetItem(name)
            g_item.setToolTip(path)
            g_item.setData(Qt.UserRole, path)
            # Set default icon initially, ThumbnailWorker will update it later
            g_item.setIcon(self.icon_provider.icon(QFileInfo(path)))
            self.grid.addItem(g_item)
            
            # Queue for custom thumbnail generation
            ext = os.path.splitext(name)[1].lower()
            if ext in ['.jpg', '.jpeg', '.png', '.bmp', '.mp4', '.mkv', '.avi', '.mov']:
                self.thumb_worker.add_to_queue(path)

        self.tree.addTopLevelItems(tree_items)
        self.tree.setUpdatesEnabled(True)

    def update_grid_icon(self, path, icon):
        # Find items with this path and update icon
        # This can be slow if list is huge, but safe for reasonable batches
        for i in range(self.grid.count()):
            item = self.grid.item(i)
            if item.data(Qt.UserRole) == path:
                item.setIcon(icon)
                return

    def finish_search(self, count, duration, tree_widget):
        self.progress_bar.setVisible(False)
        self.btn_cancel.setVisible(False)
        self.status_label.setText(f"Found {count} files in {duration:.2f}s")

    # ==========================
    # LOGIC: INTERACTIONS
    # ==========================
    def on_tree_double_click(self, item, column):
        path = item.text(1)
        self.smart_open_file(path)

    def on_grid_double_click(self, item):
        path = item.data(Qt.UserRole)
        self.smart_open_file(path)

    def smart_open_file(self, path):
        if not os.path.exists(path): return
        
        # Check if media
        ext = os.path.splitext(path)[1].lower()
        is_media = ext in ['.jpg', '.jpeg', '.png', '.gif', '.mp4', '.mkv', '.avi', '.mov', '.mp3', '.wav']
        
        if is_media:
            # Launch file
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        else:
            # Open location
            folder = os.path.dirname(path)
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def get_selected_files(self): 
        if self.results_stack.currentIndex() == 0:
            return [i.text(1) for i in self.tree.selectedItems()]
        else:
            return [i.data(Qt.UserRole) for i in self.grid.selectedItems()]

    # ==========================
    # LOGIC: ORGANIZER LIVE VIEW
    # ==========================
    def schedule_organizer_search(self): 
        self.auto_select_all = False
        self.org_search_timer.start(500)

    def start_organizer_search(self):
        root = self.org_path_input.text().strip()
        if not root or not os.path.isdir(root): return
        if self.org_search_thread and self.org_search_thread.isRunning(): self.org_search_thread.stop()

        self.org_tree.clear()
        self.organizer_files = []
        self.status_label.setText(f"Previewing {root}...")
        
        keywords = [k.strip() for k in self.org_keyword.text().split(',') if k.strip()]
        exts = [e.strip() if e.strip().startswith('.') else f'.{e.strip()}' 
                for e in self.org_ext.text().split(',') if e.strip()]
        date_filter = ('modified', self.org_date.date().toPython()) if self.org_date_chk.isChecked() else None

        self.org_search_thread = SearchWorker(root, True, keywords, exts, None, date_filter, self.batch_size)
        self.org_search_thread.batch_found.connect(self.add_batch_to_org_tree)
        self.org_search_thread.finished.connect(self.organizer_search_finished)
        self.org_search_thread.start()

    def add_batch_to_org_tree(self, batch_list):
        self.org_tree.setUpdatesEnabled(False)
        items = []
        for name, path, size, timestamp in batch_list:
            self.organizer_files.append(path)
            item = QTreeWidgetItem()
            item.setText(0, name)
            item.setText(1, f"{size / 1024:.2f} KB")
            item.setText(2, datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d"))
            item.setIcon(0, self.icon_provider.icon(QFileInfo(path)))
            item.setData(0, Qt.UserRole, path)
            items.append(item)
        self.org_tree.addTopLevelItems(items)
        self.org_tree.setUpdatesEnabled(True)

    def organizer_search_finished(self, count, duration):
        self.progress_bar.setVisible(False)
        self.status_label.setText(f"Preview: {count} files found.")
        if self.auto_select_all:
            self.org_tree.selectAll()
            self.auto_select_all = False

    # ==========================
    # LOGIC: ORGANIZER RULES
    # ==========================
    def preview_rule(self, item):
        rule = self.rule_table.item(item.row(), 0).data(Qt.UserRole)
        
        self.org_keyword.blockSignals(True)
        self.org_ext.blockSignals(True)
        self.org_date_chk.blockSignals(True)
        self.org_date.blockSignals(True)

        self.org_keyword.setText(rule.get("contains", ""))
        self.org_ext.setText(rule.get("extensions", ""))
        
        if rule.get("date_after"):
            self.org_date_chk.setChecked(True)
            self.org_date.setDate(QDate.fromString(rule["date_after"], "yyyy-MM-dd"))
        else:
            self.org_date_chk.setChecked(False)

        self.org_keyword.blockSignals(False)
        self.org_ext.blockSignals(False)
        self.org_date_chk.blockSignals(False)
        self.org_date.blockSignals(False)

        self.auto_select_all = True
        self.start_organizer_search()

    def add_rule_from_filters(self):
        data = {
            "name": "New Filter Rule",
            "contains": self.org_keyword.text(),
            "extensions": self.org_ext.text(),
            "date_after": self.org_date.date().toString("yyyy-MM-dd") if self.org_date_chk.isChecked() else None,
            "destination": "",
            "pattern": "{Year}/{Month}",
            "prefix": "",
            "suffix": ""
        }
        dlg = RuleEditDialog(self, data)
        if dlg.exec():
            self.insert_rule_row(dlg.get_data())

    def edit_rule(self):
        rows = self.rule_table.selectedItems()
        if not rows: return
        row = rows[0].row()
        current_data = self.rule_table.item(row, 0).data(Qt.UserRole)
        dlg = RuleEditDialog(self, current_data)
        if dlg.exec():
            self.update_rule_row(row, dlg.get_data())

    def insert_rule_row(self, data):
        row = self.rule_table.rowCount()
        self.rule_table.insertRow(row)
        self.update_rule_row(row, data)

    def update_rule_row(self, row, data):
        name_item = QTableWidgetItem(data['name'])
        name_item.setData(Qt.UserRole, data)
        self.rule_table.setItem(row, 0, name_item)
        pat = data.get('pattern', '')
        pre = data.get('prefix', '')
        suf = data.get('suffix', '')
        folder_display = f"[{pre}] {pat} [{suf}]"
        self.rule_table.setItem(row, 1, QTableWidgetItem(folder_display))

    def remove_rule(self):
        rows = set(i.row() for i in self.rule_table.selectedItems())
        for row in sorted(rows, reverse=True):
            self.rule_table.removeRow(row)

    def save_current_preset(self):
        name, ok = QInputDialog.getText(self, "Save Profile", "Profile Name:")
        if ok and name:
            rules = []
            for r in range(self.rule_table.rowCount()):
                rules.append(self.rule_table.item(r, 0).data(Qt.UserRole))
            self.organizer_presets[name] = rules
            self.save_presets_to_file()
            self.preset_combo.addItem(name)
            QMessageBox.information(self, "Success", f"Profile '{name}' saved.")

    def load_selected_preset(self, name):
        if name in self.organizer_presets:
            self.rule_table.setRowCount(0)
            for rule in self.organizer_presets[name]:
                self.insert_rule_row(rule)

    def delete_preset(self):
        name = self.preset_combo.currentText()
        if name in self.organizer_presets:
            del self.organizer_presets[name]
            self.save_presets_to_file()
            self.preset_combo.removeItem(self.preset_combo.currentIndex())

    def run_organizer(self):
        if self.org_source_mode.currentIndex() == 0:
            files_to_proc = self.organizer_files
        else:
            files_to_proc = [i.data(0, Qt.UserRole) for i in self.org_tree.selectedItems()]
            
        if not files_to_proc:
            QMessageBox.warning(self, "No Files", "No files found/selected in the preview.")
            return

        rules = []
        for r in range(self.rule_table.rowCount()):
            rules.append(self.rule_table.item(r, 0).data(Qt.UserRole))
            
        if not rules:
            QMessageBox.warning(self, "No Rules", "Add at least one rule to define destination.")
            return

        action = "move" if self.org_action_mode.currentIndex() == 1 else "copy"
        
        # Log Reset
        self.log_dialog.clear()
        self.log_dialog.log(f"Starting Batch for {len(files_to_proc)} files.")
        self.log_dialog.show()
        
        self.progress_bar.setVisible(True)
        self.btn_cancel.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        
        self.action_thread = ActionWorker(files_to_proc, rules, action)
        self.action_thread.progress.connect(lambda v, m: (self.progress_bar.setValue(v), self.status_label.setText(m)))
        self.action_thread.log_msg.connect(self.log_dialog.log) 
        self.action_thread.finished.connect(self.action_finished)
        self.action_thread.start()

    def action_finished(self, results):
        self.progress_bar.setVisible(False)
        self.btn_cancel.setVisible(False)
        
        self.log_dialog.log("--------------------------------")
        self.log_dialog.log(f"BATCH COMPLETE.")
        self.log_dialog.log(f"Success: {results['success']}")
        self.log_dialog.log(f"Skipped: {results['skipped']}")
        self.log_dialog.log(f"Errors: {results['errors']}")
        
        msg = f"Done.\nSuccess: {results['success']}\nSkipped: {results['skipped']}\nErrors: {results['errors']}\n\nCheck log for details."
        QMessageBox.information(self, "Report", msg)
        self.start_organizer_search()

    # ==========================
    # LOGIC: BASIC ACTIONS
    # ==========================
    def action_copy(self):
        files = self.get_selected_files()
        if not files: return
        dest = QFileDialog.getExistingDirectory(self, "Copy To")
        if dest:
            self.run_manual_action(files, dest, "copy")

    def action_move(self):
        files = self.get_selected_files()
        if not files: return
        dest = QFileDialog.getExistingDirectory(self, "Move To")
        if dest:
            self.run_manual_action(files, dest, "move")

    def run_manual_action(self, files, dest, mode):
        rule = {"name": "Manual", "destination": dest, "pattern": "", "contains": "", "extensions": ""}
        
        self.log_dialog.clear()
        self.log_dialog.show()
        self.progress_bar.setVisible(True)
        
        self.action_thread = ActionWorker(files, [rule], mode)
        self.action_thread.progress.connect(lambda v, m: self.progress_bar.setValue(v))
        self.action_thread.log_msg.connect(self.log_dialog.log)
        self.action_thread.finished.connect(lambda r: (self.progress_bar.setVisible(False), self.status_label.setText("Done.")))
        self.action_thread.start()

    def action_rename(self):
        files = self.get_selected_files()
        if not files: return
        text, ok = QInputDialog.getText(self, "Rename", "Append suffix:")
        if ok and text:
            for f in files:
                try: os.rename(f, f"{os.path.splitext(f)[0]}_{text}{os.path.splitext(f)[1]}")
                except: pass
            self.start_search()

    def action_compress(self):
        files = self.get_selected_files()
        if not files: return
        dest, _ = QFileDialog.getSaveFileName(self, "Save Zip", "", "Zip (*.zip)")
        if dest:
            with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED) as z:
                for f in files: z.write(f, os.path.basename(f))
            self.status_label.setText("Compressed.")

    def action_decompress(self):
        files = self.get_selected_files()
        if not files: return
        dest = QFileDialog.getExistingDirectory(self, "Extract To")
        if dest:
            for f in files:
                if f.endswith('.zip'): 
                    try: 
                        with zipfile.ZipFile(f, 'r') as z: z.extractall(dest)
                    except: pass
            self.status_label.setText("Decompressed.")
            
    def action_delete(self):
        files = self.get_selected_files()
        if files and QMessageBox.question(self, "Delete", f"Delete {len(files)} files?", 
           QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            for f in files: 
                try: os.remove(f)
                except: pass
            self.start_search()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FileManagerApp()
    window.show()
    sys.exit(app.exec())