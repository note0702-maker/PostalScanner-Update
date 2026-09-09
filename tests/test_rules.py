import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from postal_rules import (
    filter_general_english,
    normalize_general_result,
    general_address_has_structure,
    ledger_name_is_plausible,
    GENERAL_MAIL_PROMPT,
    LEDGER_PROMPT,
)


def test_general_k_t_rule():
    assert filter_general_english('ABC KT타워 101호') == 'KT타워 101호'
    assert filter_general_english('kt 빌딩') == 'KT 빌딩'


def test_general_honorific_and_structure():
    address, name = normalize_general_result('포항시 남구 오천읍 123 KT', '홍길동 귀하')
    assert address == '포항시 남구 오천읍 123 KT'
    assert name == '홍길동'
    assert general_address_has_structure(address)


def test_general_prompt_preserves_rules():
    assert '도/광역시가 생략' in GENERAL_MAIL_PROMPT
    assert 'K와 T만 허용' in GENERAL_MAIL_PROMPT
    assert '담당자' in GENERAL_MAIL_PROMPT


def test_ledger_prompt_preserves_rules():
    assert '가로선/세로선/행번호' in LEDGER_PROMPT
    assert '가장 아래' in LEDGER_PROMPT
    assert '시/구/도/군/장' in LEDGER_PROMPT
    assert '등기번호 열' in LEDGER_PROMPT
    assert '육장/욕장/읖장/읏장' in LEDGER_PROMPT


def test_ledger_name_rule():
    assert ledger_name_is_plausible('김명현')
    assert not ledger_name_is_plausible('김')
    assert not ledger_name_is_plausible('KIM')
