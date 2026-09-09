# -*- coding: utf-8 -*-
"""PostalScanner 2.2.0 업무 판독 규칙.

OCR/AI 엔진과 분리해 유지해야 하는 업무 규칙만 둔다.
개인정보/실제 주소/실제 이름을 파일로 저장하지 않는다.
"""

import re

GENERAL_ALLOWED_LATIN = {"K", "T"}

GENERAL_DETAIL_KEYWORDS = (
    "층", "호", "빌딩", "타워", "아파트", "공단", "공사", "센터",
    "대학교", "학교", "병원", "청사", "본관", "별관", "회관",
    "읍", "면", "동", "리", "로", "길", "KT",
)

GENERAL_MAIL_PROMPT = r"""
일반 우편물 사진에서 '받는 사람'의 주소와 이름만 읽어라.

[반드시 지킬 업무 규칙]
1. 발신인/보내는 사람/회신주소/우편번호/바코드/등기번호/요금후납/로고/광고문구는 결과에서 제외한다.
2. 도/광역시가 생략되어도 '포항시 남구 오천읍 ...'처럼 시·군·구·읍·면·동·로·길 구조가 분명하면 수신주소로 인정한다.
3. 주소가 여러 줄이면 읽는 순서대로 한 줄로 합친다. 건물명, 아파트, 빌딩, 타워, 공단, 공사, 센터, 학교, 병원, 청사, 본관, 별관, 회관, 층, 호, 동 등이 수신주소의 일부면 포함한다.
4. 수취인 표시에 '담당자'가 포함된 경우에도 수신인 후보로 본다.
5. 이름 뒤의 '귀하', '님', '선생님'은 제거한다.
6. 영문자는 업무 규칙상 K와 T만 허용한다. 그 외 A-Z/a-z 영문자는 주소/이름 결과에서 제외한다. 'KT'는 유지한다.
7. 보이지 않는 내용은 추측하지 않는다. 불확실한 값은 빈 문자열로 반환한다.
8. 주소와 이름 각각의 confidence는 0~1 숫자로 반환한다.
9. 설명 없이 지정된 JSON 형식으로만 반환한다.
""".strip()

LEDGER_PROMPT = r"""
고정 양식 '인감대장송부'에서 가장 아래쪽에 실제로 작성된 한 행만 읽어라.

[반드시 지킬 업무 규칙]
1. 가로선/세로선/행번호를 근거로 작성행을 결정하지 않는다. 실제 손글씨가 있는 가장 아래 작성 묶음을 기준으로 한다.
2. 수신기관명 칸의 손글씨를 같은 높이의 인쇄된 '시/구/도/군/장' 위치와 결합해 완성 주소로 복원한다.
3. 인쇄된 접미사와 손글씨 끝 글자가 충돌하면 가까운 인쇄 접미사를 우선한다. 예: 손글씨가 '포항구'처럼 읽혀도 가까운 인쇄 글자가 '시'면 '포항시'로 정리한다.
4. 예: 경북+도=경상북도, 포항+시=포항시, 남+구=남구, 대이동+장=대이동장.
5. 도 약칭은 공식 명칭으로 정규화한다.
6. 등기번호 열에 적힌 손글씨 한글 이름은 이 업무의 수신인 이름이다. 이름은 보통 한글 2~8자이며 '귀하'를 붙이지 않는다.
7. 인쇄된 단일 '시/구/도/군/장' 자체는 결과값으로 출력하지 않는다.
8. '번호', '우편번호', '수신기관명', '등기번호', '우표첨부란', '인감대장송부', '인감증명법 시행령 별지 서식', '특수우편물배달증 첨부란', '내가 아낀 종이 한 장 늘어나는 나라살림' 등 양식 인쇄문구는 결과에서 제외한다.
9. 주소에는 같은 행정단위를 중복해서 넣지 않는다. '시시', '구구', '군군', '구시군' 같은 깨진 조합을 만들지 않는다.
10. 읍/면/동 뒤의 '장'은 하나만 붙인다. 손글씨 OCR이 '육장/욕장/읖장/읏장'처럼 보이면 문맥상 읍장일 때만 '읍장'으로 정리한다.
11. 보이지 않는 내용은 추측하지 않는다. 불확실한 값은 빈 문자열로 반환한다.
12. 설명 없이 지정된 JSON 형식으로만 반환한다.
""".strip()


def filter_general_english(text):
    """일반우편 결과의 영문은 K/T만 보존한다."""
    out = []
    for ch in str(text or ""):
        if ("A" <= ch <= "Z") or ("a" <= ch <= "z"):
            upper = ch.upper()
            if upper in GENERAL_ALLOWED_LATIN:
                out.append(upper)
            continue
        out.append(ch)
    value = "".join(out)
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"\(\s+", "(", value)
    value = re.sub(r"\s+\)", ")", value)
    value = re.sub(r"(\d+)\s+([층호])", r"\1\2", value)
    return value


def normalize_general_result(address, name):
    address = filter_general_english(address)
    name = filter_general_english(name)
    name = re.sub(r"\s*(귀하|님|선생님)\s*$", "", name).strip()
    return address, name


def general_address_has_structure(address):
    """도/광역시가 생략된 주소도 허용하는 최종 구조 검사."""
    value = str(address or "").strip()
    if not value:
        return False
    if re.search(r"[가-힣]{2,12}(?:특별시|광역시|특별자치시|특별자치도|도)", value):
        return True
    admin_hits = re.findall(r"[가-힣]{1,12}(?:시|군|구|읍|면|동|리|로|길)", value)
    if len(admin_hits) >= 2:
        return True
    if re.search(r"[가-힣]{1,12}(?:로|길|동|읍|면|리)\s*\d+", value):
        return True
    if re.search(r"[가-힣]{2,10}시\s+[가-힣]{1,10}(?:구|군)", value):
        return True
    return False


def general_name_is_plausible(name):
    value = str(name or "").strip()
    if not value:
        return False
    return bool(re.fullmatch(r"[가-힣]{2,10}", value))


def ledger_name_is_plausible(name):
    value = str(name or "").strip()
    return bool(re.fullmatch(r"[가-힣]{2,8}", value))


def general_result_needs_retry(result):
    address = str(result.get("address", "") or "").strip()
    name = str(result.get("name", "") or "").strip()
    try:
        ac = float(result.get("address_confidence", 0.0) or 0.0)
        nc = float(result.get("name_confidence", 0.0) or 0.0)
    except Exception:
        return True
    if not address or not name:
        return True
    if len(address) < 7 or not general_address_has_structure(address):
        return True
    if not general_name_is_plausible(name):
        return True
    return ac < 0.78 or nc < 0.78


def ledger_result_needs_retry(result):
    address = str(result.get("institution", "") or "").strip()
    name = str(result.get("name", "") or "").strip()
    try:
        conf = float(result.get("institution_confidence", 0.0) or 0.0)
    except Exception:
        return True
    if not address or not name:
        return True
    if len(address) < 5 or not re.search(r"(도|시|군|구|읍|면|동|장)", address):
        return True
    if re.search(r"(시시|구구|군군|구시군)", address):
        return True
    if not ledger_name_is_plausible(name):
        return True
    return conf < 0.80


# 2026-09 공식 OpenAI 모델 페이지 기준. 화면에는 '추정 비용'으로만 표시한다.
# 단위: USD / 1,000,000 tokens
_MODEL_PRICE_USD_PER_MTOK = {
    "gpt-5.6-luna": (0.20, 1.20),
    "gpt-5.6-terra": (2.00, 12.00),
    "gpt-5.6-sol": (4.00, 20.00),
    "gpt-5.6": (4.00, 20.00),
}


def estimate_openai_cost_usd(model, input_tokens, output_tokens):
    price = _MODEL_PRICE_USD_PER_MTOK.get(str(model or "").strip())
    if not price:
        return 0.0
    in_price, out_price = price
    return (
        max(0, int(input_tokens or 0)) * in_price
        + max(0, int(output_tokens or 0)) * out_price
    ) / 1_000_000.0


def normalize_ledger_address(text):
    """인감대장 주소의 확정적인 형태 오류만 보정한다."""
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    value = re.sub(r"([가-힣]{1,10})(?:육|욕|읖|읏)장\b", r"\1읍장", value)
    value = re.sub(r"(시)\s*\1+", r"\1", value)
    value = re.sub(r"(구)\s*\1+", r"\1", value)
    value = re.sub(r"(군)\s*\1+", r"\1", value)
    value = re.sub(r"(읍장|면장|동장)\s*\1+", r"\1", value)
    tokens = value.split()
    final = []
    for token in tokens:
        if token not in final:
            final.append(token)
    return " ".join(final)
