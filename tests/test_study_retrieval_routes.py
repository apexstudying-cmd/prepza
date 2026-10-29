from app import app


def test_study_retrieval_endpoint_requires_login():
    with app.test_client() as client:
        response = client.post("/api/study/retrieval", json={"query": "derivatives"})

    assert response.status_code == 401
    assert response.get_json()["error"] == "Not logged in"
