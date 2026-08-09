"""
Módulo de Seleção de Filmes (VPS Production Function)

Contém a função principal para buscar e selecionar o próximo filme em alta
que ainda não foi postado no YouTube.
"""

import logging
import re
import os
import json
from src.database import init_db, is_movie_posted, add_movie
from src.tmdb_client import get_trending_movies, get_movie_details

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def generate_movie_slug(title: str, release_date: str = "") -> str:
    """Gera um slug amigável para o título (ex: homem_aranha_2026)."""
    year = ""
    if release_date and len(release_date) >= 4:
        year = release_date[:4]
    
    # Remove acentos e caracteres especiais
    clean_title = re.sub(r'[^\w\s]', '', title.lower())
    words = clean_title.split()
    slug_base = "_".join(words)
    
    if year and year not in slug_base:
        return f"{slug_base}_{year}"
    return slug_base

def save_movie_info_txt(movie_info: dict, output_dir: str = "temp") -> str:
    """Gera e salva um arquivo TXT com os metadados do filme para ser usado pelo pipeline e notebooks."""
    os.makedirs(output_dir, exist_ok=True)
    slug = movie_info["slug"]
    txt_filepath = os.path.join(output_dir, f"{slug}.txt")
    
    content = f"""TITULO: {movie_info['title']}
TITULO_ORIGINAL: {movie_info['original_title']}
SLUG: {movie_info['slug']}
TMDB_ID: {movie_info['tmdb_id']}
LANCAMENTO: {movie_info['release_date']}
DURACAO_MIN: {movie_info['runtime']}
GENEROS: {', '.join(movie_info.get('genres', []))}
SINOPSE: {movie_info['overview']}
"""
    with open(txt_filepath, "w", encoding="utf-8") as f:
        f.write(content)
        
    logging.info(f"Arquivo TXT com metadados salvo em: {txt_filepath}")
    return txt_filepath

def get_next_unposted_movie(language: str = "pt-BR", output_dir: str = "temp") -> dict | None:
    """
    Busca a lista de filmes em alta (Trending Top Today) no TMDB,
    compara com o banco SQLite e retorna o primeiro filme que ainda não foi postado.
    
    Returns:
        dict: Dicionário com os detalhes do filme selecionado e slug gerado ou None.
    """
    # 1. Garante que o banco de dados e a tabela existam
    init_db()
    
    logging.info("Buscando títulos em alta no TMDB...")
    trending_list = get_trending_movies(language=language)
    
    if not trending_list:
        logging.warning("Nenhum filme retornado da API de tendências do TMDB.")
        return None

    # 2. Percorre a lista em ordem de relevância
    for idx, item in enumerate(trending_list, 1):
        tmdb_id = item.get("id")
        title = item.get("title") or item.get("name")
        
        logging.info(f"[{idx}/{len(trending_list)}] Verificando status de '{title}' (TMDB ID: {tmdb_id})...")
        
        # 3. Ignora filmes já postados
        if is_movie_posted(tmdb_id):
            logging.info(f"-> Filme '{title}' já foi POSTADO. Pulando...")
            continue
        
        # 4. Seleciona o filme válido e busca detalhes completos
        logging.info(f"-> '{title}' selecionado como próximo candidato VÁLIDO.")
        detalhes = get_movie_details(tmdb_id, language=language)
        
        runtime = detalhes.get("runtime")
        overview = detalhes.get("overview") or item.get("overview")
        original_title = detalhes.get("original_title") or item.get("original_title")
        release_date = detalhes.get("release_date") or item.get("release_date")
        
        # Registra no banco de dados com status 'selected'
        add_movie(
            tmdb_id=tmdb_id,
            title=title,
            original_title=original_title,
            overview=overview,
            release_date=release_date,
            runtime=runtime,
            status="selected"
        )
        
        slug = generate_movie_slug(title, release_date)
        
        selected_movie = {
            "tmdb_id": tmdb_id,
            "title": title,
            "original_title": original_title,
            "slug": slug,
            "overview": overview,
            "release_date": release_date,
            "runtime": runtime,
            "poster_path": detalhes.get("poster_path"),
            "backdrop_path": detalhes.get("backdrop_path"),
            "genres": [g.get("name") for g in detalhes.get("genres", [])]
        }
        
        # Salva o arquivo TXT
        txt_path = save_movie_info_txt(selected_movie, output_dir=output_dir)
        selected_movie["txt_path"] = txt_path
        
        logging.info(f"Filme '{title}' ({runtime} min) registrado no banco. Slug: {slug}")
        return selected_movie

    logging.warning("Todos os filmes da lista de tendências do TMDB já foram postados.")
    return None

def get_movie_by_tmdb_id(tmdb_id: int, language: str = "pt-BR", output_dir: str = "temp") -> dict:
    """
    Busca os detalhes completos de um filme no TMDB pelo seu ID,
    registra/atualiza no banco SQLite com status 'selected' e salva o arquivo TXT de metadados.
    """
    init_db()
    detalhes = get_movie_details(tmdb_id, language=language)
    
    title = detalhes.get("title") or detalhes.get("name", "Filme Desconhecido")
    original_title = detalhes.get("original_title") or detalhes.get("original_name", title)
    overview = detalhes.get("overview", "")
    release_date = detalhes.get("release_date", "")
    runtime = detalhes.get("runtime")
    
    add_movie(
        tmdb_id=tmdb_id,
        title=title,
        original_title=original_title,
        overview=overview,
        release_date=release_date,
        runtime=runtime,
        status="selected"
    )
    
    slug = generate_movie_slug(title, release_date)
    
    selected_movie = {
        "tmdb_id": tmdb_id,
        "title": title,
        "original_title": original_title,
        "slug": slug,
        "overview": overview,
        "release_date": release_date,
        "runtime": runtime,
        "poster_path": detalhes.get("poster_path"),
        "backdrop_path": detalhes.get("backdrop_path"),
        "genres": [g.get("name") for g in detalhes.get("genres", [])]
    }
    
    txt_path = save_movie_info_txt(selected_movie, output_dir=output_dir)
    selected_movie["txt_path"] = txt_path
    
    logging.info(f"Filme '{title}' (ID {tmdb_id}) selecionado manualmente. Slug: {slug}")
    return selected_movie

def limpar_arquivos_locais_temporarios(dirs: list[str] = ["temp", "output"]):
    """Limpa arquivos temporários locais mantendo a estrutura das pastas intacta."""
    for d in dirs:
        if os.path.exists(d):
            for item in os.listdir(d):
                file_path = os.path.join(d, item)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        import shutil
                        shutil.rmtree(file_path)
                except Exception as e:
                    logging.warning(f"Erro ao remover arquivo temporário local '{file_path}': {e}")
            logging.info(f"Pasta temporária local '{d}' limpa com sucesso.")



