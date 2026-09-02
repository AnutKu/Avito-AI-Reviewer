import pytest
from fastapi.testclient import TestClient

from routes.predict import router
from main import app


client = TestClient(app)


def test_predict_negative_verified_seller() -> None:
    payload = {
        "seller_id": 1,
        "is_verified_seller": True,
        "item_id": 10,
        "name": "Phone",
        "description": "Nice phone",
        "category": 3,
        "images_qty": 0,
    }
    resp = client.post("/predict", json=payload)
    assert resp.status_code == 200
    assert resp.json() is False


def test_predict_positive_unverified_without_images() -> None:
    payload = {
        "seller_id": 2,
        "is_verified_seller": False,
        "item_id": 11,
        "name": "Book",
        "description": "Good condition",
        "category": 1,
        "images_qty": 0,
    }
    resp = client.post("/predict", json=payload)
    assert resp.status_code == 200
    assert resp.json() is True

def test_predict_negative_unverified_with_images() -> None:
    payload = {
        "seller_id": 2,
        "is_verified_seller": False,
        "item_id": 11,
        "name": "Book",
        "description": "Good condition",
        "category": 1,
        "images_qty": 1,
    }
    resp = client.post("/predict", json=payload)
    assert resp.status_code == 200
    assert resp.json() is False

@pytest.mark.parametrize(
    "payload",
    [
        {},  # отсутствуют необходимые поля
        {
            "seller_id": "oops",  # неверный тип данных
            "is_verified_seller": False,
            "item_id": 11,
            "name": "Book",
            "description": "Good condition",
            "category": 1,
            "images_qty": 0,
        },
        {
            "seller_id": 0,  # не соответствует ge=1
            "is_verified_seller": False,
            "item_id": 11,
            "name": "Book",
            "description": "Good condition",
            "category": 1,
            "images_qty": 0,
        },
        {
            "seller_id": 1,
            "is_verified_seller": False,
            "item_id": 11,
            "name": "",  # min_length=1
            "description": "Good condition",
            "category": 1,
            "images_qty": 0,
        },      
        {
            "seller_id": 1,
            "is_verified_seller": True,
            # пропущено item_id
            "name": "Test Item",
            "description": "Test Description",
            "category": 5,
            "images_qty": 0
        },
        {
            "seller_id": 1,
            "is_verified_seller": "invalid_string",  # должно быть bool
            "item_id": 100,
            "name": "Test Item",
            "description": "Test Description",
            "category": 5,
            "images_qty": 0
        },
        {
            "seller_id": 1,
            "is_verified_seller": True,
            "item_id": 100,
            "name": "",  # пустой name
            "description": "Test Description",
            "category": 5,
            "images_qty": 0
        },
        {
            "seller_id": 1,
            "is_verified_seller": True,
            "item_id": 100,
            "name": "Test Item",
            "description": "",  # пустой description
            "category": 5,
            "images_qty": 0
        }
    ],
)
def test_predict_validation_errors(payload: dict) -> None:
    resp = client.post("/predict", json=payload)
    assert resp.status_code == 422


from errors import BusinessLogicError
from services.moderation import ModerationService



def test_predict_business_logic_error_returns_500(monkeypatch):
    def broken_predict(self, req):
        raise BusinessLogicError("Forced business logic error")

    # подменяем метод predict у ModerationService
    monkeypatch.setattr(ModerationService, "predict", broken_predict)

    payload = {
        "seller_id": 1,
        "is_verified_seller": True,
        "item_id": 10,
        "name": "Test",
        "description": "Test",
        "category": 1,
        "images_qty": 1
    }

    r = client.post("/predict", json=payload)

    assert r.status_code == 500
    assert r.json()["detail"] == "Forced business logic error"