"""
Módulo de Upload Automático para o YouTube (YouTube Data API v3)
Envia o vídeo produzido para o canal do YouTube no modo Privado com Título, Descrição, Tags e Thumbnail.
"""

import os
import logging
from typing import Dict, Any, Union, List

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)


def upload_video_to_youtube(
    video_path: str,
    title: str,
    description: str,
    tags: Union[str, List[str]],
    thumbnail_path: str = None,
    privacy_status: str = "private"
) -> Dict[str, Any]:
    """
    Realiza o upload do vídeo para o YouTube no modo Privado via API v3.

    :param video_path: Caminho local do arquivo de vídeo MP4.
    :param title: Título otimizado para SEO (máximo 100 caracteres).
    :param description: Descrição completa com disclaimer e hashtags.
    :param tags: Lista de tags ou string com tags separadas por vírgula.
    :param thumbnail_path: Caminho local da thumbnail 16:9.
    :param privacy_status: Status de privacidade ("private", "unlisted" ou "public").
    :return: Dicionário contendo status do upload e URL do vídeo no YouTube.
    """
    refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN") or os.getenv("DRIVE_REFRESH_TOKEN")
    client_id = os.getenv("YOUTUBE_CLIENT_ID") or os.getenv("DRIVE_CLIENT_ID")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET") or os.getenv("DRIVE_CLIENT_SECRET")

    if not all([refresh_token, client_id, client_secret]):
        return {
            "success": False,
            "error": "Credenciais Google OAuth (YOUTUBE_REFRESH_TOKEN, YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET) ausentes no .env"
        }


    if not os.path.exists(video_path):
        return {
            "success": False,
            "error": f"Arquivo de vídeo local não encontrado: {video_path}"
        }

    if isinstance(tags, str):
        tags_list = [t.strip() for t in tags.split(",") if t.strip()]
    else:
        tags_list = tags or []

    try:
        credentials = Credentials(
            token=None,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            token_uri="https://oauth2.googleapis.com/token",
            scopes=["https://www.googleapis.com/auth/youtube.upload"]
        )

        youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)

        body = {
            "snippet": {
                "title": title[:100],
                "description": description,
                "tags": tags_list,
                "categoryId": "24"  # 24 = Entertainment / Cinema & Filmes
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False
            }
        }

        logger.info(f"📤 Uploading para o YouTube ({privacy_status}): '{title[:100]}'")
        media = MediaFileUpload(video_path, chunksize=1024 * 1024 * 10, resumable=True, mimetype="video/mp4")
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logger.info(f"  --> Progresso Upload YouTube: {int(status.progress() * 100)}%")

        video_id = response.get("id")
        video_url = f"https://youtu.be/{video_id}"
        logger.info(f"✅ Vídeo enviado ao YouTube com sucesso! ID: {video_id} | Link: {video_url}")

        # Se houver thumbnail, aplica na capa do vídeo
        if thumbnail_path and os.path.exists(thumbnail_path):
            try:
                logger.info(f"🖼️ Aplicando thumbnail 16:9 no vídeo {video_id}...")
                youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(thumbnail_path, mimetype="image/png")
                ).execute()
                logger.info("✅ Thumbnail 16:9 aplicada no YouTube com sucesso!")
            except Exception as thumb_err:
                logger.warning(f"⚠️ Aviso ao definir a thumbnail no YouTube: {thumb_err}")

        return {
            "success": True,
            "video_id": video_id,
            "video_url": video_url
        }

    except Exception as e:
        logger.error(f"❌ Falha no upload para o YouTube: {e}")
        return {
            "success": False,
            "error": str(e)
        }
