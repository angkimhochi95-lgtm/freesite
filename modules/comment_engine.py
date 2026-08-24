# -*- coding: utf-8 -*-
# modules/comment_engine.py
import os
import re
import html
import random
from PIL import Image, ImageDraw, ImageFont

DEFAULT_MOCK_COMMENTS = [
    {"text": "올해 이게 젤웃겼닼ㅋㅋㅋㅋㅋㅋ", "likes": "316"},
    {"text": "아 ㅋㅋㅋㅋㅋ 진짜 빵터졌네 레전드다", "likes": "542"},
    {"text": "이건 볼 때마다 감탄만 나옴 ㅋㅋㅋ", "likes": "820"},
    {"text": "선배들 리액션이 진짜 찐이다 ㅋㅋㅋ", "likes": "1.2천"},
    {"text": "오늘 하루 피로가 싹 풀리네 ㅋㅋㅋ 대박", "likes": "394"},
    {"text": "논리가 완벽하네 ㅋㅋㅋ 몰입감 미쳤다", "likes": "912"},
    {"text": "알고리즘이 진짜 일 잘했다 ㅋㅋㅋ", "likes": "430"},
    {"text": "이 조합은 언제 봐도 치트키네 ㅋㅋㅋ", "likes": "675"},
    {"text": "표정 연기 미쳤나 봐 ㅋㅋㅋㅋㅋ", "likes": "281"},
    {"text": "진짜 숨도 안 쉬고 웃었넼ㅋㅋㅋ", "likes": "1.5천"}
]

def clean_comment_text(text: str) -> str:
    """HTML 특수문자 및 타임스탬프 제거"""
    if not text:
        return ""
    decoded = html.unescape(text)
    cleaned = re.sub(r'^\s*\[?\d{1,2}:\d{2}\]?\s*', '', decoded)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

def get_system_font(size: int, bold: bool = False):
    candidate_fonts = [
        "C:\\Windows\\Fonts\\malgunbd.ttf" if bold else "C:\\Windows\\Fonts\\malgun.ttf",
        "C:\\Windows\\Fonts\\NanumGothicBold.ttf" if bold else "C:\\Windows\\Fonts\\NanumGothic.ttf",
        "C:\\Windows\\Fonts\\gulim.ttc",
        "C:\\Windows\\Fonts\\arialbd.ttf" if bold else "C:\\Windows\\Fonts\\arial.ttf",
        "malgun.ttf",
        "arial.ttf"
    ]
    for font_path in candidate_fonts:
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size)
            except Exception:
                continue
    return ImageFont.load_default()

def wrap_comment_text(text: str, font: ImageFont.ImageFont, max_width: int, draw: ImageDraw.ImageDraw):
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
    return lines[:2]

def render_crisp_comment_card(
    author: str = "익명",
    text: str = "",
    likes: str = "316",
    is_white: bool = False,
    out_path: str = "comment_card.png"
):
    """
    슬림 & 미니멀 모바일 댓글 카드 (작고 세련된 폰트 크기 적용)
    """
    clean_txt = clean_comment_text(text)
    if not clean_txt:
        mock = random.choice(DEFAULT_MOCK_COMMENTS)
        clean_txt = mock["text"]
        likes = mock["likes"]

    # 카드 높이를 150px로 슬림하게 축소
    card_w, card_h = 1080, 150
    img = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    main_text_color = (20, 20, 20, 255) if is_white else (245, 245, 245, 255)
    meta_color = (110, 110, 115, 255) if is_white else (160, 160, 165, 255)
    heart_color = (255, 55, 65, 255)

    # 1. 댓글 본문 (26pt 크기로 부담 없이 슬림하게 정렬)
    start_x = 70
    font_main = get_system_font(26, bold=True)
    lines = wrap_comment_text(clean_txt, font_main, 940, draw)

    start_y = 10
    for ln in lines:
        draw.text((start_x, start_y), ln, fill=main_text_color, font=font_main)
        start_y += 36

    # 2. 하단 메타 바 (빨간 하트 ♥ + 좋아요 + 답글)
    font_meta = get_system_font(20, bold=False)
    font_bold_meta = get_system_font(20, bold=True)
    meta_y = max(start_y + 8, 56)

    draw.text((start_x, meta_y - 2), "♥", fill=heart_color, font=font_meta)
    draw.text((start_x + 28, meta_y), str(likes), fill=meta_color, font=font_bold_meta)
    likes_w = draw.textbbox((0, 0), str(likes), font=font_bold_meta)[2]

    reply_x = start_x + 28 + likes_w + 28
    draw.text((reply_x, meta_y), "답글", fill=meta_color, font=font_meta)

    img.save(out_path)
    return out_path