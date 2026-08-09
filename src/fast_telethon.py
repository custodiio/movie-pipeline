"""
Módulo FastTelethon para Download e Upload Paralelo em 32 Chunks Concorrentes.
Utiliza Fila Assíncrona (asyncio.Queue) e conexões otimizadas para velocidade máxima no Telegram.
"""

import os
import math
import asyncio
import time
from typing import Callable, Optional
from telethon import TelegramClient
from telethon.tl.functions.upload import GetFileRequest
from telethon.tl.types import Document, MessageMediaDocument, InputDocumentFileLocation

CHUNK_SIZE = 512 * 1024  # 512 KB por parte (máximo do MTProto)
PARALLEL_WORKERS = 32    # 32 pedaços paralelos simultâneos

async def download_file_parallel(
    client: TelegramClient,
    msg_or_media,
    out_filepath: str,
    progress_callback: Optional[Callable] = None,
    workers_count: int = 32
) -> str:
    """
    Baixa mídia do Telegram dividindo o arquivo em 32 partes concorrentes usando fila assíncrona.
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

    # Pre-aloca o arquivo no disco com o tamanho total exato
    with open(out_filepath, "wb") as f:
        f.truncate(total_size)

    # Preenche a fila de chunks
    queue = asyncio.Queue()
    for i in range(total_chunks):
        queue.put_nowait(i)

    downloaded_bytes = 0
    lock = asyncio.Lock()

    # Prepara os senders exportados para o DC exato do arquivo
    senders = []
    for _ in range(min(workers_count, total_chunks)):
        try:
            sender = await client._borrow_sender(dc_id)
            senders.append(sender)
        except Exception:
            break

    if not senders:
        return await client.download_media(msg_or_media, file=out_filepath, progress_callback=progress_callback)

    async def worker(sender):
        nonlocal downloaded_bytes
        while not queue.empty():
            try:
                chunk_index = queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            offset = chunk_index * CHUNK_SIZE
            limit = min(CHUNK_SIZE, total_size - offset)

            success = False
            for attempt in range(3):
                try:
                    result = await sender.send(GetFileRequest(
                        location=location,
                        offset=offset,
                        limit=limit
                    ))
                    chunk_data = result.bytes
                    if chunk_data:
                        with open(out_filepath, "rb+") as f:
                            f.seek(offset)
                            f.write(chunk_data)

                        async with lock:
                            downloaded_bytes += len(chunk_data)
                            if progress_callback:
                                progress_callback(downloaded_bytes, total_size)
                        success = True
                        break
                except Exception:
                    await asyncio.sleep(0.2)

            if not success:
                # Se falhar, coloca o bloco de volta na fila
                queue.put_nowait(chunk_index)

            queue.task_done()

    try:
        workers = [asyncio.create_task(worker(s)) for s in senders]
        await asyncio.gather(*workers)
    finally:
        for s in senders:
            try:
                await client._return_sender(s)
            except Exception:
                pass

    return out_filepath
