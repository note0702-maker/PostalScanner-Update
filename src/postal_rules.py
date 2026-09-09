# -*- coding: utf-8 -*-
"""PostalScanner 업무 판독 규칙.

OCR/AI 엔진과 분리해서 보존하는 규칙만 둔다.
개인정보/실제 주소 데이터는 저장하지 않는다.
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

LEDGER_PRINTED_TOKENS = {"시", "구", "도", "군", "장"}

LEDGER_IGNORE_TEXTS = {
    "번호",
    "우편번호",
    "수신기관명",
    "등기번호",
    "우표첨부란",
    "인감대장송부",
    "인감증명법시행령별지제호서식",
    "특수우편물배달증첨부란",
    "내가아낀종이한장늘어나는나라살림",
}

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
    """사용자 요구: 일반우편 결과의 영문은 K/T만 보존."""
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
    """도/광역시가 생략된 주소도 허용하는 공통 최종 검증."""
    value = str(address or "").strip()
    if not value:
        return False
    admin_hits = re.findall(r"[가-힣]{1,12}(?:시|군|구|읍|면|동|리|로|길)", value)
    if len(admin_hits) >= 2:
        return True
    if re.search(r"[가-힣]{1,12}(?:로|길|동|읍|면|리)\s*\d+", value):
        return True
    if re.search(r"[가-힣]{2,10}시\s+[가-힣]{1,10}(?:구|군)", value):
        return True
    return False


def ledger_name_is_plausible(name):
    value = str(name or "").strip()
    return bool(re.fullmatch(r"[가-힣]{2,8}", value))
