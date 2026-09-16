def test_health_requires_api_key(client):
    response = client.get("/health")

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid API key"}


def test_health_rejects_wrong_api_key(client):
    response = client.get("/health", headers={"X-API-Key": "wrong"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid API key"}


def test_health_accepts_valid_api_key(client, api_key):
    response = client.get("/health", headers={"X-API-Key": api_key})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
