"""
Módulo de Geração e Composição de Thumbnails (Capas 16:9 HD)
TMDB Backdrops & Logos + Composição Personalizada via Pillow (PIL)
"""

import os
import logging
import requests
from io import BytesIO
from PIL import Image
from src.tmdb_client import TMDB_API_KEY, BASE_URL, get_headers

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def get_movie_images_tmdb(movie_id: int) -> dict:
    """
    Busca backdrops e logos transparentes de um filme na API do TMDB.
    """
    if not TMDB_API_KEY:
        raise ValueError("TMDB_API_KEY não encontrada no arquivo .env")

    url = f"{BASE_URL}/movie/{movie_id}/images"
    params = {
        "api_key": TMDB_API_KEY,
        "include_image_language": "pt,en,null"
    }

    res = requests.get(url, headers=get_headers(), params=params, timeout=15)
    res.raise_for_status()
    data = res.json()

    backdrops = data.get("backdrops", [])
    logos = data.get("logos", [])

    return {
        "backdrops": [f"https://image.tmdb.org/t/p/original{b['file_path']}" for b in backdrops if b.get("file_path")],
        "logos": [f"https://image.tmdb.org/t/p/original{l['file_path']}" for l in logos if l.get("file_path")]
    }

def compose_thumbnail(
    bg_image_path_or_url: str,
    logo_image_path_or_url: str = None,
    logo_scale_pct: float = 0.25,
    logo_position: str = "bottom_right",
    output_path: str = "temp/thumbnail.png"
) -> str:
    """
    Compõe uma Thumbnail 16:9 no tamanho oficial do YouTube (1280x720),
    aplicando a imagem de fundo e sobrepondo a logo transparente na posição e escala escolhidas.

    Posições suportadas (Grid de 9 posições):
    - top_left, top_center, top_right
    - middle_left, middle_center, middle_right
    - bottom_left, bottom_center, bottom_right
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    canvas_w, canvas_h = 1280, 720

    # 1. Carrega Fundo
    if bg_image_path_or_url.startswith("http://") or bg_image_path_or_url.startswith("https://"):
        resp = requests.get(bg_image_path_or_url, timeout=15)
        bg = Image.open(BytesIO(resp.content)).convert("RGBA")
    else:
        bg = Image.open(bg_image_path_or_url).convert("RGBA")

    # Redimensiona mantendo aspecto e preenchendo 1280x720 (Crop/Resize centralizado)
    bg_ratio = bg.width / bg.height
    target_ratio = canvas_w / canvas_h

    if bg_ratio > target_ratio:
        new_h = canvas_h
        new_w = int(new_h * bg_ratio)
    else:
        new_w = canvas_w
        new_h = int(new_w / bg_ratio)

    bg_resized = bg.resize((new_w, new_h), Image.Resampling.LANCZOS)
    
    left = (new_w - canvas_w) // 2
    top = (new_h - canvas_h) // 2
    canvas = bg_resized.crop((left, top, left + canvas_w, top + canvas_h))

    # 2. Se houver logo, redimensiona e cola na posição escolhida
    if logo_image_path_or_url:
        try:
            if logo_image_path_or_url.startswith("http://") or logo_image_path_or_url.startswith("https://"):
                r_logo = requests.get(logo_image_path_or_url, timeout=15)
                logo = Image.open(BytesIO(r_logo.content)).convert("RGBA")
            else:
                logo = Image.open(logo_image_path_or_url).convert("RGBA")

            target_logo_w = int(canvas_w * logo_scale_pct)
            logo_ratio = logo.height / logo.width
            target_logo_h = int(target_logo_w * logo_ratio)

            logo_resized = logo.resize((target_logo_w, target_logo_h), Image.Resampling.LANCZOS)

            margin = 40
            lw, lh = target_logo_w, target_logo_h

            pos_map = {
                "top_left": (margin, margin),
                "top_center": ((canvas_w - lw) // 2, margin),
                "top_right": (canvas_w - lw - margin, margin),
                "middle_left": (margin, (canvas_h - lh) // 2),
                "middle_center": ((canvas_w - lw) // 2, (canvas_h - lh) // 2),
                "middle_right": (canvas_w - lw - margin, (canvas_h - lh) // 2),
                "bottom_left": (margin, canvas_h - lh - margin),
                "bottom_center": ((canvas_w - lw) // 2, canvas_h - lh - margin),
                "bottom_right": (canvas_w - lw - margin, canvas_h - lh - margin)
            }

            paste_pos = pos_map.get(logo_position, pos_map["bottom_right"])
            canvas.paste(logo_resized, paste_pos, logo_resized)
        except Exception as e:
            logging.warning(f"Erro ao processar e colar a logo na thumbnail: {e}")

    canvas.convert("RGB").save(output_path, "PNG", quality=95)
    logging.info(f"Thumbnail 16:9 gerada com sucesso em: {output_path}")
    return output_path
