import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "orders.db")
    with TestClient(main.app) as test_client:
        yield test_client


def test_health_and_seeded_orders(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    orders = client.get("/api/orders").json()
    assert len(orders) == 3
    assert {order["priority"] for order in orders} == {"standard", "express"}


def test_create_and_update_order(client):
    response = client.post(
        "/api/orders",
        json={"customer": "Taylor", "item": "Mug", "priority": "standard"},
    )
    assert response.status_code == 201
    order_id = response.json()["id"]
    assert client.get(f"/api/orders/{order_id}").json()["status"] == "received"
    updated = client.patch(f"/api/orders/{order_id}", json={"status": "shipped"})
    assert updated.status_code == 200
    assert updated.json()["status"] == "shipped"


def test_missing_order(client):
    assert client.get("/api/orders/missing").status_code == 404


@pytest.mark.parametrize(
    ("created_at", "expected_delivery"),
    [
        ("2026-09-30T14:30:00+00:00", "2026-10-02"),
        ("2026-01-30T14:30:00+00:00", "2026-02-01"),
        ("2026-01-31T14:30:00+00:00", "2026-02-02"),
        ("2026-02-28T14:30:00+00:00", "2026-03-02"),
        ("2024-02-28T14:30:00+00:00", "2024-03-01"),
        ("2024-02-29T14:30:00+00:00", "2024-03-02"),
        ("2026-12-31T14:30:00+00:00", "2027-01-02"),
        ("2026-10-05T14:30:00+00:00", "2026-10-07"),
    ],
)
def test_express_lookup_delivery_date(client, created_at, expected_delivery):
    with main.connect() as db:
        db.execute(
            "UPDATE orders SET created_at = ? WHERE id = ?",
            (created_at, "express-1002"),
        )

    response = client.get("/api/orders/express-1002")

    assert response.status_code == 200
    assert response.json() == {
        "id": "express-1002",
        "customer": "Sam",
        "item": "Headphones",
        "priority": "express",
        "status": "preparing",
        "created_at": created_at,
        "estimated_delivery": expected_delivery,
    }
