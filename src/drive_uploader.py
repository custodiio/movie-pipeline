"""
Módulo de Integração com Google Drive (Upload, Download e Limpeza)

Gerencia a estrutura de pastas no Drive para o Movie-Pipeline, garantindo a permanência dos
ativos fixos (Movie-Pipeline/Assets/) e o gerenciamento dos projetos (Movie-Pipeline/Projetos/<slug>/).
"""

import os
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

DRIVE_ACCESS_TOKEN  = os.getenv("DRIVE_ACCESS_TOKEN", "")
DRIVE_REFRESH_TOKEN = os.getenv("DRIVE_REFRESH_TOKEN", "")
DRIVE_CLIENT_ID     = os.getenv("DRIVE_CLIENT_ID", "")
DRIVE_CLIENT_SECRET = os.getenv("DRIVE_CLIENT_SECRET", "")

def get_drive_service():
    """Autentica e retorna o cliente de serviço da API do Google Drive."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        creds = Credentials(
            token=DRIVE_ACCESS_TOKEN if DRIVE_ACCESS_TOKEN else None,
            refresh_token=DRIVE_REFRESH_TOKEN,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=DRIVE_CLIENT_ID,
            client_secret=DRIVE_CLIENT_SECRET,
            scopes=["https://www.googleapis.com/auth/drive"]
        )
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return build("drive", "v3", credentials=creds, cache_discovery=False)
    except Exception as e:
        logging.warning(f"Falha ao autenticar no Google Drive (Modo local/fallback ativo): {e}")
        return None

def buscar_id(drive_service, caminho_no_drive: str) -> str | None:
    """Busca o ID de um arquivo ou pasta no Google Drive pelo caminho exato."""
    if not drive_service: return None
    partes = caminho_no_drive.strip("/").split("/")
    parent_id = "root"
    for parte in partes:
        query = f"name='{parte}' and '{parent_id}' in parents and trashed=false"
        results = drive_service.files().list(q=query, fields="files(id, mimeType)").execute()
        arquivos = results.get("files", [])
        if not arquivos: return None
        parent_id = arquivos[0]["id"]
    return parent_id

def garantir_pasta(drive_service, caminho_pasta: str) -> str | None:
    """Garante a existência de uma estrutura de pastas no Google Drive."""
    if not drive_service: return None
    partes = caminho_pasta.strip("/").split("/")
    parent_id = "root"
    for pasta in partes:
        query = f"name='{pasta}' and '{parent_id}' in parents and trashed=false and mimeType='application/vnd.google-apps.folder'"
        results = drive_service.files().list(q=query, fields="files(id)").execute()
        existentes = results.get("files", [])
        if existentes:
            parent_id = existentes[0]["id"]
        else:
            nova = drive_service.files().create(
                body={"name": pasta, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]},
                fields="id"
            ).execute()
            parent_id = nova["id"]
    return parent_id

def salvar_no_drive(drive_service, caminho_local: str, caminho_destino_drive: str):
    """Envia um arquivo local para o Google Drive."""
    if not drive_service or not os.path.exists(caminho_local): return
    from googleapiclient.http import MediaFileUpload
    try:
        partes = caminho_destino_drive.strip("/").split("/")
        nome_arquivo = partes[-1]
        pasta_drive  = "/".join(partes[:-1]) if len(partes) > 1 else ""
        parent_id = garantir_pasta(drive_service, pasta_drive) if pasta_drive else "root"
        
        query = f"name='{nome_arquivo}' and '{parent_id}' in parents and trashed=false"
        results = drive_service.files().list(q=query, fields="files(id)").execute()
        existentes = results.get("files", [])
        
        media = MediaFileUpload(caminho_local, resumable=True)
        if existentes:
            drive_service.files().update(fileId=existentes[0]["id"], media_body=media).execute()
        else:
            drive_service.files().create(
                body={"name": nome_arquivo, "parents": [parent_id]},
                media_body=media, fields="id"
            ).execute()
        logging.info(f"Salvo no Drive: {caminho_destino_drive}")
    except Exception as e:
        logging.error(f"Erro ao salvar '{caminho_local}' no Drive: {e}")

def upload_pasta_projeto(drive_service, slug: str, local_project_dir: str):
    """Sobe a pasta do projeto (TXT + Imagens) para Movie-Pipeline/Projetos/<slug>/ no Google Drive."""
    if not drive_service or not os.path.exists(local_project_dir): return
    drive_base_path = f"Movie-Pipeline/Projetos/{slug}"
    
    for root, _, files in os.walk(local_project_dir):
        for file in files:
            full_local_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_local_path, local_project_dir)
            drive_dest_path = f"{drive_base_path}/{rel_path}".replace("\\", "/")
            salvar_no_drive(drive_service, full_local_path, drive_dest_path)

def limpar_temporarios_drive(drive_service, manter_assets: bool = True):
    """
    Limpa pastas e arquivos temporários de projetos anteriores no Drive,
    preservando estritamente a pasta Movie-Pipeline/Assets (intro.mp4 e Clonagem/).
    """
    if not drive_service: return
    try:
        proj_folder_id = buscar_id(drive_service, "Movie-Pipeline/Projetos")
        if proj_folder_id:
            # Lista subpastas temporárias antigas em Projetos
            results = drive_service.files().list(
                q=f"'{proj_folder_id}' in parents and trashed=false",
                fields="files(id, name)"
            ).execute()
            for f in results.get("files", []):
                drive_service.files().delete(fileId=f["id"]).execute()
                logging.info(f"Limpeza de temporário no Drive removida: {f['name']}")
    except Exception as e:
        logging.warning(f"Aviso durante limpeza do Drive: {e}")

def baixar_do_drive(drive_service, caminho_drive: str, caminho_dest_local: str) -> str | None:
    """Baixa um arquivo do Google Drive para o caminho local fornecido."""
    if not drive_service: return None
    try:
        from googleapiclient.http import MediaIoBaseDownload
        file_id = buscar_id(drive_service, caminho_drive)
        if not file_id:
            logging.warning(f"Arquivo não encontrado no Drive: {caminho_drive}")
            return None

        os.makedirs(os.path.dirname(os.path.abspath(caminho_dest_local)), exist_ok=True)
        request = drive_service.files().get_media(fileId=file_id)
        with open(caminho_dest_local, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
        logging.info(f"✅ Arquivo baixado do Drive com sucesso: {caminho_drive} -> {caminho_dest_local}")
        return caminho_dest_local
    except Exception as e:
        logging.error(f"Erro ao baixar arquivo '{caminho_drive}' do Drive: {e}")
        return None

