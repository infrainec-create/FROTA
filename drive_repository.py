"""Persistência do FrotaControl em uma planilha Google Sheets no Google Drive."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

import gspread
from google.oauth2.service_account import Credentials


TABLES: dict[str, list[str]] = {
    "vehicles": ["id", "name", "plate", "year", "status", "created_at"],
    "drivers": ["id", "name", "phone", "license", "license_expiry", "status", "created_at"],
    "maintenance": ["id", "vehicle_id", "description", "cost", "maint_date", "odometer", "created_at"],
    "fuel": ["id", "vehicle_id", "liters", "cost", "fuel_date", "odometer", "created_at"],
    "checkins": ["id", "vehicle_id", "driver_id", "checkin_at", "checkout_at", "odometer_start", "odometer_end", "notes", "created_at"],
    "fines": ["id", "driver_id", "description", "amount", "fine_date", "status", "created_at"],
}


class DriveRepository:
    """Pequeno repositório para uma planilha privada compartilhada com a conta de serviço."""

    def __init__(self, service_account: dict[str, Any], spreadsheet_id: str):
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.file",
        ]
        credentials = Credentials.from_service_account_info(service_account, scopes=scopes)
        self.sheet = gspread.authorize(credentials).open_by_key(spreadsheet_id)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        existing = {worksheet.title: worksheet for worksheet in self.sheet.worksheets()}
        for table, headers in TABLES.items():
            worksheet = existing.get(table)
            if worksheet is None:
                worksheet = self.sheet.add_worksheet(title=table, rows=1000, cols=len(headers))
            if worksheet.row_values(1) != headers:
                worksheet.update([headers], "A1")

    def list(self, table: str) -> list[dict[str, Any]]:
        self._validate_table(table)
        return [row for row in self.sheet.worksheet(table).get_all_records() if row.get("id")]

    def add(self, table: str, values: dict[str, Any]) -> dict[str, Any]:
        self._validate_table(table)
        record = {
            "id": str(uuid4()),
            "created_at": datetime.now(timezone.utc).isoformat(),
            **values,
        }
        headers = TABLES[table]
        self.sheet.worksheet(table).append_row([self._serialize(record.get(header, "")) for header in headers])
        return record

    def update(self, table: str, record_id: str, values: dict[str, Any]) -> None:
        self._validate_table(table)
        worksheet = self.sheet.worksheet(table)
        records = worksheet.get_all_records()
        for index, record in enumerate(records, start=2):
            if str(record.get("id")) == str(record_id):
                record.update(values)
                worksheet.update([[self._serialize(record.get(header, "")) for header in TABLES[table]]], f"A{index}")
                return
        raise KeyError(f"Registro {record_id} não encontrado em {table}.")

    @staticmethod
    def _serialize(value: Any) -> str | int | float:
        if value is None:
            return ""
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        return value

    @staticmethod
    def _validate_table(table: str) -> None:
        if table not in TABLES:
            raise ValueError("Tabela inválida.")


class LocalJsonRepository:
    """Repositório local em arquivo JSON para testes sem credenciais do Google Drive."""

    def __init__(self, filepath: str = "local_db.json"):
        self.filepath = filepath
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        import os
        import json
        if not os.path.exists(self.filepath):
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump({table: [] for table in TABLES}, f, indent=2)

    def _load(self) -> dict[str, list[dict[str, Any]]]:
        import json
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {table: [] for table in TABLES}

    def _save(self, data: dict[str, list[dict[str, Any]]]) -> None:
        import json
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def list(self, table: str) -> list[dict[str, Any]]:
        self._validate_table(table)
        return self._load().get(table, [])

    def add(self, table: str, values: dict[str, Any]) -> dict[str, Any]:
        self._validate_table(table)
        data = self._load()
        record = {
            "id": str(uuid4()),
            "created_at": datetime.now(timezone.utc).isoformat(),
            **{k: self._serialize(v) for k, v in values.items()},
        }
        data.setdefault(table, []).append(record)
        self._save(data)
        return record

    def update(self, table: str, record_id: str, values: dict[str, Any]) -> None:
        self._validate_table(table)
        data = self._load()
        records = data.get(table, [])
        for record in records:
            if str(record.get("id")) == str(record_id):
                record.update({k: self._serialize(v) for k, v in values.items()})
                self._save(data)
                return
        raise KeyError(f"Registro {record_id} não encontrado em {table}.")

    @staticmethod
    def _serialize(value: Any) -> str | int | float:
        if value is None:
            return ""
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        return value

    @staticmethod
    def _validate_table(table: str) -> None:
        if table not in TABLES:
            raise ValueError("Tabela inválida.")

