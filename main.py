"""
Ponto de Entrada do Pipeline (Main Orchestrator)

Orquestra todas as etapas do Movie-Pipeline na VPS/Servidor.
"""

import sys
import os
import logging

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from src.movie_selector import get_next_unposted_movie
from src.image_downloader import download_images_for_movie
from src.drive_uploader import get_drive_service, limpar_temporarios_drive, upload_pasta_projeto
from src.script_generator import generate_detailed_movie_script
from src.omni_tts import generate_voiceover_parallel
from src.video_editor import render_movie_video

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

from src.database import update_movie_status

def main():
    print("\n🚀 ========================================================")
    print("   INICIANDO MOVIE-PIPELINE DE AUTOMATION DE VÍDEO")
    print("========================================================\n")
    
    # 0. Conexão ao Google Drive & Limpeza Inicial (preservando Assets/)
    drive = get_drive_service()
    if drive:
        logging.info("Limpando arquivos temporários anteriores no Google Drive (Assets preservados)...")
        limpar_temporarios_drive(drive)

    # 1. Selecionar o próximo filme em alta não postado & gerar TXT
    filme = get_next_unposted_movie()
    if not filme:
        print("⚠️ Nenhum filme pendente para processamento no momento.")
        return

    print("\n" + "="*60)
    print("🎬 FILME SELECIONADO PARA PRODUÇÃO:")
    print(f"📌 Título: {filme['title']}")
    print(f"🔑 Slug: {filme['slug']}")
    print(f"📅 Lançamento: {filme['release_date']}")
    print(f"📄 Arquivo TXT Gerado: {filme['txt_path']}")
    print("="*60 + "\n")

    # 2. Download e filtragem de imagens (mínimo 30, máximo 150 imagens 16:9 / 1:1)
    imagens = download_images_for_movie(filme, min_images=30, max_images=150)
    
    # 3. Upload da pasta do projeto pro Google Drive
    if drive:
        local_project_dir = os.path.join("temp", filme['slug'])
        logging.info(f"Subindo dados do projeto para o Drive (Movie-Pipeline/Projetos/{filme['slug']})...")
        upload_pasta_projeto(drive, filme['slug'], local_project_dir)

    # 4. Gerar Roteiro / Review Detalhada por IA (Gemini API)
    roteiro = generate_detailed_movie_script(filme)

    # 5. Síntese de Voz Paralela via Omni TTS (2 blocos simultâneos)
    audio_narracao = generate_voiceover_parallel(roteiro, output_dir=os.path.join("temp", filme['slug']))

    # 6. Renderização do Vídeo Final (Intro + Slideshow + Marca d'Água DVD Bounce)
    video_final = render_movie_video(
        slug=filme['slug'],
        images=imagens,
        voiceover_path=audio_narracao,
        output_dir="output"
    )

    # 7. Atualização do Status para 'concluido' no Banco SQLite
    if filme and filme.get("tmdb_id"):
        update_movie_status(filme["tmdb_id"], "concluido")
        logging.info(f"✅ Status do filme '{filme['title']}' atualizado para 'concluido' no banco SQLite!")

    print("\n🎉 ========================================================")
    print(f"   VÍDEO FINAL RENDERIZADO COM SUCESSO: {video_final}")
    print("========================================================\n")


if __name__ == "__main__":
    main()

