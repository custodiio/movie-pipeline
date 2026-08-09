"""
Módulo FastTelethon (Parallel Transferer) de Alta Velocidade para Telethon.
Abre até 32 conexões MTProto paralelas independentes com o Data Center do arquivo,
multiplicando a velocidade de download/upload por até 20x.
"""

import os
import math
import asyncio
import time
from typing import Callable, Optional
from telethon import TelegramClient
from telethon.tl.functions.upload import GetFileRequest
from telethon.tl.types import Document, MessageMediaDocument, InputDocumentFileLocation

CHUNK_SIZE = 512 * 1024  # 512 KB por chunk (tamanho máximo permitido pelo Telegram)
DEFAULT_CONNECTIONS = 32 # 32 conexões paralelas simultâneas

async def _get_dc_client(client: TelegramClient, dc_id: int):
    """
    Obtém uma conexão de remetente (sender) para o Data Center específico onde o arquivo está armazenado.
    """
    try:
        sender = await client._borrow_sender(dc_id)
        return sender
    except Exception:
        return client._sender

async def download_file_parallel(
    client: TelegramClient,
    msg_or_media,
    out_filepath: str,
    progress_callback: Optional[Callable] = None,
    workers_count: int = 32
) -> str:
    """
    Baixa o arquivo do Telegram em paralelo dividindo a transferência entre 32 conexões MTProto.
    O progresso reportado ao callback é o TOTAL ACUMULADO de todos os 32 pedaços somados.
    """
    if hasattr(msg_or_media, 'media') and msg_or_media.media:
        media = msg_or_media.media
    else:
        media = msg_or_media

    if isinstance(media, MessageMediaDocument):
        doc = media.document
    elif isinstance(media, Document):
        doc = media
    else:
        return await client.download_media(msg_or_media, file=out_filepath, progress_callback=progress_callback)

    if not isinstance(doc, Document):
        return await client.download_media(msg_or_media, file=out_filepath, progress_callback=progress_callback)

    total_size = doc.size
    total_chunks = math.ceil(total_size / CHUNK_SIZE)
    dc_id = doc.dc_id

    location = InputDocumentFileLocation(
        id=doc.id,
        access_hash=doc.access_hash,
        file_reference=doc.file_reference,
        thumb_size=""
    )

    # Pre-aloca o arquivo com o tamanho total exato
    with open(out_filepath, "wb") as f:
        f.truncate(total_size)

    # Cria conexões paralelas com o Data Center correto (DC_ID)
    senders = []
    conns_needed = min(workers_count, total_chunks)
    
    for _ in range(conns_needed):
        try:
            s = await client._borrow_sender(dc_id)
            senders.append(s)
        except Exception:
            break

    if not senders:
        senders = [client._sender]

    num_senders = len(senders)
    downloaded_bytes = 0
    lock = asyncio.Lock()

    queue = asyncio.Queue()
    for i in range(total_chunks):
        queue.put_nowait(i)

    async def worker_loop(sender):
        nonlocal downloaded_bytes
        while not queue.empty():
            try:
                chunk_index = queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            offset = chunk_index * CHUNK_SIZE
            limit = min(CHUNK_SIZE, total_size - offset)

            download_success = False
            for retry in range(3):
                try:
                    res = await sender.send(GetFileRequest(
                        location=location,
                        offset=offset,
                        limit=limit
                    ))
                    chunk_bytes = res.bytes
                    if chunk_bytes:
                        # Grava na posição relativa exata do arquivo no disco
                        with open(out_filepath, "rb+") as f:
                            f.seek(offset)
                            f.write(chunk_bytes)

                        async with lock:
                            downloaded_bytes += len(chunk_bytes)
                            if progress_callback:
                                # Reporta o TOTAL acumulado de todos os pedacos baixados
                                progress_callback(downloaded_bytes, total_size)
                        download_success = True
                        break
                except Exception:
                    await asyncio.sleep(0.1)

            if not download_success:
                # Reenfileira o pedaço em caso de falha
                queue.put_nowait(chunk_index)

            queue.task_done()

    try:
        tasks = [asyncio.create_task(worker_loop(s)) for s in senders]
        await asyncio.gather(*tasks)
    finally:
        for s in senders:
            if s != client._sender:
                try:
                    await client._return_sender(s)
                except Exception:
                    pass

    return out_filepath
