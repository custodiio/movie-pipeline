"""
Database Manager para Movie-Pipeline — Neon.tech PostgreSQL com fallback SQLite.
"""

import os
import sqlite3
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "database.db")


def _get_pg_conn():
    return psycopg2.connect(DATABASE_URL)


def _get_sqlite_conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    """Inicializa a tabela de filmes se não existir."""
    if DATABASE_URL:
        conn = _get_pg_conn()
        cur = conn.cursor()
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
        conn.commit()
        cur.close()
        conn.close()
    else:
        conn = _get_sqlite_conn()
        cur = conn.cursor()
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
        conn.commit()
        cur.close()
        conn.close()


def is_movie_posted(tmdb_id: int) -> bool:
    """Verifica se o filme já foi registrado e marcado como 'posted' ou 'concluido'."""
    if DATABASE_URL:
        conn = _get_pg_conn()
        cur = conn.cursor()
        cur.execute("SELECT status FROM movie_pipeline_movies WHERE tmdb_id = %s", (tmdb_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row and row[0] in ("posted", "concluido"):
            return True
        return False
    else:
        conn = _get_sqlite_conn()
        cur = conn.cursor()
        cur.execute("SELECT status FROM movies WHERE tmdb_id = ?", (tmdb_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row and row[0] in ("posted", "concluido"):
            return True
        return False


def is_movie_in_db(tmdb_id: int) -> bool:
    """Verifica se o filme já existe no banco de dados (em qualquer status)."""
    if DATABASE_URL:
        conn = _get_pg_conn()
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM movie_pipeline_movies WHERE tmdb_id = %s", (tmdb_id,))
        exists = cur.fetchone() is not None
        cur.close()
        conn.close()
        return exists
    else:
        conn = _get_sqlite_conn()
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM movies WHERE tmdb_id = ?", (tmdb_id,))
        exists = cur.fetchone() is not None
        cur.close()
        conn.close()
        return exists


def add_movie(tmdb_id: int, title: str, original_title: str, overview: str, release_date: str, runtime: int = None, status: str = "pending"):
    """Registra ou atualiza as informações do filme no banco de dados."""
    if DATABASE_URL:
        conn = _get_pg_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO movie_pipeline_movies (tmdb_id, title, original_title, overview, release_date, runtime, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(tmdb_id) DO UPDATE SET
                title = EXCLUDED.title,
                overview = EXCLUDED.overview,
                runtime = EXCLUDED.runtime,
                status = EXCLUDED.status
        """, (tmdb_id, title, original_title, overview, release_date, runtime, status))
        conn.commit()
        cur.close()
        conn.close()
    else:
        conn = _get_sqlite_conn()
        cur = conn.cursor()
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
    if DATABASE_URL:
        conn = _get_pg_conn()
        cur = conn.cursor()
        cur.execute("""
            UPDATE movie_pipeline_movies 
            SET status = 'posted', posted_at = NOW() 
            WHERE tmdb_id = %s
        """, (tmdb_id,))
        conn.commit()
        cur.close()
        conn.close()
    else:
        conn = _get_sqlite_conn()
        cur = conn.cursor()
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
    if DATABASE_URL:
        conn = _get_pg_conn()
        cur = conn.cursor()
        cur.execute("""
            UPDATE movie_pipeline_movies 
            SET status = %s 
            WHERE tmdb_id = %s
        """, (status, tmdb_id))
        conn.commit()
        cur.close()
        conn.close()
    else:
        conn = _get_sqlite_conn()
        cur = conn.cursor()
        cur.execute("""
            UPDATE movies 
            SET status = ? 
            WHERE tmdb_id = ?
        """, (status, tmdb_id))
        conn.commit()
        cur.close()
        conn.close()
