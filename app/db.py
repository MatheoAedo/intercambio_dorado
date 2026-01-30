import os
import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

if not os.getenv("DATABASE_URL"):
    load_dotenv()

def _normalize_database_url(url: str) -> str:
    """
    Render Postgres suele requerir SSL.
    Si la URL no trae ?sslmode=..., se lo agregamos.
    """
    if not url:
        return url
    if "sslmode=" in url:
        return url
    sep = "&" if "?" in url else "?"
    return url + f"{sep}sslmode=require"

def get_conn():
    """
    Prioridad:
    1) DATABASE_URL (Render)
    2) Variables locales (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD)
    """
    database_url = os.getenv("DATABASE_URL")

    if database_url:
        database_url = database_url.strip()

        if database_url.lower().startswith("database_url="):
            database_url = database_url.split("=", 1)[1].strip()

        database_url = _normalize_database_url(database_url)

        return psycopg.connect(database_url, row_factory=dict_row)

    # ---- Local ----
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    dbname = os.getenv("DB_NAME", "intercambio_dorado")
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "")

    return psycopg.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password,
        row_factory=dict_row
    )

def query_one(sql: str, params=None):
    """SELECT -> 1 fila (dict) o None."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchone()

def query_all(sql: str, params=None):
    """SELECT -> lista de filas (dict)."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchall() or []

def execute(sql: str, params=None):
    """INSERT/UPDATE/DELETE -> rowcount."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            conn.commit()
            return cur.rowcount
