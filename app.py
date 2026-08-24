# -*- coding: utf-8 -*-
# app.py
import os
import shutil
import importlib
import streamlit as st
import config

# 모듈 핫 리로드
import modules.session_manager
import modules.downloader
import modules.transcription
import modules.highlight_analyzer
import modules.structure_engine
import modules.comment_engine
import modules.renderer
import modules.youtube_service
import views.view_trending
import views.view_studio

importlib.reload(modules.session_manager)
importlib.reload(modules.downloader)
importlib.reload(modules.transcription)
importlib.reload(modules.highlight_analyzer)
importlib.reload(modules.structure_engine)
importlib.reload(modules.comment_engine)
importlib.reload(modules.renderer)
importlib.reload(modules.youtube_service)
importlib.reload(views.view_trending)
importlib.reload(views.view_studio)

from modules.session_manager import (
    init_session_states,
    save_active_session_to_disk,
    load_all_saved_projects,
    PROJECTS_DIR
)
from views.view_trending import render_trending_view
from views.view_studio import render_studio_view

# Streamlit 페이지 기본 설정
st.set_page_config(
    page_title="이지컷(EasyCut) AI 올인원 숏폼 스튜디오 Pro",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 세션 초기화
init_session_states()

BASE_CACHE_DIR = getattr(config, "BASE_CACHE_DIR", ".")
COOKIE_FILE_PATH = os.path.join(BASE_CACHE_DIR, "cookies.txt")

# 사이드바 내비게이션 & 프로젝트 보관함
st.sidebar.title("🎛️ 워크스페이스 내비게이션")
nav_options = ["🎬 AI 숏폼 제작 스튜디오", "🔥 실시간 인기 & 맞춤 탐색기"]

current_nav = st.session_state.get("nav_selection", nav_options[0])
if current_nav not in nav_options:
    current_nav = nav_options[0]

menu_choice = st.sidebar.radio("메뉴 이동:", nav_options, index=nav_options.index(current_nav))
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

# 메인 뷰 라우팅
if st.session_state["nav_selection"] == "🔥 실시간 인기 & 맞춤 탐색기":
    render_trending_view()
else:
    render_studio_view(BASE_CACHE_DIR, COOKIE_FILE_PATH)