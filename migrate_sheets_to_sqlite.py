"""Script utilitário para migrar dados das abas do Google Sheets para o novo banco de dados SQLite."""
import tomllib
import sqlite3
import gspread
from google.oauth2.service_account import Credentials
from drive_repository import TABLES


def migrate():
    try:
        with open(".streamlit/secrets.toml", "rb") as file:
            secrets = tomllib.load(file)
    except FileNotFoundError:
        print("Arquivo .streamlit/secrets.toml não encontrado.")
        return

    account = secrets.get("gcp_service_account")
    spreadsheet_id = secrets.get("google_sheet_id")
    if not account or not spreadsheet_id:
        print("Credenciais do Google Sheets ou ID da planilha não encontrados nos segredos.")
        return

    print("Conectando ao Google Sheets...")
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = Credentials.from_service_account_info(account, scopes=scopes)
    gc = gspread.authorize(credentials)
    sheet = gc.open_by_key(spreadsheet_id)

    db_path = "frota_drive.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Criação das tabelas
    for table, columns in TABLES.items():
        cols_def = []
        for col in columns:
            if col == "id":
                cols_def.append("id TEXT PRIMARY KEY")
            else:
                cols_def.append(f"{col} TEXT")
        cursor.execute(f"CREATE TABLE IF NOT EXISTS {table} ({', '.join(cols_def)})")
    conn.commit()

    # Ler dados das abas e escrever no SQLite
    for table, columns in TABLES.items():
        try:
            worksheet = sheet.worksheet(table)
            records = [r for r in worksheet.get_all_records() if r.get("id")]
            if not records:
                print(f"Tabela {table}: Sem registros para migrar.")
                continue

            # Limpa tabela local antes da inserção
            cursor.execute(f"DELETE FROM {table}")

            placeholders = ", ".join(["?"] * len(columns))
            columns_str = ", ".join(columns)

            for r in records:
                values = [r.get(c, "") for c in columns]
                cursor.execute(f"INSERT INTO {table} ({columns_str}) VALUES ({placeholders})", values)
            print(f"Tabela {table}: {len(records)} registros migrados para SQLite local.")
        except Exception as e:
            print(f"Tabela {table}: Não migrada ou erro: {e}")

    conn.commit()
    conn.close()

    # Upload do banco de dados atualizado para o Drive
    print("Enviando arquivo frota.db para a pasta do Google Drive...")
    from drive_repository import DriveRepository
    repo = DriveRepository(account, spreadsheet_id)
    repo._upload_to_drive()
    print("Migração concluída com sucesso! Banco SQLite sincronizado no Google Drive.")


if __name__ == "__main__":
    migrate()
