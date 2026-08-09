"""
Bot Dedicado de Vendas Automáticas via PIX SyncPay (@telacheiafilmes_bot)
Processa pagamentos PIX instantâneos e gerencia a liberação automática de links de convite para o Canal VIP.
"""

import os
import asyncio
import logging
from typing import Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler
)
from dotenv import load_dotenv

from src.syncpay_client import create_pix_cashin, check_transaction_status

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

SALES_BOT_TOKEN = os.getenv("SALES_BOT_TOKEN")


raw_vip_id = os.getenv("TELEGRAM_VIP_CHANNEL_ID", "0")
try:
    TELEGRAM_VIP_CHANNEL_ID = int(raw_vip_id)
except ValueError:
    TELEGRAM_VIP_CHANNEL_ID = raw_vip_id

ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID") or os.getenv("TELEGRAM_ADMIN_ID", "0"))

STATE_IDLE = 0
STATE_WAITING_PAYMENT = 1


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start do Bot de Vendas."""
    user = update.effective_user
    context.user_data.clear()

    welcome_text = (
        f"🍿 **Olá, {user.first_name}! Seja muito bem-vindo ao Tela Cheia Filmes VIP!**\n\n"
        f"Garanta agora mesmo o seu **Acesso Vitalício ao Canal VIP** para assistir e baixar "
        f"todos os Lançamentos de Filmes e Séries em **4K ULTRA HD, Áudio Dual (Dublado/Legendado)** sem anúncios!\n\n"
        f"💰 **Valor Promocional:** Apenas **R$ 10,00** (Pagamento Único)\n"
        f"⚡ **Liberação:** Automática e Imediata via PIX\n\n"
        f"Clique no botão abaixo para gerar o seu **PIX Copia e Cola**:"
    )

    keyboard = [
        [InlineKeyboardButton("⚡ Comprar Acesso VIP (R$ 10,00) via PIX", callback_data="generate_pix")],
        [InlineKeyboardButton("💬 Falar com Suporte Humano", url="https://t.me/leh_lurdes")]
    ]

    await update.message.reply_text(
        welcome_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return STATE_IDLE


async def generate_pix_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gera o PIX Copia e Cola via API SyncPay ao clicar no botão."""
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    await query.edit_message_text("⏳ **Gerando seu código PIX seguro na SyncPay... Por favor, aguarde a chave Copia e Cola.**", parse_mode="Markdown")

    client_name = user.full_name if user.full_name else f"Cliente_{user.id}"
    username_str = f"_{user.username}" if user.username else ""
    client_email = f"user{user.id}{username_str}@telegram.com".replace("_", "")

    # Tenta usar o telefone real capturado do usuário ou envia None para usar a sanitização dinâmica
    client_phone = context.user_data.get("user_phone", None)

    # Gera o PIX na API SyncPay
    pix_res = create_pix_cashin(
        amount=10.00,
        description="Acesso VIP Tela Cheia Filmes",
        client_name=client_name,
        client_email=client_email,
        client_phone=client_phone
    )



    if not pix_res.get("success"):
        error_msg = pix_res.get("error", "Erro desconhecido")
        keyboard = [
            [InlineKeyboardButton("🔄 Tentar Novamente", callback_data="generate_pix")],
            [InlineKeyboardButton("💬 Falar com Suporte Humano", url="https://t.me/leh_lurdes")]
        ]
        await query.edit_message_text(
            f"❌ **Não foi possível gerar a chave PIX no momento.**\n\n_{error_msg}_\n\n"
            f"Por favor, tente novamente ou contate o suporte.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return STATE_IDLE

    pix_code = pix_res["pix_code"]
    identifier = pix_res["identifier"]

    context.user_data["pix_identifier"] = identifier
    context.user_data["pix_code"] = pix_code

    pix_instructions = (
        f"💎 **PIX GERADO COM SUCESSO!**\n\n"
        f"📌 **Valor:** R$ 10,00\n"
        f"📌 **Produto:** Acesso VIP Vitalício Tela Cheia Filmes\n\n"
        f"👇 **Código PIX Copia e Cola:** (Toque no código abaixo para copiar)\n\n"
        f"`{pix_code}`\n\n"
        f"⚡ **Como Pagar:**\n"
        f"1️⃣ Abra o aplicativo do seu Banco ou NuBank\n"
        f"2️⃣ Escolha a opção **PIX Copia e Cola**\n"
        f"3️⃣ Cole o código acima e confirme o pagamento de **R$ 10,00**\n\n"
        f"✨ *Assim que você concluir o pagamento, o seu link de acesso ao Canal VIP será liberado automaticamente aqui no chat!*"
    )

    keyboard = [
        [InlineKeyboardButton("✅ Já Paguei / Verificar Pagamento", callback_data="check_pix")],
        [InlineKeyboardButton("💬 Suporte / Falar com Atendente", url="https://t.me/leh_lurdes")],
        [InlineKeyboardButton("❌ Cancelar", callback_data="cancel_order")]
    ]

    await query.message.reply_text(
        pix_instructions,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

    # Inicia tarefa em background para checar o status do PIX periodicamente (até 15 minutos)
    chat_id = update.effective_chat.id
    user_id = user.id
    user_name = user.full_name or f"User_{user.id}"

    asyncio.create_task(auto_check_pix_loop(context.application, chat_id, user_id, user_name, identifier))

    return STATE_WAITING_PAYMENT


async def check_pix_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Checagem manual do PIX solicitada pelo usuário ao clicar no botão 'Já Paguei'."""
    query = update.callback_query
    await query.answer()

    identifier = context.user_data.get("pix_identifier")
    if not identifier:
        await query.edit_message_text("❌ Nenhuma cobrança ativa encontrada. Digite /start para iniciar uma nova compra.")
        return STATE_IDLE

    await query.answer("🔎 Consultando o sistema de pagamentos SyncPay...")

    res = check_transaction_status(identifier)
    status = res.get("status", "pending")

    if status in ["completed", "paid"]:
        await deliver_vip_access(context.application, update.effective_chat.id, update.effective_user.id, update.effective_user.full_name, identifier)
        return STATE_IDLE
    else:
        keyboard = [
            [InlineKeyboardButton("✅ Já Paguei / Verificar Novamente", callback_data="check_pix")],
            [InlineKeyboardButton("💬 Falar com Suporte Humano", url="https://t.me/leh_lurdes")]
        ]
        await query.message.reply_text(
            f"⏳ **Pagamento ainda em processamento!**\n\n"
            f"O banco ainda não confirmou o recebimento do PIX. "
            f"Geralmente leva alguns segundos após você concluir no app do seu banco.\n\n"
            f"Por favor, aguarde um instante e clique em **Verificar Novamente**.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return STATE_WAITING_PAYMENT


async def cancel_order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela o pedido atual."""
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.edit_message_text("❌ **Pedido cancelado.** Digite /start caso deseje realizar um novo pedido.")
    return STATE_IDLE


async def deliver_vip_access(app: Application, chat_id: int, user_id: int, user_name: str, identifier: str):
    """Entrega o link de acesso VIP exclusivo ao cliente e notifica o administrador."""
    invite_link = None
    try:
        # Gera um link de convite exclusivo e de uso único (1 pessoa) para o Canal VIP
        link_obj = await app.bot.create_chat_invite_link(
            chat_id=TELEGRAM_VIP_CHANNEL_ID,
            member_limit=1,
            name=f"Venda PIX - {user_name}"
        )
        invite_link = link_obj.invite_link
    except Exception as e:
        logging.error(f"Erro ao gerar link de convite único via Bot API: {e}")
        # Fallback de link genérico se houver permissão
        invite_link = "https://t.me/+o8H2Q..."

    success_text = (
        f"🎉 **PAGAMENTO CONFIRMADO COM SUCESSO!**\n\n"
        f"Parabéns, {user_name}! Seu pagamento via PIX foi aprovado instantaneamente pela SyncPay.\n\n"
        f"🍿 **Seu Acesso ao Canal VIP está Liberado!**\n"
        f"Clique no botão abaixo para entrar agora mesmo:"
    )

    keyboard = [
        [InlineKeyboardButton("🚀 ENTRAR NO CANAL VIP AGORA", url=invite_link)],
        [InlineKeyboardButton("💬 Suporte Humano", url="https://t.me/leh_lurdes")]
    ]

    await app.bot.send_message(
        chat_id=chat_id,
        text=success_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

    # Notifica o administrador do sistema
    try:
        admin_notify = (
            f"💰 **NOVA VENDA REALIZADA COM SUCESSO!**\n\n"
            f"👤 **Cliente:** {user_name} (ID: `{user_id}`)\n"
            f"💵 **Valor:** R$ 10,00 (PIX SyncPay)\n"
            f"🆔 **Transação:** `{identifier}`\n"
            f"🔗 **Convite Gerado:** {invite_link}"
        )
        await app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_notify, parse_mode="Markdown")
    except Exception as err:
        logging.warning(f"Não foi possível notificar admin {ADMIN_CHAT_ID}: {err}")



async def auto_check_pix_loop(app: Application, chat_id: int, user_id: int, user_name: str, identifier: str):
    """Checa automaticamente a transação SyncPay a cada 10 segundos por até 15 minutos."""
    max_checks = 90  # 90 tentativas * 10s = 15 minutos
    for _ in range(max_checks):
        await asyncio.sleep(10)
        res = check_transaction_status(identifier)
        status = res.get("status", "pending")
        if status in ["completed", "paid"]:
            await deliver_vip_access(app, chat_id, user_id, user_name, identifier)
            break


def create_sales_bot_app() -> Application:
    """Cria e configura o bot de vendas da classe Application."""
    if not SALES_BOT_TOKEN:
        raise ValueError("SALES_BOT_TOKEN não foi encontrado no arquivo .env!")

    app = Application.builder().token(SALES_BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start_handler),
            CallbackQueryHandler(generate_pix_callback, pattern="^generate_pix$")
        ],
        states={
            STATE_IDLE: [
                CallbackQueryHandler(generate_pix_callback, pattern="^generate_pix$")
            ],
            STATE_WAITING_PAYMENT: [
                CallbackQueryHandler(check_pix_callback, pattern="^check_pix$"),
                CallbackQueryHandler(cancel_order_callback, pattern="^cancel_order$"),
                CallbackQueryHandler(generate_pix_callback, pattern="^generate_pix$")
            ]
        },
        fallbacks=[CommandHandler("start", start_handler)]
    )

    app.add_handler(conv_handler)
    return app


async def main():
    """Função principal assíncrona para rodar o bot de vendas."""
    logging.info("Iniciando o Bot de Vendas SyncPay (@telacheiafilmes_bot)...")
    app = create_sales_bot_app()
    await app.initialize()

    # Configura a mensagem de saudação oficial exibida no centro da tela ANTES de apertar START
    bot_description = (
        "🍿 Bem-vindo ao Tela Cheia Filmes VIP!\n\n"
        "Garanta o seu Acesso Vitalício em 4K Ultra HD com Áudio Dual (Dublado/Legendado) sem anúncios por apenas R$ 10,00 (Pagamento Único).\n\n"
        "👉 Clique no botão INICIAR (START) abaixo para gerar seu PIX instantâneo e receber o convite do Canal VIP!"
    )
    bot_short_desc = "🍿 Tela Cheia Filmes VIP - Acesso Vitalício por R$ 10,00 via PIX Automático."

    try:
        await app.bot.set_my_description(bot_description)
        await app.bot.set_my_short_description(bot_short_desc)
        logging.info("✅ Mensagem de saudação exibida antes do START configurada com sucesso!")
    except Exception as e:
        logging.warning(f"Não foi possível definir descrição do bot: {e}")

    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    logging.info("Bot de Vendas @telacheiafilmes_bot rodando com sucesso em polling!")

    while True:
        await asyncio.sleep(3600)



if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot de vendas parado pelo usuário.")
