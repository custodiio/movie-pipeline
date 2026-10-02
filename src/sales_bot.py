"""
Bot Dedicado de Vendas Automáticas via PIX SyncPay (@telacheiafilmes_bot)
Processa pagamentos PIX instantâneos e gerencia a liberação automática de links de convite para o Canal VIP.
"""

import os
import asyncio
import logging
import html
import time
import requests
from typing import Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
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

SUPPORT_USERNAME = os.getenv("TELEGRAM_SALES_USERNAME", "leh_lurdes").replace("@", "").strip()
SUPPORT_URL = f"https://t.me/{SUPPORT_USERNAME}"

raw_vip_id = str(os.getenv("TELEGRAM_VIP_CHANNEL_ID", "-1003917174917")).strip("'\" \t\r\n")
try:
    TELEGRAM_VIP_CHANNEL_ID = int(raw_vip_id)
except ValueError:
    TELEGRAM_VIP_CHANNEL_ID = raw_vip_id

try:
    ADMIN_CHAT_ID = int(str(os.getenv("ADMIN_CHAT_ID") or os.getenv("TELEGRAM_ADMIN_ID", "0")).strip("'\" \t\r\n") or 0)
except ValueError:
    ADMIN_CHAT_ID = 0

STATE_IDLE = 0
STATE_WAITING_PAYMENT = 1


async def safe_send_message(bot, chat_id: int, text: str, reply_markup=None, parse_mode: str = "HTML"):
    """
    Envia mensagem com suporte a formatação HTML e fallback garantido para texto puro
    caso ocorra qualquer erro de parsing de entidades no Telegram.
    """
    try:
        return await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception as err:
        logging.warning(f"Aviso ao enviar mensagem com parse_mode={parse_mode}: {err}. Tentando texto puro...")
        try:
            import re
            clean_text = re.sub(r"<[^>]+>", "", text)
            return await bot.send_message(chat_id=chat_id, text=clean_text, reply_markup=reply_markup)
        except Exception as final_err:
            logging.error(f"Erro fatal ao enviar mensagem para chat_id {chat_id}: {final_err}")
            return None


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start do Bot de Vendas."""
    user = update.effective_user
    context.user_data.clear()

    safe_first_name = html.escape(user.first_name or "Amigo(a)")
    welcome_text = (
        f"🍿 <b>Olá, {safe_first_name}! Seja muito bem-vindo ao Tela Cheia Filmes VIP!</b>\n\n"
        f"Garanta agora mesmo o seu <b>Acesso Vitalício ao Canal VIP</b> para assistir e baixar "
        f"todos os Lançamentos de Filmes e Séries em <b>4K ULTRA HD, Áudio Dual (Dublado/Legendado)</b> sem anúncios!\n\n"
        f"💰 <b>Valor Promocional:</b> Apenas <b>R$ 10,00</b> (Pagamento Único)\n"
        f"⚡ <b>Liberação:</b> Automática e Imediata via PIX\n\n"
        f"Clique no botão abaixo para gerar o seu <b>PIX Copia e Cola</b>:"
    )

    keyboard = [
        [InlineKeyboardButton("⚡ Comprar Acesso VIP (R$ 10,00) via PIX", callback_data="generate_pix")],
        [InlineKeyboardButton("💬 Falar com Suporte Humano", url=SUPPORT_URL)]
    ]

    await safe_send_message(
        update.get_bot(),
        update.effective_chat.id,
        welcome_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
    return STATE_IDLE


async def generate_pix_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gera o PIX Copia e Cola via API SyncPay ao clicar no botão."""
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    try:
        await query.edit_message_text(
            "⏳ <b>Gerando seu código PIX seguro na SyncPay... Por favor, aguarde a chave Copia e Cola.</b>",
            parse_mode="HTML"
        )
    except Exception:
        pass

    try:
        client_name = user.full_name if user.full_name else f"Cliente_{user.id}"
        username_str = f"_{user.username}" if user.username else ""
        client_email = f"user{user.id}{username_str}@telegram.com".replace("_", "")

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
            error_msg = pix_res.get("error", "Erro ao gerar PIX")
            keyboard = [
                [InlineKeyboardButton("🔄 Tentar Novamente", callback_data="generate_pix")],
                [InlineKeyboardButton("💬 Falar com Suporte Humano", url=SUPPORT_URL)]
            ]
            await query.message.reply_text(
                f"❌ <b>Não foi possível gerar a chave PIX no momento.</b>\n\n<i>{html.escape(str(error_msg))}</i>\n\n"
                f"Por favor, tente novamente ou fale com o nosso suporte:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML"
            )
            return STATE_IDLE

        pix_code = pix_res["pix_code"]
        identifier = pix_res["identifier"]

        context.user_data["pix_identifier"] = identifier
        context.user_data["pix_code"] = pix_code

        pix_instructions = (
            f"💎 <b>PIX GERADO COM SUCESSO!</b>\n\n"
            f"📌 <b>Valor:</b> R$ 10,00\n"
            f"📌 <b>Produto:</b> Acesso VIP Vitalício Tela Cheia Filmes\n\n"
            f"👇 <b>Código PIX Copia e Cola:</b> (Toque no código abaixo para copiar)\n\n"
            f"<code>{html.escape(pix_code)}</code>\n\n"
            f"⚡ <b>Como Pagar:</b>\n"
            f"1️⃣ Abra o aplicativo do seu Banco ou NuBank\n"
            f"2️⃣ Escolha a opção <b>PIX Copia e Cola</b>\n"
            f"3️⃣ Cole o código acima e confirme o pagamento de <b>R$ 10,00</b>\n\n"
            f"✨ <i>Assim que você concluir o pagamento, o seu link de acesso ao Canal VIP será liberado automaticamente aqui no chat!</i>"
        )

        keyboard = [
            [InlineKeyboardButton("✅ Já Paguei / Verificar Pagamento", callback_data="check_pix")],
            [InlineKeyboardButton("💬 Suporte / Falar com Atendente", url=SUPPORT_URL)],
            [InlineKeyboardButton("❌ Cancelar", callback_data="cancel_order")]
        ]

        await safe_send_message(
            context.bot,
            update.effective_chat.id,
            pix_instructions,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )

        chat_id = update.effective_chat.id
        user_id = user.id
        user_name = user.full_name or f"User_{user.id}"

        asyncio.create_task(auto_check_pix_loop(context.application, chat_id, user_id, user_name, identifier))
        return STATE_WAITING_PAYMENT

    except Exception as e:
        logging.error(f"Erro em generate_pix_callback: {e}", exc_info=True)
        kb_err = [[InlineKeyboardButton("💬 Falar com Suporte Humano", url=SUPPORT_URL)]]
        await safe_send_message(
            context.bot,
            update.effective_chat.id,
            "❌ <b>Ocorreu uma instabilidade ao gerar seu PIX.</b>\n\n"
            "Por favor, entre em contato direto com o nosso suporte para receber seu acesso:",
            reply_markup=InlineKeyboardMarkup(kb_err),
            parse_mode="HTML"
        )
        return STATE_IDLE


async def check_pix_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Checagem manual do PIX solicitada pelo usuário ao clicar no botão 'Já Paguei'."""
    query = update.callback_query
    await query.answer()

    identifier = context.user_data.get("pix_identifier")
    if not identifier:
        kb = [[InlineKeyboardButton("💬 Falar com Suporte", url=SUPPORT_URL)]]
        await query.message.reply_text(
            "❌ Nenhuma cobrança ativa encontrada. Digite /start para iniciar uma nova compra ou fale com o suporte:",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return STATE_IDLE

    try:
        await query.answer("🔎 Consultando o sistema de pagamentos SyncPay...")
        res = check_transaction_status(identifier)
        status = res.get("status", "pending")

        if status in ["completed", "paid"]:
            await deliver_vip_access(
                context.application,
                update.effective_chat.id,
                update.effective_user.id,
                update.effective_user.full_name or f"User_{update.effective_user.id}",
                identifier
            )
            return STATE_IDLE
        else:
            keyboard = [
                [InlineKeyboardButton("✅ Já Paguei / Verificar Novamente", callback_data="check_pix")],
                [InlineKeyboardButton("💬 Falar com Suporte", url=SUPPORT_URL)]
            ]
            await query.message.reply_text(
                "⏳ <b>Pagamento ainda em processamento!</b>\n\n"
                "O banco ainda não confirmou o recebimento do PIX. "
                "Geralmente leva alguns segundos após você concluir no app do seu banco.\n\n"
                "Por favor, aguarde um instante e clique em <b>Verificar Novamente</b> ou chame o suporte.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML"
            )
            return STATE_WAITING_PAYMENT

    except Exception as err:
        logging.error(f"Erro em check_pix_callback: {err}", exc_info=True)
        keyboard = [
            [InlineKeyboardButton("💬 Chamar Suporte VIP", url=SUPPORT_URL)],
            [InlineKeyboardButton("🔄 Tentar Novamente", callback_data="check_pix")]
        ]
        await query.message.reply_text(
            "⚠️ Ocorreu uma instabilidade ao verificar o status. Caso já tenha pago, chame imediatamente o nosso suporte:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return STATE_WAITING_PAYMENT


async def cancel_order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela o pedido atual."""
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    kb = [[InlineKeyboardButton("💬 Suporte VIP", url=SUPPORT_URL)]]
    await query.edit_message_text(
        "❌ <b>Pedido cancelado.</b> Digite /start caso deseje realizar um novo pedido.",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="HTML"
    )
    return STATE_IDLE


DELIVERY_LOCK = asyncio.Lock()
PROCESSED_IDENTIFIERS = set()


async def generate_single_use_vip_invite(user_id: int, user_name: str, identifier: str) -> str:
    """
    Gera um link de convite exclusivo e de uso único estrito (member_limit=1, expire_date=24h)
    para o Canal VIP, garantindo entrada individual e revogação automática pelo Telegram assim que o usuário entrar.
    Utiliza cadeia de tentativas priorizando bots com permissão e fallback direto via HTTP.
    """
    vip_channel = TELEGRAM_VIP_CHANNEL_ID
    tokens_to_try = []

    # 1. Bot Admin Oficial (possui permissão de administrador no Canal VIP)
    admin_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if admin_token and admin_token.strip():
        tokens_to_try.append(("Bot Admin Oficial", admin_token.strip()))

    # 2. Bot de Vendas (@telacheiafilmes_bot)
    sales_token = os.getenv("SALES_BOT_TOKEN")
    if sales_token and sales_token.strip() and sales_token.strip() != (admin_token or "").strip():
        tokens_to_try.append(("Bot de Vendas", sales_token.strip()))

    expire_time = int(time.time()) + 86400  # Link válido por 24 horas até a entrada
    clean_name = f"VIP_{user_id}_{identifier[:6]}"[:32]

    errors = []

    for bot_label, token in tokens_to_try:
        # Tentativa 1: API HTTP Direta (independente de sessão ou event loop)
        try:
            url = f"https://api.telegram.org/bot{token}/createChatInviteLink"
            payload = {
                "chat_id": vip_channel,
                "member_limit": 1,
                "expire_date": expire_time,
                "name": clean_name
            }
            resp = requests.post(url, json=payload, timeout=12)
            data = resp.json()
            if data.get("ok") and data.get("result", {}).get("invite_link"):
                link = data["result"]["invite_link"]
                logging.info(f"✅ Link de convite único ({bot_label} via HTTP) gerado com sucesso: {link}")
                return link
            else:
                desc = data.get("description", "Sem descrição")
                logging.warning(f"Aviso ao tentar gerar convite via HTTP ({bot_label}): {desc}")
                errors.append(f"{bot_label} (HTTP): {desc}")
        except Exception as http_err:
            logging.warning(f"Erro de conexão ao gerar convite via HTTP ({bot_label}): {http_err}")
            errors.append(f"{bot_label} (HTTP): {http_err}")

        # Tentativa 2: PTB Bot Instance
        try:
            async with Bot(token) as bot_instance:
                link_obj = await bot_instance.create_chat_invite_link(
                    chat_id=vip_channel,
                    member_limit=1,
                    expire_date=expire_time,
                    name=clean_name
                )
                if link_obj and link_obj.invite_link:
                    logging.info(f"✅ Link de convite único ({bot_label} via PTB) gerado com sucesso: {link_obj.invite_link}")
                    return link_obj.invite_link
        except Exception as ptb_err:
            logging.warning(f"Aviso ao tentar gerar convite via PTB ({bot_label}): {ptb_err}")
            errors.append(f"{bot_label} (PTB): {ptb_err}")

    err_details = " | ".join(errors) if errors else "Nenhum token disponível"
    raise RuntimeError(
        f"Não foi possível gerar link exclusivo no Canal VIP ({vip_channel}). "
        f"Detalhes: {err_details}. "
        f"Certifique-se de que o bot foi adicionado como Administrador no canal VIP com a permissão 'Adicionar Membros/Links de Convite'."
    )


async def deliver_vip_access(app: Application, chat_id: int, user_id: int, user_name: str, identifier: str):
    """
    Entrega o link de acesso VIP exclusivo de uso único ao cliente e notifica o administrador.
    Possui proteção de concorrência (idempotência) para evitar envios ou links duplicados.
    Como fallback para qualquer erro, envia mensagem direcionando para o perfil do suporte.
    """
    async with DELIVERY_LOCK:
        if identifier in PROCESSED_IDENTIFIERS:
            logging.info(f"⚡ Transação {identifier} já entregue anteriormente nesta sessão. Ignorando chamada concorrente.")
            return

        from src.database import is_order_delivered, record_sales_order, get_sales_order
        if is_order_delivered(identifier):
            logging.info(f"⚡ Transação {identifier} já registrada como entregue no banco de dados.")
            order = get_sales_order(identifier)
            invite_link = order.get("invite_link")
            if invite_link:
                PROCESSED_IDENTIFIERS.add(identifier)
                return

        safe_name = html.escape(user_name or f"User_{user_id}")
        logging.info(f"🚀 Iniciando entrega de acesso VIP para {user_name} (ID: {user_id}), transação: {identifier}...")

        invite_link = None
        try:
            invite_link = await generate_single_use_vip_invite(user_id, user_name, identifier)
        except Exception as e:
            logging.error(f"❌ Erro ao gerar link de convite exclusivo: {e}")

            # Registra no banco mesmo com falha no link, para garantir contabilidade da venda
            try:
                record_sales_order(identifier, user_id, user_name, amount=10.0, status="paid_pending_invite", invite_link=None)
                PROCESSED_IDENTIFIERS.add(identifier)
            except Exception as db_err:
                logging.error(f"Erro ao registrar pedido pendente no banco: {db_err}")

            # Notifica o administrador do problema com detalhes
            if ADMIN_CHAT_ID:
                error_notify = (
                    f"🚨 <b>ALERTA DE VENDA PAGA - ERRO AO GERAR LINK VIP!</b>\n\n"
                    f"👤 <b>Cliente:</b> {safe_name} (ID: <code>{user_id}</code>)\n"
                    f"🆔 <b>Transação:</b> <code>{html.escape(identifier)}</code>\n"
                    f"⚠️ <b>Erro:</b> <code>{html.escape(str(e))}</code>\n\n"
                    f"👉 O cliente já foi direcionado para o seu perfil (<code>@{SUPPORT_USERNAME}</code>). "
                    f"Por favor, verifique se o bot está como Administrador no canal VIP <code>{TELEGRAM_VIP_CHANNEL_ID}</code> "
                    f"ou envie o convite manualmente."
                )
                await safe_send_message(app.bot, ADMIN_CHAT_ID, error_notify, parse_mode="HTML")

            # Fallback direto e acolhedor para o cliente direcionando para o perfil
            client_fallback = (
                f"🎉 <b>PAGAMENTO CONFIRMADO COM SUCESSO!</b>\n\n"
                f"Olá, {safe_name}! Seu pagamento via PIX no valor de <b>R$ 10,00</b> foi aprovado com sucesso pela SyncPay.\n\n"
                f"Tivemos uma pequena instabilidade momentânea na geração automática do seu link de acesso ao Canal VIP. "
                f"Fique tranquilo(a), sua vaga já está <b>100% garantida</b>!\n\n"
                f"👇 <b>Clique no botão abaixo para falar comigo e liberar seu acesso VIP imediatamente:</b>"
            )
            kb_fallback = [
                [InlineKeyboardButton("💬 Liberar Meu Acesso VIP Agora", url=SUPPORT_URL)]
            ]
            await safe_send_message(app.bot, chat_id, client_fallback, reply_markup=InlineKeyboardMarkup(kb_fallback), parse_mode="HTML")
            return

        # SUCESSO AO GERAR LINK
        try:
            record_sales_order(identifier, user_id, user_name, amount=10.0, status="completed", invite_link=invite_link)
            PROCESSED_IDENTIFIERS.add(identifier)
        except Exception as db_err:
            logging.error(f"Erro ao registrar pedido completo no banco: {db_err}")

        success_text = (
            f"🎉 <b>PAGAMENTO CONFIRMADO COM SUCESSO!</b>\n\n"
            f"Parabéns, {safe_name}! Seu pagamento via PIX no valor de <b>R$ 10,00</b> foi aprovado instantaneamente pela SyncPay.\n\n"
            f"🍿 <b>Seu Acesso Vitalício ao Canal VIP está Liberado!</b>\n\n"
            f"👇 <b>Clique no botão abaixo para entrar:</b>\n\n"
            f"🔒 <i>Atenção: Este link é exclusivo e de <b>uso único</b>. "
            f"Assim que você entrar no canal, o link é automaticamente expirado pelo Telegram por segurança.</i>\n\n"
            f"Se tiver qualquer dúvida ou precisar de ajuda, estou à disposição no suporte!"
        )

        keyboard = [
            [InlineKeyboardButton("🚀 ENTRAR NO CANAL VIP AGORA", url=invite_link)],
            [InlineKeyboardButton("💬 Suporte VIP", url=SUPPORT_URL)]
        ]

        await safe_send_message(app.bot, chat_id, success_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

        # Notifica o administrador do sistema
        if ADMIN_CHAT_ID:
            try:
                admin_notify = (
                    f"💰 <b>NOVA VENDA REALIZADA COM SUCESSO!</b>\n\n"
                    f"👤 <b>Cliente:</b> {safe_name} (ID: <code>{user_id}</code>)\n"
                    f"💵 <b>Valor:</b> R$ 10,00 (PIX SyncPay)\n"
                    f"🆔 <b>Transação:</b> <code>{html.escape(identifier)}</code>\n"
                    f"🔗 <b>Link Único Gerado:</b> {invite_link}\n"
                    f"⏱️ <b>Regra:</b> Limite de 1 membro (Auto-revogação ativa)"
                )
                await safe_send_message(app.bot, ADMIN_CHAT_ID, admin_notify, parse_mode="HTML")
            except Exception as err:
                logging.warning(f"Não foi possível notificar admin {ADMIN_CHAT_ID}: {err}")


async def auto_check_pix_loop(app: Application, chat_id: int, user_id: int, user_name: str, identifier: str):
    """Checa automaticamente a transação SyncPay a cada 10 segundos por até 15 minutos."""
    max_checks = 90  # 90 tentativas * 10s = 15 minutos
    for _ in range(max_checks):
        try:
            await asyncio.sleep(10)
            if identifier in PROCESSED_IDENTIFIERS:
                break
            res = check_transaction_status(identifier)
            status = res.get("status", "pending")
            if status in ["completed", "paid"]:
                await deliver_vip_access(app, chat_id, user_id, user_name, identifier)
                break
        except Exception as loop_err:
            logging.warning(f"Aviso no loop de checagem PIX ({identifier}): {loop_err}")


async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Handler global para capturar qualquer exceção não tratada e enviar fallback para o perfil do suporte."""
    logging.error(f"❌ Exceção não tratada capturada pelo bot de vendas: {context.error}", exc_info=context.error)
    if isinstance(update, Update) and update.effective_chat:
        try:
            fallback_text = (
                "⚠️ <b>Desculpe, ocorreu uma instabilidade momentânea no sistema.</b>\n\n"
                "Se você realizou um pagamento ou precisa de ajuda, por favor clique no botão abaixo para falar diretamente comigo:"
            )
            kb = [[InlineKeyboardButton("💬 Falar com Suporte VIP", url=SUPPORT_URL)]]
            await safe_send_message(
                context.bot,
                update.effective_chat.id,
                fallback_text,
                reply_markup=InlineKeyboardMarkup(kb),
                parse_mode="HTML"
            )
        except Exception as send_err:
            logging.error(f"Não foi possível enviar mensagem de fallback global: {send_err}")


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
    app.add_error_handler(global_error_handler)
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

