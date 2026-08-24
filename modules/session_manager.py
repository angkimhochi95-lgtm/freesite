# -*- coding: utf-8 -*-
# modules/session_manager.py
import os
import json
import gc
from datetime import datetime
import streamlit as st

PROJECTS_DIR = "saved_projects"
ACTIVE_SESSION_FILE = "active_session_cache.json"
os.makedirs(PROJECTS_DIR, exist_ok=True)

def init_session_states():
    """앱 시작 시 필요한 세션 상태 변수들을 안전하게 초기화합니다."""
    default_states = {
        "generated_results": [],
        "raw_transcript_segments": [],
        "subtitle_chunks": [],
        "real_comments_pool": [],
        "source_video_duration": 0.0,
        "is_source_vertical": False,
        "detected_v_top": 656,
        "detected_v_bottom": 1264,
        "current_project_id": None,
        "staged_clips": None,
        "all_candidates_pool": [],
        "stage_video_title": "",
        "channel_source_name": "",
        "active_source_path": "",
        "nav_selection": "🎬 AI 숏폼 제작 스튜디오",
        "gemini_key_input": "",
        "video_url_input": ""
    }
    for k, v in default_states.items():
        if k not in st.session_state:
            st.session_state[k] = v

    if "session_initialized" not in st.session_state:
        st.session_state["session_initialized"] = True
        load_active_session_from_disk()

def save_active_session_to_disk():
    """현재 작업 상태를 디스크에 실시간 백업합니다."""
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
        "all_candidates_pool": st.session_state.get("all_candidates_pool", []),
        "generated_results": st.session_state.get("generated_results", []),
        "current_project_id": st.session_state.get("current_project_id", None)
    }
    try:
        with open(ACTIVE_SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(state_to_save, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def load_active_session_from_disk():
    """비정상 종료나 새로고침 시 이전 작업 상태를 복원합니다."""
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
    """새 작업 시작 시 세션 상태와 캐시를 초기화합니다."""
    if os.path.exists(ACTIVE_SESSION_FILE):
        try:
            os.remove(ACTIVE_SESSION_FILE)
        except Exception:
            pass
    st.session_state["staged_clips"] = None
    st.session_state["all_candidates_pool"] = []
    st.session_state["generated_results"] = []
    st.session_state["raw_transcript_segments"] = []
    st.session_state["subtitle_chunks"] = []
    st.session_state["real_comments_pool"] = []
    st.session_state["source_video_duration"] = 0.0
    st.session_state["channel_source_name"] = ""
    st.session_state["current_project_id"] = None
    st.session_state["active_source_path"] = ""
    gc.collect()

def save_project_to_disk(project_id, title_text, results, transcript_segments, duration, is_vertical=False):
    """완성된 프로젝트 메타데이터를 저장합니다."""
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
    """저장된 지난 프로젝트 목록을 반환합니다."""
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

def update_or_append_result(new_res_item):
    """결과 목록에 쇼츠를 슬롯 ID 기준으로 갱신하거나 누적 추가합니다."""
    current_results = st.session_state.get("generated_results", [])
    updated = False
    for idx, r in enumerate(current_results):
        if r.get("slot_id") == new_res_item.get("slot_id"):
            current_results[idx] = new_res_item
            updated = True
            break
    if not updated:
        current_results.append(new_res_item)
    st.session_state["generated_results"] = current_results