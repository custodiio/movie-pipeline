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
import json
import base64
import subprocess
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
    """Recupera client_id e client_secret do arquivo .env com sanitização."""
    client_id = os.getenv("DAILYMOTION_CLIENT_ID") or os.getenv("DAILYMOTION_API_KEY", "")
    client_secret = os.getenv("DAILYMOTION_CLIENT_SECRET") or os.getenv("DAILYMOTION_API_SECRET", "")
    return client_id.strip().strip("\"'").strip(), client_secret.strip().strip("\"'").strip()


def extract_profile_id_from_token(token: str) -> str:
    """Extrai dinamicamente o sub (profile_id) do payload JWT do token Dailymotion."""
    try:
        parts = token.split(".")
        if len(parts) >= 2:
            payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
            sub = payload.get("sub")
            if sub:
                return str(sub)
    except Exception as e:
        logging.warning(f"Aviso ao extrair sub do token JWT: {e}")
    return "x5yz68a"


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
    if not client_id or not client_secret:
        raise ValueError("Credenciais do Dailymotion (DAILYMOTION_CLIENT_ID / DAILYMOTION_CLIENT_SECRET) não configuradas.")

    payload = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "video.manage"
    }

    with httpx.Client(timeout=20) as client:
        res = client.post(
            DM_TOKEN_URL,
            data=payload,
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


def get_video_info(video_path: str) -> tuple[float, int]:
    """Retorna (duracao_em_segundos, tamanho_em_bytes) usando ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration,size",
        "-of", "json", video_path
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            data = json.loads(res.stdout)
            dur = float(data.get("format", {}).get("duration", 0))
            size = int(data.get("format", {}).get("size", 0))
            return dur, size
    except Exception as e:
        logging.warning(f"Aviso ao obter metadados com ffprobe: {e}")
    return 0.0, os.path.getsize(video_path) if os.path.exists(video_path) else 0


def adapt_video_for_dailymotion(
    video_path: str,
    max_duration_sec: int = 7190,
    max_size_mb: int = 3900,
    status_callback: Optional[Callable[[str, Optional[float]], None]] = None
) -> tuple[str, bool]:
    """
    Garante que o vídeo respeite os limites estritos do Dailymotion Standard Creator:
    1. Duração máxima de 01:59:50 (limite oficial: 2 horas / 7200s).
    2. Tamanho máximo de 3.9 GB (limite oficial: 4.0 GB).
    
    Executa corte instantâneo em 1-2 segundos via FFmpeg Stream Copy (-c copy)
    e informa o status em tempo real via status_callback.
    Retorna (caminho_do_video_final, is_arquivo_temporario).
    """
    if not os.path.exists(video_path):
        return video_path, False

    dur, size_bytes = get_video_info(video_path)
    size_mb = size_bytes / (1024 * 1024)
    current_path = video_path
    is_temp = False

    # 1. Recorte de Duração instantâneo (-c copy em segundos) se ultrapassar 01:59:50
    if dur > max_duration_sec:
        dir_name = os.path.dirname(video_path) or "temp"
        base_name = os.path.basename(video_path)
        trimmed_path = os.path.join(dir_name, f"dm_trimmed_{base_name}")
        logging.info(f"✂️ Vídeo tem {dur/60:.1f} min (> 2h). Recortando instantaneamente para 01:59:50 com -c copy...")
        if status_callback:
            status_callback("✂️ Recortando duração para 01:59:50 (limite oficial de 2h do Dailymotion)...", None)

        cmd_trim = [
            "ffmpeg", "-y", "-ss", "00:00:00", "-i", video_path,
            "-t", "01:59:50", "-c", "copy", trimmed_path
        ]
        res = subprocess.run(cmd_trim, capture_output=True, text=True)
        if res.returncode == 0 and os.path.exists(trimmed_path):
            current_path = trimmed_path
            is_temp = True
            dur, size_bytes = get_video_info(current_path)
            size_mb = size_bytes / (1024 * 1024)
            logging.info(f"✅ Vídeo recortado em ~1s: {size_mb:.1f} MB | {dur/60:.1f} min")

    # 2. Otimização de Bitrate ultra-rápida (se após o corte ainda for > 3.9 GB)
    if size_mb > max_size_mb:
        dir_name = os.path.dirname(video_path) or "temp"
        base_name = os.path.basename(video_path)
        compressed_path = os.path.join(dir_name, f"dm_opt_{base_name}")
        effective_dur = min(dur, max_duration_sec) if dur > 0 else 7190
        target_bitrate_kbps = max(1500, int((3700 * 8192) / effective_dur))
        logging.info(f"⚡ Ajustando bitrate para caber no limite de 4 GB ({target_bitrate_kbps} kbps)...")
        if status_callback:
            status_callback(f"⚡ Ajustando tamanho ({size_mb:.1f} MB -> < 4 GB)...", 0.0)

        cmd_comp = [
            "ffmpeg", "-y", "-i", current_path,
            "-c:v", "libx264", "-preset", "veryfast",
            "-b:v", f"{target_bitrate_kbps}k",
            "-maxrate", f"{int(target_bitrate_kbps * 1.2)}k",
            "-bufsize", f"{target_bitrate_kbps * 2}k",
            "-c:a", "copy",
            "-progress", "pipe:1",
            "-nostats",
            compressed_path
        ]
        process = subprocess.Popen(cmd_comp, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        last_cb = 0.0
        if process.stdout:
            for line in process.stdout:
                line = line.strip()
                if line.startswith("out_time_us="):
                    try:
                        us = int(line.split("=")[1])
                        sec = us / 1_000_000
                        pct = min(100.0, (sec / effective_dur) * 100)
                        now = time.time()
                        if now - last_cb >= 2.0 or pct >= 100.0:
                            last_cb = now
                            if status_callback:
                                status_callback(f"⚡ Otimizando tamanho para limite de 4 GB ({pct:.1f}%)...", pct)
                    except Exception:
                        pass
        process.wait()

        if process.returncode == 0 and os.path.exists(compressed_path):
            if is_temp and os.path.exists(current_path):
                try:
                    os.remove(current_path)
                except Exception:
                    pass
            current_path = compressed_path
            is_temp = True
            logging.info(f"✅ Vídeo otimizado com sucesso: {os.path.getsize(current_path)/(1024*1024):.1f} MB")

    return current_path, is_temp


class ProgressFileReader:
    """
    Wrapper de arquivo com callback de progresso por chunks para o upload.
    Implementa seek, tell e __len__ para garantir que o cliente HTTP envie o cabeçalho Content-Length correto.
    """
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

    def seek(self, offset: int, whence: int = 0) -> int:
        res = self._file.seek(offset, whence)
        self.read_bytes = self._file.tell()
        return res

    def tell(self) -> int:
        return self._file.tell()

    def __len__(self) -> int:
        return self.total_bytes

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
    progress_callback: Optional[Callable[[float, int, int], None]] = None,
    status_callback: Optional[Callable[[str, Optional[float]], None]] = None
) -> dict:
    """
    Executa o pipeline completo de upload e publicação de um vídeo no Dailymotion:
    1. Adapta duração (< 2h) e tamanho (< 4GB) instantaneamente com FFmpeg e feedback em tempo real
    2. Obtém token v2 e resolve profile_id dinâmico
    3. Cria sessão de upload
    4. Faz o upload streaming do arquivo com acompanhamento de progresso
    5. Cria e publica o objeto de vídeo no perfil do canal
    """
    if not os.path.exists(video_path):
        return {"success": False, "error": f"Arquivo de vídeo não encontrado: {video_path}"}

    upload_file_path, is_temp = adapt_video_for_dailymotion(video_path, status_callback=status_callback)

    try:
        file_size = os.path.getsize(upload_file_path)
        logging.info(f"🌐 Iniciando upload para Dailymotion: '{title}' ({file_size / (1024*1024):.1f} MB)...")

        # 1. Autenticação & Profile ID
        token = get_dailymotion_access_token()
        effective_profile_id = extract_profile_id_from_token(token) if (not profile_id or profile_id == "x5yz68a") else profile_id

        # 2. Sessão de Upload
        session = create_upload_session(token)
        upload_url = session.get("upload_url")
        if not upload_url:
            return {"success": False, "error": f"Upload URL não retornada na sessão: {session}"}

        # 3. Upload streamado do arquivo
        logging.info(f"📤 Enviando stream de vídeo para {upload_url[:50]}...")
        with ProgressFileReader(upload_file_path, progress_callback=progress_callback) as p_file:
            with httpx.Client(timeout=httpx.Timeout(connect=30.0, read=600.0, write=600.0, pool=30.0)) as client:
                up_res = client.post(
                    upload_url,
                    files={"file": (os.path.basename(upload_file_path), p_file, "video/mp4")}
                )

        if up_res.status_code != 200:
            return {"success": False, "error": f"Falha no envio do arquivo ({up_res.status_code}): {up_res.text}"}

        up_data = up_res.json()
        uploaded_file_url = up_data.get("url")
        if not uploaded_file_url:
            return {"success": False, "error": f"URL do arquivo enviado não retornada: {up_data}"}

        logging.info(f"✅ Arquivo enviado para Dailymotion com sucesso! URL do arquivo: {uploaded_file_url[:60]}")

        # 4. Criação do Vídeo sob o perfil
        create_url = DM_PROFILES_VIDEOS_URL.format(profile_id=effective_profile_id)
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

    finally:
        if is_temp and os.path.exists(upload_file_path):
            try:
                os.remove(upload_file_path)
                logging.info(f"🧹 Arquivo temporário adaptado excluído: {upload_file_path}")
            except Exception as e_del:
                logging.debug(f"Aviso ao remover temp: {e_del}")

