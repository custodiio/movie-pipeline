import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "database.db")

def get_connection():
    return sqlite3.connect(DB_PATH)

def init_db():
    """Inicializa a tabela de filmes se não existir."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
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

def is_movie_posted(tmdb_id: int) -> bool:
    """Verifica se o filme já foi registrado e marcado como 'posted' no banco de dados."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM movies WHERE tmdb_id = ?", (tmdb_id,))
        row = cursor.fetchone()
        if row and row[0] == "posted":
            return True
        return False

def is_movie_in_db(tmdb_id: int) -> bool:
    """Verifica se o filme já existe no banco de dados (em qualquer status)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM movies WHERE tmdb_id = ?", (tmdb_id,))
        return cursor.fetchone() is not None

def add_movie(tmdb_id: int, title: str, original_title: str, overview: str, release_date: str, runtime: int = None, status: str = "pending"):
    """Registra ou atualiza as informações do filme no banco de dados."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO movies (tmdb_id, title, original_title, overview, release_date, runtime, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tmdb_id) DO UPDATE SET
                title=excluded.title,
                overview=excluded.overview,
                runtime=excluded.runtime,
                status=excluded.status
        """, (tmdb_id, title, original_title, overview, release_date, runtime, status))
        conn.commit()

def mark_as_posted(tmdb_id: int):
    """Marca o filme como postado no YouTube."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE movies 
            SET status = 'posted', posted_at = CURRENT_TIMESTAMP 
            WHERE tmdb_id = ?
        """, (tmdb_id,))
        conn.commit()
