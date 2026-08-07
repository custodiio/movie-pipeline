import os
import requests
from dotenv import load_dotenv

# Carrega variáveis de ambiente do .env
load_dotenv()

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
BASE_URL = "https://api.themoviedb.org/3"

def get_headers():
    return {
        "accept": "application/json"
    }

def get_trending_movies(language="pt-BR"):
    """Busca os filmes em alta (Trending Top Today) no TMDB."""
    if not TMDB_API_KEY:
        raise ValueError("TMDB_API_KEY não encontrada no arquivo .env")
        
    url = f"{BASE_URL}/trending/movie/day"
    params = {
        "api_key": TMDB_API_KEY,
        "language": language
    }
    
    response = requests.get(url, headers=get_headers(), params=params)
    response.raise_for_status()
    data = response.json()
    return data.get("results", [])

def get_movie_details(movie_id: int, language="pt-BR"):
    """Obtém detalhes completos de um filme específico (incluindo runtime)."""
    if not TMDB_API_KEY:
        raise ValueError("TMDB_API_KEY não encontrada no arquivo .env")
        
    url = f"{BASE_URL}/movie/{movie_id}"
    params = {
        "api_key": TMDB_API_KEY,
        "language": language
    }
    
    response = requests.get(url, headers=get_headers(), params=params)
    response.raise_for_status()
    return response.json()
