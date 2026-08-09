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

import urllib.parse
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "@dramasleh")

raw_vip_id = os.getenv("TELEGRAM_VIP_CHANNEL_ID", "0")
try:
    TELEGRAM_VIP_CHANNEL_ID = int(raw_vip_id)
except ValueError:
    TELEGRAM_VIP_CHANNEL_ID = raw_vip_id


TELEGRAM_SALES_USERNAME = os.getenv("TELEGRAM_SALES_USERNAME", "leh_lurdes").replace("@", "")

def build_sales_link(movie_title: str = None) -> str:
    """
    Gera o link de vendas do Telegram direcionando para o Bot de Vendas Automático SyncPay (@telacheiafilmes_bot).
    """
    bot_username = os.getenv("SALES_BOT_USERNAME", "telacheiafilmes_bot").replace("@", "")
    return f"https://t.me/{bot_username}?start=comprar_vip"


# Estados da Conversa para Criar Postagem no Canal Público
STATE_SEARCH_MOVIE, STATE_SELECT_MOVIE, STATE_SELECT_AUDIO, STATE_SELECT_IMAGES, STATE_PREVIEW_POST, STATE_EDIT_COPY = range(6)

# Estados da Conversa para Postar Vídeo no Canal VIP
STATE_RECEIVE_VIDEO, STATE_CONFIRM_VIDEO_TITLE, STATE_EDIT_VIP_TITLE = range(6, 9)



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

    # Exibe a pergunta interativa do formato de áudio para a postagem
    audio_btns = [
        [InlineKeyboardButton("🔊 DUBLADO", callback_data="audio:DUBLADO")],
        [InlineKeyboardButton("💬 LEGENDADO", callback_data="audio:LEGENDADO")],
        [InlineKeyboardButton("🔊💬 DUBLADO / LEGENDADO", callback_data="audio:DUBLADO / LEGENDADO")]
    ]

    await query.edit_message_text(
        f"🎬 **Filme Selecionado:** *{movie_details.get('title')}*\n\n"
        f"🔊 **Selecione a opção de áudio do filme:**",
        reply_markup=InlineKeyboardMarkup(audio_btns),
        parse_mode="Markdown"
    )
    return STATE_SELECT_AUDIO


async def handle_audio_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Passo 3: Salva o áudio escolhido e carrega os pôsteres do TMDB."""
    query = update.callback_query
    await query.answer()

    audio_opt = query.data.split(":", 1)[1]
    context.user_data["audio_option"] = audio_opt

    movie_details = context.user_data.get("selected_movie", {})
    movie_id = str(movie_details.get("id"))

    await query.edit_message_text(f"⏳ Carregando pôsteres e imagens de *{movie_details.get('title')}*...", parse_mode="Markdown")

    # Busca galeria de imagens do filme categorizada (PT, EN, Variadas)
    all_images_data = get_tmdb_movie_images(movie_id)
    if not all_images_data and movie_details.get("poster_path"):
        all_images_data = [{"url": f"https://image.tmdb.org/t/p/w780{movie_details['poster_path']}", "type": "🎬 Pôster Oficial"}]

    if not all_images_data:
        all_images_data = [{"url": "https://via.placeholder.com/780x1170.png?text=Poster+Nao+Disponivel", "type": "🎬 Pôster"}]

    context.user_data["all_images_data"] = all_images_data
    context.user_data["image_page"] = 0
    context.user_data["selected_images"] = []

    return await send_image_batch(query.message, context, movie_details.get('title', 'Filme'))


def get_tmdb_movie_images(movie_id: str) -> list[dict]:
    """
    Busca as imagens no TMDB categorizando obrigatoriamente:
    1. Pôster em Português (pt/br)
    2. Pôster em Inglês (en)
    3. Outras 2+ imagens variadas (pôsteres/backdrops)
    """
    api_key = os.getenv("TMDB_API_KEY", "")
    url = f"https://api.themoviedb.org/3/movie/{movie_id}/images?api_key={api_key}&include_image_language=pt,br,en,null"
    
    result = []
    seen = set()
    
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            posters = data.get("posters", [])
            backdrops = data.get("backdrops", [])
            
            # 1. Pôsteres em Português (pt / br)
            for img in posters:
                lang = (img.get("iso_639_1") or "").lower()
                if lang in ["pt", "br"]:
                    full_url = f"https://image.tmdb.org/t/p/w780{img['file_path']}"
                    if full_url not in seen:
                        seen.add(full_url)
                        result.append({"url": full_url, "type": "🇧🇷 Pôster em Português"})
                        
            # 2. Pôsteres em Inglês (en)
            for img in posters:
                lang = (img.get("iso_639_1") or "").lower()
                if lang in ["en"]:
                    full_url = f"https://image.tmdb.org/t/p/w780{img['file_path']}"
                    if full_url not in seen:
                        seen.add(full_url)
                        result.append({"url": full_url, "type": "🇺🇸 Pôster em Inglês"})
                        
            # 3. Demais Pôsteres variados
            for img in posters:
                full_url = f"https://image.tmdb.org/t/p/w780{img['file_path']}"
                if full_url not in seen:
                    seen.add(full_url)
                    result.append({"url": full_url, "type": "🎬 Pôster Oficial"})
                    
            # 4. Backdrops / Cenas de Fundo
            for img in backdrops:
                full_url = f"https://image.tmdb.org/t/p/w780{img['file_path']}"
                if full_url not in seen:
                    seen.add(full_url)
                    result.append({"url": full_url, "type": "🌄 Cena do Filme (Backdrop)"})
                    
    except Exception as e:
        logging.warning(f"Erro ao buscar imagens no TMDB: {e}")
        
    return result

async def send_image_batch(message, context: ContextTypes.DEFAULT_TYPE, title: str):
    """Envia um lote de 4 imagens com botões de seleção e opção de carregar mais."""
    all_imgs = context.user_data.get("all_images_data", [])
    page = context.user_data.get("image_page", 0)
    batch_size = 4
    
    start_idx = page * batch_size
    current_batch = all_imgs[start_idx : start_idx + batch_size]
    
    if not current_batch:
        page = 0
        context.user_data["image_page"] = 0
        start_idx = 0
        current_batch = all_imgs[:batch_size]

    await message.reply_text(
        f"🖼️ **Escolha 1 ou 2 imagens para o post de '{title}' (Lote {page+1}):**\n\n"
        f"1. Português | 2. Inglês | 3 e 4. Variadas\n"
        f"Selecione nos botões das fotos e depois clique em **✅ Confirmar Imagens**:",
        parse_mode="Markdown"
    )

    for i, item in enumerate(current_batch, 1):
        global_idx = start_idx + i - 1
        img_url = item["url"]
        img_label = item["type"]
        
        btn = InlineKeyboardButton(f"➕ Selecionar ({img_label})", callback_data=f"toggle_img:{global_idx}")
        await context.bot.send_photo(
            chat_id=message.chat_id,
            photo=img_url,
            caption=f"Opção #{global_idx+1}: {img_label}",
            reply_markup=InlineKeyboardMarkup([[btn]])
        )

    bottom_btns = [
        [InlineKeyboardButton("✅ Confirmar Imagens Selecionadas", callback_data="confirm_images")],
        [InlineKeyboardButton("🔄 Exibir Mais Imagens (Próximo Lote)", callback_data="next_image_batch")]
    ]
    await context.bot.send_message(
        chat_id=message.chat_id,
        text="Assim que escolher as imagens acima (ou quiser ver mais), clique abaixo:",
        reply_markup=InlineKeyboardMarkup(bottom_btns)
    )
    return STATE_SELECT_IMAGES

async def handle_next_image_batch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Avança para o próximo lote de imagens."""
    query = update.callback_query
    await query.answer()
    
    context.user_data["image_page"] = context.user_data.get("image_page", 0) + 1
    movie = context.user_data.get("selected_movie", {})
    return await send_image_batch(query.message, context, movie.get("title", "Filme"))


async def handle_toggle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Adiciona ou remove imagem selecionada."""
    query = update.callback_query
    await query.answer()

    idx = int(query.data.split(":")[1])
    selected = context.user_data.get("selected_images", [])
    all_imgs = context.user_data.get("all_images_data", [])

    if idx < 0 or idx >= len(all_imgs):
        await query.answer("❌ Erro ao localizar imagem.", show_alert=True)
        return STATE_SELECT_IMAGES

    img_item = all_imgs[idx]
    img_url = img_item["url"]
    img_label = img_item["type"]

    if img_url in selected:
        selected.remove(img_url)
        btn = InlineKeyboardButton(f"➕ Selecionar ({img_label})", callback_data=f"toggle_img:{idx}")
        status_txt = f"Opção #{idx+1}: {img_label}"
        await query.answer("Imagem removida da seleção!")
    else:
        if len(selected) >= 2:
            await query.answer("⚠️ Você só pode selecionar no máximo 2 imagens!", show_alert=True)
            return STATE_SELECT_IMAGES
        selected.append(img_url)
        btn = InlineKeyboardButton(f"✅ REMOVER ({img_label})", callback_data=f"toggle_img:{idx}")
        status_txt = f"Opção #{idx+1}: {img_label} (SELECIONADA ★)"
        await query.answer("Imagem selecionada com sucesso! ★")

    context.user_data["selected_images"] = selected
    await query.edit_message_caption(caption=status_txt, reply_markup=InlineKeyboardMarkup([[btn]]))
    return STATE_SELECT_IMAGES

async def handle_confirm_images(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Passo 4: Imagens confirmadas. Gera Copy por IA e mostra o Preview."""
    query = update.callback_query
    await query.answer()

    selected = context.user_data.get("selected_images", [])
    all_imgs = context.user_data.get("all_images_data", [])
    movie = context.user_data.get("selected_movie", {})

    if not selected and all_imgs:
        # Se o usuário não selecionou nenhuma manual, pega a primeira por padrão
        selected = [all_imgs[0]["url"]]
        context.user_data["selected_images"] = selected

    await query.message.reply_text("🤖 **Gerando Copying de Vendas Persuasiva por IA...**", parse_mode="Markdown")

    # Gera a Copy persuasiva via IA com a estrutura padrao estrita e opcao de audio
    audio_option = context.user_data.get("audio_option", "DUBLADO")
    copy_text = generate_sales_copy(movie, audio_option)
    context.user_data["generated_copy"] = copy_text

    # Exibe o Preview Completo
    movie_title = movie.get("title", "")
    sales_link = build_sales_link(movie_title)
    sales_button = InlineKeyboardButton("🔒 Solicitar Acesso Vitalício R$10,00", url=sales_link)
    support_button = InlineKeyboardButton("💬 Falar com Suporte", url="https://t.me/leh_lurdes")
    markup = InlineKeyboardMarkup([[sales_button], [support_button]])

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
        # Envia a mensagem com os botões em seguida
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

    movie = context.user_data.get("selected_movie", {})
    sales_link = build_sales_link(movie.get("title", ""))
    sales_button = InlineKeyboardButton("🔒 Solicitar Acesso Vitalício R$10,00", url=sales_link)
    support_button = InlineKeyboardButton("💬 Falar com Suporte", url="https://t.me/leh_lurdes")
    markup = InlineKeyboardMarkup([[sales_button], [support_button]])
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
    movie = context.user_data.get("selected_movie", {})

    sales_link = build_sales_link(movie.get("title", ""))
    sales_button = InlineKeyboardButton("🔒 Solicitar Acesso Vitalício R$10,00", url=sales_link)
    support_button = InlineKeyboardButton("💬 Falar com Suporte", url="https://t.me/leh_lurdes")
    markup = InlineKeyboardMarkup([[sales_button], [support_button]])




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
# FLUXO 2: POSTAR VÍDEO NO CANAL VIP (Telethon MTProto Ultra-Rápido)
# ==============================================================================

async def start_post_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pede para o usuário enviar o vídeo ou link da mensagem."""
    await update.message.reply_text(
        "🎥 **Postar Vídeo no Canal VIP (Ultra-Rápido via Telethon)**\n\n"
        "Envie o **arquivo do vídeo**, **encaminhe a mensagem** ou **envie o link da mensagem** (ex: `https://t.me/c/2113392315/61747`) do filme:",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )
    return STATE_RECEIVE_VIDEO

async def handle_receive_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe o vídeo ou link de mensagem e armazena os dados."""
    video = update.message.video or update.message.document
    msg_text = update.message.text or ""
    
    context.user_data["vip_message_obj"] = update.message
    caption = ""
    
    if video:
        context.user_data["vip_video_file_id"] = video.file_id
        caption = update.message.caption or ""
    elif "t.me/" in msg_text:
        link_str = msg_text.strip()
        context.user_data["vip_video_link"] = link_str
        
        # Tenta obter a legenda/texto da mensagem original via Telethon em tempo real
        api_id = os.getenv("TELEGRAM_API_ID")
        api_hash = os.getenv("TELEGRAM_API_HASH")
        sess_path = os.getenv("TELEGRAM_SESSION_PATH", "d:/Applications/DailymotionAgent/dailymotion_agent.session")
        if api_id and api_hash and os.path.exists(sess_path):
            try:
                from telethon import TelegramClient
                client = TelegramClient(sess_path, int(api_id), api_hash)
                await client.connect()
                if await client.is_user_authorized():
                    parts = link_str.split('/')
                    source_msg_id = int(parts[-1])
                    source_chat_raw = parts[-2]
                    source_chat = int("-100" + source_chat_raw) if source_chat_raw.isdigit() else source_chat_raw
                    orig_msg = await client.get_messages(source_chat, ids=source_msg_id)
                    if orig_msg and (orig_msg.text or orig_msg.message):
                        caption = orig_msg.text or orig_msg.message
                await client.disconnect()
            except Exception as e:
                logging.warning(f"Não foi possível extrair legenda via Telethon no preview: {e}")
    else:
        await update.message.reply_text("❌ Por favor, envie um **vídeo válido**, **mensagem encaminhada** ou **link da mensagem** no Telegram.")
        return STATE_RECEIVE_VIDEO

    context.user_data["vip_video_caption"] = caption

    keyboard = [
        [InlineKeyboardButton("✅ Manter Título/Legenda Original", callback_data="keep_vip_title")],
        [InlineKeyboardButton("✏️ Editar Título/Legenda", callback_data="edit_vip_title")],
        [InlineKeyboardButton("❌ Cancelar", callback_data="cancel_post")]
    ]

    await update.message.reply_text(
        f"📹 **Vídeo / Link Recebido!**\n\n"
        f"Legenda detectada:\n_{caption if caption else '(Sem legenda / Usar formato do post)'}_\n\n"
        f"Escolha o que deseja fazer:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return STATE_CONFIRM_VIDEO_TITLE

async def handle_edit_vip_title_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pede para o usuário enviar a nova legenda/título para o vídeo no VIP."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("✏️ **Envie o novo texto/legenda para a postagem no Canal VIP:**", parse_mode="Markdown")
    return STATE_EDIT_VIP_TITLE

async def handle_edit_vip_title_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe a legenda editada e mostra o botão de confirmação."""
    new_caption = update.message.text.strip()
    context.user_data["vip_video_caption"] = new_caption

    keyboard = [
        [InlineKeyboardButton("🚀 Publicar Agora no Canal VIP", callback_data="keep_vip_title")],
        [InlineKeyboardButton("❌ Cancelar", callback_data="cancel_post")]
    ]

    await update.message.reply_text(
        f"📹 **Legenda Atualizada!**\n\n"
        f"Nova legenda:\n_{new_caption}_\n\n"
        f"Clique abaixo para publicar no Canal VIP:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return STATE_CONFIRM_VIDEO_TITLE


async def handle_publish_vip_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Envia o vídeo para o Canal VIP em tela cheia via Telethon instantâneo."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⚡ **Publicando vídeo no Canal VIP em alta velocidade via Telethon...**", parse_mode="Markdown")

    video_file_id = context.user_data.get("vip_video_file_id")
    video_link = context.user_data.get("vip_video_link")
    caption = context.user_data.get("vip_video_caption", "")
    msg_obj = context.user_data.get("vip_message_obj")

    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    sess_path = os.getenv("TELEGRAM_SESSION_PATH", "d:/Applications/DailymotionAgent/dailymotion_agent.session")

    published_via_telethon = False

    # 1. Tenta publicação instantânea via Telethon (MTProto Client)
    if api_id and api_hash and os.path.exists(sess_path):
        try:
            from telethon import TelegramClient
            client = TelegramClient(sess_path, int(api_id), api_hash)
            await client.connect()
            if await client.is_user_authorized():
                chat_entity = await client.get_entity(TELEGRAM_VIP_CHANNEL_ID)
                
                if video_link and ("t.me/c/" in video_link or "t.me/" in video_link):
                    parts = video_link.strip().split('/')
                    source_msg_id = int(parts[-1])
                    source_chat_raw = parts[-2]
                    if source_chat_raw.isdigit():
                        source_chat = int("-100" + source_chat_raw)
                    else:
                        source_chat = source_chat_raw
                    
                    orig_msg = await client.get_messages(source_chat, ids=source_msg_id)
                    if orig_msg:
                        if orig_msg.media:
                            await client.send_file(chat_entity, orig_msg.media, caption=caption if caption else orig_msg.text)
                        else:
                            await client.send_message(chat_entity, caption if caption else orig_msg.text)
                        published_via_telethon = True
                elif msg_obj and msg_obj.message_id:
                    # Encaminha a mensagem original instantaneamente!
                    await client.forward_messages(chat_entity, msg_obj.message_id, msg_obj.chat_id)
                    published_via_telethon = True


                await client.disconnect()
        except Exception as e:
            logging.warning(f"Fallback para Bot API por exceção no Telethon: {e}")

    # 2. Fallback via Bot API se o Telethon não enviou
    if not published_via_telethon:
        try:
            if video_file_id:
                await context.bot.send_video(
                    chat_id=TELEGRAM_VIP_CHANNEL_ID,
                    video=video_file_id,
                    caption=caption,
                    supports_streaming=True
                )
                published_via_telethon = True
            elif msg_obj:
                await context.bot.forward_message(
                    chat_id=TELEGRAM_VIP_CHANNEL_ID,
                    from_chat_id=msg_obj.chat_id,
                    message_id=msg_obj.message_id
                )
                published_via_telethon = True
        except Exception as e:
            logging.error(f"Erro ao publicar no VIP via Bot API: {e}")
            await query.edit_message_text(f"❌ **Erro ao publicar no canal VIP `{TELEGRAM_VIP_CHANNEL_ID}`:**\n`{e}`\n\nVerifique se o bot ou a conta é ADMINISTRADORA do canal!", parse_mode="Markdown")
            return ConversationHandler.END

    await query.edit_message_text(f"🚀 **VÍDEO PUBLICADO COM SUCESSO NO CANAL VIP `{TELEGRAM_VIP_CHANNEL_ID}` em menos de 1 segundo!**", parse_mode="Markdown")
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
            STATE_SELECT_AUDIO: [CallbackQueryHandler(handle_audio_select, pattern="^audio:")],
            STATE_SELECT_IMAGES: [
                CallbackQueryHandler(handle_toggle_image, pattern="^toggle_img:"),
                CallbackQueryHandler(handle_confirm_images, pattern="^confirm_images$"),
                CallbackQueryHandler(handle_next_image_batch, pattern="^next_image_batch$")
            ],
            STATE_PREVIEW_POST: [
                CallbackQueryHandler(handle_publish_post, pattern="^publish_now$"),
                CallbackQueryHandler(handle_edit_copy_start, pattern="^edit_copy$"),
                CallbackQueryHandler(lambda u, c: ConversationHandler.END, pattern="^cancel_post$")
            ],
            STATE_EDIT_COPY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_copy_receive)]
        },

        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
        per_message=False
    )

    # ConversationHandler para Postar Vídeo no Canal VIP
    conv_post_video = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^🎥 Postar Vídeo no VIP$"), start_post_video),
            CommandHandler("postar_video", start_post_video)
        ],
        states={
            STATE_RECEIVE_VIDEO: [MessageHandler(filters.ALL & ~filters.COMMAND, handle_receive_video)],
            STATE_CONFIRM_VIDEO_TITLE: [
                CallbackQueryHandler(handle_publish_vip_video, pattern="^keep_vip_title$"),
                CallbackQueryHandler(handle_edit_vip_title_start, pattern="^edit_vip_title$"),
                CallbackQueryHandler(lambda u, c: ConversationHandler.END, pattern="^cancel_post$")
            ],
            STATE_EDIT_VIP_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_vip_title_receive)]
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
        per_message=False
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
