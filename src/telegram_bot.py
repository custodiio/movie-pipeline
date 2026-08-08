"""
Módulo Principal do Bot de Postagens & Vendas no Telegram
movie-pipeline - Automação de divulgação e postagens em canais público e VIP.
"""

import os
import sys
import logging
import asyncio
import requests
from dotenv import load_dotenv

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove
)
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

# Adiciona a raiz do projeto ao sys.path para importar módulos do src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tmdb_client import search_movies, get_movie_details
from src.script_generator import generate_sales_copy

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "@dramasleh")
TELEGRAM_VIP_CHANNEL_ID = os.getenv("TELEGRAM_VIP_CHANNEL_ID", "@telacheiafilmesvip")
TELEGRAM_SALES_LINK = os.getenv("TELEGRAM_SALES_LINK", "https://t.me/dramasleh")

# Estados da Conversa para Criar Postagem no Canal Público
STATE_SEARCH_MOVIE, STATE_SELECT_MOVIE, STATE_SELECT_IMAGES, STATE_PREVIEW_POST, STATE_EDIT_COPY = range(5)

# Estados da Conversa para Postar Vídeo no Canal VIP
STATE_RECEIVE_VIDEO, STATE_CONFIRM_VIDEO_TITLE = range(5, 7)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exibe o menu principal do Bot do Telegram."""
    reply_keyboard = [
        ["📢 Criar Postagem de Venda", "🎥 Postar Vídeo no VIP"],
        ["ℹ️ Status dos Canais", "❓ Ajuda"]
    ]
    markup = ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "👋 **Bem-vindo ao Bot Gerenciador do Movie-Pipeline!**\n\n"
        "Selecione uma das opções abaixo para gerenciar as postagens dos canais:",
        reply_markup=markup,
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💡 **Como usar o Bot:**\n\n"
        "1. **📢 Criar Postagem de Venda**: Busca o filme no TMDB, seleciona até 2 pôsteres, gera a copy persuasiva via IA e envia ao canal público (`@dramasleh`) com o botão de acesso.\n\n"
        "2. **🎥 Postar Vídeo no VIP**: Envie qualquer vídeo para o bot e publique diretamente no canal VIP em tela cheia.",
        parse_mode="Markdown"
    )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📊 **Configurações Atuais:**\n\n"
        f"• **Canal Público (Divulgação):** `{TELEGRAM_CHANNEL_ID}`\n"
        f"• **Canal VIP (Vídeos):** `{TELEGRAM_VIP_CHANNEL_ID}`\n"
        f"• **Link de Vendas Privado:** `{TELEGRAM_SALES_LINK}`\n"
        f"• **Status da API TMDB:** {'✅ Conectada' if os.getenv('TMDB_API_KEY') else '❌ Chave Faltando'}",
        parse_mode="Markdown"
    )


# ==============================================================================
# FLUXO 1: CRIAR POSTAGEM DE VENDA (CANAL PÚBLICO)
# ==============================================================================

async def start_create_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Passo 1: Pede o nome do filme."""
    await update.message.reply_text(
        "🎬 **Criar Nova Postagem de Venda**\n\n"
        "Digite o nome do filme que você deseja buscar no TMDB (ex: *Homem-Aranha*):",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )
    return STATE_SEARCH_MOVIE

async def handle_search_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Passo 2: Busca no TMDB e exibe opções em botões inline."""
    query = update.message.text.strip()
    status_msg = await update.message.reply_text(f"🔍 Buscando '{query}' no TMDB...")

    results = search_movies(query)
    if not results:
        await status_msg.edit_text("❌ Nenhum filme encontrado com esse nome. Digite outro título para buscar:")
        return STATE_SEARCH_MOVIE

    # Armazena os resultados no context do usuário
    context.user_data["tmdb_results"] = {str(m["id"]): m for m in results[:6]}

    keyboard = []
    for m in results[:6]:
        year = m.get("release_date", "")[:4]
        year_str = f" ({year})" if year else ""
        title = m.get("title", "Sem título")
        keyboard.append([InlineKeyboardButton(f"🎬 {title}{year_str}", callback_data=f"select_movie:{m['id']}")])

    keyboard.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancel_post")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await status_msg.edit_text(
        f"✨ Encontrei {len(results[:6])} resultados. Escolha o filme correto:",
        reply_markup=reply_markup
    )
    return STATE_SELECT_MOVIE

async def handle_movie_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Passo 3: Filme selecionado. Busca detalhes e imagens no TMDB."""
    query = update.callback_query
    await query.answer()

    data = query.data
    if data == "cancel_post":
        await query.edit_message_text("❌ Postagem cancelada.")
        return ConversationHandler.END

    movie_id = data.split(":")[1]
    movie_details = get_movie_details(int(movie_id))
    if not movie_details:
        await query.edit_message_text("❌ Erro ao buscar detalhes do filme no TMDB. Tente novamente:")
        return STATE_SEARCH_MOVIE

    context.user_data["selected_movie"] = movie_details
    context.user_data["selected_images"] = []

    await query.edit_message_text(f"⏳ Carregando pôsteres e imagens de *{movie_details.get('title')}*...", parse_mode="Markdown")

    # Busca galeria de imagens do filme no TMDB
    images = get_tmdb_movie_images(movie_id)
    if not images and movie_details.get("poster_path"):
        images = [f"https://image.tmdb.org/t/p/w780{movie_details['poster_path']}"]

    if not images:
        images = ["https://via.placeholder.com/780x1170.png?text=Poster+Nao+Disponivel"]

    context.user_data["available_images"] = images[:8]

    # Envia as opções de imagens como mensagens de preview
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=f"🖼️ **Escolha 1 ou 2 imagens para o post de '{movie_details.get('title')}':**\n\n"
             f"Selecione clicando nos botões abaixo das imagens e depois clique em **✅ Confirmar Imagens**:",
        parse_mode="Markdown"
    )

    for i, img_url in enumerate(context.user_data["available_images"], 1):
        btn = InlineKeyboardButton(f"➕ Selecionar Imagem #{i}", callback_data=f"toggle_img:{i-1}")
        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=img_url,
            caption=f"Opção #{i}",
            reply_markup=InlineKeyboardMarkup([[btn]])
        )

    confirm_btn = InlineKeyboardButton("✅ Confirmar Imagens Selecionadas", callback_data="confirm_images")
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="Assim que escolher 1 ou 2 imagens acima, clique abaixo:",
        reply_markup=InlineKeyboardMarkup([[confirm_btn]])
    )

    return STATE_SELECT_IMAGES

def get_tmdb_movie_images(movie_id: str) -> list[str]:
    """Busca os posters/backdrops em alta resolução do filme no TMDB."""
    api_key = os.getenv("TMDB_API_KEY", "")
    url = f"https://api.themoviedb.org/3/movie/{movie_id}/images?api_key={api_key}"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            posters = [f"https://image.tmdb.org/t/p/w780{img['file_path']}" for img in data.get("posters", [])[:5]]
            backdrops = [f"https://image.tmdb.org/t/p/w780{img['file_path']}" for img in data.get("backdrops", [])[:3]]
            return posters + backdrops
    except Exception as e:
        logging.warning(f"Erro ao buscar imagens no TMDB: {e}")
    return []

async def handle_toggle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Adiciona ou remove imagem selecionada."""
    query = update.callback_query
    await query.answer()

    idx = int(query.data.split(":")[1])
    selected = context.user_data.get("selected_images", [])
    available = context.user_data.get("available_images", [])

    img_url = available[idx]
    if img_url in selected:
        selected.remove(img_url)
        btn = InlineKeyboardButton(f"➕ Selecionar Imagem #{idx+1}", callback_data=f"toggle_img:{idx}")
        status_txt = f"Opção #{idx+1}"
    else:
        if len(selected) >= 2:
            await query.answer("⚠️ Você só pode selecionar no máximo 2 imagens!", show_alert=True)
            return STATE_SELECT_IMAGES
        selected.append(img_url)
        btn = InlineKeyboardButton(f"✅ REMOVER Imagem #{idx+1}", callback_data=f"toggle_img:{idx}")
        status_txt = f"Opção #{idx+1} (SELECIONADA ★)"

    context.user_data["selected_images"] = selected
    await query.edit_message_caption(caption=status_txt, reply_markup=InlineKeyboardMarkup([[btn]]))
    return STATE_SELECT_IMAGES

async def handle_confirm_images(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Passo 4: Imagens confirmadas. Gera Copy por IA e mostra o Preview."""
    query = update.callback_query
    await query.answer()

    selected = context.user_data.get("selected_images", [])
    available = context.user_data.get("available_images", [])
    movie = context.user_data.get("selected_movie", {})

    if not selected:
        # Se o usuário não selecionou nenhuma manual, pega a primeira por padrão
        selected = [available[0]]
        context.user_data["selected_images"] = selected

    await query.message.reply_text("🤖 **Gerando Copying de Vendas Persuasiva por IA...**", parse_mode="Markdown")

    # Gera a Copy persuasiva via IA com fallbacks
    copy_text = generate_sales_copy(movie)
    context.user_data["generated_copy"] = copy_text

    # Exibe o Preview Completo
    sales_button = InlineKeyboardButton("🔒 Solicitar Acesso (R$ 5,00)", url=TELEGRAM_SALES_LINK)
    markup = InlineKeyboardMarkup([[sales_button]])

    await query.message.reply_text("👇 **PREVIEW DA POSTAGEM DO CANAL:**", parse_mode="Markdown")

    if len(selected) == 1:
        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=selected[0],
            caption=copy_text,
            reply_markup=markup
        )
    else:
        # 2 imagens via MediaGroup
        media = [InputMediaPhoto(media=selected[0], caption=copy_text), InputMediaPhoto(media=selected[1])]
        await context.bot.send_media_group(chat_id=query.message.chat_id, media=media)
        # Envia a mensagem com o botão em seguida
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="👇 **Clique abaixo para solicitar o acesso VIP:**",
            reply_markup=markup
        )

    # Botões de confirmação para o Admin
    action_btns = [
        [InlineKeyboardButton("🚀 Publicar no Canal (@dramasleh)", callback_data="publish_now")],
        [InlineKeyboardButton("✏️ Editar Legenda", callback_data="edit_copy")],
        [InlineKeyboardButton("❌ Cancelar", callback_data="cancel_post")]
    ]
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="⚙️ **Ações de Publicação:**",
        reply_markup=InlineKeyboardMarkup(action_btns)
    )
    return STATE_PREVIEW_POST

async def handle_edit_copy_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("✏️ **Envie a nova legenda/texto para o post:**", parse_mode="Markdown")
    return STATE_EDIT_COPY

async def handle_edit_copy_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_text = update.message.text.strip()
    context.user_data["generated_copy"] = new_text

    sales_button = InlineKeyboardButton("🔒 Solicitar Acesso (R$ 5,00)", url=TELEGRAM_SALES_LINK)
    markup = InlineKeyboardMarkup([[sales_button]])
    selected = context.user_data.get("selected_images", [])

    await update.message.reply_text("👇 **NOVO PREVIEW ATUALIZADO:**", parse_mode="Markdown")
    await context.bot.send_photo(
        chat_id=update.message.chat_id,
        photo=selected[0],
        caption=new_text,
        reply_markup=markup
    )

    action_btns = [
        [InlineKeyboardButton("🚀 Publicar no Canal (@dramasleh)", callback_data="publish_now")],
        [InlineKeyboardButton("❌ Cancelar", callback_data="cancel_post")]
    ]
    await update.message.reply_text(
        "⚙️ **Ações de Publicação:**",
        reply_markup=InlineKeyboardMarkup(action_btns)
    )
    return STATE_PREVIEW_POST

async def handle_publish_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Publica a postagem oficial no Canal Público (@dramasleh)."""
    query = update.callback_query
    await query.answer()

    selected = context.user_data.get("selected_images", [])
    copy_text = context.user_data.get("generated_copy", "")

    sales_button = InlineKeyboardButton("🔒 Solicitar Acesso (R$ 5,00)", url=TELEGRAM_SALES_LINK)
    markup = InlineKeyboardMarkup([[sales_button]])

    try:
        if len(selected) == 1:
            await context.bot.send_photo(
                chat_id=TELEGRAM_CHANNEL_ID,
                photo=selected[0],
                caption=copy_text,
                reply_markup=markup
            )
        else:
            media = [InputMediaPhoto(media=selected[0], caption=copy_text), InputMediaPhoto(media=selected[1])]
            await context.bot.send_media_group(chat_id=TELEGRAM_CHANNEL_ID, media=media)
            await context.bot.send_message(
                chat_id=TELEGRAM_CHANNEL_ID,
                text="👇 **Clique abaixo para solicitar o acesso VIP:**",
                reply_markup=markup
            )

        await query.edit_message_text(f"🎉 **PUBLICADO COM SUCESSO NO CANAL `{TELEGRAM_CHANNEL_ID}`!**", parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Erro ao publicar no canal {TELEGRAM_CHANNEL_ID}: {e}")
        await query.edit_message_text(f"❌ **Erro ao publicar no canal `{TELEGRAM_CHANNEL_ID}`:**\n`{e}`\n\nVerifique se o bot foi adicionado como ADMINISTRADOR do canal!", parse_mode="Markdown")

    return ConversationHandler.END


# ==============================================================================
# FLUXO 2: POSTAR VÍDEO NO CANAL VIP
# ==============================================================================

async def start_post_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pede para o usuário enviar o vídeo ou link da mensagem."""
    await update.message.reply_text(
        "🎥 **Postar Vídeo no Canal VIP**\n\n"
        "Envie o arquivo do vídeo (ou encaminhe a mensagem com o vídeo) que você deseja publicar no canal VIP:",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )
    return STATE_RECEIVE_VIDEO

async def handle_receive_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe o vídeo e pergunta o título."""
    video = update.message.video or update.message.document
    if not video:
        await update.message.reply_text("❌ Por favor, envie um arquivo de VÍDEO válido.")
        return STATE_RECEIVE_VIDEO

    caption = update.message.caption or ""
    context.user_data["vip_video_file_id"] = video.file_id
    context.user_data["vip_video_caption"] = caption

    keyboard = [
        [InlineKeyboardButton("✅ Manter Título/Legenda Original", callback_data="keep_vip_title")],
        [InlineKeyboardButton("✏️ Editar Título/Legenda", callback_data="edit_vip_title")],
        [InlineKeyboardButton("❌ Cancelar", callback_data="cancel_post")]
    ]

    await update.message.reply_text(
        f"📹 **Vídeo Recebido!**\n\n"
        f"Legenda atual: _{caption if caption else '(Sem legenda)'}_\n\n"
        f"Escolha o que deseja fazer:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return STATE_CONFIRM_VIDEO_TITLE

async def handle_publish_vip_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Envia o vídeo para o Canal VIP em tela cheia."""
    query = update.callback_query
    await query.answer()

    video_file_id = context.user_data.get("vip_video_file_id")
    caption = context.user_data.get("vip_video_caption", "")

    try:
        await context.bot.send_video(
            chat_id=TELEGRAM_VIP_CHANNEL_ID,
            video=video_file_id,
            caption=caption,
            supports_streaming=True
        )
        await query.edit_message_text(f"🚀 **VÍDEO PUBLICADO COM SUCESSO NO CANAL VIP `{TELEGRAM_VIP_CHANNEL_ID}`!**", parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Erro ao publicar no canal VIP {TELEGRAM_VIP_CHANNEL_ID}: {e}")
        await query.edit_message_text(f"❌ **Erro ao publicar no canal VIP `{TELEGRAM_VIP_CHANNEL_ID}`:**\n`{e}`\n\nVerifique se o bot foi adicionado como ADMINISTRADOR do canal VIP!", parse_mode="Markdown")

    return ConversationHandler.END


# ==============================================================================
# INICIALIZAÇÃO DO BOT
# ==============================================================================

def create_telegram_bot_app() -> Application:
    """Cria e configura a aplicação do Telegram Bot."""
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN não está configurado no .env!")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # ConversationHandler para Criar Postagem no Canal Público
    conv_create_post = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^📢 Criar Postagem de Venda$"), start_create_post),
            CommandHandler("postar", start_create_post)
        ],
        states={
            STATE_SEARCH_MOVIE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search_movie)],
            STATE_SELECT_MOVIE: [CallbackQueryHandler(handle_movie_selection, pattern="^(select_movie|cancel_post)")],
            STATE_SELECT_IMAGES: [
                CallbackQueryHandler(handle_toggle_image, pattern="^toggle_img:"),
                CallbackQueryHandler(handle_confirm_images, pattern="^confirm_images$")
            ],
            STATE_PREVIEW_POST: [
                CallbackQueryHandler(handle_publish_post, pattern="^publish_now$"),
                CallbackQueryHandler(handle_edit_copy_start, pattern="^edit_copy$"),
                CallbackQueryHandler(lambda u, c: ConversationHandler.END, pattern="^cancel_post$")
            ],
            STATE_EDIT_COPY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_copy_receive)]
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)]
    )

    # ConversationHandler para Postar Vídeo no Canal VIP
    conv_post_video = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^🎥 Postar Vídeo no VIP$"), start_post_video),
            CommandHandler("postar_video", start_post_video)
        ],
        states={
            STATE_RECEIVE_VIDEO: [MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_receive_video)],
            STATE_CONFIRM_VIDEO_TITLE: [
                CallbackQueryHandler(handle_publish_vip_video, pattern="^keep_vip_title$"),
                CallbackQueryHandler(lambda u, c: ConversationHandler.END, pattern="^cancel_post$")
            ]
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)]
    )

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("ajuda", help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(MessageHandler(filters.Regex("^ℹ️ Status dos Canais$"), status_command))
    app.add_handler(MessageHandler(filters.Regex("^❓ Ajuda$"), help_command))

    app.add_handler(conv_create_post)
    app.add_handler(conv_post_video)

    return app


if __name__ == "__main__":
    print("🤖 Iniciando Bot do Telegram Movie-Pipeline...")
    application = create_telegram_bot_app()
    application.run_polling()
