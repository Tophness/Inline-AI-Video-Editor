import ffmpeg
import subprocess
import re
import shlex
import os
import tempfile
import uuid
from PyQt6.QtCore import QObject, pyqtSignal, QThread

class _ExportRunner(QObject):
    progress = pyqtSignal(int)
    finished = pyqtSignal(bool, str)

    def __init__(self, ffmpeg_cmd, total_duration_ms, prep_cmds=None, temp_files=None, parent=None):
        super().__init__(parent)
        self.ffmpeg_cmd = ffmpeg_cmd
        self.total_duration_ms = total_duration_ms
        self.prep_cmds = prep_cmds or []
        self.temp_files = temp_files or []
        self.process = None

    def run(self):
        try:
            startupinfo = None
            if hasattr(subprocess, 'STARTUPINFO'):
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            for cmd in self.prep_cmds:
                self.process = subprocess.Popen(
                    cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                    startupinfo=startupinfo
                )
                _, stderr = self.process.communicate()
                if self.process.returncode != 0:
                    self._cleanup_temp_files()
                    self.finished.emit(False, f"Stream copy segment preparation failed: {stderr.decode('utf-8', errors='ignore')}")
                    return

            self.process = subprocess.Popen(
                self.ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                encoding="utf-8",
                errors='ignore',
                startupinfo=startupinfo
            )

            full_output = []
            time_pattern = re.compile(r"time=(\d{2}):(\d{2}):(\d{2})\.(\d{2})")

            for line in iter(self.process.stdout.readline, ""):
                full_output.append(line)
                match = time_pattern.search(line)
                if match:
                    h, m, s, cs = [int(g) for g in match.groups()]
                    processed_ms = (h * 3600 + m * 60 + s) * 1000 + cs * 10
                    if self.total_duration_ms > 0:
                        percentage = int((processed_ms / self.total_duration_ms) * 100)
                        self.progress.emit(min(100, percentage))

            self.process.stdout.close()
            return_code = self.process.wait()

            self._cleanup_temp_files()

            if return_code == 0:
                self.progress.emit(100)
                self.finished.emit(True, "Export completed successfully!")
            else:
                print("--- FFmpeg Export FAILED ---")
                print("Command: " + " ".join(self.ffmpeg_cmd))
                print("".join(full_output))
                self.finished.emit(False, f"Export failed with code {return_code}. Check console.")

        except FileNotFoundError:
            self._cleanup_temp_files()
            self.finished.emit(False, "Export failed: ffmpeg.exe not found in your system's PATH.")
        except Exception as e:
            self._cleanup_temp_files()
            self.finished.emit(False, f"An exception occurred during export: {e}")

    def _cleanup_temp_files(self):
        for path in self.temp_files:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass

    def get_process(self):
        return self.process

class Encoder(QObject):
    progress = pyqtSignal(int)
    finished = pyqtSignal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker_thread = None
        self.worker = None
        self._is_running = False

    def start_export(self, timeline, project_settings, export_settings, app_settings=None):
        if self._is_running:
            self.finished.emit(False, "An export is already in progress.")
            return

        self._is_running = True

        try:
            total_dur_ms = timeline.get_total_duration()
            total_dur_sec = total_dur_ms / 1000.0
            w, h, fps = project_settings['width'], project_settings['height'], project_settings['fps']
            sample_rate, channel_layout = '44100', 'stereo'
            if export_settings.get('audio_sample_rate'):
                sample_rate = str(export_settings['audio_sample_rate'])

            output_args = {}
            stream_args = []

            hidden_v_tracks = getattr(timeline, 'hidden_video_tracks', set())
            muted_a_tracks = getattr(timeline, 'muted_audio_tracks', set())

            all_video_clips = sorted(
                [c for c in timeline.clips if c.track_type == 'video' and c.media_type != 'subtitle' and c.track_index not in hidden_v_tracks],
                key=lambda c: c.timeline_start_ms
            )

            all_subtitle_clips = sorted(
                [c for c in timeline.clips if c.media_type == 'subtitle' and c.track_index not in hidden_v_tracks],
                key=lambda c: c.timeline_start_ms
            )

            vcodec = export_settings.get('vcodec')
            acodec = export_settings.get('acodec')
            all_audio_clips = sorted(
                [c for c in timeline.clips if c.track_type == 'audio' and c.track_index not in muted_a_tracks],
                key=lambda c: c.timeline_start_ms
            )

            v_bitrate = export_settings.get('v_bitrate')
            is_lossless = (v_bitrate == "Lossless (QP 0 / CRF 1)")

            prep_cmds = []
            temp_files = []

            custom_temp = ""
            stream_mode = "Direct In-Memory (No intermediate video files, faster)"
            if app_settings:
                custom_temp = app_settings.get("custom_temp_dir", "").strip()
                stream_mode = app_settings.get("stream_copy_mode", stream_mode)

            temp_dir = custom_temp if (custom_temp and os.path.isdir(custom_temp)) else tempfile.gettempdir()
            use_disk_segments = ("Use Temp Files" in stream_mode)

            if vcodec == 'copy' and len(all_video_clips) > 1:
                list_path = os.path.join(temp_dir, f"ve_concat_list_{uuid.uuid4().hex}.txt")
                temp_files.append(list_path)

                if not use_disk_segments:
                    with open(list_path, 'w', encoding='utf-8') as f:
                        f.write("ffconcat version 1.0\n")
                        for c in all_video_clips:
                            escaped_path = c.source_path.replace("'", "'\\''")
                            f.write(f"file '{escaped_path}'\n")
                            if c.clip_start_ms > 0:
                                f.write(f"inpoint {c.clip_start_ms / 1000.0:.6f}\n")
                            outpoint_sec = (c.clip_start_ms + c.duration_ms) / 1000.0
                            f.write(f"outpoint {outpoint_sec:.6f}\n")
                else:
                    seg_files = []
                    last_end_ms = 0
                    for i, c in enumerate(all_video_clips):
                        gap_ms = c.timeline_start_ms - last_end_ms
                        if acodec == 'copy' and gap_ms > 40:
                            silence_seg = os.path.join(temp_dir, f"ve_silence_{uuid.uuid4().hex}_{i}.mp4")
                            silence_dur = gap_ms / 1000.0
                            silence_cmd = [
                                'ffmpeg', '-y', '-f', 'lavfi',
                                '-i', f'color=c=black:s={w}x{h}:r={fps}:d={silence_dur:.6f}',
                                '-f', 'lavfi',
                                '-i', f'anullsrc=r={sample_rate}:cl={channel_layout}:d={silence_dur:.6f}',
                                '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', '-b:a', '192k',
                                silence_seg
                            ]
                            prep_cmds.append(silence_cmd)
                            temp_files.append(silence_seg)
                            seg_files.append(silence_seg)

                        has_audio = (acodec == 'copy' and any(a for a in all_audio_clips if abs(a.timeline_start_ms - c.timeline_start_ms) < 40))
                        cut_start = c.clip_start_ms / 1000.0
                        cut_dur = c.duration_ms / 1000.0
                        temp_seg = os.path.join(temp_dir, f"ve_concat_seg_{uuid.uuid4().hex}_{i}.mp4")

                        slice_cmd = ['ffmpeg', '-y', '-ss', f"{cut_start:.6f}", '-t', f"{cut_dur:.6f}", '-i', c.source_path]
                        if has_audio:
                            slice_cmd.extend(['-map', '0:v:0', '-map', '0:a:0?'])
                        else:
                            slice_cmd.extend(['-map', '0:v:0', '-an'])
                        slice_cmd.extend(['-c', 'copy', '-avoid_negative_ts', 'make_zero', temp_seg])

                        prep_cmds.append(slice_cmd)
                        temp_files.append(temp_seg)
                        seg_files.append(temp_seg)
                        last_end_ms = c.timeline_start_ms + c.duration_ms

                    with open(list_path, 'w', encoding='utf-8') as f:
                        for seg in seg_files:
                            escaped = seg.replace("'", "'\\''")
                            f.write(f"file '{escaped}'\n")

                concat_input = ffmpeg.input(list_path, f='concat', safe=0)
                stream_args.append(concat_input.video)
                output_args['vcodec'] = 'copy'
                if acodec == 'copy':
                    stream_args.append(concat_input.audio)
                    output_args['acodec'] = 'copy'

            elif vcodec == 'copy' and acodec == 'copy' and len(all_video_clips) == 1 and len(all_audio_clips) == 1 and all_video_clips[0].source_path == all_audio_clips[0].source_path and not all_subtitle_clips:
                single_v_clip = all_video_clips[0]
                cut_start_sec = single_v_clip.clip_start_ms / 1000.0
                cut_dur_sec = single_v_clip.duration_ms / 1000.0
                shared_in = ffmpeg.input(single_v_clip.source_path, ss=f"{cut_start_sec:.6f}", t=f"{cut_dur_sec:.6f}")
                stream_args.append(shared_in.video)
                stream_args.append(shared_in.audio)
                output_args['vcodec'] = 'copy'
                output_args['acodec'] = 'copy'

            elif vcodec == 'copy':
                if len(all_video_clips) == 0:
                    raise ValueError("Direct Stream Copy (copy) for video cannot be used because all video tracks are hidden or empty.")
                single_v_clip = all_video_clips[0]
                cut_start_sec = single_v_clip.clip_start_ms / 1000.0
                cut_dur_sec = single_v_clip.duration_ms / 1000.0
                v_in = ffmpeg.input(single_v_clip.source_path, ss=f"{cut_start_sec:.6f}", t=f"{cut_dur_sec:.6f}")
                stream_args.append(v_in.video)
                output_args['vcodec'] = 'copy'
            elif vcodec:
                if len(all_video_clips) == 1 and all_video_clips[0].timeline_start_ms == 0 and not all_subtitle_clips:
                    single_v_clip = all_video_clips[0]
                    clip_start_sec = single_v_clip.clip_start_ms / 1000.0
                    clip_dur_sec = single_v_clip.duration_ms / 1000.0

                    if single_v_clip.media_type == 'image':
                        clip_input = ffmpeg.input(single_v_clip.source_path, loop=1, framerate=fps)
                        v_layer = clip_input.video.filter('trim', duration=f"{clip_dur_sec:.6f}").filter('setpts', 'PTS-STARTPTS')
                    else:
                        clip_input = ffmpeg.input(single_v_clip.source_path, ss=f"{clip_start_sec:.6f}", t=f"{clip_dur_sec:.6f}")
                        v_layer = clip_input.video.filter('setpts', 'PTS-STARTPTS')

                    crop = getattr(single_v_clip, 'effects', {}).get('crop')
                    if crop and all(k in crop for k in ('x', 'y', 'w', 'h')):
                        v_layer = v_layer.filter('crop', w=crop['w'], h=crop['h'], x=crop['x'], y=crop['y'])

                    final_video = (
                        v_layer
                        .filter('scale', w, h, force_original_aspect_ratio='decrease')
                        .filter('pad', w, h, '(ow-iw)/2', '(oh-ih)/2', 'black')
                    )
                else:
                    final_video = ffmpeg.input(f'color=c=black:s={w}x{h}:r={fps}:d={total_dur_sec}', f='lavfi')

                    for clip in all_video_clips:
                        timeline_start_sec = clip.timeline_start_ms / 1000.0
                        clip_start_sec = clip.clip_start_ms / 1000.0
                        clip_dur_sec = clip.duration_ms / 1000.0

                        if clip.media_type == 'image':
                            clip_input = ffmpeg.input(clip.source_path, loop=1, framerate=fps)
                            v_layer = clip_input.video.filter('trim', duration=f"{clip_dur_sec:.6f}").filter('setpts', 'PTS-STARTPTS')
                        else:
                            clip_input = ffmpeg.input(clip.source_path, ss=f"{clip_start_sec:.6f}", t=f"{clip_dur_sec:.6f}")
                            v_layer = clip_input.video.filter('setpts', 'PTS-STARTPTS')

                        crop = getattr(clip, 'effects', {}).get('crop')
                        if crop and all(k in crop for k in ('x', 'y', 'w', 'h')):
                            v_layer = v_layer.filter('crop', w=crop['w'], h=crop['h'], x=crop['x'], y=crop['y'])

                        timed_layer = (
                            v_layer
                            .filter('scale', w, h, force_original_aspect_ratio='decrease')
                            .filter('pad', w, h, '(ow-iw)/2', '(oh-ih)/2', 'black')
                        )

                        if timeline_start_sec > 0:
                            timed_layer = timed_layer.filter('setpts', f'PTS+{timeline_start_sec}/TB')

                        timeline_end_sec = (clip.timeline_start_ms + clip.duration_ms) / 1000.0
                        enable_expression = f'between(t,{timeline_start_sec:.6f},{timeline_end_sec:.6f})'

                        final_video = ffmpeg.overlay(final_video, timed_layer, enable=enable_expression, eof_action='endall')

                for sub_clip in all_subtitle_clips:                
                    timeline_start_sec = sub_clip.timeline_start_ms / 1000.0
                    timeline_end_sec = (sub_clip.timeline_start_ms + sub_clip.duration_ms) / 1000.0
                    enable_expression = f'between(t,{timeline_start_sec:.6f},{timeline_end_sec:.6f})'
                    subtitle_layer = (
                        ffmpeg.input(f'color=c=black@0.0:s={w}x{h}:r={fps}:d={total_dur_sec}', f='lavfi')
                        .filter('subtitles', filename=sub_clip.source_path)
                    )
                    final_video = ffmpeg.overlay(final_video, subtitle_layer, enable=enable_expression)

                final_video = final_video.filter('format', pix_fmts='yuv420p').filter('fps', fps=fps)
                stream_args.append(final_video)
                output_args['vcodec'] = vcodec
                output_args['pix_fmt'] = 'yuv420p'

                if is_lossless:
                    if vcodec == 'libx265':
                        output_args['x265-params'] = 'qp=0'
                        output_args['preset'] = 'slow'
                    elif vcodec == 'libx264':
                        output_args['crf'] = '1'
                        output_args['preset'] = 'slow'
                elif v_bitrate:
                    output_args['b:v'] = v_bitrate

            if vcodec == 'copy' and acodec == 'copy' and len(all_video_clips) == 1 and len(all_audio_clips) == 1 and all_video_clips[0].source_path == all_audio_clips[0].source_path and not all_subtitle_clips:
                pass
            elif acodec == 'copy' and vcodec != 'copy':
                if len(all_audio_clips) != 1:
                    if len(all_audio_clips) == 0:
                        output_args['an'] = None
                    else:
                        raise ValueError("Direct Stream Copy (copy) for audio cannot be used when there are multiple audio clips or gaps on the timeline. Please select an audio codec such as aac or flac.")
                else:
                    single_a_clip = all_audio_clips[0]
                    cut_start_sec = single_a_clip.clip_start_ms / 1000.0
                    cut_dur_sec = single_a_clip.duration_ms / 1000.0
                    a_in = ffmpeg.input(single_a_clip.source_path, ss=f"{cut_start_sec:.6f}")
                    stream_args.append(a_in.audio)
                    output_args['acodec'] = 'copy'
                    if 't' not in output_args:
                        output_args['t'] = f"{cut_dur_sec:.6f}"
                    output_args['avoid_negative_ts'] = 'make_zero'
            elif acodec and acodec != 'copy':
                track_audio_streams = []
                for i in range(1, timeline.num_audio_tracks + 1):
                    if i in muted_a_tracks:
                        continue
                    track_clips = sorted([c for c in timeline.clips if c.track_type == 'audio' and c.track_index == i], key=lambda c: c.timeline_start_ms)
                    if not track_clips:
                        continue

                    track_segments = []
                    last_end_ms = 0
                    for clip in track_clips:
                        gap_ms = clip.timeline_start_ms - last_end_ms
                        if gap_ms > 10:
                            track_segments.append(ffmpeg.input(f'anullsrc=r={sample_rate}:cl={channel_layout}:d={gap_ms/1000.0}', f='lavfi'))

                        clip_start_sec = clip.clip_start_ms / 1000.0
                        clip_duration_sec = clip.duration_ms / 1000.0
                        audio_source_node = ffmpeg.input(clip.source_path, ss=f"{clip_start_sec:.6f}", t=f"{clip_duration_sec:.6f}")
                        a_seg = audio_source_node.audio.filter('asetpts', 'PTS-STARTPTS')
                        track_segments.append(a_seg)
                        last_end_ms = clip.timeline_start_ms + clip.duration_ms

                    if track_segments:
                        track_audio_streams.append(ffmpeg.concat(*track_segments, v=0, a=1))

                if track_audio_streams:
                    final_audio = ffmpeg.filter(track_audio_streams, 'amix', inputs=len(track_audio_streams), duration='longest')

                    aresample_kwargs = {}
                    if export_settings.get('audio_sample_rate'):
                        aresample_kwargs['sample_rate'] = export_settings['audio_sample_rate']
                    if export_settings.get('aresample_async', 0) > 0:
                        aresample_kwargs['async'] = export_settings['aresample_async']
                    if export_settings.get('aresample_min_hard_comp', 0.0) > 0.0:
                        aresample_kwargs['min_hard_comp'] = export_settings['aresample_min_hard_comp']
                    if export_settings.get('aresample_first_pts'):
                        aresample_kwargs['first_pts'] = 0

                    if aresample_kwargs:
                        final_audio = final_audio.filter('aresample', **aresample_kwargs)

                    stream_args.append(final_audio)
                    output_args['acodec'] = acodec
                    if export_settings.get('a_bitrate'): output_args['b:a'] = export_settings['a_bitrate']
                    if export_settings.get('audio_sample_rate'): output_args['ar'] = export_settings['audio_sample_rate']
                else:
                    output_args['an'] = None
            else:
                if vcodec != 'copy' or len(all_video_clips) <= 1:
                    output_args['an'] = None

            if not stream_args:
                raise ValueError("No video or audio streams to export (all tracks may be hidden or muted).")

            if export_settings.get('avoid_negative_ts'):
                output_args['avoid_negative_ts'] = 'make_zero'

            if export_settings.get('cfr_mode') and vcodec != 'copy':
                output_args['fps_mode'] = 'cfr'

            if export_settings.get('use_editlist', True):
                output_args['use_editlist'] = '1'
            else:
                output_args['use_editlist'] = '0'

            output_args['movflags'] = '+faststart'
            output_args['t'] = f"{total_dur_sec:.6f}"

            ffmpeg_cmd = ffmpeg.output(*stream_args, export_settings['output_path'], **output_args).overwrite_output().compile()

            custom_args = export_settings.get('custom_ffmpeg_args')
            if custom_args:
                extra_tokens = shlex.split(custom_args)
                ffmpeg_cmd = ffmpeg_cmd[:-1] + extra_tokens + [ffmpeg_cmd[-1]]

        except Exception as e:
            self.finished.emit(False, f"Error building FFmpeg command: {e}")
            self._is_running = False
            return

        self.worker_thread = QThread()
        self.worker = _ExportRunner(ffmpeg_cmd, total_dur_ms, prep_cmds=prep_cmds, temp_files=temp_files)
        self.worker.moveToThread(self.worker_thread)

        self.worker.progress.connect(self.progress.emit)
        self.worker.finished.connect(self._on_export_runner_finished)

        self.worker_thread.started.connect(self.worker.run)
        self.worker_thread.start()

    def _on_export_runner_finished(self, success, message):
        self._is_running = False
        self.finished.emit(success, message)
        
        if self.worker_thread:
            self.worker_thread.quit()
            self.worker_thread.wait()
        self.worker_thread = None
        self.worker = None

    def cancel_export(self):
        if self.worker and self.worker.get_process() and self.worker.get_process().poll() is None:
            self.worker.get_process().terminate()
            print("Export cancelled by user.")