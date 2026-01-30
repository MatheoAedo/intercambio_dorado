import os
from urllib.parse import urlparse, urlunparse

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

if os.getenv("RENDER") is None:
    load_dotenv()


def _ensure_port_in_url(database_url: str) -> str:
    """
    Render a veces entrega URLs sin puerto explícito.
    PostgreSQL normalmente usa 5432, así que lo agregamos si falta.
    """
    try:
        p = urlparse(database_url)
        if not p.scheme or not p.hostname:
            return database_url

        if p.port:
            return database_url

        netloc = p.netloc
        if "@" in netloc:
            creds, host = netloc.split("@", 1)
            netloc = f"{creds}@{host}:5432"
        else:
            netloc = f"{netloc}:5432"

        return urlunparse((p.scheme, netloc, p.path, p.params, p.query, p.fragment))
    except Exception:
        return database_url


def get_conn():
    """
    Crea y retorna una conexión a PostgreSQL.

    Prioridad:
    1) DATABASE_URL (Render / producción)
    2) Variables locales (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD)
    """
    database_url = os.getenv("DATABASE_URL")

    if database_url:
        database_url = _ensure_port_in_url(database_url)

        sslmode = os.getenv("DB_SSLMODE", "require")

        return psycopg.connect(
            database_url,
            row_factory=dict_row,
            sslmode=sslmode
        )

    # ----------------------------
    # Local
    # ----------------------------
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
    """Ejecuta SELECT y devuelve 1 fila como dict, o None."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchone()


def query_all(sql: str, params=None):
    """Ejecuta SELECT y devuelve lista de filas como dict."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            rows = cur.fetchall()
            return rows or []


def execute(sql: str, params=None):
    """Ejecuta INSERT/UPDATE/DELETE y retorna rowcount."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            conn.commit()
            return cur.rowcount
