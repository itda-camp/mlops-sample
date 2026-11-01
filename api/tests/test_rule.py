"""api/predictors/rule.py 기준선 함수의 계약 테스트.

기대값은 사장님 규칙(기본 10분 + 1km당 3분 + 대기 주문 1건당 2분)에서
손으로 계산한 값이다. HTTP 를 거치지 않고 함수만 확인한다.
"""

import pytest

from api.predictors.rule import estimate_delivery_minutes


@pytest.mark.parametrize(
    ("distance_km", "pending_orders", "expected"),
    [
        (0, 0, 10.0),
        (1, 0, 13.0),
        (0, 1, 12.0),
        (2, 3, 22.0),
        (2.5, 4, 25.5),
        (1000, 10000, 23010.0),
    ],
)
def test_rule_known_values(distance_km, pending_orders, expected):
    """알려진 입력에 대해 10 + 3×거리 + 2×주문 수 를 돌려준다."""
    assert estimate_delivery_minutes(distance_km, pending_orders) == pytest.approx(expected)


def test_rule_returns_float():
    """정수만 넣어도 결과는 float(분)이다."""
    result = estimate_delivery_minutes(0, 0)
    assert isinstance(result, float)


def test_rule_never_below_base_for_valid_input():
    """음수가 아닌 입력이면 결과는 기본 10분보다 작지 않다."""
    for d in (0, 0.01, 1, 50):
        for p in (0, 1, 100):
            assert estimate_delivery_minutes(d, p) >= 10.0
