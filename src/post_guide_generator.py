"""
Módulo de Geração de Guia de Postagem para o YouTube
Gera Título de Captura, Descrição Formatada Padrão e Tags em Alta para o Filme.
"""

import os
import json
import logging
import requests
import re
from src.tmdb_client import TMDB_API_KEY, BASE_URL, get_headers

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def get_movie_credits_tmdb(movie_id: int) -> dict:
    """Obtém elenco e diretor do filme no TMDB."""
    if not TMDB_API_KEY:
        return {"cast": [], "director": ""}

    url = f"{BASE_URL}/movie/{movie_id}/credits"
    params = {"api_key": TMDB_API_KEY, "language": "pt-BR"}
    try:
        res = requests.get(url, headers=get_headers(), params=params, timeout=15)
        res.raise_for_status()
        data = res.json()

        cast = [member["name"] for member in data.get("cast", [])[:4]]
        director = ""
        for crew in data.get("crew", []):
            if crew.get("job") == "Director":
                director = crew["name"]
                break

        return {"cast": cast, "director": director}
    except Exception as e:
        logging.warning(f"Erro ao buscar créditos no TMDB: {e}")
        return {"cast": [], "director": ""}

def generate_youtube_post_guide(movie_info: dict, custom_title: str = None) -> dict:
    """
    Gera o Guia Completo de Postagem do YouTube:
    - Título de Captura
    - Descrição Formatada Padrão com Elenco, Diretor, CTAs e Disclaimer
    - Tags Relevantes em Alta (separadas por vírgula)
    """
    title = movie_info.get("title", "")
    orig_title = movie_info.get("original_title", title)
    tmdb_id = movie_info.get("tmdb_id")
    slug = movie_info.get("slug", "filme")
    year = (movie_info.get("release_date") or "")[:4] or "2026"

    credits = get_movie_credits_tmdb(tmdb_id) if tmdb_id else {"cast": [], "director": ""}
    cast_str = ", ".join(credits["cast"]) if credits["cast"] else "um elenco estelar"
    director_str = credits["director"] if credits["director"] else "grandes nomes do cinema"

    # 1. Título do YouTube
    if custom_title and custom_title.strip():
        final_yt_title = custom_title.strip()
    else:
        clean_name = re.sub(r'[^\w\s]', '', title).upper()
        final_yt_title = f"{clean_name} COMPLETO DUBLADO | ASSISTA {clean_name} FULL HD GRÁTIS"

    # 2. Hashtags Relevantes
    def make_tag(text):
        return "#" + "".join(re.findall(r'[a-zA-Z0-9]', text))

    hashtags = [
        make_tag(title),
        make_tag(orig_title),
        "#" + year,
        "#Filmes" + year,
        "#Lancamentos",
        "#Cinema",
        "#ReviewDeFilmes",
        "#FinalExplicado"
    ]
    for actor in credits["cast"][:2]:
        if actor:
            hashtags.append(make_tag(actor))
    if credits["director"]:
        hashtags.append(make_tag(credits["director"]))

    hashtags_str = " ".join(hashtags)

    # 3. Descrição Padrão Estrita
    description = f"""Neste vídeo, destrinchamos cada detalhe do mais novo e aguardado lançamento de {year}: {title} ({orig_title}). Prepare-se para análises profundas, teorias, a explicação do final e todas as informações sobre esse grande filme!

Acompanhe a história eletrizante estrelada por {cast_str}, sob a direção de {director_str}. Quando segredos misteriosos vêm à tona e a tensão atinge o seu limite, os personagens precisam encarar dilemas profundos e confrontar o inevitável em uma trama cheia de reviravoltas.

🔔 INSCREVA-SE no canal e ative o sininho para não perder nenhuma crítica, análise e novidade sobre o cinema e as séries de streaming!
👍 Deixe seu LIKE se este conteúdo te ajudou a entender todos os detalhes do filme!
📢 Compartilhe este vídeo com seus amigos que adoram um bom filme e já assistiram a esse lançamento!

{hashtags_str}

⚠️ Disclaimer:
All rights to images, soundtracks, and film excerpts belong to their respective owners. The use of copyrighted material is done in accordance with the principle of fair use, for the purpose of criticism, commentary, and analysis, as permitted by applicable law."""

    # 4. Tags Relevantes em Alta (separadas por vírgula)
    tags_list = [
        title,
        f"{title} {year}",
        f"{title} filme completo",
        f"{title} dublado",
        f"{title} legendado",
        f"{title} resumo",
        f"{title} analise",
        f"{title} explicacao do final",
        f"{title} review",
        f"assistir {title}",
        f"{orig_title}",
        f"filmes de {year}",
        f"lancamentos {year}",
        f"cinema {year}"
    ]
    for c in credits["cast"]:
        if c:
            tags_list.append(f"{title} {c}")
            tags_list.append(c)

    tags_str = ", ".join(tags_list)

    guide_data = {
        "youtube_title": final_yt_title,
        "description": description,
        "tags": tags_str,
        "hashtags": hashtags_str,
        "tmdb_id": tmdb_id,
        "slug": slug
    }

    return guide_data

def save_post_guide_to_file(guide_data: dict, output_dir: str = "temp") -> str:
    """Salva o guia de postagem formatado em JSON e TXT."""
    os.makedirs(output_dir, exist_ok=True)
    slug = guide_data.get("slug", "filme")

    json_path = os.path.join(output_dir, "guia_postagem.json")
    txt_path = os.path.join(output_dir, "guia_postagem.txt")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(guide_data, f, ensure_ascii=False, indent=2)

    content_txt = f"""==================================================
GUIA DE POSTAGEM DO YOUTUBE - MOVIE-PIPELINE
==================================================

📌 TÍTULO DO YOUTUBE:
{guide_data['youtube_title']}

--------------------------------------------------
📄 DESCRIÇÃO DO VÍDEO:
{guide_data['description']}

--------------------------------------------------
🏷️ TAGS (COPIAR E COLAR NO CAMPO DE TAGS DO YOUTUBE):
{guide_data['tags']}
==================================================
"""
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(content_txt)

    logging.info(f"Guia de postagem salvo em {json_path} e {txt_path}")
    return txt_path
