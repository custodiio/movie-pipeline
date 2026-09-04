"""
Database Manager para Movie-Pipeline — Neon.tech PostgreSQL com fallback SQLite.
"""

import os
import sqlite3
import logging
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "database.db")


def _get_pg_conn():
    """Retorna conexão PostgreSQL direta (para compatibilidade legada)."""
    return psycopg2.connect(DATABASE_URL)


def _get_sqlite_conn():
    """Retorna conexão SQLite direta (para compatibilidade legada)."""
    return sqlite3.connect(DB_PATH)


def _get_active_conn():
    """Tenta conexão PostgreSQL (Neon.tech). Se falhar ou exceder cota, usa SQLite local."""
    if DATABASE_URL:
        try:
            conn = psycopg2.connect(DATABASE_URL)
            return conn, "pg"
        except Exception as e:
            logging.warning(f"Aviso Neon PostgreSQL indisponível ({e}). Usando SQLite local como fallback.")
    return sqlite3.connect(DB_PATH), "sqlite"


def init_db():
    """Inicializa as tabelas de filmes e vendas se não existirem."""
    conn, db_type = _get_active_conn()
    cur = conn.cursor()
    if db_type == "pg":
        cur.execute("""
            CREATE TABLE IF NOT EXISTS movie_pipeline_movies (
                tmdb_id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                original_title TEXT,
                overview TEXT,
                release_date TEXT,
                runtime INTEGER,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                posted_at TIMESTAMPTZ
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS movie_pipeline_sales_orders (
                identifier TEXT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                user_name TEXT,
                amount REAL DEFAULT 10.0,
                status TEXT DEFAULT 'pending',
                invite_link TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                delivered_at TIMESTAMPTZ
            )
        """)
    else:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS movies (
                tmdb_id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                original_title TEXT,
                overview TEXT,
                release_date TEXT,
                runtime INTEGER,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                posted_at TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sales_orders (
                identifier TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                user_name TEXT,
                amount REAL DEFAULT 10.0,
                status TEXT DEFAULT 'pending',
                invite_link TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                delivered_at TIMESTAMP
            )
        """)
    conn.commit()
    cur.close()
    conn.close()


def is_movie_posted(tmdb_id: int) -> bool:
    """Verifica se o filme já foi registrado e marcado como 'posted' ou 'concluido'."""
    conn, db_type = _get_active_conn()
    cur = conn.cursor()
    if db_type == "pg":
        cur.execute("SELECT status FROM movie_pipeline_movies WHERE tmdb_id = %s", (tmdb_id,))
    else:
        cur.execute("SELECT status FROM movies WHERE tmdb_id = ?", (tmdb_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row and row[0] in ("posted", "concluido"):
        return True
    return False


def is_movie_in_db(tmdb_id: int) -> bool:
    """Verifica se o filme já existe no banco de dados (em qualquer status)."""
    conn, db_type = _get_active_conn()
    cur = conn.cursor()
    if db_type == "pg":
        cur.execute("SELECT 1 FROM movie_pipeline_movies WHERE tmdb_id = %s", (tmdb_id,))
    else:
        cur.execute("SELECT 1 FROM movies WHERE tmdb_id = ?", (tmdb_id,))
    exists = cur.fetchone() is not None
    cur.close()
    conn.close()
    return exists


def add_movie(tmdb_id: int, title: str, original_title: str, overview: str, release_date: str, runtime: int = None, status: str = "pending"):
    """Registra ou atualiza as informações do filme no banco de dados."""
    conn, db_type = _get_active_conn()
    cur = conn.cursor()
    if db_type == "pg":
        cur.execute("""
            INSERT INTO movie_pipeline_movies (tmdb_id, title, original_title, overview, release_date, runtime, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(tmdb_id) DO UPDATE SET
                title = EXCLUDED.title,
                overview = EXCLUDED.overview,
                runtime = EXCLUDED.runtime,
                status = EXCLUDED.status
        """, (tmdb_id, title, original_title, overview, release_date, runtime, status))
    else:
        cur.execute("""
            INSERT INTO movies (tmdb_id, title, original_title, overview, release_date, runtime, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tmdb_id) DO UPDATE SET
                title=excluded.title,
                overview=excluded.overview,
                runtime=excluded.runtime,
                status=excluded.status
        """, (tmdb_id, title, original_title, overview, release_date, runtime, status))
    conn.commit()
    cur.close()
    conn.close()


def mark_as_posted(tmdb_id: int):
    """Marca o filme como postado no YouTube."""
    conn, db_type = _get_active_conn()
    cur = conn.cursor()
    if db_type == "pg":
        cur.execute("""
            UPDATE movie_pipeline_movies 
            SET status = 'posted', posted_at = NOW() 
            WHERE tmdb_id = %s
        """, (tmdb_id,))
    else:
        cur.execute("""
            UPDATE movies 
            SET status = 'posted', posted_at = CURRENT_TIMESTAMP 
            WHERE tmdb_id = ?
        """, (tmdb_id,))
    conn.commit()
    cur.close()
    conn.close()


def update_movie_status(tmdb_id: int, status: str):
    """Atualiza o status de um filme no banco de dados."""
    conn, db_type = _get_active_conn()
    cur = conn.cursor()
    if db_type == "pg":
        cur.execute("""
            UPDATE movie_pipeline_movies 
            SET status = %s 
            WHERE tmdb_id = %s
        """, (status, tmdb_id))
    else:
        cur.execute("""
            UPDATE movies 
            SET status = ? 
            WHERE tmdb_id = ?
        """, (status, tmdb_id))
    conn.commit()
    cur.close()
    conn.close()


def record_sales_order(identifier: str, user_id: int, user_name: str, amount: float = 10.0, status: str = "completed", invite_link: str = None):
    """Registra ou atualiza um pedido de venda e o link de convite único gerado."""
    conn, db_type = _get_active_conn()
    cur = conn.cursor()
    if db_type == "pg":
        cur.execute("""
            INSERT INTO movie_pipeline_sales_orders (identifier, user_id, user_name, amount, status, invite_link, delivered_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (identifier) DO UPDATE SET
                status = EXCLUDED.status,
                invite_link = EXCLUDED.invite_link,
                delivered_at = NOW()
        """, (identifier, user_id, user_name, amount, status, invite_link))
    else:
        cur.execute("""
            INSERT INTO sales_orders (identifier, user_id, user_name, amount, status, invite_link, delivered_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT (identifier) DO UPDATE SET
                status = excluded.status,
                invite_link = excluded.invite_link,
                delivered_at = CURRENT_TIMESTAMP
        """, (identifier, user_id, user_name, amount, status, invite_link))
    conn.commit()
    cur.close()
    conn.close()


def is_order_delivered(identifier: str) -> bool:
    """Verifica se o pedido já teve seu link de convite exclusivo entregue."""
    if not identifier:
        return False
    conn, db_type = _get_active_conn()
    cur = conn.cursor()
    if db_type == "pg":
        cur.execute("SELECT status, invite_link FROM movie_pipeline_sales_orders WHERE identifier = %s", (identifier,))
    else:
        cur.execute("SELECT status, invite_link FROM sales_orders WHERE identifier = ?", (identifier,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row and row[0] in ("completed", "paid") and row[1]:
        return True
    return False


def get_sales_order(identifier: str) -> dict:
    """Retorna os dados do pedido de venda."""
    if not identifier:
        return {}
    conn, db_type = _get_active_conn()
    cur = conn.cursor()
    if db_type == "pg":
        cur.execute("SELECT identifier, user_id, user_name, amount, status, invite_link FROM movie_pipeline_sales_orders WHERE identifier = %s", (identifier,))
    else:
        cur.execute("SELECT identifier, user_id, user_name, amount, status, invite_link FROM sales_orders WHERE identifier = ?", (identifier,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row:
        return {
            "identifier": row[0],
            "user_id": row[1],
            "user_name": row[2],
            "amount": row[3],
            "status": row[4],
            "invite_link": row[5]
        }
    return {}


def get_recent_movies_for_upload(limit: int = 5):
    """Busca filmes recentes prontos para upload no banco de dados ativo (PostgreSQL com fallback SQLite)."""
    conn, db_type = _get_active_conn()
    cur = conn.cursor()
    if db_type == "pg":
        cur.execute("SELECT tmdb_id, title, status FROM movie_pipeline_movies WHERE status IN ('concluido', 'selected', 'pending') ORDER BY tmdb_id DESC LIMIT %s", (limit,))
    else:
        cur.execute("SELECT tmdb_id, title, status FROM movies WHERE status IN ('concluido', 'selected', 'pending') ORDER BY tmdb_id DESC LIMIT ?", (limit,))
    movies = cur.fetchall()
    cur.close()
    conn.close()
    return movies
