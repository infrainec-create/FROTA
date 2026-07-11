"""Migração única do banco SQLite legado para a planilha do Google Drive.

Uso: python3 migrate_sqlite_to_sheets.py frota.db
"""
from __future__ import annotations

import sqlite3
import sys
import tomllib
from pathlib import Path

from drive_repository import DriveRepository


def load_secrets() -> dict:
    with Path(".streamlit/secrets.toml").open("rb") as file:
        return tomllib.load(file)


def migrate(db_path: str) -> None:
    secrets = load_secrets()
    repo = DriveRepository(dict(secrets["gcp_service_account"]), str(secrets["google_sheet_id"]))
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    ids: dict[str, dict[int, str]] = {"vehicles": {}, "drivers": {}}

    for table, fields in {
        "vehicles": ["name", "plate", "year", "status", "created_at"],
        "drivers": ["name", "phone", "license", "license_expiry", "status", "created_at"],
    }.items():
        for row in connection.execute(f"SELECT * FROM {table}"):
            record = repo.add(table, {field: row[field] for field in fields})
            ids[table][row["id"]] = record["id"]

    for table, fields in {
        "maintenance": ["description", "cost", "maint_date", "odometer", "created_at"],
        "fuel": ["liters", "cost", "fuel_date", "odometer", "created_at"],
    }.items():
        for row in connection.execute(f"SELECT * FROM {table}"):
            values = {field: row[field] for field in fields}
            values["vehicle_id"] = ids["vehicles"][row["vehicle_id"]]
            repo.add(table, values)

    for row in connection.execute("SELECT * FROM checkins"):
        repo.add("checkins", {
            "vehicle_id": ids["vehicles"][row["vehicle_id"]],
            "driver_id": ids["drivers"][row["driver_id"]],
            "checkin_at": row["checkin_at"], "checkout_at": row["checkout_at"],
            "odometer_start": row["odometer_start"], "odometer_end": row["odometer_end"],
            "notes": row["notes"], "created_at": row["created_at"],
        })
    connection.close()
    print("Migração concluída. Confira a planilha antes de apagar o banco SQLite.")


if __name__ == "__main__":
    migrate(sys.argv[1] if len(sys.argv) > 1 else "frota.db")
