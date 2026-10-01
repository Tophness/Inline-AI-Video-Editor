import ffmpeg
import numpy as np
import sounddevice as sd
import threading
import time
from queue import Queue, Empty
import subprocess
import copy
from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from PyQt6.QtGui import QImage, QPixmap, QColor

AUDIO_BUFFER_SECONDS = 1.0
VIDEO_BUFFER_SECONDS = 1.0
AUDIO_CHUNK_SAMPLES = 1024
DEFAULT_SAMPLE_RATE = 44100
DEFAULT_CHANNELS = 2

class PlaybackManager(QObject):
    new_frame = pyqtSignal(QPixmap)
    playback_pos_changed = pyqtSignal(int)
    stopped = pyqtSignal()
    started = pyqtSignal()
    paused = pyqtSignal()
    stats_updated = pyqtSignal(str)

    def __init__(self, get_timeline_data_func, settings=None, parent=None):
        super().__init__(parent)
        self.get_timeline_data = get_timeline_data_func
        self.settings = settings or {}

        self.is_playing = False
        self.is_muted = False
        self.volume = 1.0
        self.playback_start_time_ms = 0
        self.pause_time_ms = 0
        self.is_paused = False
        self.seeking = False
        self.stop_flag = threading.Event()
        self._seek_thread = None
        self._seek_request_ms = -1
        self._seek_lock = threading.Lock()
        self.bypass_crop = False

        self.video_process = None
        self.audio_process = None
        self.video_reader_thread = None
        self.audio_reader_thread = None
        self.audio_stream = None

        self.video_queue = None
        self.audio_queue = None

        self.stream_start_time_monotonic = 0
        self.last_emitted_pos = -1

        self.total_samples_played = 0
        self.audio_underruns = 0
        self.last_video_pts_ms = 0
        self.debug = False

        self.sync_lock = threading.Lock()
        self.audio_clock_sec = 0.0
        self.audio_clock_update_time = 0.0

        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self._update_loop)
        self.update_timer.setInterval(16)

    def set_settings(self, settings):
        self.settings = settings or {}

    def _get_hwaccel_param(self):
        mode = self.settings.get("playback_hwaccel", "CPU (Software)") if self.settings else "CPU (Software)"
        mapping = {
            "GPU (Auto)": "auto",
            "Auto (GPU)": "auto",
            "NVIDIA (CUDA)": "cuda",
            "DirectX (DXVA2)": "dxva2",
            "DirectX (D3D11VA)": "d3d11va",
            "Intel (QSV)": "qsv",
            "Apple (VideoToolbox)": "videotoolbox"
        }
        return mapping.get(mode, None)

    def _emit_playhead_pos(self, time_ms, source):
        if time_ms != self.last_emitted_pos:
            if self.debug:
                print(f"[PLAYHEAD DEBUG @ {time.monotonic():.4f}] pos={time_ms}ms, source='{source}'")
            self.playback_pos_changed.emit(time_ms)
            self.last_emitted_pos = time_ms

    def _cleanup_resources(self):
        self.stop_flag.set()
        
        if self.update_timer.isActive():
            self.update_timer.stop()

        if self.audio_stream:
            try:
                self.audio_stream.stop()
                self.audio_stream.close(ignore_errors=True)
            except Exception as e:
                print(f"Error closing audio stream: {e}")
        self.audio_stream = None
        
        for p in [self.video_process, self.audio_process]:
            if p and p.poll() is None:
                try:
                    p.terminate()
                    p.wait(timeout=1.0)
                except Exception as e:
                    print(f"Error terminating process: {e}")
                    try:
                        p.kill()
                    except Exception as ke:
                        print(f"Error killing process: {ke}")

        self.video_reader_thread = None
        self.audio_reader_thread = None
        self.video_process = None
        self.audio_process = None
        self.video_queue = None
        self.audio_queue = None

    def _video_reader_thread(self, process, width, height, fps):
        frame_size = width * height * 3
        frame_duration_ms = 1000.0 / fps
        frame_pts_ms = self.playback_start_time_ms

        while not self.stop_flag.is_set():
            try:
                if self.video_queue and self.video_queue.full():
                    time.sleep(0.01)
                    continue

                chunk = process.stdout.read(frame_size)
                if len(chunk) < frame_size:
                    break
                
                if self.video_queue: self.video_queue.put((chunk, frame_pts_ms))
                frame_pts_ms += frame_duration_ms

            except (IOError, ValueError):
                break
            except Exception as e:
                print(f"Video reader error: {e}")
                break
        if self.debug: print("Video reader thread finished.")
        if self.video_queue: self.video_queue.put(None)

    def _audio_reader_thread(self, process):
        chunk_size = AUDIO_CHUNK_SAMPLES * DEFAULT_CHANNELS * 4
        while not self.stop_flag.is_set():
            try:
                if self.audio_queue and self.audio_queue.full():
                    time.sleep(0.01)
                    continue

                chunk = process.stdout.read(chunk_size)
                if not chunk:
                    break
                
                np_chunk = np.frombuffer(chunk, dtype=np.float32)

                if self.audio_queue:
                    self.audio_queue.put(np_chunk)

            except (IOError, ValueError):
                break
            except Exception as e:
                print(f"Audio reader error: {e}")
                break
        if self.debug: print("Audio reader thread finished.")
        if self.audio_queue: self.audio_queue.put(None)

    def _audio_callback(self, outdata, frames, time_info, status):
        if status:
            self.audio_underruns += 1
        try:
            if self.audio_queue is None: raise Empty
            chunk = self.audio_queue.get_nowait()
            if chunk is None:
                raise sd.CallbackStop
            
            chunk_len = len(chunk)
            outdata_len = outdata.shape[0] * outdata.shape[1]
            
            if chunk_len < outdata_len:
                outdata.fill(0)
                outdata.flat[:chunk_len] = chunk
            else:
                outdata[:] = chunk[:outdata.size].reshape(outdata.shape)

            if self.is_muted:
                outdata.fill(0)
            else:
                outdata *= self.volume

            with self.sync_lock:
                self.audio_clock_sec = self.total_samples_played / DEFAULT_SAMPLE_RATE
                self.audio_clock_update_time = time_info.outputBufferDacTime
            
            self.total_samples_played += frames
        except Empty:
            outdata.fill(0)

    def _seek_worker(self):
        while True:
            with self._seek_lock:
                time_ms = self._seek_request_ms
                self._seek_request_ms = -1
            
            timeline, clips, proj_settings = self.get_timeline_data()
            w, h, fps = proj_settings['width'], proj_settings['height'], proj_settings['fps']

            seek_time_ms = time_ms
            is_clip_end = False

            hidden_v_tracks = getattr(timeline, 'hidden_video_tracks', set())

            video_clip_at_time = next((c for c in sorted(clips, key=lambda x: x.track_index, reverse=True) 
                                     if c.track_type == 'video' and c.track_index not in hidden_v_tracks and c.media_type in ['video', 'image'] and c.timeline_start_ms <= time_ms < c.timeline_end_ms), None)

            if not video_clip_at_time and time_ms > 0:
                candidates = [c for c in clips if c.track_type == 'video' and c.track_index not in hidden_v_tracks and c.media_type in ['video', 'image'] and c.timeline_end_ms <= time_ms]
                if candidates:
                    max_end = max(c.timeline_end_ms for c in candidates)
                    total_dur = timeline.get_total_duration()
                    if time_ms == max_end or time_ms >= total_dur or abs(max_end - time_ms) <= 500:
                        video_clip_at_time = next((c for c in sorted(candidates, key=lambda x: x.track_index, reverse=True) if c.timeline_end_ms == max_end), None)
                        if video_clip_at_time:
                            is_clip_end = True
                            seek_time_ms = video_clip_at_time.timeline_end_ms

            subtitle_clip_at_time = next((c for c in sorted(clips, key=lambda x: x.track_index, reverse=True)
                                        if c.media_type == 'subtitle' and c.track_index not in hidden_v_tracks and c.timeline_start_ms <= seek_time_ms < c.timeline_end_ms), None)

            pixmap = QPixmap(w, h)
            pixmap.fill(QColor("black"))

            if video_clip_at_time:
                try:
                    output_kwargs = {'format': 'rawvideo', 'pix_fmt': 'rgb24'}
                    hwaccel = self._get_hwaccel_param()
                    in_kwargs = {'hwaccel': hwaccel} if (hwaccel and video_clip_at_time.media_type != 'image') else {}

                    if video_clip_at_time.media_type == 'image':
                        video_node = ffmpeg.input(video_clip_at_time.source_path, loop=1, framerate=fps)
                        output_kwargs['vframes'] = 1
                    elif is_clip_end:
                        clip_start_sec = video_clip_at_time.clip_start_ms / 1000.0
                        clip_end_sec = (video_clip_at_time.clip_start_ms + video_clip_at_time.duration_ms) / 1000.0
                        seek_sec = max(clip_start_sec, clip_end_sec - 0.3)
                        dur_sec = max(0.04, clip_end_sec - seek_sec)
                        video_node = ffmpeg.input(video_clip_at_time.source_path, ss=f"{seek_sec:.6f}", t=f"{dur_sec:.6f}", **in_kwargs)
                    else:
                        video_seek_sec = max(0.0, (seek_time_ms - video_clip_at_time.timeline_start_ms + video_clip_at_time.clip_start_ms) / 1000.0)
                        video_node = ffmpeg.input(video_clip_at_time.source_path, ss=f"{video_seek_sec:.6f}", **in_kwargs)
                        output_kwargs['vframes'] = 1

                    final_node = video_node.video

                    crop = getattr(video_clip_at_time, 'effects', {}).get('crop')
                    if crop and not getattr(self, 'bypass_crop', False) and all(k in crop for k in ('x', 'y', 'w', 'h')):
                        final_node = final_node.filter('crop', w=crop['w'], h=crop['h'], x=crop['x'], y=crop['y'])

                    if subtitle_clip_at_time:
                        sub_seek_sec = (seek_time_ms - subtitle_clip_at_time.timeline_start_ms + subtitle_clip_at_time.clip_start_ms) / 1000.0
                        final_node = final_node.filter('setpts', f'PTS-STARTPTS+{sub_seek_sec}/TB')
                        final_node = final_node.filter('subtitles', filename=subtitle_clip_at_time.source_path)

                    out, _ = (final_node
                                    .filter('scale', w, h, force_original_aspect_ratio='decrease')
                                    .filter('pad', w, h, '(ow-iw)/2', '(oh-ih)/2', 'black')
                                    .output('pipe:', **output_kwargs)
                                    .run(capture_stdout=True, quiet=True))

                    frame_size = w * h * 3
                    if out and len(out) >= frame_size:
                        last_frame_bytes = out[-frame_size:]
                        image = QImage(last_frame_bytes, w, h, w * 3, QImage.Format.Format_RGB888)
                        pixmap = QPixmap.fromImage(image)

                except ffmpeg.Error as e:
                    print(f"Error seeking to frame: {e.stderr.decode('utf-8') if e.stderr else str(e)}")
            
            self.new_frame.emit(pixmap)

            with self._seek_lock:
                if self._seek_request_ms == -1:
                    self.seeking = False
                    break

    def seek_to_frame(self, time_ms):
        self.stop()
        self._emit_playhead_pos(time_ms, "seek_to_frame")
        
        with self._seek_lock:
            self._seek_request_ms = time_ms
            if self.seeking:
                return
            self.seeking = True
            self._seek_thread = threading.Thread(target=self._seek_worker, daemon=True)
            self._seek_thread.start()

    def _build_video_graph(self, start_ms, timeline, clips, proj_settings):
        w, h, fps = proj_settings['width'], proj_settings['height'], proj_settings['fps']

        hidden_v_tracks = getattr(timeline, 'hidden_video_tracks', set())
        visual_clips = [c for c in clips if c.track_type == 'video' and c.track_index not in hidden_v_tracks and c.media_type in ['video', 'image'] and c.timeline_end_ms > start_ms]
        subtitle_clips = [c for c in clips if c.media_type == 'subtitle' and c.track_index not in hidden_v_tracks and c.timeline_end_ms > start_ms]
        
        if not visual_clips:
            return None

        visual_clips = sorted(visual_clips, key=lambda c: c.track_index, reverse=True)

        class VSegment:
            def __init__(self, c, t_start, t_end):
                self.source_path = c.source_path
                self.duration_ms = t_end - t_start
                self.timeline_start_ms = t_start
                self.media_type = c.media_type
                self.clip_start_ms = c.clip_start_ms + (t_start - c.timeline_start_ms)
                self.effects = copy.deepcopy(getattr(c, 'effects', {}))

            @property
            def timeline_end_ms(self):
                return self.timeline_start_ms + self.duration_ms

        event_points = {start_ms}
        for c in visual_clips:
            event_points.update({c.timeline_start_ms, c.timeline_end_ms})
        
        total_duration = timeline.get_total_duration()
        if total_duration > start_ms:
            event_points.add(total_duration)

        sorted_points = sorted([p for p in list(event_points) if p >= start_ms])

        visible_segments = []
        for t_start, t_end in zip(sorted_points[:-1], sorted_points[1:]):
            if t_end <= t_start: continue
            
            midpoint = t_start + 1
            top_clip = next((c for c in visual_clips if c.timeline_start_ms <= midpoint < c.timeline_end_ms), None)

            if top_clip:
                visible_segments.append(VSegment(top_clip, t_start, t_end))

        concat_inputs = []
        last_end_time_ms = start_ms
        hwaccel = self._get_hwaccel_param()

        for segment_clip in visible_segments:
            clip_read_start_ms = segment_clip.clip_start_ms
            clip_duration_ms = segment_clip.duration_ms

            if clip_duration_ms <= 0:
                last_end_time_ms = max(last_end_time_ms, segment_clip.timeline_end_ms)
                continue

            in_kwargs = {'re': None}
            if hwaccel and segment_clip.media_type != 'image':
                in_kwargs['hwaccel'] = hwaccel

            input_stream = ffmpeg.input(segment_clip.source_path, ss=clip_read_start_ms / 1000.0, t=clip_duration_ms / 1000.0, **in_kwargs)

            segment_node = input_stream.video
            if segment_clip.media_type == 'image':
                segment_node = segment_node.filter('loop', loop=-1, size=1, start=0).filter('setpts', 'N/(FRAME_RATE*TB)').filter('trim', duration=clip_duration_ms / 1000.0)

            crop = getattr(segment_clip, 'effects', {}).get('crop')
            if crop and all(k in crop for k in ('x', 'y', 'w', 'h')):
                segment_node = segment_node.filter('crop', w=crop['w'], h=crop['h'], x=crop['x'], y=crop['y'])

            segment_node = (
                segment_node
                .filter('scale', w, h, force_original_aspect_ratio='decrease')
                .filter('pad', w, h, '(ow-iw)/2', '(oh-ih)/2', 'black')
            )

            segment_midpoint_ms = segment_clip.timeline_start_ms + (segment_clip.duration_ms / 2)
            active_sub_clip = next((sc for sc in subtitle_clips if sc.timeline_start_ms <= segment_midpoint_ms < sc.timeline_end_ms), None)

            if active_sub_clip:
                time_offset_sec = (segment_clip.timeline_start_ms - active_sub_clip.timeline_start_ms + active_sub_clip.clip_start_ms) / 1000.0
                segment_node = segment_node.filter('setpts', f'PTS-STARTPTS+{max(0, time_offset_sec):.6f}/TB')
                segment_node = segment_node.filter('subtitles', filename=active_sub_clip.source_path)
                segment_node = segment_node.filter('setpts', 'PTS-STARTPTS')

            gap_start_ms = max(start_ms, last_end_time_ms)
            if segment_clip.timeline_start_ms > gap_start_ms:
                gap_duration_sec = (segment_clip.timeline_start_ms - gap_start_ms) / 1000.0
                segment_node = segment_node.filter('tpad', start_duration=f'{gap_duration_sec:.6f}', color='black')

            segment_node = segment_node.filter('setsar', '1')
            concat_inputs.append(segment_node)
            last_end_time_ms = segment_clip.timeline_end_ms

        if not concat_inputs:
            return None

        return ffmpeg.concat(*concat_inputs, v=1, a=0)

    def _build_audio_graph(self, start_ms, timeline, clips, proj_settings):
        muted_a_tracks = getattr(timeline, 'muted_audio_tracks', set())
        active_clips = [c for c in clips if c.track_type == 'audio' and c.track_index not in muted_a_tracks and c.timeline_end_ms > start_ms]
        if not active_clips:
            return None

        tracks = {}
        for clip in active_clips:
            tracks.setdefault(clip.track_index, []).append(clip)
        
        track_streams = []
        for track_index, track_clips in sorted(tracks.items()):
            track_clips.sort(key=lambda c: c.timeline_start_ms)
            
            concat_inputs = []
            last_end_time_ms = start_ms

            for clip in track_clips:
                gap_start_ms = max(start_ms, last_end_time_ms)
                if clip.timeline_start_ms > gap_start_ms:
                    gap_duration_sec = (clip.timeline_start_ms - gap_start_ms) / 1000.0
                    concat_inputs.append(ffmpeg.input(f'anullsrc=r={DEFAULT_SAMPLE_RATE}:cl={DEFAULT_CHANNELS}:d={gap_duration_sec}', f='lavfi'))

                clip_read_start_ms = clip.clip_start_ms + max(0, start_ms - clip.timeline_start_ms)
                clip_play_start_ms = max(start_ms, clip.timeline_start_ms)
                clip_remaining_duration_ms = clip.timeline_end_ms - clip_play_start_ms
                
                if clip_remaining_duration_ms > 0:
                    dur_sec = clip_remaining_duration_ms / 1000.0
                    segment = ffmpeg.input(clip.source_path, ss=clip_read_start_ms/1000.0, re=None).audio
                    segment = segment.filter('apad').filter('atrim', start=0, duration=f"{dur_sec:.6f}").filter('asetpts', 'PTS-STARTPTS')
                    concat_inputs.append(segment)
                
                last_end_time_ms = clip.timeline_end_ms
            
            if concat_inputs:
                track_streams.append(ffmpeg.concat(*concat_inputs, v=0, a=1))

        if not track_streams:
            return None

        return ffmpeg.filter(track_streams, 'amix', inputs=len(track_streams), duration='longest')

    def play(self, time_ms):
        if self.is_playing:
            self.stop()
        
        if self.debug: print(f"Play requested from {time_ms}ms.")

        self.stop_flag.clear()
        self.playback_start_time_ms = time_ms
        self.pause_time_ms = time_ms
        self.is_paused = False

        self.total_samples_played = 0
        self.audio_underruns = 0
        self.last_video_pts_ms = time_ms
        with self.sync_lock:
            self.audio_clock_sec = 0.0
            self.audio_clock_update_time = 0.0

        timeline, clips, proj_settings = self.get_timeline_data()
        w, h, fps = proj_settings['width'], proj_settings['height'], proj_settings['fps']

        video_buffer_size = int(fps * VIDEO_BUFFER_SECONDS)
        audio_buffer_size = int((DEFAULT_SAMPLE_RATE / AUDIO_CHUNK_SAMPLES) * AUDIO_BUFFER_SECONDS)
        self.video_queue = Queue(maxsize=video_buffer_size)
        self.audio_queue = Queue(maxsize=audio_buffer_size)

        video_graph = self._build_video_graph(time_ms, timeline, clips, proj_settings)
        if video_graph:
            try:
                args = (video_graph
                        .output('pipe:', format='rawvideo', pix_fmt='rgb24', r=fps).compile())
                self.video_process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            except Exception as e:
                print(f"Failed to start video process: {e}")
                self.video_process = None

        audio_graph = self._build_audio_graph(time_ms, timeline, clips, proj_settings)
        if audio_graph:
            try:
                args = ffmpeg.output(audio_graph, 'pipe:', format='f32le', ac=DEFAULT_CHANNELS, ar=DEFAULT_SAMPLE_RATE).compile()
                self.audio_process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            except Exception as e:
                print(f"Failed to start audio process: {e}")
                self.audio_process = None

        if self.video_process:
            self.video_reader_thread = threading.Thread(target=self._video_reader_thread, args=(self.video_process, w, h, fps), daemon=True)
            self.video_reader_thread.start()
        if self.audio_process:
            self.audio_reader_thread = threading.Thread(target=self._audio_reader_thread, args=(self.audio_process,), daemon=True)
            self.audio_reader_thread.start()
            self.audio_stream = sd.OutputStream(samplerate=DEFAULT_SAMPLE_RATE, channels=DEFAULT_CHANNELS, callback=self._audio_callback, blocksize=AUDIO_CHUNK_SAMPLES)
            self.audio_stream.start()

        self.stream_start_time_monotonic = time.monotonic()
        self.is_playing = True
        self.update_timer.start()
        self.started.emit()

    def pause(self):
        if not self.is_playing or self.is_paused:
            return
        if self.debug: print("Playback paused.")
        self.is_paused = True
        if self.audio_stream:
            self.audio_stream.stop()
        self.pause_time_ms = self._get_current_time_ms()
        self.update_timer.stop()
        self.paused.emit()

    def resume(self):
        if not self.is_playing or not self.is_paused:
            return
        if self.debug: print("Playback resumed.")
        self.is_paused = False
        
        time_since_start_sec = (self.pause_time_ms - self.playback_start_time_ms) / 1000.0
        self.stream_start_time_monotonic = time.monotonic() - time_since_start_sec
        
        if self.audio_stream:
            self.audio_stream.start()
        
        self.update_timer.start()
        self.started.emit()

    def stop(self):
        was_playing = self.is_playing
        if was_playing and self.debug: print("Playback stopped.")
        self._cleanup_resources()
        self.is_playing = False
        self.is_paused = False
        if was_playing:
            self.stopped.emit()

    def set_volume(self, value):
        self.volume = max(0.0, min(1.0, value))

    def set_muted(self, muted):
        self.is_muted = bool(muted)
        
    def _get_current_time_ms(self):
        with self.sync_lock:
            audio_clk_sec = self.audio_clock_sec
            audio_clk_update_time = self.audio_clock_update_time

        if self.audio_stream and self.audio_stream.active and audio_clk_update_time > 0:
            time_since_dac_start = max(0, time.monotonic() - audio_clk_update_time)
            current_audio_time_sec = audio_clk_sec + time_since_dac_start
            current_pos_ms = self.playback_start_time_ms + int(current_audio_time_sec * 1000.0)
        else:
            elapsed_sec = time.monotonic() - self.stream_start_time_monotonic
            current_pos_ms = self.playback_start_time_ms + int(elapsed_sec * 1000)
        
        return current_pos_ms

    def _update_loop(self):
        if not self.is_playing or self.is_paused:
            return
        
        current_pos_ms = self._get_current_time_ms()
        
        clock_source = "SYSTEM"
        with self.sync_lock:
            if self.audio_stream and self.audio_stream.active and self.audio_clock_update_time > 0:
                clock_source = "AUDIO"

        if abs(current_pos_ms - self.last_emitted_pos) >= 20:
            source_str = f"_update_loop (clock:{clock_source})"
            self._emit_playhead_pos(current_pos_ms, source_str)

        if self.video_queue:
            while not self.video_queue.empty():
                try:
                    if self.video_queue.queue[0] is None: 
                        self.stop()
                        break
                    _, frame_pts = self.video_queue.queue[0]
                    
                    if frame_pts <= current_pos_ms:
                        frame_bytes, frame_pts = self.video_queue.get_nowait()
                        if frame_bytes is None:
                             self.stop()
                             break
                        self.last_video_pts_ms = frame_pts
                        _, _, proj_settings = self.get_timeline_data()
                        w, h = proj_settings['width'], proj_settings['height']
                        img = QImage(frame_bytes, w, h, w * 3, QImage.Format.Format_RGB888)
                        self.new_frame.emit(QPixmap.fromImage(img))
                    else:
                        break
                except Empty:
                    break
                except IndexError:
                    break

        vq_size = self.video_queue.qsize() if self.video_queue else 0
        vq_max = self.video_queue.maxsize if self.video_queue else 0
        aq_size = self.audio_queue.qsize() if self.audio_queue else 0
        aq_max = self.audio_queue.maxsize if self.audio_queue else 0
        
        video_audio_sync_ms = int(self.last_video_pts_ms - current_pos_ms)
        
        stats_str = (f"AQ: {aq_size}/{aq_max} | VQ: {vq_size}/{vq_max} | "
                     f"V-A Δ: {video_audio_sync_ms}ms | Clock: {clock_source} | "
                     f"Underruns: {self.audio_underruns}")
        self.stats_updated.emit(stats_str)

        total_duration = self.get_timeline_data()[0].get_total_duration()
        if total_duration > 0 and current_pos_ms >= total_duration:
            self.stop()
            self._emit_playhead_pos(int(total_duration), "_update_loop.end_of_timeline")