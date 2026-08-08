"""
Script de Inicialização do Bot do Telegram do Movie-Pipeline
Executa o bot em modo de polling contínuo para ouvir comandos e mensagens.
"""

import sys
import asyncio
import logging
from src.telegram_bot import create_telegram_bot_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

async def main():
    app = create_telegram_bot_app()
    logging.info("🚀 Inicializando Bot do Telegram Movie-Pipeline...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    logging.info("🤖 Bot do Telegram rodando e ouvindo comandos no Telegram...")
    # Mantém a execução assíncrona ativa
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("🛑 Bot do Telegram encerrado pelo usuário.")
    except Exception as e:
        logging.error(f"❌ Erro no Bot do Telegram: {e}")
