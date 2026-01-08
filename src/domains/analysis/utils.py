import re
from datetime import datetime, timezone, timedelta

def clean_filename(title: str) -> str:
    """파일명으로 쓸 수 없는 특수문자를 제거합니다."""
    # 허용할 문자: 영문, 숫자, 한글, 공백, 하이픈(-), 언더바(_)
    # 그 외의 문자는 제거
    cleaned = re.sub(r'[^a-zA-Z0-9가-힣\s\-\_]', '', title)
    return cleaned.strip().replace(' ', '_')

def get_korean_time_str() -> str:
    """현재 한국 시간(KST)을 문자열로 반환합니다. (예: 2024-05-21_14-30)"""
    KST = timezone(timedelta(hours=9))
    now_kst = datetime.now(KST)
    return now_kst.strftime("%Y-%m-%d_%H-%M")


