"""
Módulo de Síntese de Voz Paralela via Omni TTS com Clonagem de Voz

Busca o áudio de referência para clonagem na pasta Movie-Pipeline/Assets/Clonagem/
e gera a narração em 2 blocos simultâneos (ThreadPoolExecutor).
"""

import os
import glob
import logging
from concurrent.futures import ThreadPoolExecutor
from pydub import AudioSegment
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

CLONAGEM_DIR_DEFAULT = os.getenv("CLONAGEM_DIR", r"D:\Applications\Movie-Pipeline\Assets\Clonagem")

def get_reference_audio(clonagem_dir: str = CLONAGEM_DIR_DEFAULT, nome_narrador: str = "") -> str:
    """Busca o áudio de referência de clonagem na pasta de ativos."""
    if not os.path.exists(clonagem_dir):
        # Tenta buscar caminho relativo
        clonagem_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Assets", "Clonagem")
        os.makedirs(clonagem_dir, exist_ok=True)

    audio_files = glob.glob(os.path.join(clonagem_dir, "*.mp3")) + glob.glob(os.path.join(clonagem_dir, "*.wav"))
    
    if not audio_files:
        logging.warning(f"Nenhum áudio de clonagem (.mp3/.wav) encontrado em '{clonagem_dir}'.")
        return ""

    if nome_narrador:
        for f in audio_files:
            if nome_narrador.lower() in os.path.basename(f).lower():
                logging.info(f"Áudio de clonagem correspondente encontrado: {f}")
                return f

    # Retorna o primeiro disponível se não houver filtro de nome
    selected = audio_files[0]
    logging.info(f"Áudio de clonagem selecionado: {selected}")
    return selected

def split_text_into_two_chunks(text: str) -> tuple[str, str]:
    """Divide o texto do roteiro na metade respeitando parágrafos e pontuação."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if len(paragraphs) <= 1:
        sentences = [s.strip() for s in text.split(". ") if s.strip()]
        mid = max(1, len(sentences) // 2)
        chunk1 = ". ".join(sentences[:mid]) + "."
        chunk2 = ". ".join(sentences[mid:])
        return chunk1, chunk2
    
    mid = max(1, len(paragraphs) // 2)
    chunk1 = "\n\n".join(paragraphs[:mid])
    chunk2 = "\n\n".join(paragraphs[mid:])
    return chunk1, chunk2

def synthesize_audio_block(block_idx: int, text: str, ref_audio_path: str, output_dir: str, omnivoice_port: int = 8001) -> str:
    """Sintetiza um bloco de texto individual clonando a voz informada via OmniVoice ou fallback."""
    out_file = os.path.join(output_dir, f"audio_block_{block_idx}.wav")
    logging.info(f"[Bloco {block_idx}] Iniciando síntese ({len(text)} caracteres)...")

    # 1. Tentativa via Servidor local OmniVoice / Gradio API
    if ref_audio_path and os.path.exists(ref_audio_path):
        try:
            from gradio_client import Client, handle_file
            client = Client(f"http://127.0.0.1:{omnivoice_port}/")
            logging.info(f"[Bloco {block_idx}] Enviando requisição de clonagem para o OmniVoice (Porta {omnivoice_port})...")
            res = client.predict(
                ref_audio=handle_file(ref_audio_path),
                gen_text=text,
                api_name="/generate_audio"
            )
            if res and os.path.exists(res):
                sound = AudioSegment.from_file(res)
                sound.export(out_file, format="wav")
                logging.info(f"[Bloco {block_idx}] Síntese OmniVoice concluída com sucesso!")
                return out_file
        except Exception as e:
            logging.warning(f"[Bloco {block_idx}] OmniVoice (Porta {omnivoice_port}) não respondeu ({e}). Usando fallback TTS...")

    # 2. Fallback Edge-TTS
    try:
        import asyncio
        import edge_tts
        
        async def _run_edge():
            communicate = edge_tts.Communicate(text, "pt-BR-AntonioNeural")
            mp3_out = os.path.join(output_dir, f"audio_block_{block_idx}.mp3")
            await communicate.save(mp3_out)
            sound = AudioSegment.from_file(mp3_out)
            sound.export(out_file, format="wav")
            if os.path.exists(mp3_out): os.remove(mp3_out)

        asyncio.run(_run_edge())
        logging.info(f"[Bloco {block_idx}] Concluído via Edge-TTS (pt-BR-AntonioNeural).")
        return out_file
    except Exception as err:
        logging.error(f"[Bloco {block_idx}] Edge-TTS falhou: {err}")

    # 3. Fallback gTTS
    from gtts import gTTS
    tts = gTTS(text=text, lang="pt", slow=False)
    mp3_out = os.path.join(output_dir, f"audio_block_{block_idx}.mp3")
    tts.save(mp3_out)
    sound = AudioSegment.from_file(mp3_out)
    sound.export(out_file, format="wav")
    if os.path.exists(mp3_out): os.remove(mp3_out)
    return out_file

def generate_voiceover_parallel(script_text: str, nome_narrador: str = "", output_dir: str = "temp") -> str:
    """
    Localiza o áudio de clonagem, divide o roteiro em 2 blocos e executa a síntese de voz
    simultaneamente em 2 threads em paralelo nas portas OmniVoice (8001 e 8002).
    
    Returns:
        str: Caminho do arquivo de áudio final concatenado (narracao_final.wav).
    """
    os.makedirs(output_dir, exist_ok=True)
    final_audio_path = os.path.join(output_dir, "narracao_final.wav")

    # Localiza o áudio de clonagem de voz
    ref_audio = get_reference_audio(nome_narrador=nome_narrador)
    
    chunk1, chunk2 = split_text_into_two_chunks(script_text)
    logging.info(f"Iniciando narração em 2 blocos simultâneos (Bloco 1: {len(chunk1)} chars | Bloco 2: {len(chunk2)} chars)...")

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(synthesize_audio_block, 1, chunk1, ref_audio, output_dir, 8001)
        f2 = executor.submit(synthesize_audio_block, 2, chunk2, ref_audio, output_dir, 8002)
        
        file1 = f1.result()
        file2 = f2.result()

    logging.info("Unindo blocos de áudio de narração sintetizados...")
    audio1 = AudioSegment.from_file(file1)
    audio2 = AudioSegment.from_file(file2)
    
    pause = AudioSegment.silent(duration=400)
    combined = audio1 + pause + audio2
    combined.export(final_audio_path, format="wav")
    
    for f in [file1, file2]:
        if os.path.exists(f): os.remove(f)

    logging.info(f"Áudio final de narração gerado em: {final_audio_path} ({len(combined)/1000.0:.2f}s).")
    return final_audio_path
