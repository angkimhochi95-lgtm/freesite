# -*- coding: utf-8 -*-
# modules/ocr_detector.py
import cv2
import numpy as np

_EASYOCR_READER = None

def get_ocr_reader():
    global _EASYOCR_READER
    if _EASYOCR_READER is None:
        try:
            import easyocr
            # GPU 가속 자동 활성화 및 한국어/영어 로드
            _EASYOCR_READER = easyocr.Reader(['ko', 'en'], gpu=True, verbose=False)
        except Exception:
            _EASYOCR_READER = False
    return _EASYOCR_READER

def is_subtitle_overlapping(frame_crop):
    """
    화질 손실 없이 OCR 판별 연산만 초고속화 (그레이스케일 + 경량 리사이즈)
    """
    reader = get_ocr_reader()
    if not reader:
        return False

    try:
        # 1. 흑백 변환 및 가로 400px 다운스케일 (판별 정확도 유지 + 연산량 80% 감소)
        gray = cv2.cvtColor(frame_crop, cv2.COLOR_RGB2GRAY)
        h, w = gray.shape
        target_w = 400
        target_h = int(h * (target_w / w))
        resized = cv2.resize(gray, (target_w, target_h), interpolation=cv2.INTER_AREA)

        # 2. 텍스트 박스 검출
        results = reader.readtext(resized, detail=0, paragraph=True)
        detected_text = "".join(results).replace(" ", "").strip()
        
        # 2글자 이상의 의미 있는 텍스트가 있을 때만 겹침으로 판정
        return len(detected_text) >= 2
    except Exception:
        return False