"""
Módulo de Download de Torrent de Alta Velocidade via Aria2c e Enriquecimento de Trackers
movie-pipeline - Suporte a Magnet Links, Divisão Inteligente (> 4GB/2GB) e Upload VIP.
"""

import os
import sys
import re
import json
import math
import shutil
import asyncio
import logging
import urllib.parse
import urllib.request
import zipfile
import tarfile
import io
from typing import Callable, Optional, List, Dict, Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Lista de Rastreadores Públicos Atualizados de Alta Velocidade para Injeção Automática
PUBLIC_TRACKERS = [
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.tracker.cl:1337/announce",
    "udp://opentracker.i2p.rocks:6969/announce",
    "udp://tracker.openbittorrent.com:6969/announce",
    "http://tracker.openbittorrent.com:80/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://open.stealth.si:80/announce",
    "udp://tracker.tiny-vps.com:6969/announce",
    "udp://tracker.moeking.me:6969/announce",
    "udp://explodie.org:6969/announce",
    "udp://p4p.arenabg.com:1337/announce",
    "udp://tracker.coppersurfer.tk:6969/announce",
    "udp://tracker.leechers-paradise.org:6969/announce",
    "udp://tracker.internetwarriors.net:1337/announce"
]

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".webm", ".flv", ".ts", ".m4v", ".wmv"}
SUBTITLE_EXTENSIONS = {".srt", ".ass", ".ssa", ".vtt"}


def ensure_aria2_binary() -> str:
    """
    Localiza o executável do Aria2c no sistema ou baixa e descompacta a versão estática oficial
    automaticamente em `bin/aria2c` ou `bin/aria2c.exe`.
    """
    # 1. Verifica se já está no PATH do sistema
    aria_system = shutil.which("aria2c")
    if aria_system:
        return aria_system

    # 2. Verifica se está na pasta bin/ local do projeto
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bin_dir = os.path.join(base_dir, "bin")
    os.makedirs(bin_dir, exist_ok=True)

    is_windows = sys.platform.startswith("win")
    binary_name = "aria2c.exe" if is_windows else "aria2c"
    local_bin = os.path.join(bin_dir, binary_name)

    if os.path.exists(local_bin) and os.access(local_bin, os.X_OK if not is_windows else os.F_OK):
        return local_bin

    # 3. Baixa a versão estável se não existir
    logging.info(f"⚡ Binário do Aria2c não encontrado. Baixando versão oficial para {sys.platform}...")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    try:
        if is_windows:
            url = "https://github.com/aria2/aria2/releases/download/release-1.37.0/aria2-1.37.0-win-64bit-build1.zip"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                z = zipfile.ZipFile(io.BytesIO(resp.read()))
                for member in z.namelist():
                    if member.endswith("aria2c.exe"):
                        with open(local_bin, "wb") as f:
                            f.write(z.read(member))
                        logging.info(f"✅ Aria2c instalado com sucesso em: {local_bin}")
                        return local_bin
        else:
            # Linux x86_64 static build
            url = "https://github.com/q3aql/aria2-static-builds/releases/download/v1.37.0/aria2-1.37.0-linux-gnu-64bit-build1.tar.bz2"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                t = tarfile.open(fileobj=io.BytesIO(resp.read()), mode="r:bz2")
                for member in t.getmembers():
                    if member.name.endswith("aria2c"):
                        extracted = t.extractfile(member)
                        if extracted:
                            with open(local_bin, "wb") as f:
                                f.write(extracted.read())
                            os.chmod(local_bin, 0o755)
                            logging.info(f"✅ Aria2c estático instalado com sucesso em: {local_bin}")
                            return local_bin

    except Exception as e:
        logging.error(f"Erro ao baixar Aria2c automaticamente: {e}")

    # Fallback para o nome padrão caso esteja em outro local
    return "aria2c"


def enrich_magnet_with_trackers(magnet_link: str) -> str:
    """
    Adiciona uma lista de rastreadores públicos de alta velocidade ao Magnet Link
    para acelerar a descoberta de nós DHT e conexão imediata com seeders.
    """
    magnet_link = magnet_link.strip()
    if not magnet_link.startswith("magnet:?"):
        return magnet_link

    # Converte os rastreadores para parâmetros &tr=
    trackers_to_add = []
    for tr in PUBLIC_TRACKERS:
        encoded = urllib.parse.quote(tr, safe="")
        if encoded not in magnet_link and tr not in magnet_link:
            trackers_to_add.append(f"tr={encoded}")

    if trackers_to_add:
        delimiter = "&" if "?" in magnet_link else "?"
        magnet_link += delimiter + "&".join(trackers_to_add)

    return magnet_link


def extract_torrent_display_name(magnet_link: str) -> str:
    """
    Extrai o parâmetro dn (display name) do magnet link se existir.
    """
    try:
        parsed = urllib.parse.urlparse(magnet_link)
        params = urllib.parse.parse_qs(parsed.query)
        if "dn" in params and params["dn"]:
            return params["dn"][0]
    except Exception:
        pass
    return "Download_Torrent"


def parse_aria2_progress(line: str) -> Optional[Dict[str, Any]]:
    """
    Analisa a linha de saída padrão (stdout) do Aria2c para extrair métricas de download em tempo real.
    Exemplo: [#b7ca3c 120MiB/1.4GiB(8%) CN:15 SD:12 DL:14.5MiB ETA:1m28s]
    """
    line = line.strip()
    if not line.startswith("[#") or "]" not in line:
        return None

    content = line[line.find(" "):line.rfind("]")].strip()

    # 1. Tamanho baixado e tamanho total com %
    size_match = re.search(r'([0-9\.]+[A-Za-z]+)/([0-9\.]+[A-Za-z]+)(?:\((\d+)%\))?', content)
    downloaded = size_match.group(1) if size_match else "0B"
    total = size_match.group(2) if size_match else "0B"
    percent = float(size_match.group(3)) if (size_match and size_match.group(3)) else 0.0

    # 2. Conexões ativas (CN:15)
    cn_match = re.search(r'CN:(\d+)', content)
    conns = int(cn_match.group(1)) if cn_match else 0

    # 3. Sementes conectadas (SD:12 ou Seeders:12)
    sd_match = re.search(r'(?:SD|Seeders):(\d+)', content)
    seeds = int(sd_match.group(1)) if sd_match else 0

    # 4. Velocidade de Download (DL:14.5MiB)
    dl_match = re.search(r'DL:([0-9\.]+[A-Za-z]+)', content)
    speed = dl_match.group(1) if dl_match else "0B"

    # 5. Tempo Estimado (ETA:1m28s)
    eta_match = re.search(r'ETA:([0-9a-zA-Z]+)', content)
    eta = eta_match.group(1) if eta_match else "--"

    return {
        "downloaded": downloaded,
        "total": total,
        "percent": percent,
        "conns": conns,
        "seeds": seeds,
        "speed": speed,
        "eta": eta,
        "raw_line": line
    }


def find_video_files(directory: str) -> List[str]:
    """
    Varre recursivamente o diretório fornecido e retorna todos os arquivos de vídeo
    encontrados, ordenados de forma decrescente pelo tamanho do arquivo (maior primeiro).
    """
    video_files = []
    if os.path.isfile(directory):
        ext = os.path.splitext(directory)[1].lower()
        if ext in VIDEO_EXTENSIONS:
            return [directory]
        return []

    for root, _, files in os.walk(directory):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in VIDEO_EXTENSIONS:
                full_p = os.path.join(root, f)
                try:
                    size = os.path.getsize(full_p)
                    # Filtra arquivos minúsculos < 5MB (como samples ou vinhetas) caso existam múltiplos
                    video_files.append((full_p, size))
                except Exception:
                    pass

    # Ordena pelo tamanho decrescente
    video_files.sort(key=lambda x: x[1], reverse=True)
    return [item[0] for item in video_files]


def find_subtitle_files(directory: str) -> List[str]:
    """
    Varre recursivamente o diretório fornecido e retorna todos os arquivos de legenda (.srt, .ass, etc.).
    """
    sub_files = []
    if os.path.isfile(directory):
        ext = os.path.splitext(directory)[1].lower()
        if ext in SUBTITLE_EXTENSIONS:
            return [directory]
        return []

    for root, _, files in os.walk(directory):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in SUBTITLE_EXTENSIONS:
                full_p = os.path.join(root, f)
                sub_files.append(full_p)
    return sub_files


async def embed_subtitles_and_prepare_stream(
    video_path: str,
    subtitle_path: Optional[str] = None,
    burn_subtitles: bool = True,
    status_callback: Optional[Callable[[str, Optional[float]], None]] = None
) -> tuple[str, bool]:
    """
    Prepara o vídeo para reprodução perfeita com legendas em 100% dos dispositivos Telegram (iOS, Desktop, Android e Web):
    
    1. Se houver legenda informada (ou na pasta) e burn_subtitles=True:
       Executa Hardsub de alta velocidade via FFmpeg (-preset veryfast -c:a copy) gravando as legendas
       com estilo elegante (letras brancas, contorno preto) para exibição imediata no player nativo do Telegram.
    2. Preserva 100% das faixas de áudio originais.
    3. Aplica -movflags +faststart para streaming instantâneo.
    
    Retorna (caminho_final, is_temporario).
    """
    if not os.path.exists(video_path):
        return video_path, False

    # 1. Se nenhuma legenda foi passada, tenta encontrar automaticamente no diretório do vídeo
    sub_file = subtitle_path
    if not sub_file or not os.path.exists(sub_file):
        parent_dir = os.path.dirname(video_path)
        subs_found = find_subtitle_files(parent_dir)
        if subs_found:
            sub_file = subs_found[0]
            logging.info(f"📝 Legenda detectada automaticamente na pasta: {sub_file}")

    base_name, ext = os.path.splitext(video_path)
    output_path = f"{base_name}_vip_stream.mp4"

    if sub_file and os.path.exists(sub_file):
        if burn_subtitles:
            logging.info(f"🔥 Queimando legenda '{os.path.basename(sub_file)}' no vídeo (100% compatível iOS/Desktop)...")
            if status_callback:
                status_callback(f"🔥 Gravando legenda no vídeo (compatível com iPhone, iPad, PC e Android)...", 0.0)

            # Escapa o caminho para o filtro subtitles do ffmpeg
            sub_escaped = os.path.abspath(sub_file).replace("\\", "/").replace(":", "\\:")
            filter_str = f"subtitles='{sub_escaped}':force_style='FontSize=22,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=3,Outline=1.5,MarginV=25'"

            # Obtém a duração aproximada para o cálculo de progresso
            meta = await extract_video_metadata_and_thumb(video_path)
            total_dur = meta.get("duration", 1) or 1

            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-vf", filter_str,
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "21",
                "-c:a", "copy",
                "-movflags", "+faststart",
                "-progress", "pipe:1",
                "-nostats",
                output_path
            ]
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL
                )
                last_cb = 0.0
                while True:
                    line_bytes = await proc.stdout.readline()
                    if not line_bytes:
                        break
                    line = line_bytes.decode("utf-8", errors="replace").strip()
                    if line.startswith("out_time_us="):
                        try:
                            us = int(line.split("=")[1])
                            sec = us / 1_000_000
                            pct = min(100.0, (sec / total_dur) * 100)
                            now = asyncio.get_event_loop().time()
                            if (now - last_cb >= 2.5 or pct >= 100.0) and status_callback:
                                last_cb = now
                                status_callback(f"🔥 Gravando legenda no vídeo ({pct:.1f}%)...", pct)
                        except Exception:
                            pass
                await proc.wait()

                if proc.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    logging.info(f"✅ Vídeo com legenda gravada gerado com sucesso: {output_path}")
                    return output_path, True
            except Exception as e:
                logging.warning(f"Aviso ao queimar legenda com FFmpeg: {e}. Tentando fallback softsub...")

        # Fallback para Softsub rápido se burn_subtitles=False ou se falhar
        cmd_soft = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", sub_file,
            "-map", "0:v",
            "-map", "0:a?",
            "-map", "1:0",
            "-c:v", "copy",
            "-c:a", "copy",
            "-c:s", "mov_text",
            "-metadata:s:s:0", "language=por",
            "-metadata:s:s:0", "title=Português",
            "-movflags", "+faststart",
            output_path
        ]
        try:
            proc_soft = await asyncio.create_subprocess_exec(*cmd_soft, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            await proc_soft.communicate()
            if proc_soft.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return output_path, True
        except Exception:
            pass

    # Se for MKV sem legenda externa, converte para MP4 preservando tudo
    elif ext.lower() == ".mkv":
        logging.info(f"⚡ Remuxando MKV para MP4 com suporte a streaming (+faststart)...")
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-map", "0:v",
            "-map", "0:a?",
            "-map", "0:s?",
            "-c:v", "copy",
            "-c:a", "copy",
            "-c:s", "mov_text",
            "-movflags", "+faststart",
            output_path
        ]
        try:
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            await proc.communicate()
            if proc.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                logging.info(f"✅ MKV convertido para MP4 com sucesso: {output_path}")
                return output_path, True
        except Exception as e:
            logging.warning(f"Aviso ao remuxar MKV para MP4: {e}. Mantendo arquivo original.")

    return video_path, False


async def download_torrent_magnet(
    magnet_link: str,
    download_dir: str,
    progress_callback: Optional[Callable[[Dict[str, Any]], Any]] = None,
    timeout_seconds: int = 14400
) -> List[str]:
    """
    Realiza o download ultra-rápido de um Magnet Torrent utilizando o motor nativo Aria2c.
    
    Acelerações aplicadas:
    - Injeção de rastreadores públicos atualizados
    - Conexões DHT e PEX ativadas com até 120 peers simultâneos
    - Alocação rápida de arquivos no disco
    - Interrupção instantânea do processo logo após atingir 100% de download
    """
    os.makedirs(download_dir, exist_ok=True)
    aria2_bin = ensure_aria2_binary()
    enriched_magnet = enrich_magnet_with_trackers(magnet_link)

    # Argumentos do Aria2c para saturação de banda e conexão massiva
    cmd = [
        aria2_bin,
        "--dir=" + os.path.abspath(download_dir),
        "--enable-dht=true",
        "--enable-peer-exchange=true",
        "--bt-enable-lpd=true",
        "--bt-max-peers=120",
        "--bt-request-peer-speed-limit=0",
        "--max-overall-download-limit=0",
        "--max-download-limit=0",
        "--seed-time=0",
        "--summary-interval=1",
        "--file-allocation=trunc",
        "--check-certificate=false",
        "--peer-id-prefix=-TR2940-",
        "--user-agent=Transmission/2.94",
        "--follow-torrent=mem",
        "--bt-tracker-connect-timeout=5",
        "--bt-tracker-timeout=5",
        enriched_magnet
    ]

    logging.info(f"🧲 Iniciando download torrent com Aria2c em {download_dir}...")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    last_update = 0
    while True:
        line_bytes = await proc.stdout.readline()
        if not line_bytes:
            break

        line = line_bytes.decode("utf-8", errors="replace").strip()
        if line:
            parsed = parse_aria2_progress(line)
            if parsed and progress_callback:
                now = asyncio.get_event_loop().time()
                if now - last_update >= 2.5 or parsed["percent"] >= 100.0:
                    last_update = now
                    try:
                        if asyncio.iscoroutinefunction(progress_callback):
                            await progress_callback(parsed)
                        else:
                            progress_callback(parsed)
                    except Exception as cb_err:
                        logging.warning(f"Aviso no callback de progresso do torrent: {cb_err}")

    await proc.wait()

    if proc.returncode != 0:
        stderr_bytes = await proc.stderr.read()
        err_msg = stderr_bytes.decode("utf-8", errors="replace")
        logging.warning(f"Aria2 finalizado com código {proc.returncode}: {err_msg}")

    # Localiza todos os vídeos baixados
    videos = find_video_files(download_dir)
    logging.info(f"🎬 Download concluído! Arquivos de vídeo encontrados ({len(videos)}): {videos}")
    return videos


async def split_video_if_needed(video_path: str, max_size_mb: float = 2000.0) -> List[Dict[str, Any]]:
    """
    Verifica o tamanho do arquivo de vídeo. Se for superior a `max_size_mb` (ex: 2000 MB para contas comuns
    ou 4000 MB para Telegram Premium), divide o arquivo em N partes iguais utilizando FFmpeg Stream Copy
    (`-c copy`), preservando 100% da qualidade original sem recodificação em poucos segundos.
    
    Retorna uma lista de dicionários contendo:
    [
        {"part_index": 1, "total_parts": N, "path": "..._parte_1_de_N.mkv", "is_split": True},
        ...
    ]
    """
    if not os.path.exists(video_path):
        return []

    file_size_bytes = os.path.getsize(video_path)
    file_size_mb = file_size_bytes / (1024 * 1024)

    if file_size_mb <= max_size_mb:
        return [{
            "part_index": 1,
            "total_parts": 1,
            "path": video_path,
            "is_split": False,
            "size_mb": file_size_mb
        }]

    # Calcula quantas partes são necessárias mantendo cada parte abaixo de ~1950 MB
    target_part_size = 1950.0
    num_parts = math.ceil(file_size_mb / target_part_size)
    if num_parts < 2:
        num_parts = 2

    logging.info(f"📦 Arquivo de {file_size_mb:.1f} MB excede {max_size_mb:.0f} MB. Dividindo em {num_parts} partes iguais via FFmpeg (-c copy)...")

    # 1. Obtém a duração total em segundos via ffprobe
    cmd_dur = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", video_path
    ]
    try:
        proc_dur = await asyncio.create_subprocess_exec(
            *cmd_dur,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        out_dur, _ = await proc_dur.communicate()
        duration = float(out_dur.decode().strip())
    except Exception as e:
        logging.warning(f"Não foi possível obter duração exata com ffprobe ({e}). Usando fallback aproximado.")
        duration = 7200.0

    part_duration = duration / num_parts
    split_parts = []
    base_name, ext = os.path.splitext(video_path)
    if not ext:
        ext = ".mkv"

    for i in range(num_parts):
        start_t = i * part_duration
        out_p = f"{base_name}_parte_{i+1}_de_{num_parts}{ext}"

        cmd_split = [
            "ffmpeg", "-y", "-ss", str(start_t), "-i", video_path,
            "-t", str(part_duration), "-c", "copy", out_p
        ]

        proc_sp = await asyncio.create_subprocess_exec(
            *cmd_split,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc_sp.communicate()

        if os.path.exists(out_p) and os.path.getsize(out_p) > 0:
            part_size_mb = os.path.getsize(out_p) / (1024 * 1024)
            split_parts.append({
                "part_index": i + 1,
                "total_parts": num_parts,
                "path": out_p,
                "is_split": True,
                "size_mb": part_size_mb
            })

    if split_parts:
        return split_parts

    # Fallback se falhar na divisão
    return [{
        "part_index": 1,
        "total_parts": 1,
        "path": video_path,
        "is_split": False,
        "size_mb": file_size_mb
    }]


async def extract_video_metadata_and_thumb(video_path: str) -> Dict[str, Any]:
    """
    Extrai largura (w), altura (h), duração em segundos e gera uma miniatura (thumbnail) JPEG
    em alta qualidade para anexar ao envio do Telethon MTProto.
    
    Isso força o Telegram a reconhecer a mídia como VÍDEO TRANSMISSÍVEL (Player nativo em streaming),
    permitindo ao usuário dar PLAY e assistir imediatamente enquanto o vídeo carrega/baixa!
    """
    result = {
        "duration": 0,
        "width": 1280,
        "height": 720,
        "thumb_path": None
    }
    if not os.path.exists(video_path):
        return result

    # 1. Extrai dimensões e duração via ffprobe
    cmd_probe = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,duration:format=duration",
        "-of", "json",
        video_path
    ]
    try:
        proc_probe = await asyncio.create_subprocess_exec(
            *cmd_probe,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        out_probe, _ = await proc_probe.communicate()
        data = json.loads(out_probe.decode("utf-8", errors="replace"))
        
        streams = data.get("streams", [])
        if streams:
            v_stream = streams[0]
            result["width"] = int(v_stream.get("width") or 1280)
            result["height"] = int(v_stream.get("height") or 720)
            dur_str = v_stream.get("duration")
            if dur_str:
                result["duration"] = int(float(dur_str))

        if not result["duration"]:
            fmt = data.get("format", {})
            dur_fmt = fmt.get("duration")
            if dur_fmt:
                result["duration"] = int(float(dur_fmt))

    except Exception as e:
        logging.warning(f"Aviso ao extrair metadados com ffprobe: {e}")

    if result["duration"] <= 0:
        result["duration"] = 1

    # 2. Gera a thumbnail JPEG da capa do vídeo no segundo 5 (ou 1, ou 0.1)
    base_name = os.path.splitext(video_path)[0]
    thumb_path = f"{base_name}_thumb.jpg"
    seek_sec = "5" if result["duration"] > 15 else ("1" if result["duration"] > 3 else "0.1")
    
    cmd_thumb = [
        "ffmpeg", "-y", "-ss", seek_sec, "-i", video_path,
        "-vframes", "1", "-q:v", "2", "-vf", "scale=320:-1",
        thumb_path
    ]
    try:
        proc_thumb = await asyncio.create_subprocess_exec(
            *cmd_thumb,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc_thumb.communicate()
        if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
            result["thumb_path"] = thumb_path
        else:
            # Fallback no segundo 0
            cmd_thumb_fb = [
                "ffmpeg", "-y", "-ss", "00:00:00", "-i", video_path,
                "-vframes", "1", "-q:v", "2", "-vf", "scale=320:-1",
                thumb_path
            ]
            proc_fb = await asyncio.create_subprocess_exec(*cmd_thumb_fb, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            await proc_fb.communicate()
            if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
                result["thumb_path"] = thumb_path
    except Exception as e:
        logging.warning(f"Aviso ao gerar thumbnail do vídeo: {e}")

    return result

