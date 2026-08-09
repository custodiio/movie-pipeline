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
from src.script_generator import generate_llm_text

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
    Gera o Guia Completo de Postagem do YouTube via IA com 3 requisições distintas:
    1. Título SEO de Captura + Descrição com Liberdade Criativa
    2. Hashtags Relevantes em Alta
    3. Tags de Alta Busca separadas por vírgula
    + Disclaimer Fixo de Direitos Autorais
    """
    title = movie_info.get("title", "")
    orig_title = movie_info.get("original_title", title)
    tmdb_id = movie_info.get("tmdb_id")
    slug = movie_info.get("slug", "filme")
    year = (movie_info.get("release_date") or "")[:4] or "2026"
    overview = movie_info.get("overview", "")

    credits = get_movie_credits_tmdb(tmdb_id) if tmdb_id else {"cast": [], "director": ""}
    cast_str = ", ".join(credits["cast"]) if credits["cast"] else "um elenco estelar"
    director_str = credits["director"] if credits["director"] else "grandes nomes do cinema"

    # --- REQUISIÇÃO 1: Título SEO + Descrição Criativa via IA ---
    prompt_req1 = f"""Gere o Título SEO de Captura e a Descrição para o YouTube do filme:
Título: {title} ({orig_title})
Lançamento: {year}
Sinopse: {overview}
Elenco: {cast_str}
Direção: {director_str}

ESTRUTURA E PADRÃO OBRIGATÓRIOS:

1. TÍTULO DO YOUTUBE:
Gere um título com o nome exato do filme [{title}] seguido de elementos SEO em CAIXA ALTA focados em capturar buscas de usuários que querem assistir (ex: ASSISTIR {title.upper()} COMPLETO HD, {title.upper()} DUBLADO FULL HD GRÁTIS, etc.). Você tem liberdade criativa para definir os ganchos SEO.

2. DESCRIÇÃO:
Siga esse padrão e estrutura abaixo com total liberdade criativa para adaptar o texto, tom e detalhes ao filme:

Neste vídeo, destrinchamos cada detalhe do mais novo e aguardado lançamento de {year}: {title} ({orig_title}). Prepare-se para análises profundas, teorias, a explicação do final e todas as informações sobre esse grande lançamento!

Acompanhe a história eletrizante estrelada por {cast_str}, sob a direção de {director_str}. Quando segredos misteriosos vêm à tona e a tensão atinge o seu limite, os personagens precisam encarar dilemas profundos e confrontar o inevitável em uma trama cheia de reviravoltas.

🔔 INSCREVA-SE no canal e ative o sininho para não perder nenhuma crítica, análise e novidade sobre o cinema e as séries de streaming!
👍 Deixe seu LIKE se este conteúdo te ajudou a entender todos os detalhes do filme!
📢 Compartilhe este vídeo com seus amigos que adoram um bom filme e já assistiram a esse lançamento!

FORMATO DA RESPOSTA:
TITULO: [Título Gerado]
DESCRICAO: [Descrição Gerada]"""

    res_req1 = ""
    try:
        res_req1 = generate_llm_text(prompt_req1, system_instruction="Você é um especialista em SEO de YouTube e Copywriting Cinematográfico.")
    except Exception as e:
        logging.warning(f"Erro na requisição 1 da IA: {e}")

    # Processa Título e Descrição retornados da IA
    final_yt_title = ""
    base_desc = ""

    if "TITULO:" in res_req1 and "DESCRICAO:" in res_req1:
        parts = res_req1.split("DESCRICAO:")
        title_part = parts[0].replace("TITULO:", "").strip()
        final_yt_title = title_part
        base_desc = parts[1].strip()
    elif res_req1:
        base_desc = res_req1.strip()

    if custom_title and custom_title.strip():
        final_yt_title = custom_title.strip()
    elif not final_yt_title:
        clean_name = re.sub(r'[^\w\s]', '', title).upper()
        final_yt_title = f"{clean_name} COMPLETO DUBLADO | ASSISTA {clean_name} FULL HD GRÁTIS"

    if not base_desc:
        base_desc = f"""Neste vídeo, destrinchamos cada detalhe do mais novo e aguardado lançamento de {year}: {title} ({orig_title}). Prepare-se para análises profundas, teorias, a explicação do final e todas as informações sobre esse grande lançamento!

Acompanhe a história eletrizante estrelada por {cast_str}, sob a direção de {director_str}. Quando segredos misteriosos vêm à tona e a tensão atinge o seu limite, os personagens precisam encarar dilemas profundos e confrontar o inevitável em uma trama cheia de reviravoltas.

🔔 INSCREVA-SE no canal e ative o sininho para não perder nenhuma crítica, análise e novidade sobre o cinema e as séries de streaming!
👍 Deixe seu LIKE se este conteúdo te ajudou a entender todos os detalhes do filme!
📢 Compartilhe este vídeo com seus amigos que adoram um bom filme e já assistiram a esse lançamento!"""

    # --- REQUISIÇÃO 2: Hashtags em Alta via IA ---
    prompt_req2 = f"""Gere uma lista de 8 a 12 Hashtags em alta estritamente relacionadas ao filme '{title}' ({orig_title}), elenco '{cast_str}' e ano {year}.
Retorne apenas as hashtags na mesma linha separadas por espaço (ex: #NomeDoFilme #Diretor #Filmes2026 #ReviewDeFilmes #FinalExplicado)."""
    
    hashtags_str = ""
    try:
        hashtags_str = generate_llm_text(prompt_req2, system_instruction="Retorne apenas a lista de hashtags válidas do YouTube iniciadas com #.").strip()
    except Exception as e:
        logging.warning(f"Erro na requisição 2 da IA: {e}")

    if not hashtags_str or "#" not in hashtags_str:
        def make_tag(text):
            return "#" + "".join(re.findall(r'[a-zA-Z0-9]', text))
        hashtags_list = [make_tag(title), make_tag(orig_title), f"#{year}", f"#Filmes{year}", "#Lancamentos", "#Cinema", "#ReviewDeFilmes", "#FinalExplicado"]
        hashtags_str = " ".join(hashtags_list)

    # Disclaimer Fixo
    disclaimer_fixo = """⚠️ Disclaimer:
All rights to images, soundtracks, and film excerpts belong to their respective owners. The use of copyrighted material is done in accordance with the principle of fair use, for the purpose of criticism, commentary, and analysis, as permitted by applicable law."""

    # Montagem Final da Descrição (IA Descrição + IA Hashtags + Disclaimer Fixo)
    full_description = f"""{base_desc}

{hashtags_str}

{disclaimer_fixo}"""

    # --- REQUISIÇÃO 3: Tags de Alta Busca via IA (separadas por vírgulas) ---
    prompt_req3 = f"""Gere uma lista de 15 a 20 Tags de alta busca estritamente relacionadas ao filme '{title}' ({orig_title}) para o YouTube.
Retorne apenas as tags separadas por vírgulas (ex: {title}, {title} {year}, {title} filme completo, {title} dublado, {title} explicacao do final)."""

    tags_str = ""
    try:
        tags_str = generate_llm_text(prompt_req3, system_instruction="Retorne apenas as palavras-chave separadas por vírgulas.").strip()
    except Exception as e:
        logging.warning(f"Erro na requisição 3 da IA: {e}")

    if not tags_str or "," not in tags_str:
        tags_list = [
            title, f"{title} {year}", f"{title} filme completo", f"{title} dublado", f"{title} legendado",
            f"{title} resumo", f"{title} analise", f"{title} explicacao do final", f"{title} review",
            f"assistir {title}", orig_title, f"filmes de {year}", f"lancamentos {year}", f"cinema {year}"
        ]
        tags_str = ", ".join(tags_list)

    guide_data = {
        "youtube_title": final_yt_title,
        "description": full_description,
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
