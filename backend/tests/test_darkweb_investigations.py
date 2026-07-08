def test_investigation_saves_search_results_and_gets_by_new_route(client, monkeypatch):
    from backend.routers import darkweb

    fake_results = [
        {"title": f"Result {i}", "link": f"http://result{i}.onion"}
        for i in range(226)
    ]

    monkeypatch.setattr(darkweb, "_robin_available", True)
    monkeypatch.setattr(darkweb, "_llm_available", False)
    monkeypatch.setattr(darkweb, "_check_tor", lambda: {"status": "up", "latency_ms": 10, "error": None})
    monkeypatch.setattr(darkweb, "get_search_results", lambda query, max_workers=5: fake_results)
    monkeypatch.setattr(
        darkweb,
        "scrape_multiple",
        lambda urls, max_workers=3: {url["link"]: url["title"] for url in urls},
    )

    create_resp = client.post(
        "/api/darkweb/investigate",
        json={
            "query": "acme leak",
            "scrape_top_n": 5,
            "max_search_results": 20,
        },
    )
    assert create_resp.status_code == 200
    create_body = create_resp.json()
    assert create_body["results_found"] == 226
    assert create_body["filtered_count"] == 20

    inv_id = create_body["investigation_id"]

    get_resp = client.get(f"/api/darkweb/investigations/{inv_id}")
    assert get_resp.status_code == 200
    inv = get_resp.json()
    assert inv["id"] == inv_id
    assert inv["query"] == "acme leak"
    assert inv["raw_results_count"] == 226
    assert len(inv["raw_results"]) == 226
    assert inv["filtered_count"] == 20
    assert len(inv["filtered_results"]) == 20


def test_new_investigation_route_returns_404_for_missing_id(client):
    resp = client.get("/api/darkweb/investigations/inv_missing")
    assert resp.status_code == 404
