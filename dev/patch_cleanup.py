from pathlib import Path
p=Path('src/PostalScanner.py')
s=p.read_text(encoding='utf-8')

start=s.find('# ============================================================\n# Paddle 모델\n# ============================================================\n')
if start!=-1:
    end=s.find('# ============================================================\n# 개인정보 감사 로그', start)
    s=s[:start]+s[end:]

start=s.index('def friendly_error_message(error):')
end=s.index('\n\ndef _privacy_safe_audit_detail', start)
new = '''def friendly_error_message(error):
    """영문 라이브러리 원문 대신 개인정보 없는 사용자용 메시지만 반환한다."""
    raw = str(error or "").strip()
    lower = raw.lower()

    if raw.startswith((
        "마지막 입력",
        "취소할 마지막 입력",
        "Excel 저장 후 입력값 검증",
        "마지막 입력 취소 후 Excel 검증",
    )):
        return raw

    if "촬영 품질 확인:" in raw:
        return raw.replace("촬영 품질 확인:", "촬영 품질을 다시 확인해주세요.\\n", 1).strip()

    if "openai" in lower or "api" in lower:
        if "401" in raw or "invalid_api_key" in lower or "incorrect api key" in lower:
            return "OpenAI API Key 인증에 실패했습니다.\\n[API Key 설정]에서 Key를 다시 저장해주세요."
        if "429" in raw:
            return "OpenAI API 사용량/결제 한도를 확인해주세요."
        if "403" in raw:
            return "OpenAI API 권한 또는 프로젝트 설정을 확인해주세요."
        if "timeout" in lower or "timed out" in lower:
            return "OpenAI 응답 시간이 초과되었습니다.\\n인터넷 연결을 확인하고 다시 촬영해주세요."
        return "OpenAI 처리 중 오류가 발생했습니다.\\nAPI 설정과 인터넷 연결을 확인해주세요."

    if "timed out" in lower or "timeout" in lower or "시간이 초과" in raw:
        return "서버 응답 시간이 초과되었습니다.\\n인터넷 연결을 확인한 뒤 다시 시도해주세요."

    if any(x in lower for x in ("urlopen", "getaddrinfo", "name resolution", "connection")) or "연결 실패" in raw:
        return "인터넷 연결 문제로 OpenAI에 접속하지 못했습니다.\\n네트워크 연결을 확인해주세요."

    if "camera" in lower or "카메라" in raw or "videocapture" in lower:
        return "카메라를 사용할 수 없습니다.\\n다른 프로그램의 카메라 사용 여부와 카메라 선택을 확인해주세요."

    if any(x in lower for x in ("excel", "workbook", "worksheet", "com_error")):
        return "Excel 처리 중 오류가 발생했습니다.\\nExcel 파일 상태를 확인한 뒤 다시 시도해주세요."

    if "인식 실패" in raw:
        return "글씨를 충분히 인식하지 못했습니다.\\n문서를 조금 더 가까이 두고 밝게 촬영한 뒤 다시 시도해주세요."

    return "처리 중 오류가 발생했습니다.\\n문서 위치와 카메라 상태를 확인한 뒤 다시 시도해주세요."
'''
s=s[:start]+new+s[end:]

start=s.find('# ============================================================\n# 인감대장 - 표 선을 찾지 않는 부분 인식\n')
if start!=-1:
    end=s.find('def order_quad(points):', start)
    newhead='''# ============================================================
# 인감대장 문서 원근 보정 (OpenAI 전송 전 로컬 처리)
# - 표의 가로선/세로선/행번호는 판독 기준으로 사용하지 않는다.
# ============================================================

'''
    s=s[:start]+newhead+s[end:]

marker='\n# ============================================================\n# CLOVA OCR\n'
if marker in s:
    st=s.index(marker)
    en=s.index('def normalize_ledger_address', st)
    s=s[:st]+'\n\n# 인감대장 공통 주소 후처리\n'+s[en:]

p.write_text(s,encoding='utf-8')
