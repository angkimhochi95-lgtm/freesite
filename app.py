# -*- coding: utf-8 -*-
# app.py
import streamlit as st
import os
import io
import json
import zipfile
import shutil
import importlib
import re
import time
import uuid
import gc
from datetime import datetime
import yt_dlp
import config

# 모듈 핫 리로드
import modules.transcription
import modules.highlight_analyzer
import modules.structure_engine
import modules.comment_engine
import modules.renderer
import modules.youtube_service

importlib.reload(modules.transcription)
importlib.reload(modules.highlight_analyzer)
importlib.reload(modules.structure_engine)
importlib.reload(modules.comment_engine)
importlib.reload(modules.renderer)
importlib.reload(modules.youtube_service)

from modules.transcription import transcribe_audio_with_word_timestamps
from modules.highlight_analyzer import analyze_video_highlights
from modules.structure_engine import build_shorts_timeline_plan
from modules.renderer import render_final_shorts_video, generate_layout_preview_image, auto_detect_video_boundary

from modules.youtube_service import (
    DEFAULT_YOUTUBE_API_KEY,
    CATEGORY_QUERY_MAP,
    get_official_trending_videos,
    search_custom_videos,
    fetch_real_video_comments,
    extract_youtube_video_id,
    format_duration
)

try:
    from moviepy.editor import VideoFileClip, concatenate_videoclips
except ImportError:
    from moviepy import VideoFileClip, concatenate_videoclips

BASE_CACHE_DIR = getattr(config, "BASE_CACHE_DIR", ".")
COOKIE_FILE_PATH = os.path.join(BASE_CACHE_DIR, "cookies.txt")

st.set_page_config(
    page_title="이지컷(EasyCut) AI 올인원 숏폼 스튜디오 Pro",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

PROJECTS_DIR = "saved_projects"
ACTIVE_SESSION_FILE = "active_session_cache.json"
os.makedirs(PROJECTS_DIR, exist_ok=True)

# =========================================================================
# 무결점 안티봇 다운로드 엔진
# =========================================================================
def download_media_final_v2(video_url, output_path):
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
    for c_cand in [COOKIE_FILE_PATH, "cookies.txt", os.path.join(os.getcwd(), "cookies.txt")]:
        if os.path.exists(c_cand) and os.path.getsize(c_cand) > 100:
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
    try:
        raw_v = VideoFileClip(source_path)
        clips = []
        for seg in segments_plan:
            st_t = float(seg["source_start"])
            en_t = float(seg["source_end"])
            sub = raw_v.subclip(st_t, en_t) if hasattr(raw_v, "subclip") else raw_v.subclipped(st_t, en_t)
            clips.append(sub)
        
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

def save_active_session_to_disk():
    state_to_save = {
        "gemini_key_input": st.session_state.get("gemini_key_input", ""),
        "video_url_input": st.session_state.get("video_url_input", ""),
        "active_source_path": st.session_state.get("active_source_path", ""),
        "stage_video_title": st.session_state.get("stage_video_title", ""),
        "channel_source_name": st.session_state.get("channel_source_name", ""),
        "source_video_duration": st.session_state.get("source_video_duration", 0.0),
        "is_source_vertical": st.session_state.get("is_source_vertical", False),
        "detected_v_top": st.session_state.get("detected_v_top", 656),
        "detected_v_bottom": st.session_state.get("detected_v_bottom", 1264),
        "raw_transcript_segments": st.session_state.get("raw_transcript_segments", []),
        "subtitle_chunks": st.session_state.get("subtitle_chunks", []),
        "real_comments_pool": st.session_state.get("real_comments_pool", []),
        "staged_clips": st.session_state.get("staged_clips", None),
        "real_source": st.session_state.get("real_source", ""),
        "generated_results": st.session_state.get("generated_results", []),
        "current_project_id": st.session_state.get("current_project_id", None)
    }
    try:
        with open(ACTIVE_SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(state_to_save, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def load_active_session_from_disk():
    if os.path.exists(ACTIVE_SESSION_FILE):
        try:
            with open(ACTIVE_SESSION_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                for k, v in saved.items():
                    if k not in st.session_state or not st.session_state[k]:
                        st.session_state[k] = v
        except Exception:
            pass

def clear_active_session():
    if os.path.exists(ACTIVE_SESSION_FILE):
        try:
            os.remove(ACTIVE_SESSION_FILE)
        except Exception:
            pass
    st.session_state["staged_clips"] = None
    st.session_state["generated_results"] = []
    st.session_state["raw_transcript_segments"] = []
    st.session_state["subtitle_chunks"] = []
    st.session_state["real_comments_pool"] = []
    st.session_state["source_video_duration"] = 0.0
    st.session_state["channel_source_name"] = ""
    st.session_state["current_project_id"] = None
    st.session_state["active_source_path"] = ""
    gc.collect()

if "session_initialized" not in st.session_state:
    st.session_state["session_initialized"] = True
    load_active_session_from_disk()

if "generated_results" not in st.session_state:
    st.session_state["generated_results"] = []
if "raw_transcript_segments" not in st.session_state:
    st.session_state["raw_transcript_segments"] = []
if "subtitle_chunks" not in st.session_state:
    st.session_state["subtitle_chunks"] = []
if "real_comments_pool" not in st.session_state:
    st.session_state["real_comments_pool"] = []
if "source_video_duration" not in st.session_state:
    st.session_state["source_video_duration"] = 0.0
if "is_source_vertical" not in st.session_state:
    st.session_state["is_source_vertical"] = False
if "detected_v_top" not in st.session_state:
    st.session_state["detected_v_top"] = 656
if "detected_v_bottom" not in st.session_state:
    st.session_state["detected_v_bottom"] = 1264
if "current_project_id" not in st.session_state:
    st.session_state["current_project_id"] = None
if "staged_clips" not in st.session_state:
    st.session_state["staged_clips"] = None
if "stage_video_title" not in st.session_state:
    st.session_state["stage_video_title"] = ""
if "channel_source_name" not in st.session_state:
    st.session_state["channel_source_name"] = ""
if "active_source_path" not in st.session_state:
    st.session_state["active_source_path"] = ""
if "nav_selection" not in st.session_state:
    st.session_state["nav_selection"] = "🎬 AI 숏폼 제작 스튜디오"
if "gemini_key_input" not in st.session_state:
    st.session_state["gemini_key_input"] = ""
if "video_url_input" not in st.session_state:
    st.session_state["video_url_input"] = ""

def format_time(seconds):
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"

def save_project_to_disk(project_id, title_text, results, transcript_segments, duration, is_vertical=False):
    p_path = os.path.join(PROJECTS_DIR, project_id)
    os.makedirs(p_path, exist_ok=True)
    meta = {
        "id": project_id,
        "title": title_text,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "duration": duration,
        "is_vertical": is_vertical,
        "results": results,
        "transcript_segments": transcript_segments
    }
    with open(os.path.join(p_path, "project.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

def load_all_saved_projects():
    projects = []
    if not os.path.exists(PROJECTS_DIR):
        return []
    for p_id in sorted(os.listdir(PROJECTS_DIR), reverse=True):
        meta_file = os.path.join(PROJECTS_DIR, p_id, "project.json")
        if os.path.exists(meta_file):
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    projects.append(json.load(f))
            except Exception:
                continue
    return projects

st.sidebar.title("🎛️ 워크스페이스 내비게이션")
nav_options = ["🎬 AI 숏폼 제작 스튜디오", "🔥 실시간 인기 & 맞춤 탐색기"]

current_nav = st.session_state.get("nav_selection", nav_options[0])
if current_nav not in nav_options:
    current_nav = nav_options[0]

menu_choice = st.sidebar.radio(
    "메뉴 이동:",
    nav_options,
    index=nav_options.index(current_nav)
)
st.session_state["nav_selection"] = menu_choice

st.sidebar.markdown("---")
st.sidebar.subheader("📚 지난 프로젝트 보관함")
saved_list = load_all_saved_projects()
if saved_list:
    options = [f"[{p.get('date', '')[:16]}] {p.get('title', '제목 없음')[:20]}" for p in saved_list]
    selected_idx = st.sidebar.selectbox("보관함 프로젝트:", range(len(options)), format_func=lambda x: options[x], key="sb_project_selector")
    
    col_sb1, col_sb2 = st.sidebar.columns(2)
    with col_sb1:
        if st.button("📂 불러오기", use_container_width=True, key="btn_sb_load_project"):
            p_data = saved_list[selected_idx]
            st.session_state["current_project_id"] = p_data.get("id")
            st.session_state["generated_results"] = p_data.get("results", [])
            st.session_state["raw_transcript_segments"] = p_data.get("transcript_segments", [])
            st.session_state["source_video_duration"] = p_data.get("duration", 0.0)
            st.session_state["is_source_vertical"] = p_data.get("is_vertical", False)
            st.session_state["staged_clips"] = None
            st.session_state["nav_selection"] = nav_options[0]
            save_active_session_to_disk()
            st.rerun()
    with col_sb2:
        if st.button("🗑️ 삭제하기", use_container_width=True, key="btn_sb_delete_project"):
            p_id = saved_list[selected_idx].get("id")
            target_p = os.path.join(PROJECTS_DIR, p_id)
            if os.path.exists(target_p):
                shutil.rmtree(target_p)
            if st.session_state.get("current_project_id") == p_id:
                st.session_state["generated_results"] = []
            st.rerun()
else:
    st.sidebar.info("보관된 지난 프로젝트가 없습니다.")

# =========================================================================
# 화면 1: 🔥 유튜브 실시간 인기 & 맞춤 탐색기
# =========================================================================
if st.session_state["nav_selection"] == "🔥 실시간 인기 & 맞춤 탐색기":
    st.markdown("## 🔥 유튜브 실시간 인기 & 맞춤 탐색기")
    st.caption("인기 급상승 차트와 카테고리별 대량 고속 탐색 · 클릭 한 번으로 숏폼 제작대로 즉시 전송")

    category_list = list(CATEGORY_QUERY_MAP.keys())
    region_options = ["🇰🇷 국내만 (KR)", "🌐 해외만 (US/글로벌)", "🌍 국내 + 해외 전체"]
    period_options = ["전체 기간", "일간 (최근 24시간)", "주간 (최근 7일)", "월간 (최근 30일)", "특정 연·월 지정"]
    length_options = ["전체", "롱폼만 (70초 초과)", "숏폼만 (60초 이하)"]

    tab_trend, tab_search = st.tabs(["📈 유튜브 실시간 급상승 차트", "🔍 키워드 & 카테고리/기간 정밀 탐색"])

    with tab_trend:
        t_col1, t_col2, t_col3, t_col4, t_col5 = st.columns([1.8, 1.4, 1.8, 1.1, 0.9])
        with t_col1:
            trend_cat_name = st.selectbox("카테고리 선택:", category_list, key="trend_cat")
        with t_col2:
            trend_region = st.selectbox("국가/지역 범위:", region_options, key="trend_region")
        with t_col3:
            trend_len = st.selectbox("영상 길이:", length_options, key="trend_len")
        with t_col4:
            st.write("")
            trend_cc = st.checkbox("재사용(CC)만", value=False, key="trend_cc")
        with t_col5:
            st.write("")
            btn_trend = st.button("차트 갱신", use_container_width=True, key="btn_trend")

        if btn_trend:
            get_official_trending_videos.clear()

        with st.spinner("실시간 유튜브 공식 인기 급상승 차트 불러오는 중..."):
            trend_list = get_official_trending_videos(
                DEFAULT_YOUTUBE_API_KEY,
                category_name=trend_cat_name,
                region_mode=trend_region,
                only_cc=trend_cc,
                length_type=trend_len
            )

        if trend_list:
            cols = st.columns(3)
            for idx, vid in enumerate(trend_list):
                with cols[idx % 3]:
                    st.image(vid["thumb"], use_container_width=True)
                    badge = "숏폼" if vid["duration"] <= 60 else f"{format_duration(vid['duration'])}"
                    cc_badge = " · CC재사용" if vid["is_cc"] else ""
                    st.markdown(f"**{vid['title'][:28]}...**" if len(vid['title']) > 28 else f"**{vid['title']}**")
                    st.caption(f"채널: {vid['channel']} · 조회수: {vid['views']:,}회\n게시: {vid['published_at']} [{badge}{cc_badge}]")
                    if st.button("이 영상으로 숏폼 만들기", key=f"sel_t_{vid['id']}_{idx}", use_container_width=True):
                        st.session_state["video_url_input"] = vid["url"]
                        st.session_state["nav_selection"] = "🎬 AI 숏폼 제작 스튜디오"
                        save_active_session_to_disk()
                        st.rerun()
        else:
            st.info("조건에 맞는 급상승 영상이 없습니다. CC 필터를 끄거나 길이를 '전체'로 설정해보세요.")

    with tab_search:
        s_col1, s_col2 = st.columns([2, 1])
        with s_col1:
            search_kw = st.text_input("검색 키워드:", placeholder="예: 무한도전, 침착맨, 피지컬갤러리, 런닝맨", key="s_kw")
        with s_col2:
            search_cat_name = st.selectbox("카테고리 필터:", category_list, key="s_cat")

        f_col1, f_col2, f_col3, f_col4, f_col5 = st.columns([1.2, 1.2, 1.6, 1.1, 0.9])
        with f_col1:
            search_region = st.selectbox("국가/지역 범위:", region_options, key="s_region")
        with f_col2:
            search_period = st.selectbox("기간 설정:", period_options, index=0, key="s_period")
        with f_col3:
            search_len = st.selectbox("영상 길이:", length_options, index=1, key="s_len")
        with f_col4:
            st.write("")
            search_cc = st.checkbox("재사용(CC)만 보기", value=False, key="s_cc")
        with f_col5:
            st.write("")
            btn_search = st.button("탐색 실행", use_container_width=True, key="btn_s")

        sel_year, sel_month = None, None
        if search_period == "특정 연·월 지정":
            y_col, m_col, _ = st.columns([1, 1, 2])
            with y_col:
                sel_year = st.selectbox("연도 선택:", [str(y) for y in range(2026, 2019, -1)], key="sel_y")
            with m_col:
                sel_month = st.selectbox("월 선택:", [f"{m:02d}" for m in range(1, 13)], key="sel_m")

        if btn_search or "search_data_cache" not in st.session_state:
            with st.spinner(f"[{search_period}] 기준 인기 영상 탐색 중..."):
                st.session_state["search_data_cache"] = search_custom_videos(
                    DEFAULT_YOUTUBE_API_KEY,
                    keyword=search_kw,
                    category_name=search_cat_name,
                    region_mode=search_region,
                    period_type=search_period,
                    selected_year=sel_year,
                    selected_month=sel_month,
                    only_cc=search_cc,
                    length_type=search_len
                )

        search_list = st.session_state.get("search_data_cache", [])
        if search_list:
            cols = st.columns(3)
            for idx, vid in enumerate(search_list):
                with cols[idx % 3]:
                    st.image(vid["thumb"], use_container_width=True)
                    badge = "숏폼" if vid["duration"] <= 60 else f"{format_duration(vid['duration'])}"
                    cc_badge = " · CC재사용" if vid["is_cc"] else ""
                    st.markdown(f"**{vid['title'][:28]}...**" if len(vid['title']) > 28 else f"**{vid['title']}**")
                    st.caption(f"채널: {vid['channel']} · 조회수: {vid['views']:,}회\n게시: {vid['published_at']} [{badge}{cc_badge}]")
                    if st.button("이 영상으로 숏폼 만들기", key=f"sel_s_{vid['id']}_{idx}", use_container_width=True):
                        st.session_state["video_url_input"] = vid["url"]
                        st.session_state["nav_selection"] = "🎬 AI 숏폼 제작 스튜디오"
                        save_active_session_to_disk()
                        st.rerun()
        else:
            st.info(f"선택한 조건([{search_period}])에 맞는 영상이 없습니다. CC 필터를 해제하거나 기간을 완화해보세요.")

# =========================================================================
# 화면 2: 🎬 AI 숏폼 제작 스튜디오
# =========================================================================
else:
    head_col1, head_col2 = st.columns([4, 1])
    with head_col1:
        st.title("🎬 이지컷(EasyCut) AI 올인원 숏폼 스튜디오 Pro")
        st.caption("유튜브 · 틱톡 · 인스타 릴스 · X(트위터) · 웹 링크 & PC 영상 직접 업로드 올인원 숏폼 제작기")
    with head_col2:
        st.write("")
        if st.button("새 작업 시작 (초기화)", use_container_width=True, key="btn_clear_main_session"):
            clear_active_session()
            st.rerun()

    if st.session_state.get("staged_clips") or st.session_state.get("generated_results"):
        st.info("이전 작업 상태가 안전하게 복원되었습니다. (새로운 영상으로 작업하시려면 우측 상단 '새 작업 시작'을 누르세요)")

    st.markdown("### ⚙️ 1. 영상 입력 및 AI 설정")
    
    gemini_api_key = st.text_input(
        "🔑 Gemini API 키 입력",
        type="password",
        value=st.session_state.get("gemini_key_input", ""),
        key="gemini_key_input",
        placeholder="AIzaSy..."
    )

    with st.expander("🔐 유튜브 로그인 인증 쿠키 관리", expanded=False):
        has_cookie = os.path.exists(COOKIE_FILE_PATH) and os.path.getsize(COOKIE_FILE_PATH) > 100
        if has_cookie:
            st.success("✅ cookies.txt 활성화됨")
            if st.button("쿠키 파일 삭제", key="btn_del_cookie"):
                try:
                    os.remove(COOKIE_FILE_PATH)
                    st.rerun()
                except Exception: pass
        else:
            uploaded_cookie = st.file_uploader("cookies.txt 업로드:", type=["txt"], key="cookie_file_uploader")
            if uploaded_cookie is not None:
                with open(COOKIE_FILE_PATH, "wb") as f_c:
                    f_c.write(uploaded_cookie.getbuffer())
                st.success("쿠키 등록 완료")
                st.rerun()

    tab_url_in, tab_file_in = st.tabs(["🔗 영상 URL 입력 (유튜브/틱톡/인스타/웹링크)", "📁 내 PC 영상 파일 직접 업로드 (MP4/MKV/MOV)"])

    with tab_url_in:
        video_url = st.text_input(
            "영상 링크를 입력하세요:",
            value=st.session_state.get("video_url_input", ""),
            key="video_url_input",
            placeholder="https://www.youtube.com/watch?v=... 또는 틱톡/인스타/트위터 링크"
        )

    with tab_file_in:
        uploaded_video_file = st.file_uploader(
            "PC에서 영상 파일을 직접 선택하거나 끌어다 놓으세요:",
            type=["mp4", "mkv", "mov", "webm", "avi"],
            key="local_video_file_uploader"
        )

    is_vertical_url = any(k in video_url.lower() for k in ["/shorts/", "tiktok.com", "instagram.com/reel", "/reels/"]) if video_url else False
    is_youtube = any(k in video_url.lower() for k in ["youtube.com", "youtu.be"]) if video_url else False

    col_opt1, col_opt2, col_opt3 = st.columns(3)
    with col_opt1:
        if is_vertical_url:
            st.info("📱 세로 숏폼 감지: 원본 비율을 유지하며 상하단 가림막 및 자막을 합성합니다.")
            video_count = 1
        else:
            video_count = st.slider("생성할 쇼츠 개수", 1, 5, 3, key="slider_video_count")
    with col_opt2:
        design_template = st.selectbox("🎨 디자인 템플릿", ["댓글 캡처 (다크)", "댓글 캡처 (화이트)", "심플 다크", "심플 화이트"], key="sel_design_template")
    with col_opt3:
        accel_choice = st.selectbox("⚡ 렌더링 가속 엔진", ["⚡ NVIDIA GPU 가속 (h264_nvenc)", "⚡ Intel QuickSync 가속 (h264_qsv)", "💻 CPU 초고속 멀티스레드 (libx264)"], key="sel_accel_choice")

    if st.button("🔍 1단계: 영상 준비 & Whisper 음성/대본 정밀 분석 시작", type="primary", use_container_width=True, key="btn_start_analysis_step1"):
        if not gemini_api_key:
            st.error("Gemini API 키를 입력해주세요.")
        elif not video_url and not uploaded_video_file:
            st.error("영상 URL을 입력하거나 내 PC 영상 파일을 업로드해주세요.")
        else:
            try:
                gc.collect()

                session_uid = uuid.uuid4().hex[:8]
                unique_working_video = os.path.join(BASE_CACHE_DIR, f"working_source_{session_uid}.mp4")

                video_title = "신규 숏폼 프로젝트"
                channel_name = ""

                if uploaded_video_file is not None:
                    with st.spinner("내 PC 영상 파일 로드 및 준비 중..."):
                        with open(unique_working_video, "wb") as f_out:
                            f_out.write(uploaded_video_file.getbuffer())
                        video_title = os.path.splitext(uploaded_video_file.name)[0]
                        channel_name = ""
                        st.session_state["stage_video_title"] = video_title
                        st.session_state["channel_source_name"] = ""
                        st.session_state["active_source_path"] = unique_working_video

                else:
                    with st.spinner("1/4 영상 다운로드 중 (안티봇 다중 분리 엔진 가동)..."):
                        clean_url = video_url.strip()
                        if is_youtube:
                            clean_url = clean_url.replace("youtube.com/shorts/", "youtube.com/watch?v=").replace("m.youtube.com/shorts/", "youtube.com/watch?v=")

                        success, v_title, ch_name, err_detail = download_media_final_v2(clean_url, unique_working_video)

                        if not success or not os.path.exists(unique_working_video) or os.path.getsize(unique_working_video) < 10000:
                            raise Exception(f"다운로드 실패: {err_detail}")

                        st.session_state["stage_video_title"] = v_title if v_title else "신규 숏폼 프로젝트"
                        st.session_state["channel_source_name"] = ch_name.strip() if ch_name else ""
                        st.session_state["active_source_path"] = unique_working_video

                with st.spinner("2/4 시청자 베스트 댓글 수집 및 데이터 처리 중..."):
                    real_comments = []
                    if video_url and is_youtube:
                        try:
                            v_id = extract_youtube_video_id(video_url)
                            real_comments = fetch_real_video_comments(DEFAULT_YOUTUBE_API_KEY, v_id, max_count=40)
                        except Exception:
                            real_comments = []
                    st.session_state["real_comments_pool"] = real_comments

                with st.spinner("3/4 Whisper 고정밀 음성 인식 중 (단어 단위 싱크)..."):
                    target_source_path = st.session_state["active_source_path"]
                    raw_segs, words, sub_chunks = transcribe_audio_with_word_timestamps(target_source_path)
                    st.session_state["raw_transcript_segments"] = raw_segs
                    st.session_state["subtitle_chunks"] = sub_chunks
                    transcript_full = "\n".join([f"[{s['start']:.1f}s ~ {s['end']:.1f}s] {s['text']}" for s in raw_segs])

                with st.spinner("4/4 알고리즘 지표(VVSA 1~3초/완독률 100%+/무한 루프) 분석 중..."):
                    temp_v = VideoFileClip(target_source_path)
                    duration = temp_v.duration
                    is_vert = temp_v.size[1] > temp_v.size[0]
                    st.session_state["source_video_duration"] = duration
                    st.session_state["is_source_vertical"] = is_vert

                    if is_vert:
                        detected_top, detected_bottom = auto_detect_video_boundary(temp_v, duration)
                    else:
                        detected_top, detected_bottom = 656, 1264

                    st.session_state["detected_v_top"] = detected_top
                    st.session_state["detected_v_bottom"] = detected_bottom
                    temp_v.close()
                    gc.collect()

                    clips, real_src = analyze_video_highlights(
                        gemini_api_key=gemini_api_key,
                        video_title=st.session_state.get("stage_video_title", video_title),
                        transcript_text=transcript_full,
                        duration=duration,
                        target_count=video_count,
                        real_comments=real_comments,
                        channel_name=st.session_state.get("channel_source_name", "")
                    )

                    st.session_state["staged_clips"] = clips
                    st.session_state["real_source"] = real_src
                    save_active_session_to_disk()
                    st.success("알고리즘 최적화 분석 완료! 아래 2단계에서 지표를 확인하세요.")
                    st.rerun()

            except Exception as e:
                st.error(f"오류 발생: {e}")

    # =========================================================================
    # 2단계: 정밀 검토 및 노잼 구간 수동 컷팅 & 라이브 프리뷰 & 실제 영상 재생 검수
    # =========================================================================
    if st.session_state.get("staged_clips"):
        st.markdown("---")
        st.markdown("### ✍️ 2단계: 알고리즘 지표 검수 & 노잼 컷팅 & 실시간 검수")
        
        v_dur = max(3.0, float(st.session_state.get("source_video_duration", 600.0)))
        is_vert_src = st.session_state.get("is_source_vertical", False)
        active_src_file = st.session_state.get("active_source_path", "input_video.mp4")
        all_whisper_chunks = st.session_state.get("subtitle_chunks", [])

        st.markdown("#### 📐 전체 화면 레이아웃 및 줌(Zoom) 설정")
        col_ctrl1, col_ctrl2, col_ctrl3 = st.columns(3)
        
        with col_ctrl1:
            if not is_vert_src:
                zoom_choice = st.select_slider(
                    "🔍 롱폼 화면 확대 줌(Zoom)",
                    options=[1.0, 1.15, 1.25, 1.35, 1.5],
                    value=1.0,
                    format_func=lambda x: f"{x}x ({'가로 중앙 원본 보존' if x==1.0 else '인물/중심 확대'})",
                    key="slider_zoom_choice"
                )
            else:
                zoom_choice = 1.0
                st.info("📱 세로 숏폼 영상: 1080x1920 풀화면 유지")

        with col_ctrl2:
            custom_v_top = st.slider("상단 배너 위치 (px)", min_value=250, max_value=750, value=st.session_state.get("detected_v_top", 656), step=10, key="slider_custom_v_top")
        with col_ctrl3:
            custom_v_bottom = st.slider("하단 댓글 위치 (px)", min_value=1150, max_value=1700, value=st.session_state.get("detected_v_bottom", 1264), step=10, key="slider_custom_v_bottom")

        staged = st.session_state["staged_clips"]
        pure_channel = st.session_state.get("channel_source_name", "")
        
        for idx, c in enumerate(staged):
            c_start = float(c.get("context_start", 0.0))
            c_end = float(c.get("context_end", min(v_dur, c_start + 20.0)))
            dur_len = round(c_end - c_start, 1)
            
            with st.expander(f"📌 쇼츠 #{idx+1}: {c.get('title')} [{format_time(c_start)} ~ {format_time(c_end)} ({dur_len}초)] 🔥 알고리즘 점수: {c.get('score')}점", expanded=True):
                loop_hint = c.get("loop_hook_hint", "마지막 대사가 첫 1초 질문으로 이어지는 무한 루프 구조")
                st.success(f"🎯 **알고리즘 공략 완료**: 1~3초 VVSA 이탈 방어 적용 | ⏱️ 완독률 목표 길이: **{dur_len}초** | 🔁 **무한 루프:** {loop_hint}")
                
                col_e1, col_e2 = st.columns([1.3, 1.0])
                
                with col_e1:
                    st.markdown("**재생 구간 및 노잼 컷팅 (0.1초 단위)**")
                    use_multi_cut = st.checkbox("중간 노잼 구간 건너뛰기 (2개 구간 이어붙이기)", value=False, key=f"multi_cut_chk_{idx}")
                    
                    if not use_multi_cut:
                        t_col1, t_col2 = st.columns(2)
                        with t_col1:
                            val_st = max(0.0, min(v_dur, float(c_start)))
                            new_c_start = st.number_input(
                                f"시작 시간 (초) #{idx+1}",
                                min_value=0.0,
                                max_value=float(v_dur),
                                value=val_st,
                                step=0.1,
                                key=f"st_num_{idx}"
                            )
                        with t_col2:
                            val_et = max(0.0, min(v_dur, float(c_end)))
                            if val_et <= new_c_start:
                                val_et = min(v_dur, new_c_start + 15.0)
                            new_c_end = st.number_input(
                                f"종료 시간 (초) #{idx+1}",
                                min_value=0.0,
                                max_value=float(v_dur),
                                value=val_et,
                                step=0.1,
                                key=f"et_num_{idx}"
                            )
                        
                        actual_end = max(new_c_start + 1.0, new_c_end)
                        c["context_start"] = new_c_start
                        c["context_end"] = actual_end
                        c["custom_segments"] = [{"source_start": new_c_start, "source_end": actual_end}]
                        st.caption(f"선택된 총 재생 길이: **{actual_end - new_c_start:.1f}초**")

                    else:
                        custom_segs = c.get("custom_segments", [])
                        if len(custom_segs) == 2:
                            def_s1 = float(custom_segs[0].get("source_start", c_start))
                            def_e1 = float(custom_segs[0].get("source_end", c_start + 8.0))
                            def_s2 = float(custom_segs[1].get("source_start", c_start + 12.0))
                            def_e2 = float(custom_segs[1].get("source_end", c_end))
                        else:
                            mid = c_start + (c_end - c_start) / 2
                            def_s1 = c_start
                            def_e1 = max(c_start + 1.0, mid - 2.0)
                            def_s2 = min(c_end - 1.0, mid + 2.0)
                            def_e2 = c_end

                        col_mc1, col_mc2 = st.columns(2)
                        with col_mc1:
                            st.markdown("1️⃣ 첫 번째 재미 구간")
                            s1 = st.number_input(f"구간1 시작 (초) #{idx+1}", min_value=0.0, max_value=float(v_dur), value=max(0.0, min(v_dur, float(def_s1))), step=0.1, key=f"s1_{idx}")
                            e1 = st.number_input(f"구간1 종료 (초) #{idx+1}", min_value=0.0, max_value=float(v_dur), value=max(0.0, min(v_dur, float(def_e1))), step=0.1, key=f"e1_{idx}")
                        with col_mc2:
                            st.markdown("2️⃣ 두 번째 재미 구간")
                            s2 = st.number_input(f"구간2 시작 (초) #{idx+1}", min_value=0.0, max_value=float(v_dur), value=max(0.0, min(v_dur, float(def_s2))), step=0.1, key=f"s2_{idx}")
                            e2 = st.number_input(f"구간2 종료 (초) #{idx+1}", min_value=0.0, max_value=float(v_dur), value=max(0.0, min(v_dur, float(def_e2))), step=0.1, key=f"e2_{idx}")

                        act_e1 = max(s1 + 0.5, e1)
                        act_s2 = max(act_e1, s2)
                        act_e2 = max(act_s2 + 0.5, e2)

                        c["custom_segments"] = [
                            {"source_start": s1, "source_end": act_e1},
                            {"source_start": act_s2, "source_end": act_e2}
                        ]
                        total_cut_len = (act_e1 - s1) + (act_e2 - act_s2)
                        st.success(f"노잼 구간 스킵 적용! 총 재생 길이: **{total_cut_len:.1f}초**")

                    st.write("")
                    st.markdown("**텍스트 & 3초 릴레이 댓글 수정**")
                    c["title"] = st.text_input(f"📌 상단 후킹 타이틀 (#{idx+1})", value=c.get("title", ""), key=f"t_{idx}")
                    c["source"] = st.text_input(f"🏷️ 출처 표기 (빈칸 시 완전 삭제) (#{idx+1})", value=c.get("source", pure_channel), key=f"s_{idx}")

                    if "custom_script" not in c:
                        matching_whisper_lines = []
                        for chk in all_whisper_chunks:
                            chk_st = float(chk.get("start", 0))
                            chk_et = float(chk.get("end", 0))
                            if max(chk_st, c_start) < min(chk_et, c_end):
                                txt_val = chk.get("text", "").strip()
                                if txt_val and txt_val not in matching_whisper_lines:
                                    matching_whisper_lines.append(txt_val)
                        
                        if matching_whisper_lines:
                            default_subs_val = "\n".join(matching_whisper_lines)
                        else:
                            key_subs_lines = [k.get("text", "") for k in c.get("key_subtitles", [])]
                            default_subs_val = "\n".join(key_subs_lines) if key_subs_lines else ""
                        c["custom_script"] = default_subs_val

                    c["custom_script"] = st.text_area(
                        f"💬 [영상 하단 가림막] 자막 검수/수정 (#{idx+1}) - 빈칸 시 자막 완전 미출력",
                        value=c.get("custom_script", ""),
                        height=75,
                        help="Whisper가 자동 인식한 대본입니다. 오타를 수정하거나, 지우면 영상에 자막이 전혀 나오지 않습니다.",
                        key=f"script_area_{idx}"
                    )

                    timeline_cmts = c.get("timeline_comments", [])
                    if timeline_cmts:
                        cmt_lines = "\n".join([item.get("text", "") for item in timeline_cmts if item.get("text")])
                    else:
                        cmt_lines = c.get("matched_comment", {}).get("text", "올해 이게 젤웃겼닼ㅋㅋㅋㅋㅋㅋ")

                    c["custom_comments_block"] = st.text_area(
                        f"💬 [하단 가림막] 3~4초 간격 실시간 교체 댓글 (#{idx+1}) - 줄바꿈으로 여러 개 작성",
                        value=c.get("custom_comments_block", cmt_lines),
                        height=100,
                        help="작성된 줄 수에 맞춰 영상 재생 동안 3~4초마다 댓글이 실시간으로 교체됩니다.",
                        key=f"cmt_block_{idx}"
                    )

                with col_e2:
                    st.markdown(f"**📱 [쇼츠 #{idx+1}] 실시간 검수 및 재생**")
                    
                    tab_pv_img, tab_pv_video = st.tabs(["🖼️ 레이아웃 스틸컷", "▶️ 설정 구간 영상 재생 (소리/싱크 검수)"])
                    
                    with tab_pv_img:
                        sample_t = float(c.get("context_start", c_start)) + 1.5
                        prev_path = os.path.join(BASE_CACHE_DIR, f"live_prev_{idx}.png")
                        
                        generate_layout_preview_image(
                            video_path=active_src_file,
                            is_vertical=is_vert_src,
                            v_top=custom_v_top,
                            v_bottom=custom_v_bottom,
                            zoom_factor=zoom_choice,
                            sample_time=sample_t,
                            title=c["title"],
                            comment_text=c.get("custom_comments_block", cmt_lines),
                            comment_likes="520",
                            sub_text=c["custom_script"],
                            source=c.get("source", ""),
                            is_white="화이트" in design_template,
                            out_path=prev_path
                        )
                        
                        if prev_path and os.path.exists(prev_path):
                            st.image(prev_path, caption="모바일 9:16 예상 화면", use_container_width=True)

                    with tab_pv_video:
                        st.caption("설정한 시작/종료 시간(및 스킵 컷팅) 구간만 잘라내어 소리와 함께 실제 재생합니다.")
                        if st.button(f"🎬 #{idx+1} 구간 영상 즉시 추출 및 재생", key=f"btn_quick_vid_{idx}", use_container_width=True):
                            with st.spinner("구간 영상 고속 추출 중 (1~2초)..."):
                                q_plan = c.get("custom_segments") if c.get("custom_segments") else [{"source_start": c_start, "source_end": c_end}]
                                q_out_path = os.path.join(BASE_CACHE_DIR, f"quick_preview_{idx}.mp4")
                                res_q = generate_quick_cut_preview(active_src_file, q_plan, q_out_path)
                                if res_q and os.path.exists(res_q):
                                    st.session_state[f"quick_vid_ready_{idx}"] = res_q
                        
                        cached_vid = st.session_state.get(f"quick_vid_ready_{idx}")
                        if cached_vid and os.path.exists(cached_vid):
                            st.video(cached_vid)

        save_active_session_to_disk()

        if st.button("🎬 3단계: 검토 완료! 설정된 옵션으로 최종 렌더링 시작", type="primary", use_container_width=True, key="btn_start_render_step3"):
            try:
                results = []
                progress_bar = st.progress(0)
                timestamp_id = datetime.now().strftime("%Y%m%d_%H%M%S")
                project_save_path = os.path.join(PROJECTS_DIR, timestamp_id)
                os.makedirs(project_save_path, exist_ok=True)
                st.session_state["current_project_id"] = timestamp_id

                for i, c_info in enumerate(staged):
                    with st.spinner(f"[{i+1}/{len(staged)}] 번째 쇼츠 인코딩 중 ({accel_choice})..."):
                        if c_info.get("custom_segments"):
                            timeline_plan = c_info["custom_segments"]
                        else:
                            timeline_plan = build_shorts_timeline_plan(c_info, v_dur)

                        clip_source = c_info.get("source", "").strip()
                        
                        out_file = render_final_shorts_video(
                            source_video_path=active_src_file,
                            segments_plan=timeline_plan,
                            subtitle_chunks=st.session_state.get("subtitle_chunks", []),
                            clip_info=c_info,
                            real_source=clip_source,
                            template_name=design_template,
                            accel_engine=accel_choice,
                            out_dir=project_save_path,
                            index=i+1,
                            is_vertical=is_vert_src,
                            v_top=custom_v_top,
                            v_bottom=custom_v_bottom,
                            zoom_factor=zoom_choice,
                            custom_sub_text=c_info.get("custom_script"),
                            custom_title=c_info.get("title"),
                            custom_comment_text=c_info.get("custom_comments_block")
                        )
                        
                        results.append({
                            "file": out_file,
                            "title": c_info.get("title", ""),
                            "start": c_info.get("context_start", 0.0),
                            "end": c_info.get("context_end", 30.0),
                            "source": clip_source,
                            "ai_note": c_info.get("ai_note", ""),
                            "script_text": c_info.get("custom_script", ""),
                            "comment_block": c_info.get("custom_comments_block", ""),
                            "template": design_template,
                            "v_top": custom_v_top,
                            "v_bottom": custom_v_bottom,
                            "zoom_factor": zoom_choice
                        })
                        progress_bar.progress((i + 1) / len(staged))

                st.session_state["generated_results"] = results
                save_project_to_disk(
                    project_id=timestamp_id,
                    title_text=st.session_state.get("stage_video_title", "신규 숏폼 프로젝트"),
                    results=results,
                    transcript_segments=st.session_state.get("raw_transcript_segments", []),
                    duration=v_dur,
                    is_vertical=is_vert_src
                )
                save_active_session_to_disk()
                st.success("모든 쇼츠 완성이 완료되었습니다!")
                st.rerun()

            except Exception as e:
                st.error(f"렌더링 중 오류 발생: {e}")

    # =========================================================================
    # 3단계: 결과 화면 및 제목/출처/구간/자막 완전 재렌더링
    # =========================================================================
    if st.session_state.get("generated_results"):
        st.markdown("---")
        res_list = st.session_state["generated_results"]
        active_src_file = st.session_state.get("active_source_path", "input_video.mp4")
        
        top_col1, top_col2 = st.columns([3, 1])
        with top_col1:
            st.markdown(f"### 📂 완성된 쇼츠 결과물 (총 {len(res_list)}개)")
        with top_col2:
            if len(res_list) > 1:
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w") as zf:
                    for item in res_list:
                        if os.path.exists(item["file"]):
                            zf.write(item["file"], os.path.basename(item["file"]))
                zip_buffer.seek(0)
                st.download_button(
                    label="모든 쇼츠 일괄 다운로드",
                    data=zip_buffer,
                    file_name="easycut_all_shorts.zip",
                    mime="application/zip",
                    type="primary",
                    use_container_width=True,
                    key="btn_zip_download_all"
                )

        for idx, item in enumerate(res_list):
            st.markdown(f"#### #{idx+1} {item['title']}")
            card_col1, card_col2 = st.columns([1, 2])
            
            with card_col1:
                if os.path.exists(item["file"]):
                    st.video(item["file"])
                    with open(item["file"], "rb") as f:
                        st.download_button(
                            label=f"쇼츠 #{idx+1} 다운로드",
                            data=f,
                            file_name=f"shorts_{idx+1}.mp4",
                            mime="video/mp4",
                            key=f"dl_btn_{idx}",
                            use_container_width=True
                        )

            with card_col2:
                dur_sec = int(item['end'] - item['start'])
                st.caption(f"영상 길이: **{dur_sec}초** ({item['start']:.1f}s ~ {item['end']:.1f}s)")
                st.info(f"**AI 하이라이트 요약:** {item.get('ai_note')}")
                
                with st.expander("✏️ 제목 / 출처 / 자막 / 재생 구간 수정 및 즉시 재렌더링", expanded=False):
                    max_dur = st.session_state.get("source_video_duration", 600.0)
                    
                    re_col_t1, re_col_t2 = st.columns([2, 1])
                    with re_col_t1:
                        re_title = st.text_input(f"📌 상단 타이틀 수정 (#{idx+1})", value=item.get("title", ""), key=f"re_title_{idx}")
                    with re_col_t2:
                        re_source = st.text_input(f"🏷️ 출처 수정 (빈칸 시 제거) (#{idx+1})", value=item.get("source", ""), key=f"re_src_{idx}")

                    adj_col1, adj_col2 = st.columns(2)
                    with adj_col1:
                        re_start = st.number_input(f"시작 시간 (초) - #{idx+1}", min_value=0.0, max_value=float(max_dur), value=max(0.0, min(float(max_dur), float(item["start"]))), step=0.1, key=f"re_st_{idx}")
                    with adj_col2:
                        re_end = st.number_input(f"종료 시간 (초) - #{idx+1}", min_value=0.0, max_value=float(max_dur), value=max(0.0, min(float(max_dur), float(item["end"]))), step=0.1, key=f"re_et_{idx}")
                    
                    re_sub = st.text_area(f"💬 자막 대본 수정 (#{idx+1}) - 빈칸 시 완전 미출력", value=item.get("script_text", ""), key=f"re_sub_{idx}")
                    re_cmts = st.text_area(f"💬 3초 릴레이 댓글 수정 (#{idx+1})", value=item.get("comment_block", ""), key=f"re_cmts_{idx}")
                    
                    if st.button(f"🔄 #{idx+1} 즉시 재렌더링 적용", key=f"btn_re_{idx}"):
                        with st.spinner(f"#{idx+1} 숏폼 새 설정으로 재렌더링 중..."):
                            cur_p_dir = os.path.dirname(item["file"]) if os.path.dirname(item["file"]) else "."
                            re_plan = [{"source_start": re_start, "source_end": max(re_start + 1.0, re_end)}]
                            
                            new_out = render_final_shorts_video(
                                source_video_path=active_src_file,
                                segments_plan=re_plan,
                                subtitle_chunks=st.session_state.get("subtitle_chunks", []),
                                clip_info=item,
                                real_source=re_source.strip(),
                                template_name=item.get("template", "댓글 캡처 (다크)"),
                                accel_engine=accel_choice,
                                out_dir=cur_p_dir,
                                index=idx+1,
                                is_vertical=st.session_state.get("is_source_vertical", False),
                                v_top=item.get("v_top", 656),
                                v_bottom=item.get("v_bottom", 1264),
                                zoom_factor=item.get("zoom_factor", 1.0),
                                custom_title=re_title.strip(),
                                custom_sub_text=re_sub,
                                custom_comment_text=re_cmts
                            )
                            st.session_state["generated_results"][idx]["file"] = new_out
                            st.session_state["generated_results"][idx]["title"] = re_title.strip()
                            st.session_state["generated_results"][idx]["source"] = re_source.strip()
                            st.session_state["generated_results"][idx]["start"] = re_start
                            st.session_state["generated_results"][idx]["end"] = re_end
                            st.session_state["generated_results"][idx]["script_text"] = re_sub
                            st.session_state["generated_results"][idx]["comment_block"] = re_cmts
                            
                            if st.session_state.get("current_project_id"):
                                save_project_to_disk(
                                    project_id=st.session_state["current_project_id"],
                                    title_text=re_title.strip(),
                                    results=st.session_state["generated_results"],
                                    transcript_segments=st.session_state.get("raw_transcript_segments", []),
                                    duration=max_dur,
                                    is_vertical=st.session_state.get("is_source_vertical", False)
                                )
                            save_active_session_to_disk()
                            st.success(f"#{idx+1} 재렌더링이 완료되었습니다!")
                            st.rerun()
            st.markdown("---")