"""
Módulo de Upload de Vídeos para o Dailymotion (API v2)

Fornece:
1. Autenticação OAuth2 via client_credentials com escopo 'video.manage'
2. Handshake de sessão de upload de alta velocidade (upload_sessions)
3. Upload streamado com chunking e cálculo de progresso em tempo real
4. Publicação e vinculação do vídeo sob o perfil oficial do canal
"""

import os
import time
import logging
import httpx
from typing import Callable, Optional
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

DM_TOKEN_URL = "https://oauth2.dailymotion.com/v2/token"
DM_UPLOAD_SESSION_URL = "https://api.dailymotion.com/v2/files/upload_sessions"
DM_PROFILES_VIDEOS_URL = "https://api.dailymotion.com/v2/profiles/{profile_id}/videos"

_cached_token = None
_token_expires_at = 0.0


def get_dailymotion_credentials() -> tuple[str, str]:
    """Recupera client_id e client_secret do arquivo .env com fallbacks."""
    client_id = os.getenv("DAILYMOTION_CLIENT_ID") or os.getenv("DAILYMOTION_API_KEY", "")
    client_secret = os.getenv("DAILYMOTION_CLIENT_SECRET") or os.getenv("DAILYMOTION_API_SECRET", "")
    return client_id.strip(), client_secret.strip()


def get_dailymotion_access_token(force_refresh: bool = False) -> str:
    """
    Obtém um token de acesso OAuth 2.0 (JWT) da API v2 do Dailymotion.
    Mantém cache local do token enquanto for válido.
    """
    global _cached_token, _token_expires_at
    now = time.time()

    if not force_refresh and _cached_token and now < _token_expires_at:
        return _cached_token

    client_id, client_secret = get_dailymotion_credentials()
    if not (client_id and client_secret):
        raise ValueError("Credenciais DAILYMOTION_CLIENT_ID e DAILYMOTION_CLIENT_SECRET não configuradas no .env!")

    with httpx.Client(timeout=20) as client:
        res = client.post(
            DM_TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "video.manage"
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        if res.status_code != 200:
            raise RuntimeError(f"Erro na autenticação Dailymotion ({res.status_code}): {res.text}")

        data = res.json()
        token = data.get("access_token")
        expires_in = data.get("expires_in", 1800)

        if not token:
            raise RuntimeError(f"Token não retornado pelo Dailymotion: {data}")

        _cached_token = token
        _token_expires_at = now + max(60, expires_in - 300)
        logging.info("✅ Novo Access Token do Dailymotion API v2 obtido com sucesso!")
        return token


def create_upload_session(token: str) -> dict:
    """Cria uma sessão de upload na API v2 e retorna upload_url e progress_url."""
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=20) as client:
        res = client.post(DM_UPLOAD_SESSION_URL, headers=headers)
        if res.status_code not in (200, 201):
            raise RuntimeError(f"Erro ao criar sessão de upload Dailymotion ({res.status_code}): {res.text}")
        return res.json()


class ProgressFileReader:
    """Wrapper de arquivo com callback de progresso por chunks para o upload."""
    def __init__(self, file_path: str, progress_callback: Optional[Callable[[float, int, int], None]] = None, chunk_size: int = 1024 * 1024):
        self.file_path = file_path
        self.total_bytes = os.path.getsize(file_path)
        self.progress_callback = progress_callback
        self.chunk_size = chunk_size
        self.read_bytes = 0
        self._file = open(file_path, "rb")

    def read(self, size: int = -1):
        chunk = self._file.read(size)
        if chunk:
            self.read_bytes += len(chunk)
            if self.progress_callback:
                pct = (self.read_bytes / self.total_bytes * 100) if self.total_bytes > 0 else 0
                try:
                    self.progress_callback(pct, self.read_bytes, self.total_bytes)
                except Exception as e:
                    logging.debug(f"Erro no progress_callback: {e}")
        return chunk

    def close(self):
        self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def upload_video_to_dailymotion(
    video_path: str,
    title: str,
    description: str = "",
    category: str = "tv",
    visibility: str = "public",
    profile_id: str = "x5yz68a",
    progress_callback: Optional[Callable[[float, int, int], None]] = None
) -> dict:
    """
    Executa o pipeline completo de upload e publicação de um vídeo no Dailymotion:
    1. Obtém token v2
    2. Cria sessão de upload
    3. Faz o upload streaming do arquivo com acompanhamento de progresso
    4. Cria e publica o objeto de vídeo no perfil do canal
    """
    if not os.path.exists(video_path):
        return {"success": False, "error": f"Arquivo de vídeo não encontrado: {video_path}"}

    try:
        file_size = os.path.getsize(video_path)
        logging.info(f"🌐 Iniciando upload para Dailymotion: '{title}' ({file_size / (1024*1024):.1f} MB)...")

        # 1. Autenticação
        token = get_dailymotion_access_token()

        # 2. Sessão de Upload
        session = create_upload_session(token)
        upload_url = session.get("upload_url")
        if not upload_url:
            return {"success": False, "error": f"Upload URL não retornada na sessão: {session}"}

        # 3. Upload streamado do arquivo
        logging.info(f"📤 Enviando stream de vídeo para {upload_url[:50]}...")
        with ProgressFileReader(video_path, progress_callback=progress_callback) as p_file:
            with httpx.Client(timeout=httpx.Timeout(connect=30.0, read=300.0, write=300.0, pool=30.0)) as client:
                up_res = client.post(
                    upload_url,
                    files={"file": (os.path.basename(video_path), p_file, "video/mp4")}
                )

        if up_res.status_code != 200:
            return {"success": False, "error": f"Falha no envio do arquivo ({up_res.status_code}): {up_res.text}"}

        up_data = up_res.json()
        uploaded_file_url = up_data.get("url")
        if not uploaded_file_url:
            return {"success": False, "error": f"URL do arquivo enviado não retornada: {up_data}"}

        logging.info(f"✅ Arquivo enviado para Dailymotion com sucesso! URL do arquivo: {uploaded_file_url[:60]}")

        # 4. Criação do Vídeo sob o perfil
        create_url = DM_PROFILES_VIDEOS_URL.format(profile_id=profile_id)
        payload = {
            "title": title[:255],
            "description": description[:3000] if description else title,
            "source": {
                "file_url": uploaded_file_url
            },
            "category": category,
            "visibility": visibility,
            "is_for_kids": False
        }

        with httpx.Client(timeout=30) as client:
            pub_res = client.post(
                create_url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                },
                json=payload
            )

        if pub_res.status_code not in (200, 201):
            return {"success": False, "error": f"Falha ao criar vídeo no perfil ({pub_res.status_code}): {pub_res.text}"}

        pub_data = pub_res.json()
        video_id = pub_data.get("video_id") or pub_data.get("id")
        video_url = f"https://www.dailymotion.com/video/{video_id}" if video_id else ""

        logging.info(f"🎉 Vídeo publicado com sucesso no Dailymotion! ID: {video_id} | Link: {video_url}")

        return {
            "success": True,
            "video_id": video_id,
            "video_url": video_url,
            "title": title,
            "details": pub_data
        }

    except Exception as e:
        logging.error(f"Erro crítico no upload Dailymotion: {e}", exc_info=True)
        return {"success": False, "error": str(e)}
