# -*- coding: utf-8 -*-
# modules/downloader.py
import os
import shutil
import uuid
import yt_dlp
from modules.youtube_service import extract_youtube_video_id

try:
    from moviepy.editor import VideoFileClip, concatenate_videoclips
except ImportError:
    from moviepy import VideoFileClip, concatenate_videoclips

def download_media_final_v2(video_url, output_path, cookie_file_path=None):
    """안티봇 다중 분리 엔진을 사용해 고품질 소스 비디오를 안전하게 다운로드합니다."""
    clean_id = extract_youtube_video_id(video_url)
    clean_url = f"https://www.youtube.com/watch?v={clean_id}" if clean_id else video_url.strip()

    try:
        import imageio_ffmpeg
        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        ffmpeg_path = None

    base_name = os.path.splitext(output_path)[0]
    raw_template = base_name + "_raw.%(ext)s"

    if os.path.exists(output_path):
        try: os.remove(output_path)
        except Exception: pass

    cookie_file = None
    for c_cand in [cookie_file_path, "cookies.txt", os.path.join(os.getcwd(), "cookies.txt")]:
        if c_cand and os.path.exists(c_cand) and os.path.getsize(c_cand) > 100:
            cookie_file = os.path.abspath(c_cand)
            break

    strategies = [
        {
            'format': 'bv*+ba/b',
            'outtmpl': raw_template,
            'merge_output_format': 'mp4',
            'ffmpeg_location': ffmpeg_path,
            'nocheckcertificate': True,
            'quiet': True,
            'no_warnings': True,
            'overwrites': True,
            'extractor_args': {
                'youtube': {
                    'player_client': ['android_embedded', 'android'],
                    'player_skip': ['webpage', 'configs', 'js']
                }
            }
        },
        {
            'format': 'bv*+ba/b',
            'outtmpl': raw_template,
            'merge_output_format': 'mp4',
            'ffmpeg_location': ffmpeg_path,
            'nocheckcertificate': True,
            'quiet': True,
            'no_warnings': True,
            'overwrites': True,
            'extractor_args': {
                'youtube': {
                    'player_client': ['ios'],
                    'player_skip': ['webpage', 'configs']
                }
            }
        },
        {
            'format': 'bv*+ba/b',
            'outtmpl': raw_template,
            'merge_output_format': 'mp4',
            'ffmpeg_location': ffmpeg_path,
            'cookiefile': cookie_file,
            'nocheckcertificate': True,
            'quiet': True,
            'no_warnings': True,
            'overwrites': True
        }
    ]

    last_error = ""
    for opt in strategies:
        try:
            with yt_dlp.YoutubeDL(opt) as ydl:
                info = ydl.extract_info(clean_url, download=True)
                v_title = info.get('title') or '신규 숏폼 프로젝트'
                ch_name = info.get('uploader') or info.get('channel') or ''

            for ext in ["mp4", "mkv", "webm", "ts"]:
                cand = base_name + f"_raw.{ext}"
                if os.path.exists(cand) and os.path.getsize(cand) > 10000:
                    if os.path.exists(output_path):
                        try: os.remove(output_path)
                        except Exception: pass
                    shutil.move(cand, output_path)
                    return True, v_title, ch_name, ""
        except Exception as e:
            last_error = str(e)
            continue

    return False, "", "", last_error

def generate_quick_cut_preview(source_path, segments_plan, out_path):
    """선택된 1~3개 구간을 1~2초 내에 고속 추출하여 검수용 영상을 생성합니다."""
    try:
        raw_v = VideoFileClip(source_path)
        clips = []
        for seg in segments_plan:
            st_t = float(seg["source_start"])
            en_t = float(seg["source_end"])
            if en_t > st_t:
                sub = raw_v.subclip(st_t, en_t) if hasattr(raw_v, "subclip") else raw_v.subclipped(st_t, en_t)
                clips.append(sub)

        if not clips:
            raw_v.close()
            return None

        assembled = concatenate_videoclips(clips) if len(clips) > 1 else clips[0]
        temp_aud = f"quick_aud_{uuid.uuid4().hex[:6]}.m4a"
        assembled.write_videofile(
            out_path,
            codec="libx264",
            audio_codec="aac",
            temp_audiofile=temp_aud,
            remove_temp=True,
            fps=24,
            preset="ultrafast",
            threads=4,
            logger=None
        )
        assembled.close()
        raw_v.close()
        return out_path
    except Exception:
        return None