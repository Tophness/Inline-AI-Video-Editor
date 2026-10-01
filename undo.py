import copy
from PyQt6.QtCore import QObject, pyqtSignal

class UndoCommand:
    def __init__(self, description=""):
        self.description = description
        self.executed = True

    def undo(self):
        raise NotImplementedError

    def redo(self):
        raise NotImplementedError

class CompositeCommand(UndoCommand):
    def __init__(self, description, commands):
        super().__init__(description)
        self.commands = commands

    def undo(self):
        for cmd in reversed(self.commands):
            cmd.undo()
        self.executed = False

    def redo(self):
        for cmd in self.commands:
            cmd.redo()
        self.executed = True

class ProjectSnapshot:
    def __init__(self, clips, num_video_tracks, num_audio_tracks,
                 project_width, project_height, project_fps,
                 media_pool=None, media_properties=None, selected_clip_ids=None,
                 selection_regions=None, hidden_video_tracks=None, muted_audio_tracks=None):
        self.clips = [c.clone() if hasattr(c, 'clone') else copy.deepcopy(c) for c in clips]
        self.num_video_tracks = int(num_video_tracks)
        self.num_audio_tracks = int(num_audio_tracks)
        self.project_width = int(project_width)
        self.project_height = int(project_height)
        self.project_fps = float(project_fps)
        self.media_pool = list(media_pool) if media_pool is not None else []
        self.media_properties = copy.deepcopy(media_properties) if media_properties is not None else {}
        self.selected_clip_ids = set(selected_clip_ids) if selected_clip_ids is not None else set()
        self.selection_regions = copy.deepcopy(selection_regions) if selection_regions is not None else []
        self.hidden_video_tracks = set(hidden_video_tracks) if hidden_video_tracks is not None else set()
        self.muted_audio_tracks = set(muted_audio_tracks) if muted_audio_tracks is not None else set()

    def clone(self):
        return ProjectSnapshot(
            self.clips, self.num_video_tracks, self.num_audio_tracks,
            self.project_width, self.project_height, self.project_fps,
            self.media_pool, self.media_properties, self.selected_clip_ids,
            self.selection_regions, self.hidden_video_tracks, self.muted_audio_tracks
        )

    def __getitem__(self, idx):
        if idx == 0: return self.clips
        elif idx == 1: return self.num_video_tracks
        elif idx == 2: return self.num_audio_tracks
        raise IndexError(f"Index {idx} out of range for ProjectSnapshot")

    def is_equal_to(self, other):
        if not isinstance(other, ProjectSnapshot):
            return False
        if (self.num_video_tracks != other.num_video_tracks or
            self.num_audio_tracks != other.num_audio_tracks or
            self.project_width != other.project_width or
            self.project_height != other.project_height or
            abs(self.project_fps - other.project_fps) > 1e-5 or
            self.media_pool != other.media_pool or
            self.hidden_video_tracks != getattr(other, 'hidden_video_tracks', set()) or
            self.muted_audio_tracks != getattr(other, 'muted_audio_tracks', set()) or
            len(self.clips) != len(other.clips)):
            return False
        for c1, c2 in zip(self.clips, other.clips):
            if c1 != c2:
                return False
        return True

class TimelineStateChangeCommand(UndoCommand):
    def __init__(self, description, target, *args, **kwargs):
        super().__init__(description)
        self.executed = kwargs.get('executed', True)
        self.main_window = None
        self.timeline = None
        self.before_snapshot = None
        self.after_snapshot = None

        if len(args) == 2 and isinstance(args[0], ProjectSnapshot):
            self.main_window = target
            self.before_snapshot = args[0].clone()
            self.after_snapshot = args[1].clone()
        elif len(args) == 6:
            self.timeline = target
            self.old_clips_state = [c.clone() if hasattr(c, 'clone') else copy.deepcopy(c) for c in args[0]]
            self.old_v_tracks = args[1]
            self.old_a_tracks = args[2]
            self.new_clips_state = [c.clone() if hasattr(c, 'clone') else copy.deepcopy(c) for c in args[3]]
            self.new_v_tracks = args[4]
            self.new_a_tracks = args[5]
        else:
            raise ValueError(f"Invalid arguments for TimelineStateChangeCommand: {args}")

    def undo(self):
        if self.before_snapshot is not None and self.main_window is not None:
            self.main_window._restore_snapshot(self.before_snapshot)
        elif self.timeline is not None:
            self.timeline.clips = [c.clone() if hasattr(c, 'clone') else copy.deepcopy(c) for c in self.old_clips_state]
            self.timeline.num_video_tracks = self.old_v_tracks
            self.timeline.num_audio_tracks = self.old_a_tracks
        self.executed = False

    def redo(self):
        if self.after_snapshot is not None and self.main_window is not None:
            self.main_window._restore_snapshot(self.after_snapshot)
        elif self.timeline is not None:
            self.timeline.clips = [c.clone() if hasattr(c, 'clone') else copy.deepcopy(c) for c in self.new_clips_state]
            self.timeline.num_video_tracks = self.new_v_tracks
            self.timeline.num_audio_tracks = self.new_a_tracks
        self.executed = True

class MoveClipsCommand(UndoCommand):
    def __init__(self, description, timeline_model, move_data):
        super().__init__(description)
        self.timeline = timeline_model
        self.move_data = move_data

    def _apply_state(self, state_key_prefix):
        for data in self.move_data:
            clip_id = data['clip_id']
            clip = next((c for c in self.timeline.clips if c.id == clip_id), None)
            if clip:
                clip.timeline_start_ms = data[f'{state_key_prefix}_start']
                clip.track_index = data[f'{state_key_prefix}_track']
        self.timeline.clips.sort(key=lambda c: c.timeline_start_ms)

    def undo(self):
        self._apply_state('old')
        self.executed = False

    def redo(self):
        self._apply_state('new')
        self.executed = True

class UndoStack(QObject):
    history_changed = pyqtSignal()
    timeline_changed = pyqtSignal()

    def __init__(self, max_history=100, parent=None):
        super().__init__(parent)
        self.undo_stack = []
        self.redo_stack = []
        self.max_history = max_history

    def push(self, command, execute=False):
        if execute or not getattr(command, 'executed', True):
            command.redo()
            command.executed = True
        self.undo_stack.append(command)
        self.redo_stack.clear()
        if len(self.undo_stack) > self.max_history:
            self.undo_stack.pop(0)
        self.history_changed.emit()
        self.timeline_changed.emit()

    def undo(self):
        if not self.can_undo():
            return
        self.undo_steps(1)

    def redo(self):
        if not self.can_redo():
            return
        self.redo_steps(1)

    def undo_steps(self, count):
        if count <= 0 or not self.undo_stack:
            return
        actual_count = min(count, len(self.undo_stack))
        for _ in range(actual_count):
            command = self.undo_stack.pop()
            self.redo_stack.append(command)
            command.undo()
        self.history_changed.emit()
        self.timeline_changed.emit()

    def redo_steps(self, count):
        if count <= 0 or not self.redo_stack:
            return
        actual_count = min(count, len(self.redo_stack))
        for _ in range(actual_count):
            command = self.redo_stack.pop()
            self.undo_stack.append(command)
            command.redo()
        self.history_changed.emit()
        self.timeline_changed.emit()

    def can_undo(self):
        return bool(self.undo_stack)

    def can_redo(self):
        return bool(self.redo_stack)

    def undo_text(self):
        return self.undo_stack[-1].description if self.can_undo() else ""

    def redo_text(self):
        return self.redo_stack[-1].description if self.can_redo() else ""

    def get_undo_descriptions(self):
        return [cmd.description for cmd in reversed(self.undo_stack)]

    def get_redo_descriptions(self):
        return [cmd.description for cmd in reversed(self.redo_stack)]

    def clear(self):
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.history_changed.emit()