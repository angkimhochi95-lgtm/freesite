# -*- coding: utf-8 -*-
# modules/highlight_analyzer.py
import json
import re
import os
import google.generativeai as genai

def clean_and_parse_json(raw_text):
    """AI 응답 텍스트에서 마크다운 및 제어문자를 정제하고 무결점 JSON으로 파싱합니다."""
    text = raw_text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)

    try:
        return json.loads(text)
    except Exception:
        match = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', text)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
    return None


def generate_fallback_plan(video_title, channel_name, duration, target_count):
    """AI 통신 지연 시 작동하는 고품질 폴백 엔진 (숫자 나열 방지)"""
    clips = []
    candidates = []
    
    # 동적 훅 타이틀 템플릿 풀
    hook_templates = [
        "결국 참다못해 제대로 폭발해버린 순간 ㅋㅋㅋ",
        "갑자기 돌발상황 발생해서 난리 난 현장 분위기",
        "아무도 예상 못 한 충격적인 전개 ㄷㄷ",
        "보자마자 빵 터진 역대급 명장면",
        "이 한마디로 촬영장 초토화된 이유",
        "진짜 봐도 봐도 레전드인 명대사"
    ]
    
    clean_base_title = re.sub(r'\[.*?\]|\(.*?\)|#\S+', '', video_title).strip()
    if not clean_base_title:
        clean_base_title = "화제의 그 장면"

    step = duration / (target_count + 1)
    for i in range(target_count):
        base_s = round(i * step + 5.0, 1)
        s1 = base_s
        e1 = round(min(duration, s1 + 10.0), 1)
        s2 = round(min(duration, e1 + 5.0), 1)
        e2 = round(min(duration, s2 + 18.0), 1)
        s3 = round(min(duration, e2 + 4.0), 1)
        e3 = round(min(duration, s3 + 8.0), 1)

        custom_segs = [
            {"source_start": s1, "source_end": e1},
            {"source_start": s2, "source_end": e2}
        ]
        if e3 > s3 and (e3 - s1) < 58.0:
            custom_segs.append({"source_start": s3, "source_end": e3})

        chosen_title = hook_templates[i % len(hook_templates)]

        clip_obj = {
            "id": i + 1,
            "title": f"{chosen_title}",
            "source": channel_name,
            "score": 92 - (i * 2),
            "loop_hook_hint": "마지막 리액션이 첫 1초 질문으로 자연스럽게 연결되는 무한 루프 구조",
            "ai_note": "루즈한 설명 구간을 건너뛰고 핵심 리액션 2~3구간을 직결한 점프컷",
            "context_start": s1,
            "context_end": custom_segs[-1]["source_end"],
            "custom_segments": custom_segs,
            "custom_comments_block": "이 부분 편집 진짜 미쳤넼ㅋㅋㅋㅋ\n알고리즘 타고 성지순례 왔습니다\n이게 여기서 이렇게 이어지네 ㄷㄷ"
        }
        clips.append(clip_obj)

    total_cand_count = max(6, target_count * 2)
    cand_step = duration / (total_cand_count + 1)
    for j in range(total_cand_count):
        c_s = round(j * cand_step + 3.0, 1)
        c_e1 = round(min(duration, c_s + 12.0), 1)
        c_s2 = round(min(duration, c_e1 + 6.0), 1)
        c_e2 = round(min(duration, c_s2 + 20.0), 1)
        
        m_start = int(c_s // 60)
        s_start = int(c_s % 60)
        m_end = int(c_e2 // 60)
        s_end = int(c_e2 % 60)

        cand_title = hook_templates[j % len(hook_templates)]

        candidates.append({
            "candidate_id": j + 1,
            "time_range": f"{m_start:02d}:{s_start:02d} ~ {m_end:02d}:{s_end:02d}",
            "summary": f"주요 대화 및 사건 발생 구간 ({clean_base_title[:12]})",
            "title": cand_title,
            "score": 90 - j,
            "segments": [
                {"source_start": c_s, "source_end": c_e1},
                {"source_start": c_s2, "source_end": c_e2}
            ]
        })

    return clips, candidates


def analyze_video_highlights(gemini_api_key, video_title, transcript_text, duration, target_count=3, real_comments=None, channel_name=""):
    """
    영상 대본의 실제 맥락/사건을 반영하여 강력한 후킹 제목과 2~3구간 점프컷을 추출합니다.
    """
    if not gemini_api_key:
        return generate_fallback_plan(video_title, channel_name, duration, target_count)

    try:
        genai.configure(api_key=gemini_api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
    except Exception:
        return generate_fallback_plan(video_title, channel_name, duration, target_count)

    comments_context = ""
    if real_comments and len(real_comments) > 0:
        comments_sample = "\n".join([f"- {c.get('text', '')}" for c in real_comments[:30] if c.get('text')])
        comments_context = f"\n[시청자 실제 반응 및 인기 댓글]\n{comments_sample}\n"

    transcript_sample = transcript_text[:35000] if len(transcript_text) > 35000 else transcript_text

    prompt = f"""
    당신은 대한민국 1위 숏폼 바이럴 전문 디렉터입니다.
    영상 대본(타임스탬프 포함)을 정밀 분석하여, 단일 구간만 뽑지 말고 **지루한 공백/잡담을 건너뛴 2~3개 알짜 점프컷 쇼츠**를 기획하세요.

    [영상 정보]
    - 원본 제목: {video_title}
    - 전체 영상 길이: {duration:.1f}초
    - 채널명: {channel_name}
    {comments_context}

    [대본 타임라인 데이터]
    {transcript_sample}

    ================================================================================
    [🔥 쇼츠 제목(Title) 작명 절대 수칙 - 위반 시 무효]
    ================================================================================
    1. **절대 금지 표현**:
       - '#1', '#2', '1탄', '2탄', '3탄', '파트1', 'Part 1', '하이라이트', '모음집', '핵심요약' 등의 무의미한 숫자 및 형식적 단어는 **절대 작성하지 마세요.**
       - 원본 영상 제목을 단순히 복사하여 뒤에 숫자만 붙이는 행위는 엄격히 금지합니다.
    2. **필수 작명 공식**:
       - 반드시 해당 쇼츠 구간에서 **실제로 일어난 구체적인 사건, 충격적인 발언, 인물의 감정 변화, 반전 리액션**을 담아 15자~25자 사이로 작성하세요.
       - 시청자가 피드를 넘기다 멈출 수밖에 없는 **클릭 유도형 어그로/호기심 자극 문장**이어야 합니다.
       - [작명 예시]:
         * "선 넘는 질문에 멘붕 온 실제 반응 ㅋㅋㅋ"
         * "통장 잔고 보고 촬영장 뒤집어진 이유 ㄷㄷ"
         * "결국 참다못해 방송 중에 욕설 튀어나옴"
         * "이 한마디로 분위기 순식간에 싸해짐"
         * "아무도 예상 못 한 결말에 다들 기겁함"

    ================================================================================
    [✂️ 2~3구간 스마트 점프컷 규칙]
    ================================================================================
    - 1구간(도입부): 시청자 이탈 방어용 핵심 사건/도입 발언 (8~14초)
    - 2구간(전개/리액션): 1구간과 맥락이 이어지는 사건의 절정 및 반응 (10~18초)
    - 3구간(결말/반전 - 선택): 펀치라인 및 마무리 (8~15초)
    - 각 구간 사이의 늘어지는 잡담/오디오 공백은 건너뛰고, 이어붙인 총 재생 시간은 **35초 ~ 55초**로 맞추세요.
    - custom_comments_block에는 영상 내용과 직결되는 시청자 반응 댓글을 3줄 이상 작성하세요.

    ================================================================================
    [반드시 순수 JSON 포맷으로만 출력]:
    ================================================================================
    {{
      "all_candidates": [
        {{
          "candidate_id": 1,
          "time_range": "01:20 ~ 02:15",
          "summary": "핵심 갈등 발생 및 출연진 멘붕 순간",
          "title": "선 넘는 질문에 멘붕 온 실제 반응 ㅋㅋㅋ",
          "score": 96,
          "segments": [
            {{"source_start": 80.0, "source_end": 92.0, "desc": "도입 사건 발단"}},
            {{"source_start": 104.0, "source_end": 125.0, "desc": "핵심 반전 및 리액션"}}
          ]
        }}
      ],
      "selected_shorts": [
        {{
          "id": 1,
          "title": "통장 잔고 보고 촬영장 뒤집어진 이유 ㄷㄷ",
          "source": "{channel_name}",
          "score": 98,
          "loop_hook_hint": "마지막 리액션이 첫 질문으로 이어지는 무한 루프",
          "ai_note": "지루한 설명 구간 15초를 스킵하고 핵심 순간 2구간을 직결",
          "context_start": 80.0,
          "context_end": 125.0,
          "custom_segments": [
            {{"source_start": 80.0, "source_end": 92.0}},
            {{"source_start": 104.0, "source_end": 125.0}}
          ],
          "custom_comments_block": "와 여기서 이게 이렇게 터지넼ㅋㅋㅋㅋ\\n진짜 레전드 찍었다\\n알고리즘 타고 성지순례 옴"
        }}
      ]
    }}
    """

    try:
        response = model.generate_content(prompt)
        parsed = clean_and_parse_json(response.text)

        if not parsed or not isinstance(parsed, dict):
            return generate_fallback_plan(video_title, channel_name, duration, target_count)

        selected_shorts = parsed.get("selected_shorts", [])
        all_candidates = parsed.get("all_candidates", [])

        if not selected_shorts:
            return generate_fallback_plan(video_title, channel_name, duration, target_count)

        final_clips = selected_shorts[:target_count]

        # 세그먼트 데이터 및 타이틀 검증/보정
        for c in final_clips:
            # 타이틀에서 '#1', '#2', '1탄' 등 잔여 숫자 패턴 필터링
            raw_t = c.get("title", "")
            raw_t = re.sub(r'#\d+|\b\d+탄\b|\b파트\s*\d+\b|\bPart\s*\d+\b', '', raw_t).strip()
            c["title"] = raw_t if raw_t else "화제의 그 명장면 ㅋㅋㅋ"

            segs = c.get("custom_segments", [])
            if not segs or len(segs) == 0:
                c_s = float(c.get("context_start", 0.0))
                c_e = float(c.get("context_end", min(duration, c_s + 40.0)))
                mid = c_s + (c_e - c_s) / 2
                c["custom_segments"] = [
                    {"source_start": round(c_s, 1), "source_end": round(max(c_s + 1.0, mid - 2.0), 1)},
                    {"source_start": round(min(c_e - 1.0, mid + 2.0), 1), "source_end": round(c_e, 1)}
                ]
            else:
                for s in segs:
                    s["source_start"] = round(max(0.0, float(s.get("source_start", 0.0))), 1)
                    s["source_end"] = round(min(duration, float(s.get("source_end", duration))), 1)

            c["context_start"] = float(c["custom_segments"][0]["source_start"])
            c["context_end"] = float(c["custom_segments"][-1]["source_end"])

        for cand in all_candidates:
            raw_ct = cand.get("title", "")
            raw_ct = re.sub(r'#\d+|\b\d+탄\b|\b파트\s*\d+\b|\bPart\s*\d+\b', '', raw_ct).strip()
            cand["title"] = raw_ct if raw_ct else "놓치면 아쉬운 핵심 장면"

        if not all_candidates:
            _, all_candidates = generate_fallback_plan(video_title, channel_name, duration, target_count)

        return final_clips, all_candidates

    except Exception:
        return generate_fallback_plan(video_title, channel_name, duration, target_count)