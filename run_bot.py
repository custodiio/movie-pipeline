"""
Script de Inicialização do Bot do Telegram do Movie-Pipeline
Executa o bot em modo de polling contínuo para ouvir comandos e mensagens.
"""

import sys
import logging
from src.telegram_bot import create_telegram_bot_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

if __name__ == "__main__":
    logging.info("🚀 Iniciando Servidor do Bot do Telegram Movie-Pipeline...")
    try:
        app = create_telegram_bot_app()
        app.run_polling()
    except KeyboardInterrupt:
        logging.info("🛑 Bot do Telegram encerrado pelo usuário.")
    except Exception as e:
        logging.error(f"❌ Erro fatal no Bot do Telegram: {e}")
