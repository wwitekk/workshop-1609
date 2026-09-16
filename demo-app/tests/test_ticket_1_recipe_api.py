"""Acceptance coverage for Ticket #1's public recipe-domain API."""

import re


RECIPE_FIELDS = {
    "id",
    "title",
    "description",
    "category",
    "dietary_tags",
    "prep_minutes",
    "cook_minutes",
    "difficulty",
    "servings",
    "ingredients",
    "steps",
    "colors",
    "featured",
}


def test_recipe_collection_is_complete_validated_and_searchable(client):
    response = client.get("/api/recipes")
    assert response.status_code == 200
    recipes = response.get_json()

    assert len(recipes) >= 12
    assert len({recipe["id"] for recipe in recipes}) == len(recipes)
    assert sum("vegetarian" in {tag.lower() for tag in r["dietary_tags"]} for r in recipes) >= 3
    assert sum("vegan" in {tag.lower() for tag in r["dietary_tags"]} for r in recipes) >= 2
    assert sum(r["prep_minutes"] + r["cook_minutes"] <= 30 for r in recipes) >= 3
    assert sum(r["category"].lower() == "dessert" for r in recipes) >= 2

    searchable_examples = []
    for field in ("title", "description", "category"):
        recipe = next(recipe for recipe in recipes if recipe[field])
        searchable_examples.append((recipe["id"], recipe[field]))
    tagged_recipe = next(recipe for recipe in recipes if recipe["dietary_tags"])
    searchable_examples.append((tagged_recipe["id"], tagged_recipe["dietary_tags"][0]))
    ingredient_recipe = next(recipe for recipe in recipes if recipe["ingredients"])
    searchable_examples.append((ingredient_recipe["id"], ingredient_recipe["ingredients"][0]))

    for recipe in recipes:
        assert RECIPE_FIELDS <= recipe.keys()
        assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", recipe["id"])
        assert isinstance(recipe["title"], str) and recipe["title"]
        assert isinstance(recipe["description"], str) and recipe["description"]
        assert isinstance(recipe["category"], str) and recipe["category"]
        assert isinstance(recipe["dietary_tags"], list)
        assert isinstance(recipe["prep_minutes"], int) and recipe["prep_minutes"] > 0
        assert isinstance(recipe["cook_minutes"], int) and recipe["cook_minutes"] >= 0
        assert recipe["difficulty"] in {"Easy", "Medium", "Confident Cook"}
        assert isinstance(recipe["servings"], int) and recipe["servings"] > 0
        assert recipe["ingredients"] and all(isinstance(item, str) and item for item in recipe["ingredients"])
        assert len(recipe["steps"]) >= 3 and all(isinstance(step, str) and step for step in recipe["steps"])
        assert len(recipe["colors"]) == 2 and all(isinstance(color, str) and color for color in recipe["colors"])
        assert isinstance(recipe["featured"], bool)
        assert "total_minutes" not in recipe

    assert client.get("/api/recipes?q=   ").get_json() == recipes
    for recipe_id, query in searchable_examples:
        assert recipe_id in {
            recipe["id"] for recipe in client.get("/api/recipes", query_string={"q": query.upper()}).get_json()
        }


def test_recipe_detail_and_cookbook_lifecycle_are_recipe_specific_and_deterministic(client):
    collection = client.get("/api/recipes")
    assert collection.status_code == 200
    recipes = collection.get_json()
    first_id, second_id = recipes[0]["id"], recipes[1]["id"]

    detail = client.get(f"/api/recipes/{first_id}")
    assert detail.status_code == 200
    assert detail.get_json() == recipes[0]

    missing = client.get("/api/recipes/not-a-recipe")
    assert missing.status_code == 404
    assert missing.get_json() == {"error": "Recipe not found"}

    assert client.get("/api/cookbook").get_json() == []
    invalid = client.post("/api/cookbook", json={"id": "not-a-recipe"})
    assert invalid.status_code == 400
    assert "recipe" in invalid.get_json()["error"].lower()
    missing_id = client.post("/api/cookbook", json={})
    assert missing_id.status_code == 400
    assert "recipe" in missing_id.get_json()["error"].lower()
    assert client.post("/api/cookbook", json={"id": first_id}).status_code == 201
    assert client.post("/api/cookbook", json={"id": second_id}).status_code == 201
    assert [recipe["id"] for recipe in client.get("/api/cookbook").get_json()] == [first_id, second_id]
    assert client.post("/api/cookbook", json={"id": first_id}).status_code == 201
    assert [recipe["id"] for recipe in client.get("/api/cookbook").get_json()] == [first_id, second_id]
    assert client.delete(f"/api/cookbook/{first_id}").status_code == 200
    assert client.delete(f"/api/cookbook/{first_id}").status_code == 200
    assert [recipe["id"] for recipe in client.get("/api/cookbook").get_json()] == [second_id]


def test_recipe_rails_tv_entry_and_deprecated_routes(client):
    collection = client.get("/api/recipes")
    assert collection.status_code == 200
    recipes = collection.get_json()
    known_ids = {recipe["id"] for recipe in recipes}
    rails_response = client.get("/api/rails")
    assert rails_response.status_code == 200
    rails = rails_response.get_json()

    assert [rail["name"] for rail in rails] == [
        "Popular this week",
        "Ready in 30 minutes",
        "Vegetarian favourites",
        "My Cookbook",
    ]
    for rail in rails:
        assert set(rail) == {"name", "recipe_ids"}
        assert set(rail["recipe_ids"]) <= known_ids
    assert all(len(rail["recipe_ids"]) >= 2 for rail in rails[:-1])
    assert rails[-1]["recipe_ids"] == []

    saved_id = recipes[0]["id"]
    client.post("/api/cookbook", json={"id": saved_id})
    assert client.get("/api/rails").get_json()[-1]["recipe_ids"] == [saved_id]
    assert b"Popular this week" in client.get("/?mode=tv").data
    assert b"Vegetarian favourites" in client.get("/", headers={"User-Agent": "SmartTV"}).data

    for path in ("/movie/afterlight", "/api/movies", "/api/movies/afterlight", "/api/watchlist"):
        assert client.get(path).status_code == 404
