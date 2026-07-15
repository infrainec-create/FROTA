"""Persistência do FrotaControl em um banco de dados SQLite sincronizado no Google Drive."""
from __future__ import annotations

from datetime import date, datetime, timezone
import os
import json
import sqlite3
import threading
from typing import Any
from uuid import uuid4

from google.oauth2.service_account import Credentials
from google.auth.transport.requests import AuthorizedSession


TABLES: dict[str, list[str]] = {
    "users": ["id", "username", "password", "name", "security_question", "security_answer", "created_at"],
    "vehicles": ["id", "name", "plate", "year", "status", "ipva_expiry", "insurance_expiry", "created_at"],
    "drivers": ["id", "name", "phone", "license", "license_expiry", "status", "created_at"],
    "maintenance": ["id", "vehicle_id", "description", "cost", "maint_date", "odometer", "maint_type", "created_at"],
    "fuel": ["id", "vehicle_id", "liters", "cost", "fuel_date", "odometer", "created_at"],
    "checkins": ["id", "vehicle_id", "driver_id", "checkin_at", "checkout_at", "odometer_start", "odometer_end", "destination", "notes", "created_at"],
    "fines": ["id", "driver_id", "description", "amount", "fine_date", "status", "created_at"],
    "audit_log": ["id", "action", "details", "created_at"],
    "config": ["key", "value"],
}


class DriveRepository:
    """Repositório de dados que utiliza um arquivo SQLite local e sincroniza no Google Drive."""

    def __init__(self, service_account: dict[str, Any] | None, google_drive_folder_id: str | None):
        self.service_account = service_account
        self.google_drive_folder_id = google_drive_folder_id
        self.db_path = "frota_drive.db"
        self.drive_file_id = None
        self.upload_lock = threading.Lock()

        # 1. Tenta baixar o arquivo do Drive se as credenciais existirem
        self._download_from_drive()

        # 2. Garante que as tabelas SQL estão criadas localmente
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        for table, columns in TABLES.items():
            cols_def = []
            for col in columns:
                if col == "id":
                    cols_def.append("id TEXT PRIMARY KEY")
                else:
                    cols_def.append(f"{col} TEXT")
            cursor.execute(f"CREATE TABLE IF NOT EXISTS {table} ({', '.join(cols_def)})")
        conn.commit()
        conn.close()

    def _get_session(self) -> AuthorizedSession:
        scopes = ["https://www.googleapis.com/auth/drive"]
        credentials = Credentials.from_service_account_info(self.service_account, scopes=scopes)
        return AuthorizedSession(credentials)

    def _download_from_drive(self) -> None:
        if not self.service_account or not self.google_drive_folder_id:
            return

        try:
            session = self._get_session()

            # Busca se o frota.db já existe na pasta compartilhada do Drive
            q = f"name='frota.db' and '{self.google_drive_folder_id}' in parents and trashed=false"
            search_res = session.get("https://www.googleapis.com/drive/v3/files", params={"q": q, "fields": "files(id)"})
            
            if search_res.status_code == 200:
                files = search_res.json().get("files", [])
                if files:
                    self.drive_file_id = files[0]["id"]
                    # Baixa o conteúdo do arquivo
                    dl_res = session.get(f"https://www.googleapis.com/drive/v3/files/{self.drive_file_id}", params={"alt": "media"})
                    if dl_res.status_code == 200:
                        with open(self.db_path, "wb") as f:
                            f.write(dl_res.content)
        except Exception as e:
            print(f"Erro ao baixar do Drive: {e}", flush=True)

    def _upload_to_drive(self) -> None:
        if not self.service_account or not self.google_drive_folder_id:
            return

        def run_upload():
            with self.upload_lock:
                try:
                    session = self._get_session()

                    # Se não temos o ID do arquivo do Drive, tenta buscar novamente na pasta
                    if not self.drive_file_id:
                        q = f"name='frota.db' and '{self.google_drive_folder_id}' in parents and trashed=false"
                        search_res = session.get("https://www.googleapis.com/drive/v3/files", params={"q": q, "fields": "files(id)"})
                        if search_res.status_code == 200:
                            files = search_res.json().get("files", [])
                            if files:
                                self.drive_file_id = files[0]["id"]

                    if self.drive_file_id:
                        # Atualiza o arquivo existente
                        with open(self.db_path, "rb") as f:
                            session.patch(
                                f"https://www.googleapis.com/upload/drive/v3/files/{self.drive_file_id}?uploadType=media",
                                data=f.read(),
                                headers={"Content-Type": "application/x-sqlite3"}
                            )
                    else:
                        # Cria um novo arquivo dentro da pasta compartilhada do usuário
                        # (isso consome a cota de armazenamento do proprietário da pasta, não do Service Account)
                        metadata = {
                            "name": "frota.db",
                            "parents": [self.google_drive_folder_id]
                        }
                        files = {
                            "data": ("metadata", json.dumps(metadata), "application/json; charset=UTF-8"),
                            "file": ("frota.db", open(self.db_path, "rb"), "application/x-sqlite3")
                        }
                        res = session.post("https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart", files=files)
                        if res.status_code == 200:
                            self.drive_file_id = res.json().get("id")
                except Exception as e:
                    print(f"Erro ao subir para o Drive: {e}", flush=True)

        threading.Thread(target=run_upload, daemon=True).start()

    def list(self, table: str) -> list[dict[str, Any]]:
        self._validate_table(table)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {table}")
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def add(self, table: str, values: dict[str, Any]) -> dict[str, Any]:
        self._validate_table(table)
        record = {
            "id": str(uuid4()),
            "created_at": datetime.now(timezone.utc).isoformat(),
            **{k: self._serialize(v) for k, v in values.items()},
        }
        
        headers = TABLES[table]
        for h in headers:
            if h not in record:
                record[h] = ""

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        placeholders = ", ".join(["?"] * len(headers))
        columns_str = ", ".join(headers)
        values_list = [record[h] for h in headers]
        
        cursor.execute(f"INSERT INTO {table} ({columns_str}) VALUES ({placeholders})", values_list)
        conn.commit()
        conn.close()
        
        self._upload_to_drive()
        return record

    def update(self, table: str, record_id: str, values: dict[str, Any]) -> None:
        self._validate_table(table)
        serialized_values = {k: self._serialize(v) for k, v in values.items()}
        set_clause = ", ".join([f"{k} = ?" for k in serialized_values.keys()])
        bind_values = list(serialized_values.values()) + [str(record_id)]
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(f"UPDATE {table} SET {set_clause} WHERE id = ?", bind_values)
        conn.commit()
        conn.close()
        
        self._upload_to_drive()

    def delete(self, table: str, record_id: str) -> None:
        self._validate_table(table)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM {table} WHERE id = ?", (str(record_id),))
        conn.commit()
        conn.close()
        
        self._upload_to_drive()

    def clear_all_data(self) -> None:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        for table in TABLES.keys():
            cursor.execute(f"DELETE FROM {table}")
        conn.commit()
        conn.close()
        self._upload_to_drive()

    def get_config(self, key: str, default: Any = None) -> str:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT value FROM config WHERE key = ?", (key,))
            row = cursor.fetchone()
            val = row[0] if row else default
        except sqlite3.OperationalError:
            val = default
        conn.close()
        return val

    def set_config(self, key: str, value: Any) -> None:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, str(value)))
        conn.commit()
        conn.close()
        self._upload_to_drive()

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
