"""Deterministic recipe data and public API for TableStory."""
from __future__ import annotations

import json
import re
from pathlib import Path

from flask import Flask, abort, jsonify, render_template_string, request

ROOT = Path(__file__).parent
FIELDS = {"id", "title", "description", "category", "dietary_tags", "prep_minutes", "cook_minutes", "difficulty", "servings", "ingredients", "steps", "colors", "featured"}
TV_HINTS = ("smarttv", "appletv", "hbbtv")


def validate_recipes(recipes: list[dict]) -> None:
    if not isinstance(recipes, list) or len(recipes) < 12:
        raise ValueError("Recipe data needs at least 12 recipes")
    identifiers = set()
    for recipe in recipes:
        recipe_id = recipe.get("id") if isinstance(recipe, dict) else None
        if not isinstance(recipe, dict) or not FIELDS <= recipe.keys() or not isinstance(recipe_id, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", recipe_id) or recipe_id in identifiers:
            raise ValueError("Recipe requires a unique URL-safe id and complete fields")
        identifiers.add(recipe_id)
        if not all(isinstance(recipe[key], str) and recipe[key] for key in ("title", "description", "category")):
            raise ValueError(f"Recipe {recipe_id} has empty text")
        if (not isinstance(recipe["dietary_tags"], list) or not all(isinstance(tag, str) and tag for tag in recipe["dietary_tags"]) or not isinstance(recipe["prep_minutes"], int) or recipe["prep_minutes"] <= 0 or not isinstance(recipe["cook_minutes"], int) or recipe["cook_minutes"] < 0):
            raise ValueError(f"Recipe {recipe_id} has invalid tags or timing")
        if recipe["difficulty"] not in {"Easy", "Medium", "Confident Cook"} or not isinstance(recipe["servings"], int) or recipe["servings"] <= 0:
            raise ValueError(f"Recipe {recipe_id} has invalid metadata")
        if not recipe["ingredients"] or not all(isinstance(item, str) and item for item in recipe["ingredients"]) or len(recipe["steps"]) < 3 or not all(isinstance(step, str) and step for step in recipe["steps"]):
            raise ValueError(f"Recipe {recipe_id} has invalid ordered content")
        if len(recipe["colors"]) != 2 or not all(isinstance(color, str) and color for color in recipe["colors"]) or not isinstance(recipe["featured"], bool):
            raise ValueError(f"Recipe {recipe_id} has invalid presentation fields")
    tags = [tag.lower() for recipe in recipes for tag in recipe["dietary_tags"]]
    if tags.count("vegetarian") < 3 or tags.count("vegan") < 2 or sum(recipe["prep_minutes"] + recipe["cook_minutes"] <= 30 for recipe in recipes) < 3 or sum(recipe["category"].lower() == "dessert" for recipe in recipes) < 2:
        raise ValueError("Recipe data does not meet coverage requirements")


def load_recipes() -> list[dict]:
    recipes = json.loads((ROOT / "catalog.json").read_text())
    validate_recipes(recipes)
    return recipes


def matches_recipe_query(recipe: dict, query: str) -> bool:
    text = " ".join([recipe["title"], recipe["description"], recipe["category"], *recipe["dietary_tags"], *recipe["ingredients"]]).lower()
    return not (query := str(query or "").strip().lower()) or query in text


def ordered_cookbook(recipe_ids: set[str], recipes: list[dict]) -> list[dict]:
    return [recipe for recipe in recipes if recipe["id"] in recipe_ids]


def build_rails(recipes: list[dict], cookbook_ids: set[str]) -> list[dict]:
    rails = [
        {"name": "Popular this week", "recipe_ids": [r["id"] for r in recipes if r["featured"]][:4]},
        {"name": "Ready in 30 minutes", "recipe_ids": [r["id"] for r in recipes if r["prep_minutes"] + r["cook_minutes"] <= 30]},
        {"name": "Vegetarian favourites", "recipe_ids": [r["id"] for r in recipes if "vegetarian" in {t.lower() for t in r["dietary_tags"]}]},
        {"name": "My Cookbook", "recipe_ids": [r["id"] for r in ordered_cookbook(cookbook_ids, recipes)]},
    ]
    if any(len(rail["recipe_ids"]) < 2 for rail in rails[:3]):
        raise ValueError("Static recipe rails need at least two recipes")
    return rails


def is_tv_request(mode: str | None, user_agent: str) -> bool:
    return mode == "tv" or any(hint in (user_agent or "").lower() for hint in TV_HINTS)


def create_app(testing: bool = False) -> Flask:
    app = Flask(__name__)
    app.config.update(TESTING=testing, COOKBOOK=set())
    recipes = load_recipes()
    by_id = {recipe["id"]: recipe for recipe in recipes}

    @app.get("/")
    def browse():
        tv = is_tv_request(request.args.get("mode"), request.headers.get("User-Agent", ""))
        return render_template_string("<!doctype html><title>TableStory</title><main><h1>TableStory</h1><p>Good food, clearly told.</p>{% if tv %}{% for rail in rails %}<h2>{{ rail.name }}</h2>{% endfor %}{% endif %}</main>", tv=tv, rails=build_rails(recipes, app.config["COOKBOOK"]))

    @app.get("/recipe/<recipe_id>")
    def recipe_detail(recipe_id: str):
        recipe = by_id.get(recipe_id)
        if recipe is None:
            abort(404)
        return render_template_string("<!doctype html><title>{{ recipe.title }} · TableStory</title><main><a href=\"/\">Browse recipes</a><h1>{{ recipe.title }}</h1><p>{{ recipe.description }}</p></main>", recipe=recipe)

    @app.get("/api/recipes")
    def recipes_api():
        return jsonify([recipe for recipe in recipes if matches_recipe_query(recipe, request.args.get("q", ""))])

    @app.get("/api/recipes/<recipe_id>")
    def recipe_api(recipe_id: str):
        recipe = by_id.get(recipe_id)
        return jsonify(recipe) if recipe is not None else (jsonify({"error": "Recipe not found"}), 404)

    @app.route("/api/cookbook", methods=["GET", "POST"])
    def cookbook_api():
        if request.method == "GET":
            return jsonify(ordered_cookbook(app.config["COOKBOOK"], recipes))
        recipe_id = (request.get_json(silent=True) or {}).get("id")
        if recipe_id not in by_id:
            return jsonify({"error": "Unknown recipe"}), 400
        app.config["COOKBOOK"].add(recipe_id)
        return jsonify({"recipe_ids": [recipe["id"] for recipe in ordered_cookbook(app.config["COOKBOOK"], recipes)]}), 201

    @app.delete("/api/cookbook/<recipe_id>")
    def remove_cookbook(recipe_id: str):
        app.config["COOKBOOK"].discard(recipe_id)
        return jsonify({"recipe_ids": [recipe["id"] for recipe in ordered_cookbook(app.config["COOKBOOK"], recipes)]})

    @app.get("/api/rails")
    def rails_api():
        return jsonify(build_rails(recipes, app.config["COOKBOOK"]))
    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
