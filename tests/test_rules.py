from src.postal_rules import (
    filter_general_english,
    normalize_general_result,
    general_address_has_structure,
    general_result_needs_retry,
    ledger_result_needs_retry,
    normalize_ledger_address,
    estimate_openai_cost_usd,
)


def test_general_k_t_only():
    address, name = normalize_general_result('경북 포항시 KT ABC빌딩 101호', '홍길동님')
    assert 'KT' in address
    assert 'ABC' not in address
    assert name == '홍길동'


def test_general_omitted_province_structure():
    assert general_address_has_structure('포항시 남구 오천읍 문덕로 10')


def test_general_retry_logic():
    good = {'address':'포항시 남구 오천읍 문덕로 10', 'name':'홍길동', 'address_confidence':.94, 'name_confidence':.92}
    bad = dict(good, name='A')
    assert general_result_needs_retry(good) is False
    assert general_result_needs_retry(bad) is True


def test_ledger_normalization_and_retry():
    assert normalize_ledger_address('경상북도 포항시시 남구 대이읖장') == '경상북도 포항시 남구 대이읍장'
    good = {'institution':'경상북도 포항시 남구 대이동장', 'name':'김명현', 'institution_confidence':.95}
    bad = {'institution':'포항시시 남구', 'name':'김명현', 'institution_confidence':.95}
    assert ledger_result_needs_retry(good) is False
    assert ledger_result_needs_retry(bad) is True


def test_cost_estimate():
    # Luna: 1M input=$0.20, 1M output=$1.20
    assert abs(estimate_openai_cost_usd('gpt-5.6-luna', 1_000_000, 1_000_000) - 1.4) < 1e-9
