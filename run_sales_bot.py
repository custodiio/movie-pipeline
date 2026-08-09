"""
Script de Inicialização do Bot de Vendas SyncPay PIX (@telacheiafilmes_bot)
Inclui Servidor HTTP Health Check e Auto-Ping (Keep-Alive a cada 4 minutos) para rodar 24/7 sem dormir no Render.
"""

import os
import time
import asyncio
import logging
import threading
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from src.sales_bot import main

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class HealthCheckHandler(BaseHTTPRequestHandler):
    """Handler HTTP ultra leve para pings de Keep-Alive e Health Checks de plataformas Cloud."""
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"OK - Bot de Vendas SyncPay Ativo 24/7!")

    def log_message(self, format, *args):
        # Silencia o log de cada requisição HTTP de ping para evitar poluição
        pass


def start_http_server():
    """Inicia servidor HTTP na porta dinâmica da nuvem (Render/Koyeb/Railway) ou porta 8080."""
    port = int(os.getenv("PORT", "8080"))
    try:
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        logging.info(f"🌐 Servidor Health Check Keep-Alive ouvindo na porta {port}...")
        server.serve_forever()
    except Exception as e:
        logging.error(f"Erro ao iniciar servidor HTTP Keep-Alive: {e}")


def auto_ping_loop():
    """Loop em thread separada que dispara pings HTTP para o próprio bot a cada 4 minutos."""
    ping_url = os.getenv("RENDER_EXTERNAL_URL") or os.getenv("PING_URL")
    if not ping_url:
        logging.info("ℹ️ RENDER_EXTERNAL_URL/PING_URL não configurado. Auto-ping interno inativo (use UptimeRobot ou Render Health Check).")
        return

    if not ping_url.endswith("/"):
        ping_url += "/"
    
    logging.info(f"🔄 Auto-ping Keep-Alive configurado para {ping_url} a cada 4 minutos...")
    time.sleep(15)  # Aguarda a subida inicial da aplicação

    while True:
        try:
            res = requests.get(ping_url, timeout=10)
            logging.info(f"💓 [Keep-Alive 24/7] Auto-ping enviado com sucesso: HTTP {res.status_code}")
        except Exception as e:
            logging.warning(f"⚠️ [Keep-Alive] Erro no auto-ping: {e}")
        time.sleep(240)  # 4 minutos


if __name__ == "__main__":
    logging.info("🚀 Inicializando Bot de Vendas SyncPay PIX (@telacheiafilmes_bot)...")

    # Inicia o servidor HTTP em background
    http_thread = threading.Thread(target=start_http_server, daemon=True)
    http_thread.start()

    # Inicia o loop de auto-ping em background
    ping_thread = threading.Thread(target=auto_ping_loop, daemon=True)
    ping_thread.start()

    # Inicia a execução do bot do Telegram
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot de vendas encerrado.")


