import pytest
from fastapi.testclient import TestClient
from main import app


client = TestClient(app)


def test_predict_verified_seller_positive():
    response = client.post(
        "/predict",
        json={
            "seller_id": 1,
            "is_verified_seller": True,
            "item_id": 100,
            "name": "Test Item",
            "description": "Test Description",
            "category": 5,
            "images_qty": 0
        }
    )
    assert response.status_code == 200
    assert response.json()["is_valid"] is True


def test_predict_unverified_seller_with_images_positive():
    response = client.post(
        "/predict",
        json={
            "seller_id": 2,
            "is_verified_seller": False,
            "item_id": 200,
            "name": "Test Item",
            "description": "Test Description",
            "category": 3,
            "images_qty": 5
        }
    )
    assert response.status_code == 200
    assert response.json()["is_valid"] is True


def test_predict_unverified_seller_no_images_negative():
    response = client.post(
        "/predict",
        json={
            "seller_id": 3,
            "is_verified_seller": False,
            "item_id": 300,
            "name": "Test Item",
            "description": "Test Description",
            "category": 2,
            "images_qty": 0
        }
    )
    assert response.status_code == 200
    assert response.json()["is_valid"] is False


def test_predict_missing_required_field():
    response = client.post(
        "/predict",
        json={
            "seller_id": 4,
            "is_verified_seller": True,
            "item_id": 400,
            "description": "Test Description",
            "category": 1,
            "images_qty": 2
        }
    )
    assert response.status_code == 422


def test_predict_invalid_type():
    response = client.post(
        "/predict",
        json={
            "seller_id": "invalid",
            "is_verified_seller": True,
            "item_id": 500,
            "name": "Test Item",
            "description": "Test Description",
            "category": 4,
            "images_qty": 1
        }
    )
    assert response.status_code == 422


def test_predict_negative_values():
    response = client.post(
        "/predict",
        json={
            "seller_id": -1,
            "is_verified_seller": False,
            "item_id": 600,
            "name": "Test Item",
            "description": "Test Description",
            "category": 2,
            "images_qty": 3
        }
    )
    assert response.status_code == 422


def test_predict_empty_string():
    response = client.post(
        "/predict",
        json={
            "seller_id": 5,
            "is_verified_seller": False,
            "item_id": 700,
            "name": "",
            "description": "Test Description",
            "category": 1,
            "images_qty": 2
        }
    )
    assert response.status_code == 422
