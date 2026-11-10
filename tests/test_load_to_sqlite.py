"""Unit tests for the ETL in src/load_to_sqlite.py, using tiny synthetic data."""
import json
import sqlite3

import pandas as pd
import pytest

from src import load_to_sqlite as etl


@pytest.fixture
def enemies():
    return pd.DataFrame([
        {
            "id": "queen", "name": "Queen", "icon": "q.svg", "image": "q.png",
            "updatedAt": "2026-07-31",
            "dropTable": json.dumps([
                {"id": "core", "name": "Core", "rarity": "legendary", "value": 5000, "type": "part"},
                {"id": "alloy", "name": "Alloy", "rarity": "common", "value": 100, "type": "material"},
            ]),
            "relatedMaps": json.dumps([{"id": "dam", "name": "Dam"}, {"id": "port", "name": "Spaceport"}]),
        },
        {
            "id": "wasp", "name": "Wasp", "icon": "w.svg", "image": "w.png",
            "updatedAt": "2026-07-31",
            "dropTable": "[]",
            "relatedMaps": None,  # patrol drones have no fixed map
        },
    ])


@pytest.fixture
def quests():
    return pd.DataFrame([
        {"id": "q1", "title": "First", "trader": "Celeste", "xpReward": 100,
         "description": "d", "image": "i.png",
         "maps": json.dumps([{"id": "dam", "name": "Dam"}, {"id": "city", "name": "Buried City"}])},
    ])


@pytest.fixture
def items():
    return pd.DataFrame([
        {"id": "core", "name": "Core", "rarity": "legendary", "type": "part", "value": 5000,
         "weight": 1.0, "stackSize": 1, "image": "c.png", "icon": "c.svg", "extra": "dropped"},
    ])


def test_parse_json_column_handles_valid_empty_and_broken_values():
    series = pd.Series(['[{"id": 1}]', "[]", "", None, "{not json"])
    parsed = etl.parse_json_column(series).tolist()
    assert parsed == [[{"id": 1}], [], [], [], []]


def test_normalize_enemies_flattens_drop_table(enemies):
    basic, drops, maps = etl.normalize_enemies(enemies)
    assert list(basic.columns) == ["id", "name", "icon", "image", "updatedAt"]
    assert len(drops) == 2
    assert set(drops["enemy_id"]) == {"queen"}
    assert drops.loc[drops["item_id"] == "core", "value"].item() == 5000


def test_normalize_enemies_builds_enemy_map_bridge(enemies):
    _, _, maps = etl.normalize_enemies(enemies)
    assert sorted(maps["map_id"]) == ["dam", "port"]
    assert "wasp" not in set(maps["enemy_id"])


def test_normalize_items_keeps_only_selected_columns(items):
    out = etl.normalize_items(items)
    assert "extra" not in out.columns
    assert len(out.columns) == 9


def test_normalize_quests_builds_quest_map_bridge(quests):
    basic, quest_maps = etl.normalize_quests(quests)
    assert len(basic) == 1
    assert list(quest_maps["map_id"]) == ["dam", "city"]


def test_extract_all_maps_deduplicates_across_sources(enemies, quests):
    maps = etl.extract_all_maps(enemies, quests)
    assert sorted(maps["id"]) == ["city", "dam", "port"]
    assert maps["id"].is_unique


def test_main_writes_normalized_sqlite(tmp_path, monkeypatch, enemies, items, quests):
    raw = tmp_path / "raw"
    raw.mkdir()
    enemies.to_csv(raw / "arc_enemies.csv", index=False)
    items.to_csv(raw / "items.csv", index=False)
    quests.to_csv(raw / "quests.csv", index=False)
    db = tmp_path / "out" / "arc_loot.db"
    monkeypatch.setattr(etl, "DATA_PATH", raw)
    monkeypatch.setattr(etl, "DB_PATH", db)

    etl.main()

    with sqlite3.connect(db) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert tables == {"enemies", "enemy_drops", "enemy_maps", "items", "quests", "quest_maps", "maps"}
        top = conn.execute(
            "SELECT e.name, SUM(d.value) FROM enemies e JOIN enemy_drops d ON e.id = d.enemy_id "
            "GROUP BY e.name ORDER BY 2 DESC LIMIT 1").fetchone()
        assert top == ("Queen", 5100)
