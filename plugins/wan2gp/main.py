import sys
import os
import threading
import time
import json
import tempfile
import shutil
import uuid
import inspect
from pathlib import Path
from contextlib import contextmanager
import ffmpeg

class MockComponent:
    def __init__(self, type_name="Generic", *args, **kwargs):
        self.type_name = type_name
        self.args = args
        self.kwargs = kwargs
        self.children = []
        self.id = str(uuid.uuid4())
        self.label = kwargs.get('label', None)
        self.value = kwargs.get('value', None)
        self.visible = kwargs.get('visible', True)
        self.choices = kwargs.get('choices', [])
        self.elem_id = kwargs.get('elem_id', None)
        self.minimum = kwargs.get('minimum', 0)
        self.maximum = kwargs.get('maximum', 100)
        self.step = kwargs.get('step', 1)
        self.interactive = kwargs.get('interactive', True)
        self.placeholder = kwargs.get('placeholder', None)
        self.props = kwargs

    def __enter__(self):
        if hasattr(sys.modules['gradio'], '_push_context'):
            sys.modules['gradio']._push_context(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if hasattr(sys.modules['gradio'], '_pop_context'):
            sys.modules['gradio']._pop_context()

    def __getattr__(self, name):
        def dummy_method(*args, **kwargs):
            return self
        return dummy_method

    def __repr__(self):
        return f"<MockComponent {self.type_name} id={self.id} label='{self.label}'>"

class MockEventData:
    def __init__(self, target=None, _data=None):
        self.target = target
        self._data = _data or {}

class MockSelectData:
    def __init__(self, index=0, value=None, selected=True):
        self.index = index
        self.value = value
        self.selected = selected

class MockProgress:
    def __init__(self, track_tqdm=False): pass
    def __call__(self, *args, **kwargs): pass
    def tqdm(self, iterator, *args, **kwargs): return iterator

class MockThemes:
    def Soft(self, *args, **kwargs): return None

class MockGradioModule:
    def __init__(self):
        self.context_stack = []
        self.root_components = []
        self.is_capturing = False

        self.EventData = MockEventData
        self.SelectData = MockSelectData
        self.Progress = MockProgress
        self.themes = MockThemes()

    def _push_context(self, component):
        if not self.is_capturing: return
        if self.context_stack:
            self.context_stack[-1].children.append(component)
        else:
            self.root_components.append(component)
        self.context_stack.append(component)

    def _pop_context(self):
        if not self.is_capturing: return
        if self.context_stack:
            self.context_stack.pop()

    def _register_component(self, component):
        if not self.is_capturing: return component
        if self.context_stack:
            self.context_stack[-1].children.append(component)
        return component

    def start_capture(self):
        self.context_stack = []
        self.root_components = []
        self.is_capturing = True

    def stop_capture(self):
        self.is_capturing = False
        return self.root_components

    def Column(self, *args, **kwargs): return MockComponent("Column", *args, **kwargs)
    def Row(self, *args, **kwargs): return MockComponent("Row", *args, **kwargs)
    def Tabs(self, *args, **kwargs): return MockComponent("Tabs", *args, **kwargs)
    def Tab(self, *args, **kwargs): return MockComponent("Tab", *args, **kwargs)
    def Group(self, *args, **kwargs): return MockComponent("Group", *args, **kwargs)
    def Accordion(self, *args, **kwargs): return MockComponent("Accordion", *args, **kwargs)
    def Slider(self, *args, **kwargs): return self._register_component(MockComponent("Slider", *args, **kwargs))
    def Dropdown(self, *args, **kwargs): return self._register_component(MockComponent("Dropdown", *args, **kwargs))
    def Textbox(self, *args, **kwargs): return self._register_component(MockComponent("Textbox", *args, **kwargs))
    def Number(self, *args, **kwargs): return self._register_component(MockComponent("Number", *args, **kwargs))
    def Checkbox(self, *args, **kwargs): return self._register_component(MockComponent("Checkbox", *args, **kwargs))
    def Radio(self, *args, **kwargs): return self._register_component(MockComponent("Radio", *args, **kwargs))
    def Audio(self, *args, **kwargs): return self._register_component(MockComponent("Audio", *args, **kwargs))
    def File(self, *args, **kwargs): return self._register_component(MockComponent("File", *args, **kwargs))
    def Image(self, *args, **kwargs): return self._register_component(MockComponent("Image", *args, **kwargs))
    def Video(self, *args, **kwargs): return self._register_component(MockComponent("Video", *args, **kwargs))
    def HTML(self, *args, **kwargs): return self._register_component(MockComponent("HTML", *args, **kwargs))
    def Markdown(self, *args, **kwargs): return self._register_component(MockComponent("Markdown", *args, **kwargs))
    def Button(self, *args, **kwargs): return self._register_component(MockComponent("Button", *args, **kwargs))
    def DownloadButton(self, *args, **kwargs): return self._register_component(MockComponent("Button", *args, **kwargs))
    def UploadButton(self, *args, **kwargs): return self._register_component(MockComponent("Button", *args, **kwargs))
    def State(self, *args, **kwargs): return self._register_component(MockComponent("State", *args, **kwargs))
    def Gallery(self, *args, **kwargs): return self._register_component(MockComponent("Gallery", *args, **kwargs))
    def ImageEditor(self, *args, **kwargs): return self._register_component(MockComponent("Image", *args, **kwargs))
    def Text(self, *args, **kwargs): return self.Textbox(*args, **kwargs)
    def Files(self, *args, **kwargs): return self.File(*args, **kwargs) 
    def update(self, *args, **kwargs): return None
    def on(self, *args, **kwargs): return MockComponent("Dependency", *args, **kwargs)
    def Error(self, *args, **kwargs): raise Exception(f"Gradio Error: {args}")
    def Info(self, *args, **kwargs): print(f"Gradio Info: {args}")
    def Warning(self, *args, **kwargs): print(f"Gradio Warning: {args}")

class MockAdvancedMediaGallery:
    def __init__(self, *args, **kwargs):
        self.gallery = MockComponent("Gallery", label=kwargs.get("label", "Gallery"))
    def mount(self, *args, **kwargs): pass
    def get_toggable_elements(self): return []

class MockAudioGallery:
    def __init__(self, *args, **kwargs): pass
    def get_state(self):
        return [MockComponent("State", value=[]), MockComponent("State", value=-1), MockComponent("State", value=0)]
    @staticmethod
    def get_javascript(): return ""

class MockPluginModule: pass
class MockPluginManager:
    def __init__(self, *args, **kwargs): pass
    def discover_plugins(self, *args, **kwargs): return []
    def get_custom_js(self): return ""
    def run_component_insertion(self, *args, **kwargs): pass
class MockWAN2GPApplication:
    def __init__(self, *args, **kwargs): self.plugin_manager = MockPluginManager()
    def initialize_plugins(self, *args, **kwargs): pass
    def setup_ui_tabs(self, *args, **kwargs): pass
    def run_component_insertion(self, locals_dict): pass
class MockApp:
    def __init__(self):
        self.plugin_manager = MockPluginManager()
    def initialize_plugins(self, *args, **kwargs): pass
    def setup_ui_tabs(self, *args, **kwargs): pass
    def run_component_insertion(self, *args, **kwargs): pass

mock_gradio = MockGradioModule()
sys.modules['gradio'] = mock_gradio
sys.modules['gradio.gallery'] = mock_gradio
sys.modules['shared.gradio.gallery'] = mock_gallery = MockGradioModule()
mock_gallery.AdvancedMediaGallery = MockAdvancedMediaGallery

sys.modules['shared.gradio.audio_gallery'] = mock_audio_gallery = MockGradioModule()
mock_audio_gallery.AudioGallery = MockAudioGallery

mock_plugin_utils = MockPluginModule()
mock_plugin_utils.PluginManager = MockPluginManager
mock_plugin_utils.WAN2GPApplication = MockWAN2GPApplication
mock_plugin_utils.SYSTEM_PLUGINS = []
sys.modules['shared.utils.plugins'] = mock_plugin_utils

wgp = None
root_dir = Path(__file__).parent.parent.parent
wan2gp_dir = root_dir / 'WAN2GP'

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QPushButton, QLabel, QLineEdit, QTextEdit, QSlider, QCheckBox, QComboBox,
    QFileDialog, QGroupBox, QFormLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar, QScrollArea, QListWidget, QListWidgetItem,
    QMessageBox, QRadioButton, QSizePolicy, QMenu
)
from PyQt6.QtCore import Qt, QThread, QObject, pyqtSignal, QUrl, QSize, QRectF, QTimer
from PyQt6.QtGui import QPixmap, QImage, QDropEvent
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PIL.ImageQt import ImageQt

sys.path.append(str(Path(__file__).parent.parent.parent))
from plugins import VideoEditorPlugin

@contextmanager
def working_directory(path):
    old_cwd = os.getcwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(old_cwd)

class DynamicUiBuilder(QObject):
    def __init__(self, main_widget):
        super().__init__()
        self.main = main_widget
        self.widget_registry = {}
        self.id_to_name = {}

    def build_advanced_tab(self, model_type):
        mock_gradio.start_capture()

        old_advanced = wgp.advanced
        wgp.advanced = True
        
        ui_defaults = wgp.get_default_settings(model_type)
        mock_state = {
            "model_type": model_type,
            "advanced": True,
            "gen": {"queue": []},
            "loras_presets": [],
            "loras": [],
            "last_model_per_family": {},
            "last_model_per_type": {},
            "last_resolution_per_group": {}
        }
        
        try:
            with working_directory(wan2gp_dir):
                locals_dict = wgp.generate_video_tab(
                    update_form=False,
                    state_dict=mock_state,
                    ui_defaults=ui_defaults,
                    tab_id='generate',
                    model_family=MockComponent("Dropdown"),
                    model_base_type_choice=MockComponent("Dropdown"),
                    model_choice=MockComponent("Dropdown"),
                    header=MockComponent("Markdown"),
                    main=MockComponent("Blocks"),
                    main_tabs=MockComponent("Tabs")
                )

            self.id_to_name.clear()
            for name, obj in locals_dict.items():
                if isinstance(obj, MockComponent):
                    self.id_to_name[obj.id] = name

            def find_advanced_node(nodes):
                for node in nodes:
                    ref_name = self.id_to_name.get(node.id)

                    if ref_name == 'advanced_row' and node.type_name == 'Tabs':
                        return node

                    if node.type_name == 'Tabs':
                        labels = [c.args[0] if c.args else c.kwargs.get('label') for c in node.children if c.type_name=='Tab']
                        if "General" in labels and "Loras" in labels:
                            return node

                    res = find_advanced_node(node.children)
                    if res: return res
                return None

            root_components = mock_gradio.stop_capture()
            advanced_root_node = find_advanced_node(root_components)

            if not advanced_root_node:
                print("[DynamicUI] Could not locate Advanced Options root in wgp structure.")
                return None

            advanced_root_node.visible = True

            tabs_widget = QTabWidget()
            
            for tab_node in advanced_root_node.children:
                if tab_node.type_name != 'Tab': continue
                
                tab_name = tab_node.args[0] if tab_node.args else tab_node.kwargs.get('label', "Untitled")
                tab_page = QWidget()
                tab_layout = QVBoxLayout(tab_page)

                self._build_qt_layout(tab_node.children, tab_layout)
                
                tab_layout.addStretch()
                tabs_widget.addTab(tab_page, tab_name)
                
            return tabs_widget

        except Exception as e:
            print(f"[DynamicUI] Exception: {e}")
            import traceback
            traceback.print_exc()
            return None
        finally:
            wgp.advanced = old_advanced
            if mock_gradio.is_capturing: mock_gradio.stop_capture()

    def _build_qt_layout(self, nodes, parent_layout):
        for node in nodes:
            var_name = self.id_to_name.get(node.id)
            label = node.label or node.kwargs.get('label')
            if var_name in ['audio_source']: continue
            if node.type_name in ['Column', 'Row', 'Group']:
                container = QGroupBox(label) if label else QWidget()
                layout = QVBoxLayout(container) if node.type_name in ['Column', 'Group'] else QHBoxLayout(container)
                layout.setContentsMargins(0,0,0,0)
                if label: layout.setContentsMargins(5,15,5,5)
                self._build_qt_layout(node.children, layout)
                if not node.visible: container.hide()
                parent_layout.addWidget(container)
            
            elif node.type_name == 'Accordion':
                group = QGroupBox(label or "Options")
                group.setCheckable(True)
                group.setChecked(node.kwargs.get('open', False))
                layout = QVBoxLayout(group)
                self._build_qt_layout(node.children, layout)
                if not node.visible: group.hide()
                parent_layout.addWidget(group)

            elif node.type_name == 'Slider':
                if not var_name: continue
                
                min_val = node.minimum
                max_val = node.maximum
                step = node.step
                val = node.value if node.value is not None else min_val
                
                is_float = isinstance(step, float) or isinstance(min_val, float)
                scale = 100.0 if is_float else 1.0
                precision = 2 if is_float else 0
                if step < 0.01: scale = 1000.0; precision=3
                elif step < 0.1: scale = 100.0; precision=2
                elif step >= 1.0 and not is_float: scale = 1.0; precision=0

                container = self.main._create_slider_with_label_dynamic(
                    var_name, min_val, max_val, val, scale, precision, label or var_name
                )
                if not node.visible: container.hide()
                parent_layout.addWidget(container)

            elif node.type_name == 'Dropdown':
                if not var_name: continue
                combo = QComboBox()
                for choice in node.choices:
                    if isinstance(choice, (list, tuple)) and len(choice) == 2:
                        combo.addItem(str(choice[0]), choice[1])
                    else:
                        combo.addItem(str(choice), choice)
                
                val = node.value
                idx = combo.findData(val)
                if idx == -1: idx = combo.findText(str(val))
                if idx != -1: combo.setCurrentIndex(idx)
                
                self.main.dynamic_inputs_config[var_name] = {'type': 'dropdown', 'widget': combo}
                self.main.widgets[var_name] = combo
                
                cont = QWidget()
                l = QVBoxLayout(cont); l.setContentsMargins(0,0,0,0)
                l.addWidget(QLabel(label or var_name))
                l.addWidget(combo)
                if not node.visible: cont.hide()
                parent_layout.addWidget(cont)

            elif node.type_name == 'Checkbox':
                if not var_name: continue
                cb = QCheckBox(label or var_name)
                cb.setChecked(bool(node.value))
                self.main.dynamic_inputs_config[var_name] = {'type': 'checkbox', 'widget': cb}
                self.main.widgets[var_name] = cb
                if not node.visible: cb.hide()
                parent_layout.addWidget(cb)

            elif node.type_name in ['Textbox', 'Text']:
                if not var_name: continue
                is_multi = node.kwargs.get('lines', 1) > 1
                txt = QTextEdit() if is_multi else QLineEdit()
                if is_multi: txt.setMaximumHeight(80)
                
                val = str(node.value) if node.value is not None else ""
                if isinstance(txt, QLineEdit): txt.setText(val)
                else: txt.setPlainText(val)
                
                if 'placeholder' in node.kwargs:
                    txt.setPlaceholderText(node.kwargs['placeholder'])

                self.main.dynamic_inputs_config[var_name] = {'type': 'text', 'widget': txt}
                self.main.widgets[var_name] = txt
                
                cont = QWidget()
                l = QVBoxLayout(cont); l.setContentsMargins(0,0,0,0)
                l.addWidget(QLabel(label or var_name))
                l.addWidget(txt)
                if not node.visible: cont.hide()
                parent_layout.addWidget(cont)

            elif node.type_name in ['File', 'Audio', 'Image', 'Video']:
                if not var_name: continue
                container = self.main._create_file_input(var_name, label or var_name)
                if var_name in self.main.widgets:
                    self.main.dynamic_inputs_config[var_name] = {'type': 'file', 'widget': self.main.widgets[var_name]}
                if not node.visible: container.hide()
                parent_layout.addWidget(container)

            if node.type_name not in ['Row', 'Column', 'Group', 'Accordion', 'Tabs', 'Tab']:
                if node.children:
                    self._build_qt_layout(node.children, parent_layout)

class Wan2GPSetupWidget(QWidget):
    def __init__(self, plugin_instance, parent=None):
        super().__init__(parent)
        self.plugin = plugin_instance

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(15)

        info_label = QLabel(
            "<h2>AI Generator Setup Required</h2>"
            "<p>The 'Wan2GP' backend could not be found.</p>"
            "<p>Please choose an option below:</p>"
        )
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setWordWrap(True)

        self.install_button = QPushButton("Install Wan2GP Automatically (Recommended)")
        self.install_button.setToolTip("Clones the repository from GitHub and installs dependencies.\nRequires Git and an internet connection.")

        self.select_folder_button = QPushButton("Select Existing Wan2GP Folder...")
        self.select_folder_button.setToolTip("Point the plugin to a folder where you have already downloaded Wan2GP.")

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setWordWrap(True)

        layout.addStretch()
        layout.addWidget(info_label)
        layout.addWidget(self.install_button)
        layout.addWidget(self.select_folder_button)
        layout.addWidget(self.status_label)
        layout.addStretch()

        self.install_button.clicked.connect(self.plugin._handle_install)
        self.select_folder_button.clicked.connect(self.plugin._handle_select_folder)

    def show_message(self, text):
        self.status_label.setText(text)

    def set_buttons_enabled(self, enabled):
        self.install_button.setEnabled(enabled)
        self.select_folder_button.setEnabled(enabled)

class VideoResultItemWidget(QWidget):
    """A widget to display a generated video with a hover-to-play preview and insert button."""
    def __init__(self, video_path, plugin, parent=None):
        super().__init__(parent)
        self.video_path = video_path
        self.plugin = plugin
        self.app = plugin.app
        self.duration = 0.0
        self.has_audio = False

        self.setMinimumSize(200, 180)
        self.setMaximumHeight(190)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        self.media_player = QMediaPlayer()
        self.video_widget = QVideoWidget()
        self.video_widget.setFixedSize(160, 90)
        self.media_player.setVideoOutput(self.video_widget)
        self.media_player.setSource(QUrl.fromLocalFile(self.video_path))
        self.media_player.setLoops(QMediaPlayer.Loops.Infinite)
        
        self.info_label = QLabel(os.path.basename(video_path))
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_label.setWordWrap(True)

        self.insert_button = QPushButton("Insert into Timeline")
        self.insert_button.clicked.connect(self.on_insert)

        h_layout = QHBoxLayout()
        h_layout.addStretch()
        h_layout.addWidget(self.video_widget)
        h_layout.addStretch()
        
        layout.addLayout(h_layout)
        layout.addWidget(self.info_label)
        layout.addWidget(self.insert_button)
        self.probe_video()

    def probe_video(self):
        try:
            probe = ffmpeg.probe(self.video_path)
            self.duration = float(probe['format']['duration'])
            self.has_audio = any(s['codec_type'] == 'audio' for s in probe.get('streams', []))
            self.info_label.setText(f"{os.path.basename(self.video_path)}\n({self.duration:.2f}s)")
        except Exception as e:
            self.info_label.setText(f"Error probing:\n{os.path.basename(self.video_path)}")
            print(f"Error probing video {self.video_path}: {e}")
    
    def enterEvent(self, event):
        super().enterEvent(event)
        self.media_player.play()
        if not self.plugin.active_region or self.duration == 0: return
        start_ms, _ = self.plugin.active_region
        timeline = self.app.timeline_widget
        video_rect, audio_rect = None, None
        x = timeline.ms_to_x(start_ms)
        duration_ms = int(self.duration * 1000)
        w = int(duration_ms * timeline.pixels_per_ms)
        if self.plugin.insert_on_new_track:
            video_y = timeline.TIMESCALE_HEIGHT
            video_rect = QRectF(x, video_y, w, timeline.TRACK_HEIGHT)
            if self.has_audio:
                audio_y = timeline.audio_tracks_y_start + self.app.timeline.num_audio_tracks * timeline.TRACK_HEIGHT
                audio_rect = QRectF(x, audio_y, w, timeline.TRACK_HEIGHT)
        else:
            v_track_idx = 1
            visual_v_idx = self.app.timeline.num_video_tracks - v_track_idx
            video_y = timeline.video_tracks_y_start + visual_v_idx * timeline.TRACK_HEIGHT
            video_rect = QRectF(x, video_y, w, timeline.TRACK_HEIGHT)
            if self.has_audio:
                a_track_idx = 1
                visual_a_idx = a_track_idx - 1
                audio_y = timeline.audio_tracks_y_start + visual_a_idx * timeline.TRACK_HEIGHT
                audio_rect = QRectF(x, audio_y, w, timeline.TRACK_HEIGHT)
        timeline.set_hover_preview_rects(video_rect, audio_rect)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.media_player.pause()
        self.media_player.setPosition(0)
        self.app.timeline_widget.set_hover_preview_rects(None, None)
    
    def on_insert(self):
        self.media_player.stop()
        self.media_player.setSource(QUrl())
        self.media_player.setVideoOutput(None)
        self.app.timeline_widget.set_hover_preview_rects(None, None)
        self.plugin.insert_generated_clip(self.video_path)


class QueueTableWidget(QTableWidget):
    rowsMoved = pyqtSignal(int, int)
    rowsRemoved = pyqtSignal(list)
    clearAllRequested = pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(self.DragDropMode.InternalMove)
        self.setSelectionBehavior(self.SelectionBehavior.SelectRows)
        self.setSelectionMode(self.SelectionMode.ExtendedSelection)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            self.remove_selected_rows()
        else:
            super().keyPressEvent(event)

    def remove_selected_rows(self):
        selected_rows = self.selectionModel().selectedRows()
        if not selected_rows:
            return
        rows_to_remove = sorted([index.row() for index in selected_rows])
        self.rowsRemoved.emit(rows_to_remove)

    def show_context_menu(self, pos):
        menu = QMenu(self)
        selected_items = self.selectionModel().selectedRows()
        
        if selected_items:
            count = len(selected_items)
            remove_action_text = f"Remove {count} Selected Item{'s' if count > 1 else ''}"
            remove_action = menu.addAction(remove_action_text)
            remove_action.triggered.connect(self.remove_selected_rows)
            menu.addSeparator()

        clear_all_action = menu.addAction("Clear Queue")
        clear_all_action.triggered.connect(self.clearAllRequested)
        
        menu.exec(self.viewport().mapToGlobal(pos))

    def dropEvent(self, event: QDropEvent):
        if event.source() == self and event.dropAction() == Qt.DropAction.MoveAction:
            source_row = self.currentRow()
            target_item = self.itemAt(event.position().toPoint())
            dest_row = target_item.row() if target_item else self.rowCount()
            if source_row != dest_row: self.rowsMoved.emit(source_row, dest_row)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

class HoverVideoPreview(QWidget):
    def __init__(self, player, video_widget, parent=None):
        super().__init__(parent)
        self.player = player
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.addWidget(video_widget)
        self.setFixedSize(160, 90)
    
    def enterEvent(self, event):
        super().enterEvent(event)
        if self.player.source().isValid():
            self.player.play()
    
    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.player.pause()
        self.player.setPosition(0)

class Worker(QObject):
    progress = pyqtSignal(list)
    status = pyqtSignal(str)
    preview = pyqtSignal(object)
    output = pyqtSignal()
    finished = pyqtSignal()
    error = pyqtSignal(str)
    def __init__(self, plugin, state):
        super().__init__()
        self.plugin = plugin
        self.state = state
        self._is_running = True
        self._last_progress_phase = None
        self._last_preview = None

    def run(self):
        def generation_target():
            with working_directory(wan2gp_dir):
                try:
                    for _ in wgp.process_tasks(self.state):
                        if self._is_running: self.output.emit()
                        else: break
                except Exception as e:
                    import traceback
                    print("Error in generation thread:")
                    traceback.print_exc()
                    if "gradio.Error" in str(type(e)): self.error.emit(str(e))
                    else: self.error.emit(f"An unexpected error occurred: {e}")
                finally:
                    self._is_running = False
        gen_thread = threading.Thread(target=generation_target, daemon=True)
        gen_thread.start()
        while self._is_running:
            gen = self.state.get('gen', {})
            current_phase = gen.get("progress_phase")
            if current_phase and current_phase != self._last_progress_phase:
                self._last_progress_phase = current_phase
                phase_name, step = current_phase
                total_steps = gen.get("num_inference_steps", 1)
                high_level_status = gen.get("progress_status", "")
                status_msg = wgp.merge_status_context(high_level_status, phase_name)
                progress_args = [(step, total_steps), status_msg]
                self.progress.emit(progress_args)
            preview_img = gen.get('preview')
            if preview_img is not None and preview_img is not self._last_preview:
                self._last_preview = preview_img
                self.preview.emit(preview_img)
                gen['preview'] = None
            time.sleep(0.1)
        gen_thread.join()
        self.finished.emit()


class WgpDesktopPluginWidget(QWidget):
    def __init__(self, plugin):
        super().__init__()
        self.plugin = plugin
        self.widgets = {}
        self.state = {}
        self.worker = None
        self.thread = None
        self.lora_map = {}
        self.full_resolution_choices = []
        self.main_config = {}
        self.processed_files = set()
        self.dynamic_inputs_config = {}
        self.advanced_tabs_widget = None
        
        self.load_main_config()
        self.ui_builder = DynamicUiBuilder(self)
        self.setup_ui()
        self.apply_initial_config()
        self.connect_signals()
        self.init_wgp_state()

    def _get_queue_data_for_table(self, queue):
        data = []
        if len(queue) <= 1:
            return data

        for item in queue[1:]:
            repeats = item.get('repeats', "1")
            prompt = item.get('prompt', "")
            length = item.get('length', "")
            steps = item.get('steps', "")
            data.append([str(repeats), prompt, str(length), str(steps)])
        return data

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        self.header_info = QLabel("Header Info")
        main_layout.addWidget(self.header_info)
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        self.setup_generator_tab()
        self.setup_config_tab()

    def create_widget(self, widget_class, name, *args, **kwargs):
        widget = widget_class(*args, **kwargs)
        self.widgets[name] = widget
        return widget

    def _create_slider_with_label(self, name, min_val, max_val, initial_val, scale=1.0, precision=1):
        container = QWidget()
        hbox = QHBoxLayout(container)
        hbox.setContentsMargins(0, 0, 0, 0)
        slider = self.create_widget(QSlider, name, Qt.Orientation.Horizontal)
        slider.setRange(min_val, max_val)
        slider.setValue(int(initial_val * scale))
        
        value_edit = self.create_widget(QLineEdit, f"{name}_label", f"{initial_val:.{precision}f}")
        value_edit.setFixedWidth(60)
        value_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)

        def sync_slider_from_text():
            try:
                text_value = float(value_edit.text())
                slider_value = int(round(text_value * scale))
                
                slider.blockSignals(True)
                slider.setValue(slider_value)
                slider.blockSignals(False)

                actual_slider_value = slider.value()
                if actual_slider_value != slider_value:
                    value_edit.setText(f"{actual_slider_value / scale:.{precision}f}")
            except (ValueError, TypeError):
                value_edit.setText(f"{slider.value() / scale:.{precision}f}")

        def sync_text_from_slider(value):
            if not value_edit.hasFocus():
                value_edit.setText(f"{value / scale:.{precision}f}")

        value_edit.editingFinished.connect(sync_slider_from_text)
        slider.valueChanged.connect(sync_text_from_slider)

        hbox.addWidget(slider)
        hbox.addWidget(value_edit)
        return container

    def _create_slider_with_label_dynamic(self, name, min_val, max_val, initial_val, scale=1.0, precision=1, label_text=""):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0,0,0,0)
        
        label = QLabel(label_text)
        layout.addWidget(label)
        
        slider_container = self._create_slider_with_label(name, int(min_val*scale), int(max_val*scale), initial_val, scale, precision)
        
        self.widgets[name] = self.widgets[name]
        self.dynamic_inputs_config[name] = {
            'type': 'slider',
            'widget': self.widgets[name],
            'scale': scale
        }
        
        layout.addWidget(slider_container)
        return container

    def _create_file_input(self, name, label_text):
        container = self.create_widget(QWidget, f"{name}_container")
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(5)

        input_widget = QWidget()
        hbox = QHBoxLayout(input_widget)
        hbox.setContentsMargins(0, 0, 0, 0)

        line_edit = self.create_widget(QLineEdit, name)
        line_edit.setPlaceholderText("No file selected or path pasted")
        button = QPushButton("Browse...")

        def open_dialog():
            if "refs" in name:
                filenames, _ = QFileDialog.getOpenFileNames(self, f"Select {label_text}", filter="Image Files (*.png *.jpg *.jpeg *.bmp *.webp);;All Files (*)")
                if filenames: line_edit.setText(";".join(filenames))
            else:
                filter_str = "All Files (*)"
                if 'video' in name:
                    filter_str = "Video Files (*.mp4 *.mkv *.mov *.avi);;All Files (*)"
                elif 'image' in name:
                    filter_str = "Image Files (*.png *.jpg *.jpeg *.bmp *.webp);;All Files (*)"
                elif 'audio' in name:
                    filter_str = "Audio Files (*.wav *.mp3 *.flac);;All Files (*)"

                filename, _ = QFileDialog.getOpenFileName(self, f"Select {label_text}", filter=filter_str)
                if filename: line_edit.setText(filename)

        button.clicked.connect(open_dialog)
        clear_button = QPushButton("X")
        clear_button.setFixedWidth(30)
        clear_button.clicked.connect(lambda: line_edit.clear())

        hbox.addWidget(QLabel(f"{label_text}:"))
        hbox.addWidget(line_edit, 1)
        hbox.addWidget(button)
        hbox.addWidget(clear_button)
        vbox.addWidget(input_widget)

        preview_container = self.create_widget(QWidget, f"{name}_preview_container")
        preview_hbox = QHBoxLayout(preview_container)
        preview_hbox.setContentsMargins(0, 0, 0, 0)
        preview_hbox.addStretch()

        is_image_input = 'image' in name and 'audio' not in name
        is_video_input = 'video' in name and 'audio' not in name

        if is_image_input:
            preview_widget = self.create_widget(QLabel, f"{name}_preview")
            preview_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            preview_widget.setFixedSize(160, 90)
            preview_widget.setStyleSheet("border: 1px solid #cccccc; background-color: #f0f0f0;")
            preview_widget.setText("Image Preview")
            preview_hbox.addWidget(preview_widget)
        elif is_video_input:
            media_player = QMediaPlayer()
            video_widget = QVideoWidget()
            video_widget.setFixedSize(160, 90)
            media_player.setVideoOutput(video_widget)
            media_player.setLoops(QMediaPlayer.Loops.Infinite)
            
            self.widgets[f"{name}_player"] = media_player
            
            preview_widget = HoverVideoPreview(media_player, video_widget)
            preview_hbox.addWidget(preview_widget)
        else:
            preview_widget = self.create_widget(QLabel, f"{name}_preview")
            preview_widget.setText("No preview available")
            preview_hbox.addWidget(preview_widget)

        preview_hbox.addStretch()
        vbox.addWidget(preview_container)
        preview_container.setVisible(False)

        def update_preview(path):
            container = self.widgets.get(f"{name}_preview_container")
            if not container: return

            first_path = path.split(';')[0] if path else ''
            
            if not first_path or not os.path.exists(first_path):
                container.setVisible(False)
                if is_video_input:
                    player = self.widgets.get(f"{name}_player")
                    if player: player.setSource(QUrl())
                return

            container.setVisible(True)
            
            if is_image_input:
                preview_label = self.widgets.get(f"{name}_preview")
                if preview_label:
                    pixmap = QPixmap(first_path)
                    if not pixmap.isNull():
                        preview_label.setPixmap(pixmap.scaled(preview_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                    else:
                        preview_label.setText("Invalid Image")

            elif is_video_input:
                player = self.widgets.get(f"{name}_player")
                if player:
                    player.setSource(QUrl.fromLocalFile(first_path))

            else:
                preview_label = self.widgets.get(f"{name}_preview")
                if preview_label:
                    preview_label.setText(os.path.basename(path))

        line_edit.textChanged.connect(update_preview)
        
        return container
        
    def setup_generator_tab(self):
        gen_tab = QWidget()
        self.tabs.addTab(gen_tab, "Video Generator")
        gen_layout = QHBoxLayout(gen_tab)
        left_panel = QWidget()
        left_panel.setMinimumWidth(628)
        left_layout = QVBoxLayout(left_panel)
        gen_layout.addWidget(left_panel, 1)
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        gen_layout.addWidget(right_panel, 1)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        left_layout.addWidget(scroll_area)
        options_widget = QWidget()
        scroll_area.setWidget(options_widget)
        options_layout = QVBoxLayout(options_widget)
        model_layout = QHBoxLayout()
        self.widgets['model_family'] = QComboBox()
        self.widgets['model_base_type_choice'] = QComboBox()
        self.widgets['model_choice'] = QComboBox()
        model_layout.addWidget(QLabel("Model:"))
        model_layout.addWidget(self.widgets['model_family'], 2)
        model_layout.addWidget(self.widgets['model_base_type_choice'], 3)
        model_layout.addWidget(self.widgets['model_choice'], 3)
        options_layout.addLayout(model_layout)
        options_layout.addWidget(QLabel("Prompt:"))
        prompt_edit = self.create_widget(QTextEdit, 'prompt')
        prompt_edit.setMaximumHeight(prompt_edit.fontMetrics().lineSpacing() * 5 + 15)
        options_layout.addWidget(prompt_edit)
        options_layout.addWidget(QLabel("Negative Prompt:"))
        neg_prompt_edit = self.create_widget(QTextEdit, 'negative_prompt')
        neg_prompt_edit.setMaximumHeight(neg_prompt_edit.fontMetrics().lineSpacing() * 3 + 15)
        options_layout.addWidget(neg_prompt_edit)
        basic_group = QGroupBox("Basic Options")
        basic_layout = QFormLayout(basic_group)
        res_container = QWidget()
        res_hbox = QHBoxLayout(res_container)
        res_hbox.setContentsMargins(0, 0, 0, 0)
        res_hbox.addWidget(self.create_widget(QComboBox, 'resolution_group'), 2)
        res_hbox.addWidget(self.create_widget(QComboBox, 'resolution'), 3)
        basic_layout.addRow("Resolution:", res_container)
        basic_layout.addRow("Video Length:", self._create_slider_with_label('video_length', 1, 737, 81, 1.0, 0))
        basic_layout.addRow("Inference Steps:", self._create_slider_with_label('num_inference_steps', 1, 100, 30, 1.0, 0))
        basic_layout.addRow("Seed:", self.create_widget(QLineEdit, 'seed', '-1'))
        options_layout.addWidget(basic_group)
        mode_options_group = QGroupBox("Generation Mode & Input Options")
        mode_options_layout = QVBoxLayout(mode_options_group)
        mode_hbox = QHBoxLayout()
        mode_hbox.addWidget(self.create_widget(QRadioButton, 'mode_t', "Text Prompt Only"))
        mode_hbox.addWidget(self.create_widget(QRadioButton, 'mode_s', "Start with Image"))
        mode_hbox.addWidget(self.create_widget(QRadioButton, 'mode_v', "Continue Video"))
        mode_hbox.addWidget(self.create_widget(QRadioButton, 'mode_l', "Continue Last Video"))
        self.widgets['mode_t'].setChecked(True)
        mode_options_layout.addLayout(mode_hbox)
        options_hbox = QHBoxLayout()
        options_hbox.addWidget(self.create_widget(QCheckBox, 'image_end_checkbox', "Use End Image"))
        options_hbox.addWidget(self.create_widget(QCheckBox, 'control_video_checkbox', "Use Control Video"))
        options_hbox.addWidget(self.create_widget(QCheckBox, 'ref_image_checkbox', "Use Reference Image(s)"))
        mode_options_layout.addLayout(options_hbox)
        options_layout.addWidget(mode_options_group)
        inputs_group = QGroupBox("Inputs")
        inputs_layout = QVBoxLayout(inputs_group)
        inputs_layout.addWidget(self._create_file_input('image_start', "Start Image"))
        inputs_layout.addWidget(self._create_file_input('image_end', "End Image"))
        inputs_layout.addWidget(self._create_file_input('video_source', "Source Video"))
        inputs_layout.addWidget(self._create_file_input('video_guide', "Control Video"))
        inputs_layout.addWidget(self._create_file_input('video_mask', "Video Mask"))
        inputs_layout.addWidget(self._create_file_input('image_refs', "Reference Image(s)"))
        inputs_layout.addWidget(self._create_file_input('audio_guide', "Audio Guide (Voice 1)"))
        inputs_layout.addWidget(self._create_file_input('audio_guide2', "Audio Guide (Voice 2)"))
        inputs_layout.addWidget(self._create_file_input('custom_guide', "Custom Guide"))
        denoising_row = QFormLayout()
        denoising_row.addRow("Denoising Strength:", self._create_slider_with_label('denoising_strength', 0, 100, 50, 100.0, 2))
        inputs_layout.addLayout(denoising_row)
        options_layout.addWidget(inputs_group)
        self.advanced_group = self.create_widget(QGroupBox, 'advanced_group', "Advanced Options")
        self.adv_layout = QVBoxLayout(self.advanced_group)				 

        options_layout.addWidget(self.advanced_group)
        btn_layout = QHBoxLayout()
        self.generate_btn = self.create_widget(QPushButton, 'generate_btn', "Generate")
        self.add_to_queue_btn = self.create_widget(QPushButton, 'add_to_queue_btn', "Add to Queue")
        self.generate_btn.setEnabled(True)
        self.add_to_queue_btn.setEnabled(False)
        btn_layout.addWidget(self.generate_btn)
        btn_layout.addWidget(self.add_to_queue_btn)
        right_layout.addLayout(btn_layout)
        self.status_label = self.create_widget(QLabel, 'status_label', "Idle")
        right_layout.addWidget(self.status_label)
        self.progress_bar = self.create_widget(QProgressBar, 'progress_bar')
        right_layout.addWidget(self.progress_bar)
        preview_group = self.create_widget(QGroupBox, 'preview_group', "Preview")
        preview_group.setCheckable(True)
        preview_group.setStyleSheet("QGroupBox { border: 1px solid #cccccc; }")
        preview_group_layout = QVBoxLayout(preview_group)
        self.preview_image = self.create_widget(QLabel, 'preview_image', "")
        self.preview_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_image.setMinimumSize(200, 200)
        preview_group_layout.addWidget(self.preview_image)
        right_layout.addWidget(preview_group)

        results_group = QGroupBox("Generated Clips")
        results_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        results_layout = QVBoxLayout(results_group)
        self.results_list = self.create_widget(QListWidget, 'results_list')
        self.results_list.setFlow(QListWidget.Flow.LeftToRight)
        self.results_list.setWrapping(True)
        self.results_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.results_list.setSpacing(10)
        results_layout.addWidget(self.results_list)
        right_layout.addWidget(results_group)

        right_layout.addWidget(QLabel("Queue"))
        self.queue_table = self.create_widget(QueueTableWidget, 'queue_table')
        self.queue_table.verticalHeader().setVisible(False)
        self.queue_table.setColumnCount(4)
        self.queue_table.setHorizontalHeaderLabels(["Qty", "Prompt", "Length", "Steps"])
        header = self.queue_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        right_layout.addWidget(self.queue_table)

        queue_btn_layout = QHBoxLayout()
        self.remove_queue_btn = self.create_widget(QPushButton, 'remove_queue_btn', "Remove Selected")
        self.clear_queue_btn = self.create_widget(QPushButton, 'clear_queue_btn', "Clear Queue")
        self.abort_btn = self.create_widget(QPushButton, 'abort_btn', "Abort")
        queue_btn_layout.addWidget(self.remove_queue_btn)
        queue_btn_layout.addWidget(self.clear_queue_btn)
        queue_btn_layout.addWidget(self.abort_btn)
        right_layout.addLayout(queue_btn_layout)

    def setup_config_tab(self):
        config_tab = QWidget()
        self.tabs.addTab(config_tab, "Configuration")
        main_layout = QVBoxLayout(config_tab)
        self.config_status_label = QLabel("Apply changes for them to take effect. Some may require a restart.")
        main_layout.addWidget(self.config_status_label)
        config_tabs = QTabWidget()
        main_layout.addWidget(config_tabs)
        config_tabs.addTab(self._create_general_config_tab(), "General")
        config_tabs.addTab(self._create_performance_config_tab(), "Performance")
        config_tabs.addTab(self._create_extensions_config_tab(), "Extensions")
        config_tabs.addTab(self._create_outputs_config_tab(), "Outputs")
        config_tabs.addTab(self._create_notifications_config_tab(), "Notifications")
        self.apply_config_btn = QPushButton("Apply Changes")
        self.apply_config_btn.clicked.connect(self._on_apply_config_changes)
        main_layout.addWidget(self.apply_config_btn)
    
    def _create_scrollable_form_tab(self):
        tab_widget = QWidget()
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        layout = QVBoxLayout(tab_widget)
        layout.addWidget(scroll_area)
        content_widget = QWidget()
        form_layout = QFormLayout(content_widget)
        scroll_area.setWidget(content_widget)
        return tab_widget, form_layout

    def _create_config_combo(self, form_layout, label, key, choices, default_value):
        combo = QComboBox()
        for text, data in choices: combo.addItem(text, data)
        index = combo.findData(wgp.server_config.get(key, default_value))
        if index != -1: combo.setCurrentIndex(index)
        self.widgets[f'config_{key}'] = combo
        form_layout.addRow(label, combo)

    def _create_config_slider(self, form_layout, label, key, min_val, max_val, default_value, step=1):
        container = QWidget()
        hbox = QHBoxLayout(container)
        hbox.setContentsMargins(0,0,0,0)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(min_val, max_val)
        slider.setSingleStep(step)
        slider.setValue(wgp.server_config.get(key, default_value))
        value_label = QLabel(str(slider.value()))
        value_label.setMinimumWidth(40)
        slider.valueChanged.connect(lambda v, lbl=value_label: lbl.setText(str(v)))
        hbox.addWidget(slider)
        hbox.addWidget(value_label)
        self.widgets[f'config_{key}'] = slider
        form_layout.addRow(label, container)

    def _create_config_checklist(self, form_layout, label, key, choices, default_value):
        list_widget = QListWidget()
        list_widget.setMinimumHeight(100)
        current_values = wgp.server_config.get(key, default_value)
        for text, data in choices:
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, data)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if data in current_values else Qt.CheckState.Unchecked)
            list_widget.addItem(item)
        self.widgets[f'config_{key}'] = list_widget
        form_layout.addRow(label, list_widget)

    def _create_config_textbox(self, form_layout, label, key, default_value, multi_line=False):
        if multi_line:
            textbox = QTextEdit(default_value)
            textbox.setAcceptRichText(False)
        else:
            textbox = QLineEdit(default_value)
        self.widgets[f'config_{key}'] = textbox
        form_layout.addRow(label, textbox)

    def _create_general_config_tab(self):
        tab, form = self._create_scrollable_form_tab()
        _, _, dropdown_choices = wgp.get_sorted_dropdown(wgp.displayed_model_types, None, None, False)
        self._create_config_checklist(form, "Selectable Models:", "transformer_types", dropdown_choices, wgp.transformer_types)
        self._create_config_combo(form, "Model Hierarchy:", "model_hierarchy_type", [("Two Levels (Family > Model)", 0), ("Three Levels (Family > Base > Finetune)", 1)], 1)
        self._create_config_combo(form, "Video Dimensions:", "fit_canvas", [("Dimensions are Pixels Budget", 0), ("Dimensions are Max Width/Height", 1), ("Dimensions are Output Width/Height (Cropped)", 2)], 0)
        self._create_config_combo(form, "Attention Type:", "attention_mode", [("Auto (Recommended)", "auto"), ("SDPA", "sdpa"), ("Flash", "flash"), ("Xformers", "xformers"), ("Sage", "sage"), ("Sage2/2++", "sage2")], "auto")
        self._create_config_combo(form, "Metadata Handling:", "metadata_type", [("Embed in file (Exif/Comment)", "metadata"), ("Export separate JSON", "json"), ("None", "none")], "metadata")
        checkbox = QCheckBox()
        checkbox.setChecked(wgp.server_config.get("embed_source_images", False))
        self.widgets['config_embed_source_images'] = checkbox
        form.addRow("Embed Source Images in MP4:", checkbox)
        self._create_config_checklist(form, "RAM Loading Policy:", "preload_model_policy", [("Preload on App Launch", "P"), ("Preload on Model Switch", "S"), ("Unload when Queue is Done", "U")], [])
        self._create_config_combo(form, "Keep Previous Videos:", "clear_file_list", [("None", 0), ("Keep last video", 1), ("Keep last 5", 5), ("Keep last 10", 10), ("Keep last 20", 20), ("Keep last 30", 30)], 5)
        self._create_config_combo(form, "Display RAM/VRAM Stats:", "display_stats", [("Disabled", 0), ("Enabled", 1)], 0)
        self._create_config_combo(form, "Max Frames Multiplier:", "max_frames_multiplier", [(f"x{i}", i) for i in range(1, 8)], 1)
        checkpoints_paths_text = "\n".join(wgp.server_config.get("checkpoints_paths", wgp.fl.default_checkpoints_paths))
        checkpoints_textbox = QTextEdit()
        checkpoints_textbox.setPlainText(checkpoints_paths_text)
        checkpoints_textbox.setAcceptRichText(False)
        checkpoints_textbox.setMinimumHeight(60)
        self.widgets['config_checkpoints_paths'] = checkpoints_textbox
        form.addRow("Checkpoints Paths:", checkpoints_textbox)
        self._create_config_combo(form, "UI Theme (requires restart):", "UI_theme", [("Blue Sky", "default"), ("Classic Gradio", "gradio")], "default")
        self._create_config_combo(form, "Queue Color Scheme:", "queue_color_scheme", [("Pastel (Unique color per item)", "pastel"), ("Alternating Grey Shades", "alternating_grey")], "pastel")
        return tab

    def _create_performance_config_tab(self):
        tab, form = self._create_scrollable_form_tab()
        self._create_config_combo(form, "Transformer Quantization:", "transformer_quantization", [("Scaled Int8 (recommended)", "int8"), ("16-bit (no quantization)", "bf16")], "int8")
        self._create_config_combo(form, "Transformer Data Type:", "transformer_dtype_policy", [("Best Supported by Hardware", ""), ("FP16", "fp16"), ("BF16", "bf16")], "")
        self._create_config_combo(form, "Transformer Calculation:", "mixed_precision", [("16-bit only", "0"), ("Mixed 16/32-bit (better quality)", "1")], "0")
        self._create_config_combo(form, "Text Encoder:", "text_encoder_quantization", [("16-bit (more RAM, better quality)", "bf16"), ("8-bit (less RAM, slightly lower quality)", "int8")], "int8")
        self._create_config_combo(form, "VAE Precision:", "vae_precision", [("16-bit (faster, less VRAM)", "16"), ("32-bit (slower, better quality)", "32")], "16")
        self._create_config_combo(form, "Compile Transformer:", "compile", [("On (requires Triton)", "transformer"), ("Off", "")], "")
        self._create_config_combo(form, "DepthAnything v2 Variant:", "depth_anything_v2_variant", [("Large (more precise)", "vitl"), ("Big (faster)", "vitb")], "vitl")
        self._create_config_combo(form, "VAE Tiling:", "vae_config", [("Auto", 0), ("Disabled", 1), ("256x256 Tiles (~8GB VRAM)", 2), ("128x128 Tiles (~6GB VRAM)", 3)], 0)
        self._create_config_combo(form, "Boost:", "boost", [("On", 1), ("Off", 2)], 1)
        self._create_config_combo(form, "Memory Profile:", "profile", wgp.memory_profile_choices, wgp.profile_type.LowRAM_LowVRAM)
        self._create_config_slider(form, "Preload in VRAM (MB):", "preload_in_VRAM", 0, 40000, 0, 100)
        release_ram_btn = QPushButton("Force Release Models from RAM")
        release_ram_btn.clicked.connect(self._on_release_ram)
        form.addRow(release_ram_btn)
        return tab

    def _create_extensions_config_tab(self):
        tab, form = self._create_scrollable_form_tab()
        self._create_config_combo(form, "Prompt Enhancer:", "enhancer_enabled", [("Off", 0), ("Florence 2 + Llama 3.2", 1), ("Florence 2 + Joy Caption (uncensored)", 2)], 0)
        self._create_config_combo(form, "Enhancer Mode:", "enhancer_mode", [("Automatic on Generate", 0), ("On Demand Only", 1)], 0)
        self._create_config_combo(form, "MMAudio Mode:", "mmaudio_mode", [("Off", 0), ("Standard", 1), ("NSFW", 2)], 0)
        self._create_config_combo(form, "MMAudio Persistence:", "mmaudio_persistence", [("Unload after use", 1), ("Persistent in RAM", 2)], 1)
        return tab

    def _create_outputs_config_tab(self):
        tab, form = self._create_scrollable_form_tab()
        self._create_config_combo(form, "Video Codec:", "video_output_codec", [("x265 Balanced", 'libx265_28'), ("x264 Balanced", 'libx264_8'), ("x265 High Quality", 'libx265_8'), ("x264 High Quality", 'libx264_10'), ("x264 Lossless", 'libx264_lossless')], 'libx264_8')
        self._create_config_combo(form, "Image Codec:", "image_output_codec", [("JPEG Q85", 'jpeg_85'), ("WEBP Q85", 'webp_85'), ("JPEG Q95", 'jpeg_95'), ("WEBP Q95", 'webp_95'), ("WEBP Lossless", 'webp_lossless'), ("PNG Lossless", 'png')], 'jpeg_95')
        self._create_config_combo(form, "Audio Codec:", "audio_output_codec", [("AAC 128 kbit", 'aac_128')], 'aac_128')
        self._create_config_textbox(form, "Video Output Folder:", "save_path", wgp.server_config.get("save_path", "outputs"))
        self._create_config_textbox(form, "Image Output Folder:", "image_save_path", wgp.server_config.get("image_save_path", "outputs"))
        return tab

    def _create_notifications_config_tab(self):
        tab, form = self._create_scrollable_form_tab()
        self._create_config_combo(form, "Notification Sound:", "notification_sound_enabled", [("On", 1), ("Off", 0)], 0)
        self._create_config_slider(form, "Sound Volume:", "notification_sound_volume", 0, 100, 50, 5)
        return tab
        
    def init_wgp_state(self):
        with working_directory(wan2gp_dir):
            if not wgp.models_def:
                self.header_info.setText("<font color='red'>No WAN2GP models found. Please run WAN2GP normally once to download models, then restart.</font>")
                for combo_name in ['model_family', 'model_base_type_choice', 'model_choice']:
                    if combo_name in self.widgets:
                        self.widgets[combo_name].setEnabled(False)
                self.generate_btn.setEnabled(False)
                self.add_to_queue_btn.setEnabled(False)
                print("WGP Plugin Error: No model definitions found. The UI has been disabled.")
                return

            initial_model = wgp.server_config.get("last_model_type", wgp.transformer_type)
            dropdown_types = wgp.transformer_types if len(wgp.transformer_types) > 0 else wgp.displayed_model_types

            if initial_model not in wgp.models_def:
                if dropdown_types and dropdown_types[0] in wgp.models_def:
                    initial_model = dropdown_types[0]
                elif wgp.displayed_model_types and wgp.displayed_model_types[0] in wgp.models_def:
                    initial_model = wgp.displayed_model_types[0]
                else:
                    initial_model = next(iter(wgp.models_def))

            state_dict = {}
            state_dict["model_filename"] = wgp.get_model_filename(initial_model, wgp.transformer_quantization, wgp.transformer_dtype_policy)
            state_dict["model_type"] = initial_model
            state_dict["advanced"] = wgp.advanced
            state_dict["last_model_per_family"] = wgp.server_config.get("last_model_per_family", {})
            state_dict["last_model_per_type"] = wgp.server_config.get("last_model_per_type", {})
            state_dict["last_resolution_per_group"] = wgp.server_config.get("last_resolution_per_group", {})
            state_dict["gen"] = {"queue": []}
            self.state = state_dict
            self.update_model_dropdowns(initial_model)
            self.refresh_ui_from_model_change(initial_model)
            self._update_input_visibility()

    def update_model_dropdowns(self, current_model_type):
        family_mock, base_type_mock, choice_mock = wgp.generate_dropdown_model_list(current_model_type)
        for combo_name, mock in [('model_family', family_mock), ('model_base_type_choice', base_type_mock), ('model_choice', choice_mock)]:
            combo = self.widgets[combo_name]
            combo.blockSignals(True)
            combo.clear()
            if mock.choices:
                for item in mock.choices:
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        display_name, internal_key = item[0], item[1]
                        combo.addItem(display_name, internal_key)
            index = combo.findData(mock.value)
            if index != -1: combo.setCurrentIndex(index)
            
            is_visible = True
            if hasattr(mock, 'kwargs') and isinstance(mock.kwargs, dict):
                is_visible = mock.kwargs.get('visible', True)
            elif hasattr(mock, 'visible'):
                is_visible = mock.visible
            combo.setVisible(is_visible)
            
            combo.blockSignals(False)

    def refresh_ui_from_model_change(self, model_type):
        with working_directory(wan2gp_dir):
            self.header_info.setText(wgp.generate_header(model_type, wgp.compile, wgp.attention_mode))
            ui_defaults = wgp.get_default_settings(model_type)
            wgp.set_model_settings(self.state, model_type, ui_defaults)

            model_def = wgp.get_model_def(model_type)
            base_model_type = wgp.get_base_model_type(model_type)
            model_filename = self.state.get('model_filename', '')

            self._update_generation_mode_visibility(model_def)

            for widget in self.widgets.values():
                if hasattr(widget, 'blockSignals'): widget.blockSignals(True)

            self.widgets['prompt'].setText(ui_defaults.get("prompt", ""))
            self.widgets['negative_prompt'].setText(ui_defaults.get("negative_prompt", ""))
            self.widgets['seed'].setText(str(ui_defaults.get("seed", -1)))
            
            video_length_val = ui_defaults.get("video_length", 81)
            self.widgets['video_length'].setValue(video_length_val)
            self.widgets['video_length_label'].setText(str(video_length_val))

            steps_val = ui_defaults.get("num_inference_steps", 30)
            self.widgets['num_inference_steps'].setValue(steps_val)
            self.widgets['num_inference_steps_label'].setText(str(steps_val))

            self.widgets['resolution_group'].blockSignals(True)
            self.widgets['resolution'].blockSignals(True)

            current_res_choice = ui_defaults.get("resolution")
            model_resolutions = model_def.get("resolutions", None)
            self.full_resolution_choices, current_res_choice = wgp.get_resolution_choices(current_res_choice, model_resolutions)
            available_groups, selected_group_resolutions, selected_group = wgp.group_resolutions(model_def, self.full_resolution_choices, current_res_choice)

            self.widgets['resolution_group'].clear()
            self.widgets['resolution_group'].addItems(available_groups)
            group_index = self.widgets['resolution_group'].findText(selected_group)
            if group_index != -1:
                self.widgets['resolution_group'].setCurrentIndex(group_index)
            
            self.widgets['resolution'].clear()
            for label, value in selected_group_resolutions:
                self.widgets['resolution'].addItem(label, value)
            res_index = self.widgets['resolution'].findData(current_res_choice)
            if res_index != -1:
                self.widgets['resolution'].setCurrentIndex(res_index)

            self.widgets['resolution_group'].blockSignals(False)
            self.widgets['resolution'].blockSignals(False)

            for name in ['video_source', 'image_start', 'image_end', 'video_guide', 'video_mask', 'image_refs', 'audio_source', 'audio_guide', 'audio_guide2', 'custom_guide']:
                if name in self.widgets: self.widgets[name].clear()

            any_audio_prompt = model_def.get("any_audio_prompt", False)
            one_speaker = model_def.get("one_speaker_only", False)
            custom_guide_def = model_def.get("custom_guide", None)
            
            self.widgets['audio_guide_container'].setVisible(any_audio_prompt)
            self.widgets['audio_guide2_container'].setVisible(any_audio_prompt and not one_speaker)
            self.widgets['custom_guide_container'].setVisible(custom_guide_def is not None)

            denoising_val = ui_defaults.get("denoising_strength", 0.5)
            self.widgets['denoising_strength'].setValue(int(denoising_val * 100))
            self.widgets['denoising_strength_label'].setText(f"{denoising_val:.2f}")

            # Rebuild Dynamic Advanced Tabs
            if self.advanced_tabs_widget:
                self.adv_layout.removeWidget(self.advanced_tabs_widget)
                self.advanced_tabs_widget.deleteLater()
                self.advanced_tabs_widget = None
            
            self.dynamic_inputs_config.clear()
            
            tabs_widget = self.ui_builder.build_advanced_tab(model_type)
            if tabs_widget:
                self.adv_layout.addWidget(tabs_widget)
                self.advanced_tabs_widget = tabs_widget
            else:
                self.adv_layout.addWidget(QLabel("Advanced options unavailable."))

            for var_name, config in self.dynamic_inputs_config.items():
                widget = config['widget']
                widget.blockSignals(True)
                val = ui_defaults.get(var_name)
                
                if val is not None:
                    if config['type'] == 'slider':
                        scale = config.get('scale', 1.0)
                        widget.setValue(int(val * scale))
                    elif config['type'] == 'dropdown':
                        idx = widget.findData(val)
                        if idx == -1: idx = widget.findText(str(val))
                        if idx != -1: widget.setCurrentIndex(idx)
                    elif config['type'] == 'checkbox':
                        widget.setChecked(bool(val))
                    elif config['type'] == 'text':
                        if isinstance(widget, QLineEdit): widget.setText(str(val))
                        else: widget.setPlainText(str(val))
                    elif config['type'] == 'file':
                        widget.setText(str(val) if val else "")
                widget.blockSignals(False)

            with working_directory(wan2gp_dir):
                available_loras, _, _, _, _, _ = wgp.setup_loras(model_type, None, wgp.get_lora_dir(model_type), "")
            self.state['loras'] = available_loras
            self.lora_map = {os.path.basename(p): p for p in available_loras}
            
            if 'activated_loras' in self.widgets:
                lora_list_widget = self.widgets['activated_loras']
                lora_list_widget.clear()
                lora_list_widget.addItems(sorted(self.lora_map.keys()))
                selected_loras = ui_defaults.get('activated_loras', [])
                for i in range(lora_list_widget.count()):
                    item = lora_list_widget.item(i)
                    if any(item.text() == os.path.basename(p) for p in selected_loras): item.setSelected(True)

            for widget in self.widgets.values():
                if hasattr(widget, 'blockSignals'): widget.blockSignals(False)
                
            self._update_input_visibility()

    def _update_generation_mode_visibility(self, model_def):
        allowed = model_def.get("image_prompt_types_allowed", "")
        choices = []
        if "T" in allowed or not allowed: choices.append(("Text Prompt Only" if "S" in allowed else "New Video", "T"))
        if "S" in allowed: choices.append(("Start Video with Image", "S"))
        if "V" in allowed: choices.append(("Continue Video", "V"))
        if "L" in allowed: choices.append(("Continue Last Video", "L"))
        button_map = { "T": self.widgets['mode_t'], "S": self.widgets['mode_s'], "V": self.widgets['mode_v'], "L": self.widgets['mode_l'] }
        for btn in button_map.values(): btn.setVisible(False)
        allowed_values = [c[1] for c in choices]
        for label, value in choices:
            if value in button_map:
                btn = button_map[value]
                btn.setText(label)
                btn.setVisible(True)
        current_checked_value = next((value for value, btn in button_map.items() if btn.isChecked()), None)
        if current_checked_value is None or not button_map[current_checked_value].isVisible():
            if allowed_values: button_map[allowed_values[0]].setChecked(True)
        end_image_visible = "E" in allowed
        self.widgets['image_end_checkbox'].setVisible(end_image_visible)
        if not end_image_visible: self.widgets['image_end_checkbox'].setChecked(False)
        control_video_visible = model_def.get("guide_preprocessing") is not None
        self.widgets['control_video_checkbox'].setVisible(control_video_visible)
        if not control_video_visible: self.widgets['control_video_checkbox'].setChecked(False)
        ref_image_visible = model_def.get("image_ref_choices") is not None
        self.widgets['ref_image_checkbox'].setVisible(ref_image_visible)
        if not ref_image_visible: self.widgets['ref_image_checkbox'].setChecked(False)

    def _update_input_visibility(self):
        is_s_mode = self.widgets['mode_s'].isChecked()
        is_v_mode = self.widgets['mode_v'].isChecked()
        is_l_mode = self.widgets['mode_l'].isChecked()
        use_end = self.widgets['image_end_checkbox'].isChecked() and self.widgets['image_end_checkbox'].isVisible()
        use_control = self.widgets['control_video_checkbox'].isChecked() and self.widgets['control_video_checkbox'].isVisible()
        use_ref = self.widgets['ref_image_checkbox'].isChecked() and self.widgets['ref_image_checkbox'].isVisible()
        self.widgets['image_start_container'].setVisible(is_s_mode)
        self.widgets['video_source_container'].setVisible(is_v_mode)
        end_checkbox_enabled = is_s_mode or is_v_mode or is_l_mode
        self.widgets['image_end_checkbox'].setEnabled(end_checkbox_enabled)
        self.widgets['image_end_container'].setVisible(use_end and end_checkbox_enabled)
        self.widgets['video_guide_container'].setVisible(use_control)
        self.widgets['video_mask_container'].setVisible(use_control)
        self.widgets['image_refs_container'].setVisible(use_ref)

    def connect_signals(self):
        self.widgets['model_family'].currentIndexChanged.connect(self._on_family_changed)
        self.widgets['model_base_type_choice'].currentIndexChanged.connect(self._on_base_type_changed)
        self.widgets['model_choice'].currentIndexChanged.connect(self._on_model_changed)
        self.widgets['resolution_group'].currentIndexChanged.connect(self._on_resolution_group_changed)
        self.widgets['mode_t'].toggled.connect(self._update_input_visibility)
        self.widgets['mode_s'].toggled.connect(self._update_input_visibility)
        self.widgets['mode_v'].toggled.connect(self._update_input_visibility)
        self.widgets['mode_l'].toggled.connect(self._update_input_visibility)
        self.widgets['image_end_checkbox'].toggled.connect(self._update_input_visibility)
        self.widgets['control_video_checkbox'].toggled.connect(self._update_input_visibility)
        self.widgets['ref_image_checkbox'].toggled.connect(self._update_input_visibility)
        self.widgets['preview_group'].toggled.connect(self._on_preview_toggled)
        self.generate_btn.clicked.connect(self._on_generate)
        self.add_to_queue_btn.clicked.connect(self._on_add_to_queue)
        self.remove_queue_btn.clicked.connect(self._on_remove_selected_from_queue)
        self.clear_queue_btn.clicked.connect(self._on_clear_queue)
        self.abort_btn.clicked.connect(self._on_abort)
        self.queue_table.rowsMoved.connect(self._on_queue_rows_moved)
        self.queue_table.rowsRemoved.connect(self._remove_queue_rows)
        self.queue_table.clearAllRequested.connect(self._on_clear_queue)

    def load_main_config(self):
        try:
            with open('main_config.json', 'r') as f: self.main_config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError): self.main_config = {'preview_visible': False}

    def save_main_config(self):
        try:
            with open('main_config.json', 'w') as f: json.dump(self.main_config, f, indent=4)
        except Exception as e: print(f"Error saving main_config.json: {e}")

    def apply_initial_config(self):
        is_visible = self.main_config.get('preview_visible', True)
        self.widgets['preview_group'].setChecked(is_visible)
        self.widgets['preview_image'].setVisible(is_visible)

    def _on_preview_toggled(self, checked):
        self.widgets['preview_image'].setVisible(checked)
        self.main_config['preview_visible'] = checked
        self.save_main_config()

    def _on_family_changed(self):
        family = self.widgets['model_family'].currentData()
        if not family or not self.state: return
        with working_directory(wan2gp_dir):
            base_type_mock, choice_mock = wgp.change_model_family(self.state, family)

        if hasattr(base_type_mock, 'kwargs') and isinstance(base_type_mock.kwargs, dict):
            is_visible_base = base_type_mock.kwargs.get('visible', True)
        elif hasattr(base_type_mock, 'visible'):
            is_visible_base = base_type_mock.visible
        else:
            is_visible_base = True
            
        self.widgets['model_base_type_choice'].blockSignals(True)
        self.widgets['model_base_type_choice'].clear()
        if base_type_mock.choices:
            for label, value in base_type_mock.choices: self.widgets['model_base_type_choice'].addItem(label, value)
        self.widgets['model_base_type_choice'].setCurrentIndex(self.widgets['model_base_type_choice'].findData(base_type_mock.value))
        self.widgets['model_base_type_choice'].setVisible(is_visible_base)
        self.widgets['model_base_type_choice'].blockSignals(False)

        if hasattr(choice_mock, 'kwargs') and isinstance(choice_mock.kwargs, dict):
            is_visible_choice = choice_mock.kwargs.get('visible', True)
        elif hasattr(choice_mock, 'visible'):
            is_visible_choice = choice_mock.visible
        else:
            is_visible_choice = True

        self.widgets['model_choice'].blockSignals(True)
        self.widgets['model_choice'].clear()
        if choice_mock.choices:
            for label, value in choice_mock.choices: self.widgets['model_choice'].addItem(label, value)
        self.widgets['model_choice'].setCurrentIndex(self.widgets['model_choice'].findData(choice_mock.value))
        self.widgets['model_choice'].setVisible(is_visible_choice)
        self.widgets['model_choice'].blockSignals(False)
        
        self._on_model_changed()

    def _on_base_type_changed(self):
        family = self.widgets['model_family'].currentData()
        base_type = self.widgets['model_base_type_choice'].currentData()
        if not family or not base_type or not self.state: return
        with working_directory(wan2gp_dir):
            base_type_mock, choice_mock = wgp.change_model_base_types(self.state, family, base_type)

        if hasattr(choice_mock, 'kwargs') and isinstance(choice_mock.kwargs, dict):
            is_visible_choice = choice_mock.kwargs.get('visible', True)
        elif hasattr(choice_mock, 'visible'):
            is_visible_choice = choice_mock.visible
        else:
            is_visible_choice = True

        self.widgets['model_choice'].blockSignals(True)
        self.widgets['model_choice'].clear()
        if choice_mock.choices:
            for label, value in choice_mock.choices: self.widgets['model_choice'].addItem(label, value)
        self.widgets['model_choice'].setCurrentIndex(self.widgets['model_choice'].findData(choice_mock.value))
        self.widgets['model_choice'].setVisible(is_visible_choice)
        self.widgets['model_choice'].blockSignals(False)
        self._on_model_changed()

    def _on_model_changed(self):
        model_type = self.widgets['model_choice'].currentData()
        if not model_type or model_type == self.state.get('model_type'): return
        with working_directory(wan2gp_dir):
            wgp.change_model(self.state, model_type)
        self.refresh_ui_from_model_change(model_type)

    def _on_resolution_group_changed(self):
        selected_group = self.widgets['resolution_group'].currentText()
        if not selected_group or not hasattr(self, 'full_resolution_choices'): return
        model_type = self.state['model_type']
        model_def = wgp.get_model_def(model_type)
        model_resolutions = model_def.get("resolutions", None)
        group_resolution_choices = []
        if model_resolutions is None:
            group_resolution_choices = [res for res in self.full_resolution_choices if wgp.categorize_resolution(res[1]) == selected_group]
        else: return
        last_resolution = self.state.get("last_resolution_per_group", {}).get(selected_group, "")
        if not any(last_resolution == res[1] for res in group_resolution_choices) and group_resolution_choices:
            last_resolution = group_resolution_choices[0][1]
        self.widgets['resolution'].blockSignals(True)
        self.widgets['resolution'].clear()
        for label, value in group_resolution_choices: self.widgets['resolution'].addItem(label, value)
        self.widgets['resolution'].setCurrentIndex(self.widgets['resolution'].findData(last_resolution))
        self.widgets['resolution'].blockSignals(False)

    def set_resolution_from_target(self, target_w, target_h):
        if not self.full_resolution_choices:
            print("Resolution choices not available for AI resolution matching.")
            return

        target_pixels = target_w * target_h
        target_ar = target_w / target_h if target_h > 0 else 1.0

        best_res_value = None
        min_dist = float('inf')

        for label, res_value in self.full_resolution_choices:
            try:
                w_str, h_str = res_value.split('x')
                w, h = int(w_str), int(h_str)
            except (ValueError, AttributeError):
                continue

            pixels = w * h
            ar = w / h if h > 0 else 1.0

            pixel_dist = abs(target_pixels - pixels) / target_pixels
            ar_dist = abs(target_ar - ar) / target_ar
            
            dist = pixel_dist * 0.8 + ar_dist * 0.2
            
            if dist < min_dist:
                min_dist = dist
                best_res_value = res_value

        if best_res_value:
            best_group = wgp.categorize_resolution(best_res_value)

            group_combo = self.widgets['resolution_group']
            group_combo.blockSignals(True)
            group_index = group_combo.findText(best_group)
            if group_index != -1:
                group_combo.setCurrentIndex(group_index)
            group_combo.blockSignals(False)

            self._on_resolution_group_changed()

            res_combo = self.widgets['resolution']
            res_index = res_combo.findData(best_res_value)
            if res_index != -1:
                res_combo.setCurrentIndex(res_index)
            else:
                print(f"Warning: Could not find resolution '{best_res_value}' in dropdown after group change.")

    def collect_inputs(self):
        with working_directory(wan2gp_dir):
             full_inputs = wgp.get_default_settings(self.state['model_type']).copy()

        sig = inspect.signature(wgp.generate_video)
        for param in sig.parameters:
            if param not in full_inputs and param not in ['task', 'send_cmd', 'plugin_data', 'state']:
                full_inputs[param] = None

        full_inputs['lset_name'] = ""
        full_inputs['image_mode'] = 0
        full_inputs['mode'] = ""

        for key in ['prompt', 'negative_prompt']:
            w = self.widgets.get(key)
            if isinstance(w, QTextEdit):
                full_inputs[key] = w.toPlainText()
            elif isinstance(w, QLineEdit):
                full_inputs[key] = w.text()

        full_inputs['resolution'] = self.widgets['resolution'].currentData()
        full_inputs['video_length'] = self.widgets['video_length'].value()
        full_inputs['num_inference_steps'] = self.widgets['num_inference_steps'].value()

        seed_w = self.widgets.get('seed')
        if isinstance(seed_w, QSlider):
            full_inputs['seed'] = seed_w.value()
        elif hasattr(seed_w, 'text'):
            try:
                txt = seed_w.text()
                full_inputs['seed'] = int(txt) if txt.strip() else -1
            except (ValueError, TypeError):
                full_inputs['seed'] = -1

        image_prompt_type = ""
        video_prompt_type = ""
        if self.widgets['mode_t'].isChecked(): image_prompt_type = ""
        elif self.widgets['mode_s'].isChecked(): image_prompt_type = 'S'
        elif self.widgets['mode_v'].isChecked(): image_prompt_type = 'V'
        elif self.widgets['mode_l'].isChecked(): image_prompt_type = 'L'
        
        if self.widgets['image_end_checkbox'].isVisible() and self.widgets['image_end_checkbox'].isChecked(): 
            image_prompt_type += 'E'
        if self.widgets['control_video_checkbox'].isVisible() and self.widgets['control_video_checkbox'].isChecked(): 
            video_prompt_type += 'V'
        if self.widgets['ref_image_checkbox'].isVisible() and self.widgets['ref_image_checkbox'].isChecked(): 
            video_prompt_type += 'I'
            
        full_inputs['image_prompt_type'] = image_prompt_type
        full_inputs['video_prompt_type'] = video_prompt_type

        for name in ['video_source', 'image_start', 'image_end', 'video_guide', 'video_mask', 
                     'audio_source', 'audio_guide', 'audio_guide2', 'custom_guide']:
            w = self.widgets.get(name)
            if w and hasattr(w, 'text'):
                full_inputs[name] = w.text() or None

        audio_prompt_type = ""
        if full_inputs.get("audio_guide"): audio_prompt_type += "A"
        if full_inputs.get("audio_guide2"): audio_prompt_type += "B"
        full_inputs['audio_prompt_type'] = audio_prompt_type

        refs_w = self.widgets.get('image_refs')
        if refs_w and hasattr(refs_w, 'text'):
            paths = refs_w.text().split(';')
            full_inputs['image_refs'] = [p.strip() for p in paths if p.strip()] if paths and paths[0] else None

        full_inputs['denoising_strength'] = self.widgets['denoising_strength'].value() / 100.0

        full_inputs['activated_loras'] = []
        if 'activated_loras' in self.widgets:
            selected_items = self.widgets['activated_loras'].selectedItems()
            full_inputs['activated_loras'] = [self.lora_map[item.text()] for item in selected_items if item.text() in self.lora_map]

        for var_name, config in self.dynamic_inputs_config.items():
            widget = config['widget']
            if config['type'] == 'slider':
                scale = config.get('scale', 1.0)
                full_inputs[var_name] = widget.value() / scale
            elif config['type'] == 'dropdown':
                full_inputs[var_name] = widget.currentData()
            elif config['type'] == 'checkbox':
                full_inputs[var_name] = 1 if widget.isChecked() else 0
            elif config['type'] == 'text':
                full_inputs[var_name] = widget.text() if isinstance(widget, QLineEdit) else widget.toPlainText()
            elif config['type'] == 'file':
                full_inputs[var_name] = widget.text() or None

        for list_key in ['activated_loras', 'image_refs', 'slg_layers']:
            if list_key in full_inputs and full_inputs[list_key] is None:
                full_inputs[list_key] = []

        return full_inputs

    def _prepare_state_for_generation(self):
        if 'gen' in self.state:
            self.state['gen'].pop('abort', None)
            self.state['gen'].pop('in_progress', None)

    def _on_generate(self):
        try:
            is_running = self.thread and self.thread.isRunning()
            self._add_task_to_queue()
            if not is_running: self.start_generation()
        except Exception as e:
            import traceback; traceback.print_exc()

    def _on_add_to_queue(self):
        try:
            self._add_task_to_queue()
        except Exception as e:
            import traceback; traceback.print_exc()
            
    def _add_task_to_queue(self):
        all_inputs = self.collect_inputs()
        sig = inspect.signature(wgp.generate_video)
        valid_keys = set(sig.parameters.keys())
        params = {k: v for k, v in all_inputs.items() if k in valid_keys}
        params['state'] = self.state
        wgp.set_model_settings(self.state, self.state['model_type'], params)
        self.state["validate_success"] = 1
        wgp.process_prompt_and_add_tasks(self.state, 0, self.state['model_type'])
        self.update_queue_table()
        
    def start_generation(self):
        if not self.state['gen']['queue']: return
        self._prepare_state_for_generation()
        self.generate_btn.setEnabled(False)
        self.add_to_queue_btn.setEnabled(True)
        self.thread = QThread()
        self.worker = Worker(self.plugin, self.state)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.on_generation_finished)
        self.worker.status.connect(self.status_label.setText)
        self.worker.progress.connect(self.update_progress)
        self.worker.preview.connect(self.update_preview)
        self.worker.output.connect(self.update_queue_and_results)
        self.worker.error.connect(self.on_generation_error)
        self.thread.start()
        self.update_queue_table()

    def on_generation_finished(self):
        time.sleep(0.1)
        self.status_label.setText("Finished.")
        self.progress_bar.setValue(0)
        self.generate_btn.setEnabled(True)
        self.add_to_queue_btn.setEnabled(False)
        self.thread = None; self.worker = None
        self.update_queue_table()

    def on_generation_error(self, err_msg):
        QMessageBox.critical(self, "Generation Error", str(err_msg))
        self.on_generation_finished()

    def update_progress(self, data):
        if len(data) > 1 and isinstance(data[0], tuple):
            step, total = data[0]
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(step)
            self.status_label.setText(str(data[1]))
            if step <= 1: self.update_queue_table()
        elif len(data) > 1: self.status_label.setText(str(data[1]))

    def update_preview(self, pil_image):
        if pil_image and self.widgets['preview_group'].isChecked():
            q_image = ImageQt(pil_image)
            pixmap = QPixmap.fromImage(q_image)
            self.preview_image.setPixmap(pixmap.scaled(self.preview_image.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def update_queue_and_results(self):
        self.update_queue_table()
        file_list = self.state.get('gen', {}).get('file_list', [])
        for file_path in file_list:
            if file_path not in self.processed_files:
                self.add_result_item(file_path)
                self.processed_files.add(file_path)

    def add_result_item(self, video_path):
        item_widget = VideoResultItemWidget(video_path, self.plugin)
        list_item = QListWidgetItem(self.results_list)
        list_item.setSizeHint(item_widget.sizeHint())
        self.results_list.addItem(list_item)
        self.results_list.setItemWidget(list_item, item_widget)

    def update_queue_table(self):
        with wgp.lock:
            queue = self.state.get('gen', {}).get('queue', [])
            is_running = self.thread and self.thread.isRunning()
            queue_to_display = queue if is_running else [None] + queue
            table_data = self._get_queue_data_for_table(queue_to_display)
            self.queue_table.setRowCount(0)
            self.queue_table.setRowCount(len(table_data))

            for row_idx, row_data in enumerate(table_data):
                for col_idx, cell_data in enumerate(row_data):
                    item = QTableWidgetItem(str(cell_data))
                    self.queue_table.setItem(row_idx, col_idx, item)

    def _on_remove_selected_from_queue(self):
        selected_row_indexes = self.queue_table.selectionModel().selectedRows()
        row_indices_to_remove = [index.row() for index in selected_row_indexes]
        
        if not row_indices_to_remove:
            current_row = self.queue_table.currentRow()
            if current_row >= 0:
                row_indices_to_remove.append(current_row)

        if row_indices_to_remove:
            self._remove_queue_rows(row_indices_to_remove)

    def _remove_queue_rows(self, row_indices):
        if not row_indices:
            return
        with wgp.lock:
            is_running = self.thread and self.thread.isRunning()
            queue = self.state.get('gen', {}).get('queue', [])
            offset = 1 if is_running else 0
            indices_to_pop = [idx + offset for idx in row_indices]
            
            for queue_idx in sorted(indices_to_pop, reverse=True):
                if 0 < queue_idx < len(queue):
                    queue.pop(queue_idx)
        self.update_queue_table()

    def _on_queue_rows_moved(self, source_row, dest_row):
        with wgp.lock:
            queue = self.state.get('gen', {}).get('queue', [])
            is_running = self.thread and self.thread.isRunning()
            offset = 1 if is_running else 0
            real_source_idx = source_row + offset
            moved_item = queue.pop(real_source_idx)
            real_dest_idx = dest_row + offset
            queue.insert(real_dest_idx, moved_item)
        self.update_queue_table()

    def _on_clear_queue(self):
        wgp.clear_queue_action(self.state)
        self.update_queue_table()
        
    def _on_abort(self):
        if self.worker:
            wgp.abort_generation(self.state)
            self.status_label.setText("Aborting...")
            self.worker._is_running = False
    
    def _on_release_ram(self):
        wgp.release_RAM()
        QMessageBox.information(self, "RAM Released", "Models stored in RAM have been released.")

    def _on_apply_config_changes(self):
        if wgp.args.lock_config:
            self.config_status_label.setText("Configuration is locked by command-line arguments.")
            return
        if self.thread and self.thread.isRunning():
            self.config_status_label.setText("Cannot change config while a generation is in progress.")
            return

        try:
            ui_settings = {}
            list_widget = self.widgets['config_transformer_types']
            ui_settings['transformer_types'] = [list_widget.item(i).data(Qt.ItemDataRole.UserRole) for i in range(list_widget.count()) if list_widget.item(i).checkState() == Qt.CheckState.Checked]
            list_widget = self.widgets['config_preload_model_policy']
            ui_settings['preload_model_policy'] = [list_widget.item(i).data(Qt.ItemDataRole.UserRole) for i in range(list_widget.count()) if list_widget.item(i).checkState() == Qt.CheckState.Checked]

            ui_settings['model_hierarchy_type'] = self.widgets['config_model_hierarchy_type'].currentData()
            ui_settings['fit_canvas'] = self.widgets['config_fit_canvas'].currentData()
            ui_settings['attention_mode'] = self.widgets['config_attention_mode'].currentData()
            ui_settings['metadata_type'] = self.widgets['config_metadata_type'].currentData()
            ui_settings['clear_file_list'] = self.widgets['config_clear_file_list'].currentData()
            ui_settings['display_stats'] = self.widgets['config_display_stats'].currentData()
            ui_settings['max_frames_multiplier'] = self.widgets['config_max_frames_multiplier'].currentData()
            ui_settings['checkpoints_paths'] = [p.strip() for p in self.widgets['config_checkpoints_paths'].toPlainText().replace("\r", "").split("\n") if p.strip()]
            ui_settings['UI_theme'] = self.widgets['config_UI_theme'].currentData()
            ui_settings['queue_color_scheme'] = self.widgets['config_queue_color_scheme'].currentData()

            ui_settings['transformer_quantization'] = self.widgets['config_transformer_quantization'].currentData()
            ui_settings['transformer_dtype_policy'] = self.widgets['config_transformer_dtype_policy'].currentData()
            ui_settings['mixed_precision'] = self.widgets['config_mixed_precision'].currentData()
            ui_settings['text_encoder_quantization'] = self.widgets['config_text_encoder_quantization'].currentData()
            ui_settings['vae_precision'] = self.widgets['config_vae_precision'].currentData()
            ui_settings['compile'] = self.widgets['config_compile'].currentData()
            ui_settings['depth_anything_v2_variant'] = self.widgets['config_depth_anything_v2_variant'].currentData()
            ui_settings['vae_config'] = self.widgets['config_vae_config'].currentData()
            ui_settings['boost'] = self.widgets['config_boost'].currentData()
            ui_settings['profile'] = self.widgets['config_profile'].currentData()
            ui_settings['preload_in_VRAM'] = self.widgets['config_preload_in_VRAM'].value()

            ui_settings['enhancer_enabled'] = self.widgets['config_enhancer_enabled'].currentData()
            ui_settings['enhancer_mode'] = self.widgets['config_enhancer_mode'].currentData()
            ui_settings['mmaudio_mode'] = self.widgets['config_mmaudio_mode'].currentData()
            ui_settings['mmaudio_persistence'] = self.widgets['config_mmaudio_persistence'].currentData()

            ui_settings['video_output_codec'] = self.widgets['config_video_output_codec'].currentData()
            ui_settings['image_output_codec'] = self.widgets['config_image_output_codec'].currentData()
            ui_settings['audio_output_codec'] = self.widgets['config_audio_output_codec'].currentData()
            ui_settings['embed_source_images'] = self.widgets['config_embed_source_images'].isChecked()
            ui_settings['save_path'] = self.widgets['config_save_path'].text()
            ui_settings['image_save_path'] = self.widgets['config_image_save_path'].text()

            ui_settings['notification_sound_enabled'] = self.widgets['config_notification_sound_enabled'].currentData()
            ui_settings['notification_sound_volume'] = self.widgets['config_notification_sound_volume'].value()

            ui_settings['last_model_type'] = self.state["model_type"]
            ui_settings['last_model_per_family'] = self.state["last_model_per_family"]
            ui_settings['last_model_per_type'] = self.state["last_model_per_type"]
            ui_settings['last_advanced_choice'] = self.state["advanced"]
            ui_settings['last_resolution_choice'] = self.widgets['resolution'].currentData()
            ui_settings['last_resolution_per_group'] = self.state["last_resolution_per_group"]

            wgp.fl.set_checkpoints_paths(ui_settings['checkpoints_paths'])
            wgp.three_levels_hierarchy = ui_settings["model_hierarchy_type"] == 1
            wgp.attention_mode = ui_settings["attention_mode"]
            wgp.default_profile = ui_settings["profile"]
            wgp.compile = ui_settings["compile"]
            wgp.text_encoder_quantization = ui_settings["text_encoder_quantization"]
            wgp.vae_config = ui_settings["vae_config"]
            wgp.boost = ui_settings["boost"]
            wgp.save_path = ui_settings["save_path"]
            wgp.image_save_path = ui_settings["image_save_path"]
            wgp.preload_model_policy = ui_settings["preload_model_policy"]
            wgp.transformer_quantization = ui_settings["transformer_quantization"]
            wgp.transformer_dtype_policy = ui_settings["transformer_dtype_policy"]
            wgp.transformer_types = ui_settings["transformer_types"]
            wgp.reload_needed = True

            with working_directory(wan2gp_dir):
                wgp.server_config.update(ui_settings)
                with open(wgp.server_config_filename, "w", encoding="utf-8") as writer:
                    json.dump(wgp.server_config, writer, indent=4)

            self.config_status_label.setText("Settings saved successfully. Restart may be required for some changes.")
            self.header_info.setText(wgp.generate_header(self.state['model_type'], wgp.compile, wgp.attention_mode))
            self.update_model_dropdowns(wgp.transformer_type)
            self.refresh_ui_from_model_change(wgp.transformer_type)

        except Exception as e:
            self.config_status_label.setText(f"Error applying changes: {e}")
            import traceback; traceback.print_exc()

class Plugin(VideoEditorPlugin):
    def initialize(self):
        self.name = "AI Generator"
        self.description = "Uses the integrated Wan2GP library to generate video clips."
        self.client_widget = None
        self.dock_widget = None
        self._heavy_content_loaded = False
        self.setup_widget = None

        self.active_region = None
        self.temp_dir = None
        self.insert_on_new_track = False
        self.start_frame_path = None
        self.end_frame_path = None
        
        wan2gp_path_override = self.app.settings.get('wan2gp_path')
        if wan2gp_path_override and os.path.exists(wan2gp_path_override):
            global wan2gp_dir
            print(f"AI Generator: Found custom Wan2GP path: {wan2gp_path_override}")
            wan2gp_dir = Path(wan2gp_path_override)

    def enable(self):
        if not self.dock_widget:
            placeholder = QLabel("Loading AI Generator...")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.dock_widget = self.app.add_dock_widget(self, placeholder, self.name)
            self.dock_widget.visibilityChanged.connect(self._on_visibility_changed)
            if self.dock_widget.isVisible():
                self._on_visibility_changed(True)
        
        self.app.timeline_widget.context_menu_requested.connect(self.on_timeline_context_menu)
        self.app.status_label.setText(f"{self.name}: Enabled.")

    def _on_visibility_changed(self, visible):
        if visible and not self._heavy_content_loaded:
            self._load_heavy_ui()

    def _handle_select_folder(self):
        if not self.setup_widget: return
        self.setup_widget.show_message("Waiting for folder selection...")
        
        selected_path_str = QFileDialog.getExistingDirectory(self.app, "Select Wan2GP Installation Folder")

        if not selected_path_str:
            self.setup_widget.show_message("")
            return

        selected_path = Path(selected_path_str)
        wgp_path_check = selected_path / 'wgp.py'
        if not wgp_path_check.exists():
            QMessageBox.warning(self.app, "Invalid Folder", "The selected folder does not contain 'wgp.py'.\nPlease select a valid Wan2GP root directory.")
            self.setup_widget.show_message("Invalid folder selected.")
            return

        self.setup_widget.set_buttons_enabled(False)
        self.setup_widget.show_message("Valid folder selected. Checking requirements...")
        QApplication.processEvents()

        requirements_path = selected_path / 'requirements.txt'

        try:
            if requirements_path.exists():
                import subprocess

                self.setup_widget.show_message("Installing PyTorch... This can take several minutes.")
                QApplication.processEvents()
                torch_command = [
                    sys.executable, "-m", "pip", "install",
                    "torch", "torchvision", "torchaudio",
                    "--index-url", "https://download.pytorch.org/whl/cu130"
                ]
                subprocess.check_call(torch_command)

                self.setup_widget.show_message("Installing other requirements from selected folder...")
                QApplication.processEvents()
                req_command = [
                    sys.executable, "-m", "pip", "install",
                    "-r", str(requirements_path)
                ]
                subprocess.check_call(req_command)
                self.setup_widget.show_message("Dependency installation complete!")

            global wan2gp_dir
            wan2gp_dir = selected_path
            self.app.settings['wan2gp_path'] = selected_path_str
            self.app._save_settings()
            
            QTimer.singleShot(500, self._load_heavy_ui)

        except (subprocess.CalledProcessError, Exception) as e:
            error_message = f"An error occurred installing dependencies.\nPlease check the console for more details.\n\nError: {e}"
            QMessageBox.critical(self.app, "Setup Failed", error_message)
            print(f"Full error details: {e}")
            self.setup_widget.show_message(f"Installation failed. Check console for details.")
            self.setup_widget.set_buttons_enabled(True)

    def _handle_install(self):
        if not self.setup_widget: return
        self.setup_widget.set_buttons_enabled(False)
        
        repo_url = "https://github.com/deepbeepmeep/Wan2GP.git"
        requirements_path = wan2gp_dir / 'requirements.txt'

        if wan2gp_dir.exists():
            reply = QMessageBox.question(
                self.app, "Folder Exists",
                f"The target folder '{wan2gp_dir}' already exists. Delete it and re-clone?\n\nWARNING: This is irreversible.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                self.setup_widget.show_message("Installation cancelled.")
                self.setup_widget.set_buttons_enabled(True)
                return
            try:
                shutil.rmtree(wan2gp_dir)
            except OSError as e:
                QMessageBox.critical(self.app, "Error", f"Failed to delete existing directory: {e}")
                self.setup_widget.show_message("Error: Could not delete folder.")
                self.setup_widget.set_buttons_enabled(True)
                return

        self.setup_widget.show_message("Cloning Wan2GP repository...")
        QApplication.processEvents()
        
        try:
            import git
            import subprocess
            
            git.Repo.clone_from(repo_url, wan2gp_dir)
            
            if str(wan2gp_dir) not in sys.path:
                sys.path.insert(0, str(wan2gp_dir))

            self.setup_widget.show_message("Installing PyTorch... This can take several minutes.")
            QApplication.processEvents()
            torch_command = [
                sys.executable, "-m", "pip", "install",
                "torch", "torchvision", "torchaudio",
                "--index-url", "https://download.pytorch.org/whl/cu130"
            ]
            subprocess.check_call(torch_command)

            self.setup_widget.show_message("Installing other requirements...")
            QApplication.processEvents()
            req_command = [
                sys.executable, "-m", "pip", "install",
                "-r", str(requirements_path)
            ]
            subprocess.check_call(req_command)

            self.setup_widget.show_message("Installation complete! Loading plugin...")
            QMessageBox.information(
                self.app, "Installation Complete",
                "Wan2GP and its dependencies have been successfully installed. The plugin will now load."
            )
            
            QTimer.singleShot(500, self._load_heavy_ui)

        except (git.exc.GitCommandError, subprocess.CalledProcessError, Exception) as e:
            error_message = f"An error occurred during setup.\n\nPlease ensure 'git' is installed and you have an internet connection.\nCheck the console for more details.\n\nError: {e}"
            QMessageBox.critical(self.app, "Setup Failed", error_message)
            print(f"Full error details: {e}")
            self.setup_widget.show_message(f"Installation failed. Check console for details.")
            self.setup_widget.set_buttons_enabled(True)
            if wan2gp_dir.exists():
                shutil.rmtree(wan2gp_dir, ignore_errors=True)

    def _load_heavy_ui(self):
        if self._heavy_content_loaded:
            return True

        wgp_path = wan2gp_dir / 'wgp.py'

        if not wgp_path.exists():
            self.setup_widget = Wan2GPSetupWidget(self)
            self.dock_widget.setWidget(self.setup_widget)
            return False

        self.app.status_label.setText("Loading AI Generator backend...")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        try:
            import importlib
            global wgp
            if wgp is None:
                with working_directory(wan2gp_dir):
                    module_name = "wgp"
                    spec = importlib.util.spec_from_file_location(module_name, wgp_path)
                    
                    if spec is None or spec.loader is None:
                        raise ImportError(f"Could not create a module spec for the file at {wgp_path}")

                    wgp_module = importlib.util.module_from_spec(spec)

                    original_sys_path = list(sys.path)
                    if str(wan2gp_dir) not in sys.path:
                        sys.path.insert(0, str(wan2gp_dir))

                    try:
                        spec.loader.exec_module(wgp_module)
                    finally:
                        sys.path[:] = original_sys_path

                    wgp = wgp_module

            wgp.app = MockApp()
            self.client_widget = WgpDesktopPluginWidget(self)
            self.dock_widget.setWidget(self.client_widget)
            self._heavy_content_loaded = True
            self.app.status_label.setText("AI Generator loaded.")
            self.setup_widget = None
            return True
        except Exception as e:
            print(f"Failed to load AI Generator plugin backend: {e}")
            import traceback
            traceback.print_exc()
            error_label = QLabel(f"Failed to load AI Generator:\n\n{e}\n\nPlease see console for details.")
            error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            error_label.setWordWrap(True)
            if self.dock_widget:
                self.dock_widget.setWidget(error_label)
            QMessageBox.critical(self.app, "Plugin Load Error", f"Failed to load the AI Generator backend.\n\n{e}")
            return False
        finally:
            QApplication.restoreOverrideCursor()

    def disable(self):
        try: self.app.timeline_widget.context_menu_requested.disconnect(self.on_timeline_context_menu)
        except TypeError: pass

        if self.dock_widget:
            try: self.dock_widget.visibilityChanged.disconnect(self._on_visibility_changed)
            except TypeError: pass

        self._cleanup_temp_dir()
        if self.client_widget and self.client_widget.worker:
            self.client_widget._on_abort()
            
        self.app.status_label.setText(f"{self.name}: Disabled.")

    def _ensure_ui_loaded(self):
        if not self._heavy_content_loaded:
            if not self._load_heavy_ui():
                return False
        return True

    def _cleanup_temp_dir(self):
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
            self.temp_dir = None
            
    def _reset_state(self):
        self.active_region = None; self.insert_on_new_track = False
        self.start_frame_path = None; self.end_frame_path = None
        if self._heavy_content_loaded:
            self.client_widget.processed_files.clear()
            self.client_widget.results_list.clear()
            self.client_widget.widgets['image_start'].clear()
            self.client_widget.widgets['image_end'].clear()
            self.client_widget.widgets['video_source'].clear()
        self._cleanup_temp_dir()
        self.app.status_label.setText(f"{self.name}: Ready.")

    def on_timeline_context_menu(self, menu, event):
        region = self.app.timeline_widget.get_region_at_pos(event.pos())
        if region:
            menu.addSeparator()
            start_ms, end_ms = region
            start_data, _, _ = self.app.get_frame_data_at_time(start_ms)
            end_data, _, _ = self.app.get_frame_data_at_time(end_ms)

            if start_data and end_data:
                join_action = menu.addAction("Join Frames With AI")
                join_action.triggered.connect(lambda: self.setup_generator_for_region(region, on_new_track=False))
                join_action_new_track = menu.addAction("Join Frames With AI (New Track)")
                join_action_new_track.triggered.connect(lambda: self.setup_generator_for_region(region, on_new_track=True))
            elif start_data:
                from_start_action = menu.addAction("Generate from Start Frame with AI")
                from_start_action.triggered.connect(lambda: self.setup_generator_from_start(region, on_new_track=False))
                from_start_action_new_track = menu.addAction("Generate from Start Frame with AI (New Track)")
                from_start_action_new_track.triggered.connect(lambda: self.setup_generator_from_start(region, on_new_track=True))
            elif end_data:
                to_end_action = menu.addAction("Generate to End Frame with AI")
                to_end_action.triggered.connect(lambda: self.setup_generator_to_end(region, on_new_track=False))
                to_end_action_new_track = menu.addAction("Generate to End Frame with AI (New Track)")
                to_end_action_new_track.triggered.connect(lambda: self.setup_generator_to_end(region, on_new_track=True))

            create_action = menu.addAction("Create Frames With AI")
            create_action.triggered.connect(lambda: self.setup_creator_for_region(region, on_new_track=False))
            create_action_new_track = menu.addAction("Create Frames With AI (New Track)")
            create_action_new_track.triggered.connect(lambda: self.setup_creator_for_region(region, on_new_track=True))

    def setup_generator_for_region(self, region, on_new_track=False):
        if not self._ensure_ui_loaded(): return
        self._reset_state()
        self.active_region = region
        self.insert_on_new_track = on_new_track

        model_to_set = 'i2v_2_2' 
        dropdown_types = wgp.transformer_types if len(wgp.transformer_types) > 0 else wgp.displayed_model_types
        _, _, all_models = wgp.get_sorted_dropdown(dropdown_types, None, None, False)
        if any(model_to_set == m[1] for m in all_models):
            if self.client_widget.state.get('model_type') != model_to_set:
                self.client_widget.update_model_dropdowns(model_to_set)
                self.client_widget._on_model_changed()
        else:
            print(f"Warning: Default model '{model_to_set}' not found for AI Joiner. Using current model.")
        
        start_ms, end_ms = region
        start_data, w, h = self.app.get_frame_data_at_time(start_ms)
        end_data, _, _ = self.app.get_frame_data_at_time(end_ms)
        if not start_data or not end_data:
            QMessageBox.warning(self.app, "Frame Error", "Could not extract start and/or end frames.")
            return
        
        self.client_widget.set_resolution_from_target(w, h)
        
        try:
            self.temp_dir = tempfile.mkdtemp(prefix="wgp_plugin_")
            self.start_frame_path = os.path.join(self.temp_dir, "start_frame.png")
            self.end_frame_path = os.path.join(self.temp_dir, "end_frame.png")
            QImage(start_data, w, h, QImage.Format.Format_RGB888).save(self.start_frame_path)
            QImage(end_data, w, h, QImage.Format.Format_RGB888).save(self.end_frame_path)
            
            duration_ms = end_ms - start_ms
            model_type = self.client_widget.state['model_type']
            fps = wgp.get_model_fps(model_type)
            video_length_frames = int(round(((duration_ms / 1000.0) * fps - 1) / 4)) * 4 + 1
            widgets = self.client_widget.widgets
            
            for w_name in ['mode_s', 'mode_t', 'mode_v', 'mode_l', 'image_end_checkbox']:
                widgets[w_name].blockSignals(True)

            widgets['video_length'].setValue(video_length_frames)
            widgets['mode_s'].setChecked(True)
            widgets['image_end_checkbox'].setChecked(True)
            widgets['image_start'].setText(self.start_frame_path)
            widgets['image_end'].setText(self.end_frame_path)

            for w_name in ['mode_s', 'mode_t', 'mode_v', 'mode_l', 'image_end_checkbox']:
                widgets[w_name].blockSignals(False)

            self.client_widget._update_input_visibility()

        except Exception as e:
            QMessageBox.critical(self.app, "File Error", f"Could not save temporary frame images: {e}")
            self._cleanup_temp_dir()
            return
        self.app.status_label.setText(f"Ready to join frames from {start_ms / 1000.0:.2f}s to {end_ms / 1000.0:.2f}s.")
        self.dock_widget.show()
        self.dock_widget.raise_()

    def setup_generator_from_start(self, region, on_new_track=False):
        if not self._ensure_ui_loaded(): return
        self._reset_state()
        self.active_region = region
        self.insert_on_new_track = on_new_track

        model_to_set = 'i2v_2_2' 
        dropdown_types = wgp.transformer_types if len(wgp.transformer_types) > 0 else wgp.displayed_model_types
        _, _, all_models = wgp.get_sorted_dropdown(dropdown_types, None, None, False)
        if any(model_to_set == m[1] for m in all_models):
            if self.client_widget.state.get('model_type') != model_to_set:
                self.client_widget.update_model_dropdowns(model_to_set)
                self.client_widget._on_model_changed()
        else:
            print(f"Warning: Default model '{model_to_set}' not found for AI Joiner. Using current model.")
        
        start_ms, end_ms = region
        start_data, w, h = self.app.get_frame_data_at_time(start_ms)
        if not start_data:
            QMessageBox.warning(self.app, "Frame Error", "Could not extract start frame.")
            return
        
        self.client_widget.set_resolution_from_target(w, h)
        
        try:
            self.temp_dir = tempfile.mkdtemp(prefix="wgp_plugin_")
            self.start_frame_path = os.path.join(self.temp_dir, "start_frame.png")
            QImage(start_data, w, h, QImage.Format.Format_RGB888).save(self.start_frame_path)
            
            duration_ms = end_ms - start_ms
            model_type = self.client_widget.state['model_type']
            fps = wgp.get_model_fps(model_type)
            video_length_frames = int(round(((duration_ms / 1000.0) * fps - 1) / 4)) * 4 + 1
            widgets = self.client_widget.widgets
            
            widgets['video_length'].setValue(video_length_frames)
            
            for w_name in ['mode_s', 'mode_t', 'mode_v', 'mode_l', 'image_end_checkbox']:
                widgets[w_name].blockSignals(True)
            
            widgets['mode_s'].setChecked(True)
            widgets['image_end_checkbox'].setChecked(False)
            widgets['image_start'].setText(self.start_frame_path)
            widgets['image_end'].clear()

            for w_name in ['mode_s', 'mode_t', 'mode_v', 'mode_l', 'image_end_checkbox']:
                widgets[w_name].blockSignals(False)

            self.client_widget._update_input_visibility()

        except Exception as e:
            QMessageBox.critical(self.app, "File Error", f"Could not save temporary frame image: {e}")
            self._cleanup_temp_dir()
            return

        self.app.status_label.setText(f"Ready to generate from frame at {start_ms / 1000.0:.2f}s.")
        self.dock_widget.show()
        self.dock_widget.raise_()

    def setup_generator_to_end(self, region, on_new_track=False):
        if not self._ensure_ui_loaded(): return
        self._reset_state()
        self.active_region = region
        self.insert_on_new_track = on_new_track

        model_to_set = 'i2v_2_2' 
        dropdown_types = wgp.transformer_types if len(wgp.transformer_types) > 0 else wgp.displayed_model_types
        _, _, all_models = wgp.get_sorted_dropdown(dropdown_types, None, None, False)
        if any(model_to_set == m[1] for m in all_models):
            if self.client_widget.state.get('model_type') != model_to_set:
                self.client_widget.update_model_dropdowns(model_to_set)
                self.client_widget._on_model_changed()
        else:
            print(f"Warning: Default model '{model_to_set}' not found for AI Joiner. Using current model.")
        
        start_ms, end_ms = region
        end_data, w, h = self.app.get_frame_data_at_time(end_ms)
        if not end_data:
            QMessageBox.warning(self.app, "Frame Error", "Could not extract end frame.")
            return
        
        self.client_widget.set_resolution_from_target(w, h)
        
        try:
            self.temp_dir = tempfile.mkdtemp(prefix="wgp_plugin_")
            self.end_frame_path = os.path.join(self.temp_dir, "end_frame.png")
            QImage(end_data, w, h, QImage.Format.Format_RGB888).save(self.end_frame_path)
            
            duration_ms = end_ms - start_ms
            model_type = self.client_widget.state['model_type']
            fps = wgp.get_model_fps(model_type)
            video_length_frames = int(round(((duration_ms / 1000.0) * fps - 1) / 4)) * 4 + 1
            widgets = self.client_widget.widgets
            
            widgets['video_length'].setValue(video_length_frames)

            model_def = wgp.get_model_def(self.client_widget.state['model_type'])
            allowed_modes = model_def.get("image_prompt_types_allowed", "")

            if "E" not in allowed_modes:
                QMessageBox.warning(self.app, "Model Incompatible", "The current model does not support generating to an end frame.")
                return

            if "S" not in allowed_modes:
                 QMessageBox.warning(self.app, "Model Incompatible", "The current model supports end frames, but not in a way compatible with this UI feature (missing 'Start with Image' mode).")
                 return

            for w_name in ['mode_s', 'mode_t', 'mode_v', 'mode_l', 'image_end_checkbox']:
                widgets[w_name].blockSignals(True)
            
            widgets['mode_s'].setChecked(True)
            widgets['image_end_checkbox'].setChecked(True)
            widgets['image_start'].clear()
            widgets['image_end'].setText(self.end_frame_path)

            for w_name in ['mode_s', 'mode_t', 'mode_v', 'mode_l', 'image_end_checkbox']:
                widgets[w_name].blockSignals(False)

            self.client_widget._update_input_visibility()

        except Exception as e:
            QMessageBox.critical(self.app, "File Error", f"Could not save temporary frame image: {e}")
            self._cleanup_temp_dir()
            return
            
        self.app.status_label.setText(f"Ready to generate to frame at {end_ms / 1000.0:.2f}s.")
        self.dock_widget.show()
        self.dock_widget.raise_()

    def setup_creator_for_region(self, region, on_new_track=False):
        if not self._ensure_ui_loaded(): return
        self._reset_state()
        self.active_region = region
        self.insert_on_new_track = on_new_track

        model_to_set = 't2v_2_2'
        dropdown_types = wgp.transformer_types if len(wgp.transformer_types) > 0 else wgp.displayed_model_types
        _, _, all_models = wgp.get_sorted_dropdown(dropdown_types, None, None, False)
        if any(model_to_set == m[1] for m in all_models):
            if self.client_widget.state.get('model_type') != model_to_set:
                self.client_widget.update_model_dropdowns(model_to_set)
                self.client_widget._on_model_changed()
        else:
            print(f"Warning: Default model '{model_to_set}' not found for AI Creator. Using current model.")

        target_w = self.app.project_width
        target_h = self.app.project_height
        self.client_widget.set_resolution_from_target(target_w, target_h)

        start_ms, end_ms = region
        duration_ms = end_ms - start_ms
        model_type = self.client_widget.state['model_type']
        fps = wgp.get_model_fps(model_type)
        video_length_frames = int(round(((duration_ms / 1000.0) * fps - 1) / 4)) * 4 + 1
        
        self.client_widget.widgets['video_length'].setValue(video_length_frames)
        self.client_widget.widgets['mode_t'].setChecked(True)

        self.app.status_label.setText(f"Ready to create video from {start_ms / 1000.0:.2f}s to {end_ms / 1000.0:.2f}s.")
        self.dock_widget.show()
        self.dock_widget.raise_()

    def insert_generated_clip(self, video_path):
        from videoeditor import TimelineClip
        if not self.active_region:
            self.app.status_label.setText("Error: No active region to insert into."); return
        if not os.path.exists(video_path):
            self.app.status_label.setText(f"Error: Output file not found: {video_path}"); return
        start_ms, end_ms = self.active_region
        def complex_insertion_action():
            self.app._add_media_files_to_project([video_path])
            media_info = self.app.media_properties.get(video_path)
            if not media_info: raise ValueError("Could not probe inserted clip.")
            actual_duration_ms, has_audio = media_info['duration_ms'], media_info['has_audio']
            if self.insert_on_new_track:
                self.app.timeline.num_video_tracks += 1
                video_track_index = self.app.timeline.num_video_tracks
                audio_track_index = self.app.timeline.num_audio_tracks + 1 if has_audio else None
            else:
                for clip in list(self.app.timeline.clips): self.app._split_at_time(clip, start_ms)
                for clip in list(self.app.timeline.clips): self.app._split_at_time(clip, end_ms)
                clips_to_remove = [c for c in self.app.timeline.clips if c.timeline_start_ms >= start_ms and c.timeline_end_ms <= end_ms]
                for clip in clips_to_remove:
                    if clip in self.app.timeline.clips: self.app.timeline.clips.remove(clip)
                video_track_index, audio_track_index = 1, 1 if has_audio else None
            group_id = str(uuid.uuid4())
            new_clip = TimelineClip(video_path, start_ms, 0, actual_duration_ms, video_track_index, 'video', 'video', group_id)
            self.app.timeline.add_clip(new_clip)
            if audio_track_index:
                if audio_track_index > self.app.timeline.num_audio_tracks: self.app.timeline.num_audio_tracks = audio_track_index
                audio_clip = TimelineClip(video_path, start_ms, 0, actual_duration_ms, audio_track_index, 'audio', 'video', group_id)
                self.app.timeline.add_clip(audio_clip)
        try:
            self.app._perform_complex_timeline_change("Insert AI Clip", complex_insertion_action)
            self.app.prune_empty_tracks()
            self.app.status_label.setText("AI clip inserted successfully.")
            for i in range(self.client_widget.results_list.count()):
                widget = self.client_widget.results_list.itemWidget(self.client_widget.results_list.item(i))
                if widget and widget.video_path == video_path:
                    self.client_widget.results_list.takeItem(i); break
        except Exception as e:
            import traceback; traceback.print_exc()
            self.app.status_label.setText(f"Error during clip insertion: {e}")