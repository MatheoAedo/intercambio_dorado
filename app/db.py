import os
from dotenv import load_dotenv
import psycopg
from psycopg.rows import dict_row

load_dotenv()

def get_conn():
    """
    Conecta a PostgreSQL.
    - En local usa variables DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
    - En Render usa DATABASE_URL automáticamente si existe
    """

    database_url = os.getenv("DATABASE_URL")

    if database_url:
        # Render (o cualquier hosting que entregue DATABASE_URL)
        return psycopg.connect(database_url, row_factory=dict_row)

    # Local (pgAdmin)
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


def query_one(sql, params=None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchone()


def query_all(sql, params=None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()


def execute(sql, params=None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            conn.commit()
