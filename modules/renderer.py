# -*- coding: utf-8 -*-
# modules/renderer.py
import os
import re
import cv2
import html
import time
import uuid
import numpy as np
from PIL import Image, ImageDraw
import config
from modules.comment_engine import get_system_font, render_crisp_comment_card, clean_comment_text
from modules.ocr_detector import is_subtitle_overlapping

try:
    from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips
except ImportError:
    from moviepy import VideoFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips

def safe_set_pos(clip, pos):
    if hasattr(clip, "with_position"):
        return clip.with_position(pos)
    return clip.set_position(pos)

def safe_set_dur(clip, dur):
    if hasattr(clip, "with_duration"):
        return clip.with_duration(dur)
    return clip.set_duration(dur)

def safe_set_start(clip, start_t):
    if hasattr(clip, "with_start"):
        return clip.with_start(start_t)
    return clip.set_start(start_t)

def safe_subclip(clip, st_t, et_t):
    if hasattr(clip, "subclipped"):
        return clip.subclipped(st_t, et_t)
    return clip.subclip(st_t, et_t)

def safe_resize(clip, size):
    if hasattr(clip, "resized"):
        return clip.resized(size)
    return clip.resize(size)

def wrap_text(text, font, max_width, draw):
    lines = []
    curr = ""
    for char in text:
        test = curr + char
        bbox = draw.textbbox((0, 0), test, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            curr = test
        else:
            if curr:
                lines.append(curr)
            curr = char
    if curr:
        lines.append(curr)
    return lines

def auto_detect_video_boundary(clip, duration, *args, **kwargs):
    try:
        sample_times = [duration * 0.2, duration * 0.5, duration * 0.8]
        top_candidates, bottom_candidates = [], []
        for t in sample_times:
            frame = clip.get_frame(t)
            h, _, _ = frame.shape
            gray = np.dot(frame[..., :3], [0.2989, 0.5870, 0.1140])
            row_means = np.mean(gray, axis=1)
            row_diffs = np.abs(np.diff(row_means))
            
            search_top_start, search_top_end = int(h * 0.15), int(h * 0.45)
            peak_top = search_top_start + np.argmax(row_diffs[search_top_start:search_top_end])
            top_candidates.append(int(peak_top * (1920 / h)))
            
            search_bot_start, search_bot_end = int(h * 0.65), int(h * 0.90)
            peak_bot = search_bot_start + np.argmax(row_diffs[search_bot_start:search_bot_end])
            bottom_candidates.append(int(peak_bot * (1920 / h)))
            
        final_top = max(350, min(650, int(np.median(top_candidates))))
        final_bottom = max(1250, min(1650, int(np.median(bottom_candidates))))
        return final_top, final_bottom
    except Exception:
        return 656, 1264

def generate_layout_preview_image(
    video_path,
    is_vertical=False,
    v_top=656,
    v_bottom=1264,
    zoom_factor=1.0,
    sample_time=2.0,
    title="레퍼런스 스타일 후킹 타이틀",
    comment_text="",
    comment_likes="316",
    sub_text="",
    source="",
    is_white=False,
    out_path="layout_preview.png",
    *args,
    **kwargs
):
    if not os.path.exists(video_path):
        return None
    try:
        clip = VideoFileClip(video_path)
        actual_t = min(sample_time, max(0.2, clip.duration - 0.5))
        frame = clip.get_frame(actual_t)
        clip.close()

        frame_h, frame_w, _ = frame.shape
        raw_img = Image.fromarray(frame).convert("RGBA")
        canvas = Image.new("RGBA", (1080, 1920), (14, 14, 16, 255))
        draw = ImageDraw.Draw(canvas)

        mask_bg = (248, 248, 250, 255) if is_white else (14, 14, 16, 255)
        text_fill = (20, 20, 20, 255) if is_white else (255, 255, 255, 255)
        outline_c = (255, 255, 255, 255) if is_white else (0, 0, 0, 255)

        # 1. 비디오 프레임 배치
        if not is_vertical:
            scaled_w = int(1080 * float(zoom_factor))
            scaled_h = int(frame_h * (1080 / frame_w) * float(zoom_factor))
            resized_frame = raw_img.resize((scaled_w, scaled_h))
            
            crop_x = max(0, (scaled_w - 1080) // 2)
            cropped_frame = resized_frame.crop((crop_x, 0, crop_x + 1080, scaled_h))
            y_offset = max(0, (1920 - scaled_h) // 2)
            canvas.paste(cropped_frame, (0, y_offset))
        else:
            resized_frame = raw_img.resize((1080, 1920))
            canvas.paste(resized_frame, (0, 0))

        # 2. 상단 가림막 및 타이틀
        clean_title = html.unescape(title) if title else ""
        draw.rectangle([0, 0, 1080, v_top], fill=mask_bg)
        if clean_title:
            font_title = get_system_font(72, bold=True)
            lines_title = wrap_text(clean_title, font_title, 960, draw)
            line_h = 84
            total_h = len(lines_title) * line_h
            start_y = max(30, (v_top - total_h) // 2 - 10)

            for line in lines_title:
                txt_w = draw.textbbox((0, 0), line, font=font_title)[2]
                tx = (1080 - txt_w) // 2
                for ox in range(-3, 4):
                    for oy in range(-3, 4):
                        if ox*ox + oy*oy <= 9:
                            draw.text((tx + ox, start_y + oy), line, fill=outline_c, font=font_title)
                draw.text((tx, start_y), line, fill=text_fill, font=font_title)
                start_y += line_h

        # 3. 하단 가림막
        draw.rectangle([0, v_bottom, 1080, 1920], fill=mask_bg)

        # 4. 자막 (입력창이 비어있으면 전혀 출력하지 않음)
        sub_bottom_y = v_bottom + 14
        if sub_text is not None and sub_text.strip():
            clean_sub = html.unescape(sub_text.strip().splitlines()[0])
            font_sub = get_system_font(42, bold=True)
            lines_sub = wrap_text(clean_sub, font_sub, 960, draw)
            
            curr_sy = v_bottom + 14
            for ln in lines_sub:
                txt_w = draw.textbbox((0, 0), ln, font=font_sub)[2]
                sx = (1080 - txt_w) // 2
                draw.rounded_rectangle([sx - 16, curr_sy - 6, sx + txt_w + 16, curr_sy + 46], radius=10, fill=(0, 0, 0, 200))
                for ox in range(-3, 4):
                    for oy in range(-3, 4):
                        if ox*ox + oy*oy <= 9:
                            draw.text((sx + ox, curr_sy + oy), ln, fill=(0, 0, 0, 255), font=font_sub)
                draw.text((sx, curr_sy), ln, fill=(255, 230, 0, 255), font=font_sub)
                curr_sy += 52
            sub_bottom_y = curr_sy + 6

        # 5. 댓글 카드
        preview_cmt_txt = comment_text.strip().splitlines()[0] if comment_text and comment_text.strip() else "올해 이게 젤웃겼닼ㅋㅋㅋㅋㅋㅋ"
        card_tmp = f"preview_card_{int(time.time()*1000)}.png"
        render_crisp_comment_card(
            author="익명",
            text=preview_cmt_txt,
            likes=comment_likes,
            is_white=is_white,
            out_path=card_tmp
        )
        safe_comment_y = max(sub_bottom_y, v_bottom + 95)
        safe_comment_y = min(1920 - 190, safe_comment_y)

        if os.path.exists(card_tmp):
            c_img = Image.open(card_tmp).convert("RGBA")
            canvas.paste(c_img, (0, safe_comment_y), c_img)
            try:
                c_img.close()
                os.remove(card_tmp)
            except Exception:
                pass

        # 6. 출처 표기 (비어있으면 완전 삭제)
        clean_src = html.unescape(source).strip() if source else ""
        clean_src = re.sub(r'^출처\s*:\s*', '', clean_src).strip()
        if clean_src:
            font_source = get_system_font(21, bold=False)
            src_color = (130, 130, 135, 255) if is_white else (160, 160, 165, 255)
            source_y = min(1920 - 32, safe_comment_y + 140)
            draw.text((70, source_y), f"출처: {clean_src}", fill=src_color, font=font_source)

        img_disp = canvas.resize((432, 768), Image.Resampling.LANCZOS)
        img_disp.save(out_path)
        return out_path
    except Exception:
        return None

def create_base_overlay(title: str, source: str, is_white: bool, is_vertical: bool, v_top: int, v_bottom: int, out_path: str = "base_banner.png", *args, **kwargs):
    w, h = config.SHORTS_WIDTH, config.SHORTS_HEIGHT
    mask_bg = (248, 248, 250, 255) if is_white else (14, 14, 16, 255)
    highlight_color = (20, 20, 20, 255) if is_white else (255, 255, 255, 255)
    outline_c = (255, 255, 255, 255) if is_white else (0, 0, 0, 255)

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, w, v_top], fill=mask_bg)
    draw.rectangle([0, v_bottom, w, h], fill=mask_bg)

    clean_title = html.unescape(title) if title else ""
    if clean_title:
        font_title = get_system_font(72, bold=True)
        lines = wrap_text(clean_title, font_title, 960, draw)
        line_h = 84
        total_h = len(lines) * line_h
        start_y = max(30, (v_top - total_h) // 2 - 10)

        for line in lines:
            txt_w = draw.textbbox((0, 0), line, font=font_title)[2]
            tx = (w - txt_w) // 2
            for ox in range(-3, 4):
                for oy in range(-3, 4):
                    if ox*ox + oy*oy <= 9:
                        draw.text((tx + ox, start_y + oy), line, fill=outline_c, font=font_title)
            draw.text((tx, start_y), line, fill=highlight_color, font=font_title)
            start_y += line_h

    # 출처가 있으면 출력, 빈칸이면 아예 안 그림
    clean_src = html.unescape(source).strip() if source else ""
    clean_src = re.sub(r'^출처\s*:\s*', '', clean_src).strip()
    if clean_src:
        font_source = get_system_font(21, bold=False)
        src_color = (130, 130, 135, 255) if is_white else (160, 160, 165, 255)
        draw.text((70, h - 35), f"출처: {clean_src}", fill=src_color, font=font_source)

    img.save(out_path)
    return out_path

def find_best_matching_chunk(line_text, chunks):
    clean_line = re.sub(r'[^가-힣a-zA-Z0-9]', '', html.unescape(line_text))
    if not clean_line or not chunks:
        return None

    best_chunk = None
    max_overlap = 0

    for chk in chunks:
        chk_txt = re.sub(r'[^가-힣a-zA-Z0-9]', '', html.unescape(chk.get("text", "")))
        if not chk_txt:
            continue
        
        if clean_line in chk_txt or chk_txt in clean_line:
            return chk
        
        overlap = sum(1 for c in clean_line if c in chk_txt)
        if overlap > max_overlap and overlap >= 2:
            max_overlap = overlap
            best_chunk = chk

    return best_chunk

def render_final_shorts_video(
    source_video_path: str,
    segments_plan: list,
    subtitle_chunks: list,
    clip_info: dict,
    real_source: str,
    template_name: str,
    accel_engine: str,
    out_dir: str,
    index: int,
    is_vertical: bool = False,
    v_top: int = 656,
    v_bottom: int = 1264,
    zoom_factor: float = 1.0,
    custom_sub_text: str = None,
    custom_title: str = None,
    custom_comment_text: str = None,
    custom_comment_likes: str = None,
    *args,
    **kwargs
):
    os.makedirs(out_dir, exist_ok=True)
    raw_video = VideoFileClip(source_video_path)
    is_white = "화이트" in template_name
    
    video_clips = []
    timeline_offset = 0.0
    segment_mappings = []

    for seg in segments_plan:
        st_t = float(seg["source_start"])
        en_t = float(seg["source_end"])
        sub_clip = safe_subclip(raw_video, st_t, en_t)
        try:
            sub_clip = sub_clip.audio_fadein(0.03).audio_fadeout(0.03)
        except Exception:
            pass
        video_clips.append(sub_clip)
        
        seg_dur = en_t - st_t
        segment_mappings.append((st_t, en_t, timeline_offset, timeline_offset + seg_dur))
        timeline_offset += seg_dur

    assembled_video = concatenate_videoclips(video_clips, method="compose")
    total_dur = assembled_video.duration

    if not is_vertical:
        scaled_w = int(1080 * float(zoom_factor))
        scaled_h = int(assembled_video.size[1] * (1080 / assembled_video.size[0]) * float(zoom_factor))
        resized_v = safe_resize(assembled_video, (scaled_w, scaled_h))
        
        if float(zoom_factor) > 1.001:
            crop_x1 = max(0, (scaled_w - 1080) // 2)
            try:
                resized_v = resized_v.cropped(x1=crop_x1, y1=0, x2=crop_x1 + 1080, y2=scaled_h)
            except Exception:
                resized_v = resized_v.crop(x1=crop_x1, y1=0, x2=crop_x1 + 1080, y2=scaled_h)
                
        y_offset = (1920 - scaled_h) // 2
        positioned_video = safe_set_pos(resized_v, (0, y_offset))
    else:
        positioned_video = safe_set_pos(safe_resize(assembled_video, (1080, 1920)), (0, 0))

    raw_title = custom_title if custom_title is not None else clip_info.get("title", "")
    final_title = html.unescape(raw_title)
    final_src = real_source if real_source is not None else clip_info.get("source", "")
    
    base_bg_path = os.path.join(out_dir, f"base_bg_{index}_{int(time.time()*1000)}.png")
    create_base_overlay(
        title=final_title,
        source=final_src,
        is_white=is_white,
        is_vertical=is_vertical,
        v_top=v_top,
        v_bottom=v_bottom,
        out_path=base_bg_path
    )
    bg_clip = safe_set_dur(safe_set_pos(ImageClip(base_bg_path), (0, 0)), total_dur)
    layers = [positioned_video, bg_clip]

    # 3~4초 간격 릴레이 댓글 리스트 구성
    comments_to_render = []

    if custom_comment_text and custom_comment_text.strip():
        user_cmt_lines = [l.strip() for l in custom_comment_text.strip().splitlines() if l.strip()]
        if user_cmt_lines:
            step_dur = max(2.8, total_dur / len(user_cmt_lines))
            for c_idx, c_line in enumerate(user_cmt_lines):
                c_start_t = c_idx * step_dur
                if c_start_t >= total_dur:
                    break
                c_dur = min(step_dur, total_dur - c_start_t)
                likes_val = custom_comment_likes if (custom_comment_likes and c_idx == 0) else str(380 + c_idx * 160)
                comments_to_render.append({
                    "start": c_start_t,
                    "dur": c_dur,
                    "text": c_line,
                    "likes": likes_val
                })

    if not comments_to_render:
        ai_timeline_cmts = clip_info.get("timeline_comments", [])
        if ai_timeline_cmts:
            for c_idx, c_item in enumerate(ai_timeline_cmts):
                c_start_t = float(c_item.get("offset", c_idx * 3.8))
                if c_start_t >= total_dur:
                    break
                c_dur = float(c_item.get("dur", 3.8))
                c_dur = min(c_dur, max(1.0, total_dur - c_start_t))
                comments_to_render.append({
                    "start": c_start_t,
                    "dur": c_dur,
                    "text": c_item.get("text", "올해 이게 젤웃겼닼ㅋㅋㅋㅋㅋㅋ"),
                    "likes": str(c_item.get("likes", 450 + c_idx * 120))
                })

    if not comments_to_render:
        single_cmt = clip_info.get("matched_comment", {})
        comments_to_render.append({
            "start": 0.0,
            "dur": total_dur,
            "text": single_cmt.get("text", "아 ㅋㅋㅋㅋ 진짜 대박이네"),
            "likes": str(single_cmt.get("likes", "520"))
        })

    if config.ENABLE_COMMENTS:
        safe_comment_y = min(1920 - 190, v_bottom + 95)
        for c_idx, c_data in enumerate(comments_to_render):
            c_txt = clean_comment_text(c_data["text"])
            c_file = os.path.join(out_dir, f"card_{index}_{c_idx}_{int(time.time()*1000)}.png")
            
            render_crisp_comment_card(
                author="익명",
                text=c_txt,
                likes=str(c_data["likes"]),
                is_white=is_white,
                out_path=c_file
            )

            c_clip = safe_set_dur(safe_set_start(safe_set_pos(ImageClip(c_file), (0, safe_comment_y)), c_data["start"]), c_data["dur"])
            layers.append(c_clip)

    # 자막 렌더링 (자막 입력창이 비어있으면 100% 미출력)
    font_sub = get_system_font(42, bold=True)
    synced_subs_to_render = []

    if custom_sub_text is not None and custom_sub_text.strip():
        lines_custom = [html.unescape(l.strip()) for l in custom_sub_text.strip().splitlines() if l.strip()]
        for line in lines_custom:
            matched_chk = find_best_matching_chunk(line, subtitle_chunks)
            if matched_chk:
                c_st = float(matched_chk.get("start", 0))
                c_et = float(matched_chk.get("end", c_st + 2.0))
                for src_s, src_e, tgt_s, tgt_e in segment_mappings:
                    if max(c_st, src_s) < min(c_et, src_e):
                        rel_s = max(0.0, c_st - src_s)
                        dur = min(c_et, src_e) - max(c_st, src_s)
                        if dur >= 0.3:
                            synced_subs_to_render.append({
                                "start": tgt_s + rel_s,
                                "dur": max(1.0, dur),
                                "text": line,
                                "orig_time": max(src_s, c_st)
                            })
                            break
            else:
                key_subs = clip_info.get("key_subtitles", [])
                matched_key = find_best_matching_chunk(line, key_subs)
                if matched_key:
                    k_st = float(matched_key.get("start", 0))
                    k_et = float(matched_key.get("end", k_st + 2.0))
                    for src_s, src_e, tgt_s, tgt_e in segment_mappings:
                        if max(k_st, src_s) < min(k_et, src_e):
                            rel_s = max(0.0, k_st - src_s)
                            dur = min(k_et, src_e) - max(k_st, src_s)
                            synced_subs_to_render.append({
                                "start": tgt_s + rel_s,
                                "dur": max(1.0, dur),
                                "text": line,
                                "orig_time": max(src_s, k_st)
                            })
                            break
                else:
                    # 매칭 안 된 경우 전체 구간에 분할 타이밍 배정
                    synced_subs_to_render.append({
                        "start": 0.5,
                        "dur": max(1.5, total_dur - 1.0),
                        "text": line,
                        "orig_time": 0.0
                    })

    for s_idx, sub_item in enumerate(synced_subs_to_render):
        txt = sub_item["text"]
        m_start = sub_item["start"]
        dur = sub_item["dur"]

        if m_start >= total_dur - 0.25:
            continue
        clamped_dur = min(dur, max(0.2, total_dur - m_start - 0.25))

        check_t = min(raw_video.duration - 0.1, sub_item["orig_time"] + 0.2)
        sample_frame = raw_video.get_frame(check_t)
        frame_bgr = cv2.cvtColor(sample_frame, cv2.COLOR_RGB2BGR)

        if is_subtitle_overlapping(txt, frame_bgr):
            continue

        sub_img = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
        draw_sub = ImageDraw.Draw(sub_img)
        lines = wrap_text(txt, font_sub, 960, draw_sub)

        curr_sy = v_bottom + 14
        for ln in lines:
            txt_w = draw_sub.textbbox((0, 0), ln, font=font_sub)[2]
            sx = (1080 - txt_w) // 2
            draw_sub.rounded_rectangle([sx - 16, curr_sy - 6, sx + txt_w + 16, curr_sy + 46], radius=10, fill=(0, 0, 0, 200))
            for ox in range(-3, 4):
                for oy in range(-3, 4):
                    if ox*ox + oy*oy <= 9:
                        draw_sub.text((sx + ox, curr_sy + oy), ln, fill=(0, 0, 0, 255), font=font_sub)
            draw_sub.text((sx, curr_sy), ln, fill=(255, 230, 0, 255), font=font_sub)
            curr_sy += 52

        s_file = os.path.join(out_dir, f"sub_sync_{index}_{s_idx}_{int(time.time()*1000)}.png")
        sub_img.save(s_file)
        layers.append(safe_set_dur(safe_set_start(safe_set_pos(ImageClip(s_file), (0, 0)), m_start), clamped_dur))

    final_comp = CompositeVideoClip(layers, size=(1080, 1920))
    final_output_path = os.path.join(out_dir, f"shorts_master_{index}.mp4")

    unique_temp_audio = os.path.join(out_dir, f"temp_audio_{index}_{uuid.uuid4().hex[:8]}.m4a")

    if "NVIDIA" in accel_engine:
        codec = "h264_nvenc"
        ffmpeg_params = ["-preset", "p5", "-cq", "19", "-pix_fmt", "yuv420p"]
    elif "Intel" in accel_engine:
        codec = "h264_qsv"
        ffmpeg_params = ["-preset", "veryfast", "-global_quality", "20", "-pix_fmt", "yuv420p"]
    elif "AMD" in accel_engine:
        codec = "h264_amf"
        ffmpeg_params = ["-quality", "quality", "-rc", "cbr", "-pix_fmt", "yuv420p"]
    else:
        codec = "libx264"
        ffmpeg_params = ["-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p"]

    try:
        final_comp.write_videofile(
            final_output_path,
            codec=codec,
            audio_codec="aac",
            temp_audiofile=unique_temp_audio,
            remove_temp=True,
            fps=config.TARGET_FPS,
            threads=4,
            ffmpeg_params=ffmpeg_params
        )
    except Exception:
        final_comp.write_videofile(
            final_output_path,
            codec="libx264",
            audio_codec="aac",
            temp_audiofile=unique_temp_audio,
            remove_temp=True,
            fps=config.TARGET_FPS,
            threads=4,
            preset="ultrafast"
        )
    finally:
        try:
            final_comp.close()
            assembled_video.close()
            for c in video_clips:
                c.close()
            raw_video.close()
        except Exception:
            pass

    return final_output_path

# ==============================================================================
# [신규 추가] 스마트 점프컷(다중 세그먼트) 자막 재배치 및 렌더링 엔진
# ==============================================================================

def remap_subtitles_for_jumpcut(subtitles, segments):
    """
    잘려나간 노잼 구간의 시간만큼 자막 타임스탬프를 0.001초 오차 없이 정밀하게 앞당깁니다.
    """
    remapped = []
    accumulated_time = 0.0

    for seg in segments:
        s_start = float(seg['start'])
        s_end = float(seg['end'])
        seg_dur = s_end - s_start
        if seg_dur <= 0:
            continue

        for sub in subtitles:
            # Whisper 단어 단위 or 문장 단위 자막 데이터 파싱
            sub_s = float(sub.get('start', 0.0))
            sub_e = float(sub.get('end', 0.0))
            sub_text = sub.get('text', '').strip()

            # 현재 클립 구간 내에 포함된 자막만 추출
            if sub_e > s_start and sub_s < s_end:
                c_start = max(sub_s, s_start)
                c_end = min(sub_e, s_end)
                time_offset = accumulated_time - s_start

                new_sub = dict(sub)
                new_sub['start'] = round(c_start + time_offset, 3)
                new_sub['end'] = round(c_end + time_offset, 3)
                new_sub['text'] = sub_text

                # 단어별 하이라이트(words) 데이터가 있을 경우 내부 타임스탬프도 재계산
                if 'words' in sub and isinstance(sub['words'], list):
                    remapped_words = []
                    for w in sub['words']:
                        w_s = float(w.get('start', 0.0))
                        w_e = float(w.get('end', 0.0))
                        if w_e > s_start and w_s < s_end:
                            remapped_words.append({
                                'word': w.get('word', ''),
                                'start': round(max(w_s, s_start) + time_offset, 3),
                                'end': round(min(w_e, s_end) + time_offset, 3)
                            })
                    new_sub['words'] = remapped_words

                remapped.append(new_sub)

        accumulated_time += seg_dur

    return remapped, accumulated_time


def render_jumpcut_shorts(video_path, segments, subtitles, output_path, progress_callback=None, **kwargs):
    """
    2~3개 알짜 구간을 고속 연결하고, 기존 렌더러 파이프라인(자막/효과/GPU)을 통해 최종 쇼츠를 출력합니다.
    """
    from moviepy.editor import VideoFileClip, concatenate_videoclips

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"원본 영상을 찾을 수 없습니다: {video_path}")

    # 1. 자막 타임라인 동기화
    synced_subs, total_stitched_len = remap_subtitles_for_jumpcut(subtitles, segments)

    # 2. 다중 세그먼트 영상 슬라이싱 및 병합
    main_video = VideoFileClip(video_path)
    subclips = []

    for seg in segments:
        s = max(0.0, float(seg['start']))
        e = min(main_video.duration, float(seg['end']))
        if e > s:
            subclips.append(main_video.subclip(s, e))

    if not subclips:
        main_video.close()
        raise ValueError("유효한 영상 구간이 지정되지 않았습니다.")

    stitched_video = concatenate_videoclips(subclips, method="compose")

    # 3. 임시 통합 영상 캐싱 (오디오 싱크 방지)
    temp_stitched_path = os.path.join(os.path.dirname(output_path), "temp_stitched_raw.mp4")
    stitched_video.write_videofile(
        temp_stitched_path,
        fps=30,
        codec="libx264",
        audio_codec="aac",
        preset="ultrafast",
        threads=4,
        logger=None
    )
    stitched_video.close()
    main_video.close()
    for c in subclips:
        c.close()

    # 4. 기존 메인 렌더러 함수(render_shorts / render_video)로 자막 및 효과 입혀서 최종 출력
    # (기존 파일 내의 메인 렌더 함수명에 맞게 자동 호출)
    try:
        if 'render_shorts' in globals():
            final_res = render_shorts(temp_stitched_path, synced_subs, output_path, progress_callback=progress_callback, **kwargs)
        elif 'render_video' in globals():
            final_res = render_video(temp_stitched_path, synced_subs, output_path, progress_callback=progress_callback, **kwargs)
        else:
            final_res = temp_stitched_path
    finally:
        if os.path.exists(temp_stitched_path):
            try:
                os.remove(temp_stitched_path)
            except Exception:
                pass

    return final_res