"""ETL: load the ARC Raiders Kaggle CSVs, flatten nested JSON columns and
write a normalized SQLite database (data/processed/arc_loot.db)."""
import json
import os
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = Path(os.getenv("ARC_DATA_DIR", ROOT / "data" / "raw"))
DB_PATH = Path(os.getenv("ARC_DB_PATH", ROOT / "data" / "processed" / "arc_loot.db"))

def load_raw_data():
    enemies = pd.read_csv(f"{DATA_PATH}/arc_enemies.csv")
    items = pd.read_csv(f"{DATA_PATH}/items.csv")
    quests = pd.read_csv(f"{DATA_PATH}/quests.csv")
    return enemies, items, quests

def parse_json_column(series):
    def safe_parse(x):
        if pd.isna(x) or x == "" or x == "[]":
            return []
        try:
            return json.loads(x)
        except (ValueError, TypeError):
            return []
    return series.apply(safe_parse)

def normalize_enemies(enemies):
    enemies["dropTable_parsed"] = parse_json_column(enemies["dropTable"])
    enemies["relatedMaps_parsed"] = parse_json_column(enemies["relatedMaps"])

    enemy_basic = enemies[["id", "name", "icon", "image", "updatedAt"]].copy()

    enemy_drops = []
    for _, row in enemies.iterrows():
        for item in row["dropTable_parsed"]:
            enemy_drops.append({
                "enemy_id": row["id"],
                "item_id": item.get("id"),
                "item_name": item.get("name"),
                "rarity": item.get("rarity"),
                "value": item.get("value"),
                "type": item.get("type")
            })

    enemy_maps = []
    for _, row in enemies.iterrows():
        for m in row["relatedMaps_parsed"]:
            enemy_maps.append({
                "enemy_id": row["id"],
                "map_id": m.get("id"),
                "map_name": m.get("name")
            })

    return enemy_basic, pd.DataFrame(enemy_drops), pd.DataFrame(enemy_maps)

def normalize_items(items):
    items_basic = items[["id", "name", "rarity", "type", "value", "weight", "stackSize", "image", "icon"]].copy()
    return items_basic

def normalize_quests(quests):
    quests["maps_parsed"] = parse_json_column(quests["maps"])
    quests_basic = quests[["id", "title", "trader", "xpReward", "description", "image"]].copy()

    quest_maps = []
    for _, row in quests.iterrows():
        for m in row["maps_parsed"]:
            quest_maps.append({
                "quest_id": row["id"],
                "map_id": m.get("id"),
                "map_name": m.get("name")
            })

    return quests_basic, pd.DataFrame(quest_maps)

def extract_all_maps(enemies, quests):
    """Build the unique map catalog from enemy and quest JSON columns."""
    maps_set = {}
    for column in (enemies["relatedMaps"], quests["maps"]):
        for parsed_list in parse_json_column(column):
            for m in parsed_list:
                if isinstance(m, dict) and m.get("id"):
                    maps_set[m["id"]] = m.get("name")
    return pd.DataFrame([{"id": k, "name": v} for k, v in maps_set.items()])


def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    DB_PATH.unlink(missing_ok=True)

    enemies, items, quests = load_raw_data()

    enemy_basic, enemy_drops, enemy_maps = normalize_enemies(enemies)
    items_basic = normalize_items(items)
    quests_basic, quest_maps = normalize_quests(quests)
    maps = extract_all_maps(enemies, quests)

    conn = sqlite3.connect(DB_PATH)

    enemy_basic.to_sql("enemies", conn, index=False)
    enemy_drops.to_sql("enemy_drops", conn, index=False)
    enemy_maps.to_sql("enemy_maps", conn, index=False)
    items_basic.to_sql("items", conn, index=False)
    quests_basic.to_sql("quests", conn, index=False)
    quest_maps.to_sql("quest_maps", conn, index=False)
    maps.to_sql("maps", conn, index=False)

    conn.close()

    print(f"Base de datos creada: {DB_PATH}")
    print(f"  enemies:      {len(enemy_basic)} filas")
    print(f"  enemy_drops:  {len(enemy_drops)} filas")
    print(f"  enemy_maps:   {len(enemy_maps)} filas")
    print(f"  items:        {len(items_basic)} filas")
    print(f"  quests:       {len(quests_basic)} filas")
    print(f"  quest_maps:   {len(quest_maps)} filas")
    print(f"  maps:         {len(maps)} filas")

if __name__ == "__main__":
    main()
