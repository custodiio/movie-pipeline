"""
Hugging Face Spaces Entrypoint — Movie-Pipeline (alehcrim/faceless-pipeline)
Roda Gradio UI em background + Bot Telegram do Movie-Pipeline na Thread Principal.
# Reload trigger: 2026-08-14-telethon-string-added
"""

import sys
import os
import asyncio
import logging
import threading

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import gradio as gr
from dotenv import load_dotenv

load_dotenv()

from src.database import init_db
from src.telegram_bot import create_telegram_bot_app

# Compatibilidade com ZeroGPU do Hugging Face Spaces
try:
    import spaces
    @spaces.GPU
    def check_gpu():
        return "ZeroGPU Ready"
except Exception:
    pass

# Interface minimalista do Gradio para manter o Space ativo
with gr.Blocks(title="Movie-Pipeline Bot") as demo:
    gr.Markdown("# 🎬 Movie-Pipeline Bot & Automation")
    gr.Markdown("Status: **Online e Operacional** ✅")
    gr.Markdown("Servidor rodando em segundo plano integrado ao PostgreSQL (Neon.tech) e Telegram API.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    print("=" * 60)
    print("  Agente de Postagem - Movie-Pipeline (HF Spaces)")
    print("=" * 60)
    
    try:
        init_db()
        print("Tabela movie_pipeline_movies inicializada no Neon.tech!")
    except Exception as e:
        print(f"[AVISO] Falha ao inicializar DB: {e}")

    # Inicia a interface do Gradio sem bloquear a thread principal
    print("Iniciando Gradio UI na porta 7860...")
    demo.launch(server_name="0.0.0.0", server_port=7860, prevent_thread_lock=True)

    # Inicia o Bot do Telegram NA THREAD PRINCIPAL (obrigatorio para sinais do asyncio)
    print("Iniciando Bot Telegram Movie-Pipeline na Thread Principal...")
    app = create_telegram_bot_app()
    app.run_polling(drop_pending_updates=True)
