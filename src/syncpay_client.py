"""
Módulo Cliente da API SyncPay (Gateway de Pagamentos PIX)
Gerencia a autenticação OAuth2, geração de cobranças PIX Cash-In e verificação de status.
"""

import os
import time
import logging
import requests
from dotenv import load_dotenv

load_dotenv()

SYNCPAY_BASE_URL = os.getenv("SYNCPAY_BASE_URL", "https://api.syncpay.com.br").rstrip("/")
SYNCPAY_CLIENT_ID = os.getenv("SYNCPAY_CLIENT_ID", "")
SYNCPAY_CLIENT_SECRET = os.getenv("SYNCPAY_CLIENT_SECRET", "")

_token_cache = {
    "access_token": None,
    "expires_at": 0
}

def get_syncpay_token() -> str:
    """
    Obtém ou renova o Bearer Token de utilização da API SyncPay.
    Gera um novo token apenas quando o anterior expirar (validade 1h).
    """
    now = time.time()
    if _token_cache["access_token"] and now < _token_cache["expires_at"] - 60:
        return _token_cache["access_token"]

    if not SYNCPAY_CLIENT_ID or not SYNCPAY_CLIENT_SECRET:
        raise ValueError("SYNCPAY_CLIENT_ID e SYNCPAY_CLIENT_SECRET devem estar configurados no .env!")

    url = f"{SYNCPAY_BASE_URL}/api/partner/v1/auth-token"
    payload = {
        "client_id": SYNCPAY_CLIENT_ID,
        "client_secret": SYNCPAY_CLIENT_SECRET
    }
    headers = {"Content-Type": "application/json", "Accept": "application/json"}

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            expires_in = data.get("expires_in", 3600)
            _token_cache["access_token"] = token
            _token_cache["expires_at"] = now + expires_in
            logging.info("🔑 Token da API SyncPay gerado/renovado com sucesso!")
            return token
        else:
            logging.error(f"Erro ao autenticar na SyncPay [{response.status_code}]: {response.text}")
            raise RuntimeError(f"Erro de autenticação SyncPay: {response.text}")
    except Exception as e:
        logging.error(f"Exceção ao solicitar token SyncPay: {e}")
        raise e

def create_pix_cashin(
    amount: float,
    description: str = "Acesso VIP Filme",
    client_name: str = "Cliente Telegram",
    client_cpf: str = "12345678900",
    client_email: str = "cliente@telegram.com",
    client_phone: str = "64992430964",
    webhook_url: str = None
) -> dict:
    """
    Solicita um depósito via PIX (Cash-In) na SyncPay.
    Retorna um dicionário contendo:
      - pix_code: código PIX Copia e Cola / QR Code
      - identifier: UUID da transação para consultar status
      - message: mensagem de confirmação
    """
    token = get_syncpay_token()
    url = f"{SYNCPAY_BASE_URL}/api/partner/v1/cash-in"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    # Sanitização básica do CPF (somente dígitos, 11 caracteres)
    clean_cpf = "".join(filter(str.isdigit, str(client_cpf)))
    if len(clean_cpf) != 11:
        clean_cpf = "12345678900"

    # Sanitização do telefone (somente dígitos, exatamente 10 ou 11 dígitos sem DDI)
    clean_phone = "".join(filter(str.isdigit, str(client_phone)))
    if len(clean_phone) > 11:
        clean_phone = clean_phone[-11:]
    elif len(clean_phone) < 10:
        clean_phone = "64992430964"


    payload = {
        "amount": round(float(amount), 2),
        "description": description,
        "client": {
            "name": client_name if client_name else "Cliente Telegram",
            "cpf": clean_cpf,
            "email": client_email if client_email else "cliente@telegram.com",
            "phone": clean_phone
        }
    }

    if webhook_url:
        payload["webhook_url"] = webhook_url

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=20)
        if response.status_code == 200:
            res_data = response.json()
            logging.info(f"✅ PIX SyncPay gerado com sucesso! Identifier: {res_data.get('identifier')}")
            return {
                "success": True,
                "pix_code": res_data.get("pix_code"),
                "identifier": res_data.get("identifier"),
                "message": res_data.get("message")
            }
        else:
            logging.error(f"Erro ao solicitar PIX SyncPay [{response.status_code}]: {response.text}")
            return {
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text}"
            }
    except Exception as e:
        logging.error(f"Exceção ao gerar PIX SyncPay: {e}")
        return {"success": False, "error": str(e)}

def check_transaction_status(identifier: str) -> dict:
    """
    Consulta o status atual de uma transação na SyncPay via identifier (UUID).
    Retorna o status ('completed', 'pending', 'failed', 'refunded').
    """
    token = get_syncpay_token()
    url = f"{SYNCPAY_BASE_URL}/api/partner/v1/transaction/{identifier}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            res_data = response.json()
            data = res_data.get("data", {})
            status = data.get("status", "pending")
            return {
                "success": True,
                "status": status, # 'completed' quando o PIX for pago
                "amount": data.get("amount"),
                "transaction_date": data.get("transaction_date")
            }
        else:
            logging.error(f"Erro ao consultar transação {identifier} [{response.status_code}]: {response.text}")
            return {"success": False, "status": "unknown", "error": response.text}
    except Exception as e:
        logging.error(f"Exceção ao consultar status da transação {identifier}: {e}")
        return {"success": False, "status": "unknown", "error": str(e)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("🧪 Testando autenticação na API SyncPay...")
    try:
        tok = get_syncpay_token()
        print("✅ Token obtido com sucesso!")
        print("🧪 Testando solicitação de PIX CashIn...")
        pix_res = create_pix_cashin(amount=5.00, description="Teste de Cobrança PIX SyncPay")
        print("Resultado PIX:", pix_res)
    except Exception as err:
        print("❌ Erro no teste:", err)
