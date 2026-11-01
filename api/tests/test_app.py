"""api/app.py 의 HTTP 계약 테스트.

기대값은 사장님 규칙(기본 10분 + 1km당 3분 + 대기 주문 1건당 2분)에서
손으로 계산한 값이다. 예측 함수를 불러 정답을 만들지 않는다.
"""

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    """규칙 구현체(MODEL_IMPL=rule)로 앱을 새로 불러온 TestClient."""
    monkeypatch.setenv("MODEL_IMPL", "rule")
    import api.app

    app_module = importlib.reload(api.app)
    return TestClient(app_module.app)


VALID = {"distance_km": 2.0, "pending_orders": 3}


# ---------------------------------------------------------------- /health


def test_health_ok(client):
    """/health 는 200 과 함께 status=ok, 현재 구현체 이름을 돌려준다."""
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "model": "rule"}


# ---------------------------------------------------------------- /eta 규칙 값


@pytest.mark.parametrize(
    ("distance_km", "pending_orders", "expected"),
    [
        (0, 0, 10.0),  # 기본 10분만
        (1, 0, 13.0),  # 10 + 3
        (0, 1, 12.0),  # 10 + 2
        (2, 3, 22.0),  # 10 + 6 + 6
        (2.5, 4, 25.5),  # 10 + 7.5 + 8
        (0.1, 0, 10.3),  # 소수 거리
        (1000, 10000, 23010.0),  # 큰 값: 10 + 3000 + 20000
    ],
)
def test_eta_follows_owner_rule(client, distance_km, pending_orders, expected):
    """/eta 는 10 + 3×거리(km) + 2×대기 주문 수 를 분 단위로 돌려준다."""
    res = client.post("/eta", json={"distance_km": distance_km, "pending_orders": pending_orders})
    assert res.status_code == 200
    assert res.json()["minutes"] == pytest.approx(expected)


def test_eta_one_more_km_adds_three_minutes(client):
    """거리가 1km 늘면 예상 시간이 정확히 3분 늘어난다."""
    a = client.post("/eta", json={"distance_km": 4, "pending_orders": 2}).json()["minutes"]
    b = client.post("/eta", json={"distance_km": 5, "pending_orders": 2}).json()["minutes"]
    assert b - a == pytest.approx(3.0)


def test_eta_one_more_order_adds_two_minutes(client):
    """대기 주문이 1건 늘면 예상 시간이 정확히 2분 늘어난다."""
    a = client.post("/eta", json={"distance_km": 4, "pending_orders": 2}).json()["minutes"]
    b = client.post("/eta", json={"distance_km": 4, "pending_orders": 3}).json()["minutes"]
    assert b - a == pytest.approx(2.0)


# ---------------------------------------------------------------- /eta 응답 형식


def test_eta_response_shape(client):
    """/eta 응답은 정확히 minutes(숫자)와 model(문자열) 두 필드다."""
    res = client.post("/eta", json=VALID)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/json")
    body = res.json()
    assert set(body) == {"minutes", "model"}
    assert isinstance(body["minutes"], (int, float)) and not isinstance(body["minutes"], bool)
    assert body["model"] == "rule"


def test_eta_model_matches_health(client):
    """/eta 의 model 은 /health 가 알려 주는 구현체 이름과 같다."""
    eta_model = client.post("/eta", json=VALID).json()["model"]
    health_model = client.get("/health").json()["model"]
    assert eta_model == health_model


# ---------------------------------------------------------------- /eta 입력 검증


@pytest.mark.parametrize(
    "payload",
    [
        {"distance_km": "abc", "pending_orders": 3},
        {"distance_km": 2.0, "pending_orders": "many"},
        {"distance_km": None, "pending_orders": 3},
        {"distance_km": 2.0, "pending_orders": None},
        {"distance_km": [1], "pending_orders": 3},
        {"distance_km": 2.0, "pending_orders": 1.5},  # 주문 수는 정수
    ],
)
def test_eta_rejects_wrong_types(client, payload):
    """숫자가 아니거나 주문 수가 정수가 아니면 422."""
    assert client.post("/eta", json=payload).status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"distance_km": -0.1, "pending_orders": 0},
        {"distance_km": -5, "pending_orders": 3},
        {"distance_km": 0, "pending_orders": -1},
        {"distance_km": -1, "pending_orders": -1},
    ],
)
def test_eta_rejects_negative(client, payload):
    """거리나 대기 주문 수가 음수면 422."""
    assert client.post("/eta", json=payload).status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"pending_orders": 3},
        {"distance_km": 2.0},
        {},
    ],
)
def test_eta_rejects_missing_fields(client, payload):
    """필수 필드가 빠지면 422."""
    assert client.post("/eta", json=payload).status_code == 422


def test_eta_rejects_non_json_body(client):
    """JSON 이 아닌 본문은 422."""
    res = client.post("/eta", content=b"distance=2", headers={"content-type": "application/json"})
    assert res.status_code == 422


def test_eta_422_names_offending_field(client):
    """422 응답의 detail 은 문제가 된 필드를 가리킨다."""
    res = client.post("/eta", json={"distance_km": -1, "pending_orders": 0})
    assert res.status_code == 422
    locs = [err["loc"] for err in res.json()["detail"]]
    assert ["body", "distance_km"] in locs


# ---------------------------------------------------------------- /eta 경계값


def test_eta_accepts_negative_zero_as_zero(client):
    """-0.0km 는 음수가 아니므로 받아들이고 0km 와 같은 10분을 돌려준다."""
    res = client.post("/eta", json={"distance_km": -0.0, "pending_orders": 0})
    assert res.status_code == 200
    assert res.json()["minutes"] == pytest.approx(10.0)


def test_eta_accepts_tiny_positive_distance(client):
    """0 바로 위의 아주 작은 거리도 받아들이고 10분에 아주 가까운 값을 돌려준다."""
    res = client.post("/eta", json={"distance_km": 1e-9, "pending_orders": 0})
    assert res.status_code == 200
    assert res.json()["minutes"] == pytest.approx(10.0)


# ---------------------------------------------------------------- /eta 유한하지 않은 값·overflow


@pytest.mark.parametrize(
    "raw",
    [
        b'{"distance_km": NaN, "pending_orders": 0}',
        b'{"distance_km": Infinity, "pending_orders": 0}',
        b'{"distance_km": -Infinity, "pending_orders": 0}',
        b'{"distance_km": 1e400, "pending_orders": 0}',  # float 범위 밖 → inf
    ],
    ids=["nan", "inf", "neg-inf", "1e400"],
)
def test_eta_rejects_non_finite_distance(client, raw):
    """유한하지 않은 거리는 서버 오류 없이 422 로 거절하고, 거리 필드를 가리킨다."""
    client = TestClient(client.app, raise_server_exceptions=False)
    res = client.post("/eta", content=raw, headers={"content-type": "application/json"})
    assert res.status_code == 422
    assert ["body", "distance_km"] in [err["loc"] for err in res.json()["detail"]]


@pytest.mark.parametrize(
    "payload",
    [
        {"distance_km": 1e308, "pending_orders": 0},  # 3 × 1e308 → inf
        {"distance_km": 0, "pending_orders": 10**308},  # 2 × 1e308 → inf
        {"distance_km": 0, "pending_orders": 10**400},  # float 로 바꿀 수 없음
    ],
    ids=["huge-distance", "huge-orders", "orders-beyond-float"],
)
def test_eta_rejects_overflowing_result(client, payload):
    """입력은 유한해도 결과가 숫자로 표현되지 않으면 서버 오류나 null 없이 422."""
    client = TestClient(client.app, raise_server_exceptions=False)
    res = client.post("/eta", json=payload)
    assert res.status_code == 422
    detail = res.json()["detail"]
    assert isinstance(detail, list) and detail
    for err in detail:
        assert {"loc", "msg", "type"} <= set(err)


# ---------------------------------------------------------------- /eta 요청 본문 형식


@pytest.mark.parametrize(
    ("content", "content_type"),
    [
        (b"[1, 2]", "application/json"),  # 객체가 아닌 JSON
        (b"", "application/json"),  # 빈 본문
        (b'{"distance_km": 1, "pending_orders": 1}', None),  # Content-Type 없음
        (b'{"distance_km": 1, "pending_orders": 1}', "text/plain"),  # JSON 이 아닌 Content-Type
    ],
    ids=["json-array", "empty", "no-content-type", "text-plain"],
)
def test_eta_rejects_malformed_body(client, content, content_type):
    """JSON 객체가 아니거나 JSON 으로 보내지 않은 본문은 422."""
    headers = {"content-type": content_type} if content_type else {}
    assert client.post("/eta", content=content, headers=headers).status_code == 422


def test_eta_rejects_empty_string_distance(client):
    """빈 문자열 거리는 숫자가 아니므로 422."""
    res = client.post("/eta", json={"distance_km": "", "pending_orders": 1})
    assert res.status_code == 422


def test_eta_422_lists_every_offending_field(client):
    """두 필드가 모두 잘못되면 422 detail 이 두 필드를 모두 가리킨다."""
    res = client.post("/eta", json={"distance_km": -1, "pending_orders": -1})
    assert res.status_code == 422
    locs = [err["loc"] for err in res.json()["detail"]]
    assert ["body", "distance_km"] in locs
    assert ["body", "pending_orders"] in locs


def test_eta_422_body_shape(client):
    """422 응답은 detail 목록이고, 각 항목에 loc·msg·type 이 있다."""
    res = client.post("/eta", json={"distance_km": "abc", "pending_orders": 0})
    assert res.status_code == 422
    detail = res.json()["detail"]
    assert isinstance(detail, list) and detail
    for err in detail:
        assert {"loc", "msg", "type"} <= set(err)


# ---------------------------------------------------------------- HTTP 메서드


@pytest.mark.parametrize(("method", "path"), [("get", "/eta"), ("post", "/health")])
def test_wrong_method_is_405(client, method, path):
    """/eta 는 POST, /health 는 GET 만 받는다. 다른 메서드는 405."""
    assert getattr(client, method)(path).status_code == 405


# ---------------------------------------------------------------- MODEL_IMPL 설정


def test_default_model_impl_is_rule(monkeypatch):
    """MODEL_IMPL 을 설정하지 않으면 rule 구현체로 뜬다."""
    monkeypatch.delenv("MODEL_IMPL", raising=False)
    import api.app

    app_module = importlib.reload(api.app)
    client = TestClient(app_module.app)
    assert client.get("/health").json()["model"] == "rule"
    assert client.post("/eta", json=VALID).json() == {"minutes": 22.0, "model": "rule"}


def test_unknown_model_impl_fails_at_startup(monkeypatch):
    """없는 구현체 이름이면 요청을 받기 전, 앱을 불러올 때 바로 실패한다."""
    monkeypatch.setenv("MODEL_IMPL", "does_not_exist")
    import api.app

    with pytest.raises(ModuleNotFoundError):
        importlib.reload(api.app)


# ---------------------------------------------------------------- /eta 느슨한 입력 (받아들이기로 한 정책)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"distance_km": "2", "pending_orders": "3"}, 22.0),  # 숫자 문자열
        ({"distance_km": "2.5", "pending_orders": 4}, 25.5),  # 소수 문자열
        ({"distance_km": True, "pending_orders": False}, 13.0),  # bool → 1, 0
        ({"distance_km": 2, "pending_orders": 3.0}, 22.0),  # 소수부가 0인 주문 수
    ],
    ids=["numeric-strings", "decimal-string", "bools", "integral-float-orders"],
)
def test_eta_accepts_coercible_inputs(client, payload, expected):
    """숫자로 바꿀 수 있는 입력은 받아들이고, 바꾼 값으로 규칙을 계산한다."""
    res = client.post("/eta", json=payload)
    assert res.status_code == 200
    assert res.json()["minutes"] == pytest.approx(expected)


def test_eta_ignores_unknown_fields(client):
    """정의되지 않은 필드는 무시하고, 응답은 그 필드가 없을 때와 같다."""
    with_extra = client.post("/eta", json={**VALID, "foo": 1, "note": "문 앞"})
    without = client.post("/eta", json=VALID)
    assert with_extra.status_code == 200
    assert with_extra.json() == without.json()


def test_eta_accepts_very_large_pending_orders(client):
    """대기 주문 수에는 상한이 없다. 10**30 건도 받아들인다."""
    res = client.post("/eta", json={"distance_km": 0, "pending_orders": 10**30})
    assert res.status_code == 200
    assert res.json()["minutes"] == pytest.approx(2e30)
