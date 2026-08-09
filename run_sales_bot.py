"""
Script de Inicialização do Bot de Vendas SyncPay PIX (@telacheiafilmes_bot)
"""

import asyncio
import logging
from src.sales_bot import main

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    logging.info("Inicializando Bot de Vendas SyncPay PIX (@telacheiafilmes_bot)...")
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot de vendas encerrado.")

