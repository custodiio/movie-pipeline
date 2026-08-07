"""
Módulo de Download e Filtragem de Imagens (TMDB + Fallback Scraper)

Garante o download de 30 a 150 imagens de alta qualidade filtradas exclusivamente por
proporção de aspecto horizontal (16:9 ou no mínimo 1:1), descartando verticais (9:16, 3:4).
"""

import os
import requests
import logging
from io import BytesIO
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE_URL = "https://image.tmdb.org/t/p/original"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def is_valid_aspect_ratio(width: int, height: int) -> bool:
    """
    Valida se a imagem atende aos critérios de proporção:
    Retorna True se aspect_ratio (width/height) >= 1.0 (16:9 ou 1:1).
    Retorna False para formatos verticais (9:16, 3:4).
    """
    if not width or not height:
        return False
    aspect_ratio = width / height
    return aspect_ratio >= 0.95  # Tolerância para formatos 1:1 ou superiores (16:9)

def download_and_verify_image(url: str, save_path: str) -> bool:
    """Baixa a imagem da URL, verifica se é válida e se respeita o aspecto 16:9 ou 1:1."""
    try:
        response = requests.get(url, timeout=12)
        if response.status_code == 200:
            img = Image.open(BytesIO(response.content))
            width, height = img.size
            if is_valid_aspect_ratio(width, height):
                img.convert("RGB").save(save_path, "JPEG")
                return True
            else:
                logging.debug(f"Descartada imagem vertical ({width}x{height}) de {url}")
    except Exception as e:
        logging.debug(f"Erro ao baixar/verificar imagem {url}: {e}")
    return False

def fetch_tmdb_images(tmdb_id: int) -> list[str]:
    """Busca URLs de backdrops, stills e imagens de elenco no TMDB."""
    if not TMDB_API_KEY:
        logging.error("TMDB_API_KEY não configurada.")
        return []

    image_urls = []
    
    # 1. Backdrops e Stills do filme
    try:
        url = f"{BASE_URL}/movie/{tmdb_id}/images"
        params = {"api_key": TMDB_API_KEY}
        res = requests.get(url, params=params, timeout=10)
        if res.status_code == 200:
            data = res.json()
            for bg in data.get("backdrops", []):
                w = bg.get("width", 0)
                h = bg.get("height", 0)
                if is_valid_aspect_ratio(w, h):
                    image_urls.append(f"{IMAGE_BASE_URL}{bg['file_path']}")
            for st in data.get("stills", []):
                w = st.get("width", 0)
                h = st.get("height", 0)
                if is_valid_aspect_ratio(w, h):
                    image_urls.append(f"{IMAGE_BASE_URL}{st['file_path']}")
    except Exception as e:
        logging.error(f"Erro ao buscar imagens de fundo no TMDB: {e}")

    # 2. Imagens de elenco/créditos (Cast profile photos)
    try:
        url = f"{BASE_URL}/movie/{tmdb_id}/credits"
        params = {"api_key": TMDB_API_KEY}
        res = requests.get(url, params=params, timeout=10)
        if res.status_code == 200:
            data = res.json()
            for cast in data.get("cast", [])[:15]:
                profile = cast.get("profile_path")
                if profile:
                    image_urls.append(f"{IMAGE_BASE_URL}{profile}")
    except Exception as e:
        logging.error(f"Erro ao buscar créditos no TMDB: {e}")

    return list(dict.fromkeys(image_urls))

def fallback_image_scraper(movie_title: str, target_count: int) -> list[str]:
    """Fallback para buscar imagens horizontais em motores de busca (DuckDuckGo/Bing HTML scraper)."""
    urls = []
    try:
        query = f"{movie_title} movie wallpaper 16:9 HD"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        ddg_url = f"https://html.duckduckgo.com/html/?q={requests.utils.quote(query)}"
        res = requests.get(ddg_url, headers=headers, timeout=10)
        if res.status_code == 200:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(res.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "uddg=" in href and (".jpg" in href or ".png" in href or ".jpeg" in href):
                    import urllib.parse
                    parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                    if "uddg" in parsed:
                        urls.append(parsed["uddg"][0])
    except Exception as e:
        logging.warning(f"Fallback scraper encontrou falha: {e}")
    return list(dict.fromkeys(urls))

def download_images_for_movie(movie_info: dict, output_dir: str = "temp", min_images: int = 30, max_images: int = 150) -> list[str]:
    """
    Busca e salva de 30 a 150 imagens 16:9/1:1 do filme na pasta local.
    
    Returns:
        list[str]: Caminhos locais das imagens salvas.
    """
    slug = movie_info.get("slug", "filme")
    title = movie_info.get("title", slug)
    tmdb_id = movie_info.get("tmdb_id")
    
    images_dir = os.path.join(output_dir, slug, "imagens")
    os.makedirs(images_dir, exist_ok=True)

    logging.info(f"Iniciando download de imagens para '{title}' (Mínimo: {min_images}, Máximo: {max_images})...")

    downloaded_files = []
    
    # 1. Coleta URLs do TMDB
    tmdb_urls = fetch_tmdb_images(tmdb_id) if tmdb_id else []
    logging.info(f"Encontradas {len(tmdb_urls)} URLs candidatas no TMDB.")

    count = 0
    for idx, url in enumerate(tmdb_urls):
        if count >= max_images:
            break
        filename = f"img_{count+1:03d}.jpg"
        save_path = os.path.join(images_dir, filename)
        if download_and_verify_image(url, save_path):
            downloaded_files.append(save_path)
            count += 1
            logging.info(f"[{count}/{max_images}] Imagem TMDB salva: {filename}")

    # 2. Se não atingiu o mínimo de 30, dispara o fallback scraper
    if count < min_images:
        logging.info(f"Contagem atual ({count}) abaixo do mínimo ({min_images}). Acionando scraper de fallback...")
        needed = min_images - count
        fallback_urls = fallback_image_scraper(title, needed * 2)
        
        for url in fallback_urls:
            if count >= min_images and count >= max_images:
                break
            filename = f"img_{count+1:03d}.jpg"
            save_path = os.path.join(images_dir, filename)
            if download_and_verify_image(url, save_path):
                downloaded_files.append(save_path)
                count += 1
                logging.info(f"[{count}/{max_images}] Imagem Fallback salva: {filename}")

    logging.info(f"Total de {len(downloaded_files)} imagens horizontais (16:9 / 1:1) baixadas e salvas em {images_dir}.")
    return downloaded_files
