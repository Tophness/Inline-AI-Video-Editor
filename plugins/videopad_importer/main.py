import os
import uuid
import re
import urllib.parse
from PyQt6.QtWidgets import QFileDialog, QMessageBox
from PyQt6.QtGui import QAction

from plugins import VideoEditorPlugin
from videoeditor import TimelineClip

class VPJParser:
    def __init__(self, file_path):
        self.file_path = file_path
        self.media_clips = {}
        self.tracks = {}
        self.timeline_clips = []
        self.missing_files = set()

    def _parse_line(self, line):
        params = {}
        parts = line.strip().split('&')
        for part in parts:
            kv = part.split('=', 1)
            if len(kv) == 2:
                key, value = kv
                try:
                    params[key] = urllib.parse.unquote(value)
                except Exception:
                    params[key] = value
        return params

    def parse(self):
        try:
            with open(self.file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception as e:
            print(f"FATAL: Error reading VPJ file: {e}")
            return None
        clips_match = re.search(r'clips=\d+.*?\n(.*?)(?=\ntracks=\d+)', content, re.DOTALL)
        
        if clips_match:
            clips_block = clips_match.group(1).strip()
            for line in clips_block.split('\n'):
                if not line.strip().startswith('h='): continue
                params = self._parse_line(line)
                if 'h' in params and 'path' in params:
                    self.media_clips[params['h']] = params
            if self.media_clips:
                first_key = next(iter(self.media_clips))
        else:
            print("[DEBUG] Did not find 'clips' section.")

        tracks_match = re.search(r'tracks=\d+\n(.*?)(?=\ntrackclips=\d+)', content, re.DOTALL)
        if tracks_match:
            tracks_block = tracks_match.group(1).strip()
            for line in tracks_block.split('\n'):
                if not line.strip().startswith('h='): continue
                params = self._parse_line(line)
                if 'h' in params and 'type' in params:
                    self.tracks[params['h']] = params
            if self.tracks:
                first_key = next(iter(self.tracks))

        else:
            print("[DEBUG] Did not find 'tracks' section.")

        trackclips_match = re.search(r'trackclips=\d+\n(.*?)(?=\nsubtitletracks=\d+)', content, re.DOTALL)
        if trackclips_match:
            trackclips_block = trackclips_match.group(1).strip()
            for line in trackclips_block.split('\n'):
                if not line.strip().startswith('h='): continue
                params = self._parse_line(line)
                if 'horiginalclip' in params and 'htrack' in params:
                    self.timeline_clips.append(params)
        else:
            print("[DEBUG] Did not find 'trackclips' section.")
        
        if not self.media_clips and not self.timeline_clips:
            print("VPJ Parser: Could not find any clips or tracks in the file. Parsing failed.")
            return None

        return {
            "media": self.media_clips,
            "tracks": self.tracks,
            "timeline": self.timeline_clips
        }


class Plugin(VideoEditorPlugin):
    def __init__(self, app_instance):
        super().__init__(app_instance)
        self.name = "VideoPad Importer"
        self.description = "Imports project files (.vpj) from VideoPad Video Editor."
        self.import_action = None

    def initialize(self):
        self.import_action = QAction("Import VideoPad Project...", self.app)
        self.import_action.triggered.connect(self.run_import_process)
        self.import_action.setVisible(False)

    def enable(self):
        if not self.import_action:
            return

        menu_bar = self.app.menuBar()
        file_menu = next((action.menu() for action in menu_bar.actions() if action.text() == "&File"), None)

        if file_menu and self.import_action not in file_menu.actions():
            target_action = next((action for action in file_menu.actions() if "Export" in action.text()), None)
            if target_action:
                file_menu.insertAction(target_action, self.import_action)
                file_menu.insertSeparator(target_action)
            else:
                file_menu.addSeparator()
                file_menu.addAction(self.import_action)

        self.import_action.setVisible(True)

    def disable(self):
        if self.import_action:
            self.import_action.setVisible(False)

    def run_import_process(self):
        path, _ = QFileDialog.getOpenFileName(self.app, "Open VideoPad Project", "", "VideoPad Project Files (*.vpj)")
        if not path:
            return

        if self.app.timeline.clips or self.app.media_pool:
            reply = QMessageBox.question(self.app, "Confirm Import",
                                         "This will clear your current project. Are you sure you want to continue?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                         QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.No:
                return

        parser = VPJParser(path)
        parsed_data = parser.parse()

        if not parsed_data or not parsed_data.get("timeline") or not parsed_data.get("media"):
            QMessageBox.critical(self.app, "Import Error", "Failed to parse the VideoPad project file or no media/timeline clips were found. See console for debug info.")
            return
            
        self.app.new_project()
        
        description = f"Import VideoPad Project '{os.path.basename(path)}'"
        self.app._perform_complex_timeline_change(description, lambda: self.populate_timeline(parsed_data))

    def populate_timeline(self, data):
        media_clips_map = data.get("media", {})
        tracks_map = data.get("tracks", {})
        timeline_clips_data = data.get("timeline", [])
        print(f"Received {len(media_clips_map)} media clips, {len(tracks_map)} tracks, {len(timeline_clips_data)} timeline clips from parser.")
        
        missing_files = set()
        clips_created = 0

        self.app.status_label.setText("Importing media files...")
        for h_id, clip_data in media_clips_map.items():
            path = clip_data.get('path')
            if path and os.path.exists(path):
                self.app._add_media_files_to_project([path])
            elif path:
                print(f"  -> WARNING: Media file not found: {path}")
                missing_files.add(path)
        
        self.app.status_label.setText("Building timeline...")

        vpj_track_map = {}
        v_track_count, a_track_count = 0, 0
        sorted_tracks = sorted(tracks_map.values(), key=lambda t: t.get('name', ''))
        
        for track_data in sorted_tracks:
            h = track_data.get('h')
            if track_data.get('type') == '1':
                v_track_count += 1
                vpj_track_map[h] = {'type': 'video', 'index': v_track_count}
            elif track_data.get('type') == '2':
                a_track_count += 1
                vpj_track_map[h] = {'type': 'audio', 'index': a_track_count}

        if v_track_count > self.app.timeline.num_video_tracks:
            self.app.timeline.num_video_tracks = v_track_count
        if a_track_count > self.app.timeline.num_audio_tracks:
            self.app.timeline.num_audio_tracks = a_track_count

        group_id_map = {}
        for i, clip_data in enumerate(timeline_clips_data):
            orig_clip_h = clip_data.get('horiginalclip')
            track_h = clip_data.get('htrack')
            
            source_media = media_clips_map.get(orig_clip_h)
            track_info = vpj_track_map.get(track_h)
            
            if not source_media:
                print(f"    -> FAILED: Original media clip (h={orig_clip_h}) not found in media map.")
                continue
            if not track_info:
                print(f"    -> FAILED: Track (h={track_h}) not found in track map.")
                continue

            path = source_media.get('path')
            if not path or not os.path.exists(path):
                print(f"    -> FAILED: Source file path '{path}' does not exist.")
                continue
                
            media_properties = self.app.media_properties.get(path)
            if not media_properties:
                print(f"    -> FAILED: Could not find media properties for {path}. Was it added to the pool?")
                continue

            try:
                timeline_start_ms = int(float(clip_data.get('offset', '0')))
                clip_start_ms = int(float(clip_data.get('in', '0')))
                clip_end_ms = int(float(clip_data.get('out', '0')))
                duration_ms = clip_end_ms - clip_start_ms
                if duration_ms <= 0:
                    print("    -> FAILED: Calculated duration is zero or negative.")
                    continue
            except (ValueError, TypeError) as e:
                print(f"    -> FAILED: Invalid time value in clip data. Error: {e}")
                continue

            group_id = None
            clip_h = clip_data.get('h')
            linked_h = clip_data.get('hlinked', '0')
            
            if linked_h != '0':
                if linked_h in group_id_map:
                    group_id = group_id_map[linked_h]
                else:
                    group_id = str(uuid.uuid4())
                    group_id_map[clip_h] = group_id
            else:
                 group_id = group_id_map.get(clip_h, str(uuid.uuid4()))

            new_clip = TimelineClip(
                source_path=path,
                timeline_start_ms=timeline_start_ms,
                clip_start_ms=clip_start_ms,
                duration_ms=duration_ms,
                track_index=track_info['index'],
                track_type=track_info['type'],
                media_type=media_properties['media_type'],
                group_id=group_id
            )
            self.app.timeline.add_clip(new_clip)
            clips_created += 1

        if missing_files:
            msg = "Import completed, but some media files could not be found:\n\n"
            msg += "\n".join(list(missing_files)[:10])
            if len(missing_files) > 10:
                msg += f"\n...and {len(missing_files) - 10} more."
            QMessageBox.warning(self.app, "Missing Files", msg)
            self.app.status_label.setText(f"Import complete with {len(missing_files)} missing file(s).")
        else:
            self.app.status_label.setText("VideoPad project imported successfully.")
        
        self.app.timeline_widget.update()
        self.app.playback_manager.seek_to_frame(0)