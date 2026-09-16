def test_browse_and_recipe_detail_render(client):
    home = client.get("/")
    assert home.status_code == 200
    assert b"TableStory" in home.data
    recipes = client.get("/api/recipes").get_json()
    assert client.get(f"/recipe/{recipes[0]['id']}").status_code == 200
    assert client.get("/recipe/missing").status_code == 404


def test_recipe_search_and_detail_api(client):
    recipes = client.get("/api/recipes?q=VEGAN").get_json()
    assert len(recipes) >= 2
    recipe_id = recipes[0]["id"]
    assert client.get(f"/api/recipes/{recipe_id}").get_json()["id"] == recipe_id
    assert client.get("/api/recipes/missing").status_code == 404


def test_cookbook_round_trip(client):
    recipe_id = client.get("/api/recipes").get_json()[0]["id"]
    assert client.get("/api/cookbook").get_json() == []
    assert client.post("/api/cookbook", json={"id": recipe_id}).status_code == 201
    assert [recipe["id"] for recipe in client.get("/api/cookbook").get_json()] == [recipe_id]
    assert client.delete(f"/api/cookbook/{recipe_id}").status_code == 200
    assert client.post("/api/cookbook", json={"id": "missing"}).status_code == 400
