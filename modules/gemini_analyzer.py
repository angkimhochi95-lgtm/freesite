import json
import google.generativeai as genai
import config

def analyze_highlights(transcript_text, duration):
    """
    영상 대본을 분석하여 지루한 구간을 건너뛰고
    맥락이 자연스럽게 이어지는 2~3개의 핵심 구간(점프컷)을 추출합니다.
    """
    # config.py 또는 환경변수의 API 키 사용
    api_key = getattr(config, 'GEMINI_API_KEY', '')
    if not api_key:
        import os
        api_key = os.getenv('GEMINI_API_KEY', '')

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')

    prompt = f"""
    당신은 숏폼 전문 편집자입니다.
    아래 영상 대본(타임스탬프 포함)을 분석하여 지루한 구간/오디오 공백을 제거하고,
    가장 재미있는 첫 번째 핵심 장면과 맥락이 자연스럽게 이어지는 2~3개의 구간(스마트 점프컷)을 선택하세요.

    [규칙]
    1. 첫 번째 구간은 시청자의 흥미를 끄는 핵심 사건이어야 합니다.
    2. 2~3번째 구간은 1번째 구간과 맥락/대화가 자연스럽게 이어지며 지루한 부분은 건너뛰어야 합니다.
    3. 선택할 구간의 개수는 최소 2개 ~ 최대 3개입니다.
    4. 모든 구간 길이의 합은 35초 ~ 55초 사이여야 합니다.

    [대본 데이터]
    {transcript_text}

    [출력 포맷 (반드시 순수 JSON만 반환)]:
    {{
      "title": "쇼츠 제목 추천",
      "segments": [
        {{"start": 10.0, "end": 22.0, "description": "1구간: 사건 발단"}},
        {{"start": 35.0, "end": 48.0, "description": "2구간: 핵심 장면"}},
        {{"start": 60.0, "end": 72.0, "description": "3구간: 결말 및 리액션"}}
      ]
    }}
    """

    try:
        response = model.generate_content(prompt)
        raw_text = response.text.strip()
        if "```json" in raw_text:
            raw_text = raw_text.split("```json")[1].split("```")[0].strip()
        elif "```" in raw_text:
            raw_text = raw_text.split("```")[1].split("```")[0].strip()
        return json.loads(raw_text)
    except Exception as e:
        # 오류 시 기본 40초 단일 구간 Fallback
        return {
            "title": "자동 추출 쇼츠",
            "segments": [
                {"start": 0.0, "end": min(float(duration), 40.0), "description": "기본 구간"}
            ]
        }