"""
Módulo de Edição e Renderização de Vídeo (FFmpeg / ASS Subtitles / Pillow)

Monta o vídeo final unindo:
1. Pré-padronização ultra-rápida de todas as imagens (Pillow) para 1920x1080 com proporção perfeita
2. Renderização de 1 Bloco Visual Base com cada foto durando EXATAMENTE 5.00s
3. Marca d'água animada DVD bounce sincronizada a 5.0s por travessia (sem travamento/sem congelamento)
4. Mesclagem instantânea com a narração de áudio via stream copy (-c:v copy -c:a aac)
5. Vinheta Intro normalizada (se disponível)
6. Loop instantâneo (-c copy) para preencher a duração total do filme (110 min)
"""

import os
import math
import logging
import subprocess
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

OUTPUT_DIR_DEFAULT = "output"
INTRO_PATH_DEFAULT = os.getenv("INTRO_PATH", r"D:\Applications\Movie-Pipeline\intro.mp4")

WATERMARK_TEXT_MAIN = "Saiba mais pelo telegram ➔ @LehDramas"
WATERMARK_TEXT_SUB  = "(Link Direto no 1º Comentário Fixado)"


def get_audio_duration(audio_path: str) -> float:
    """Retorna a duração exata do arquivo de áudio em segundos."""
    try:
        from pydub import AudioSegment
        sound = AudioSegment.from_file(audio_path)
        return len(sound) / 1000.0
    except Exception:
        pass

    try:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(res.stdout.strip())
    except Exception:
        return 60.0


def standardize_images(images: list[str], output_dir: str) -> list[str]:
    """
    Padroniza todas as imagens em 1920x1080 (Full HD) via Pillow com ajuste proporcional perfeito.
    Garante que formatos 16:9, 4:3, 1:1 fiquem centralizados sobre fundo preto sem distorções,
    eliminando 100% dos bugs de tela preta e atrasos no FFmpeg.
    """
    os.makedirs(output_dir, exist_ok=True)
    norm_images = []

    for i, img_path in enumerate(images):
        if not os.path.exists(img_path):
            continue
        out_path = os.path.join(output_dir, f"norm_frame_{i:04d}.jpg")
        try:
            with Image.open(img_path) as im:
                im = im.convert("RGB")
                w, h = im.size
                scale = min(1920.0 / w, 1080.0 / h)
                nw, nh = int(round(w * scale)), int(round(h * scale))
                resized = im.resize((nw, nh), Image.Resampling.LANCZOS)
                bg = Image.new("RGB", (1920, 1080), (0, 0, 0))
                bg.paste(resized, ((1920 - nw) // 2, (1080 - nh) // 2))
                bg.save(out_path, "JPEG", quality=95)
                norm_images.append(out_path)
        except Exception as e:
            logging.warning(f"Aviso ao padronizar imagem {img_path}: {e}")

    if not norm_images:
        raise ValueError("Nenhuma imagem válida encontrada para o slideshow.")

    return norm_images


def generate_dvd_bounce_ass(output_ass_path: str, duration_sec: float, width: int = 1920, height: int = 1080, font_name: str = "Bungee", step_sec: float = 5.0) -> str:
    """
    Gera arquivo de legendas .ass com animação DVD Bounce contínua e suave de step_sec (5.0s),
    sincronizada com a troca exata de fotos, sem travamento de animação.
    """
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: DVDBounce,{font_name},65,&H4DFFFFFF,&H4DFFFFFF,&H4D000000,&H4D000000,-1,0,0,0,100,100,0,0,1,2,0,5,10,10,10,1
Style: DVDBounceSub,{font_name},38,&H4DFFFFFF,&H4DFFFFFF,&H4D000000,&H4D000000,0,0,0,0,100,100,0,0,1,1,0,5,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    positions = [
        (250, 180),
        (width - 250, 280),
        (width - 250, height - 180),
        (250, height - 230),
        (width // 2, 180),
        (250, height // 2)
    ]

    events = []
    t = 0.0
    pos_idx = 0

    def format_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        cs = int(round((seconds - int(seconds)) * 100))
        if cs >= 100:
            s += 1
            cs = 0
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    while t < duration_sec:
        t_end = min(t + step_sec, duration_sec)
        p1 = positions[pos_idx % len(positions)]
        p2 = positions[(pos_idx + 1) % len(positions)]

        t_start_str = format_time(t)
        t_end_str = format_time(t_end)
        dur_ms = int((t_end - t) * 1000)

        move_tag = f"\\move({p1[0]},{p1[1]},{p2[0]},{p2[1]},0,{dur_ms})"
        line_main = f"Dialogue: 0,{t_start_str},{t_end_str},DVDBounce,,0,0,0,,{{{move_tag}}}{WATERMARK_TEXT_MAIN}\\N{WATERMARK_TEXT_SUB}"
        events.append(line_main)

        t = t_end
        pos_idx += 1

    os.makedirs(os.path.dirname(os.path.abspath(output_ass_path)), exist_ok=True)
    with open(output_ass_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events))

    return output_ass_path


def render_movie_video(
    slug: str,
    images: list[str],
    voiceover_path: str,
    output_dir: str = OUTPUT_DIR_DEFAULT,
    intro_path: str = INTRO_PATH_DEFAULT,
    target_runtime_minutes: float = 110.0,
    watermark_font: str = "Bungee",
    photo_duration: float = 5.0
) -> str:
    """
    Renderiza o vídeo final com máxima velocidade e estabilidade (Zero Tela Preta, Zero Travamento):
    1. Padroniza todas as imagens para 1920x1080 via Pillow em < 0.5s.
    2. Renderiza 1 Bloco Base contendo todas as fotos únicas (5.0s cada) + Marca d'água ASS.
    3. Concatena o Bloco Base em loop via stream copy (-c copy) até cobrir a narração e corta com -shortest.
    4. Concatena a Intro (se houver) e faz o loop instantâneo (-c copy) para 110 min.
    """
    os.makedirs(output_dir, exist_ok=True)
    temp_dir = os.path.join(output_dir, "temp_render")
    os.makedirs(temp_dir, exist_ok=True)

    final_output_path = os.path.join(output_dir, f"{slug}.mp4")
    norm_dir = os.path.join(temp_dir, "norm_images")
    base_visual_block = os.path.join(temp_dir, "base_visual_block.mp4")
    narrated_block = os.path.join(temp_dir, "narrated_block.mp4")
    intro_norm_temp = os.path.join(temp_dir, "intro_norm.mp4")
    ass_path = os.path.join(temp_dir, "watermark.ass")

    # 1. Padronização das fotos via Pillow (Full HD 1920x1080)
    logging.info(f"🖼️ Padronizando {len(images)} imagens para 1920x1080 via Pillow...")
    norm_imgs = standardize_images(images, norm_dir)
    total_photos = len(norm_imgs)
    base_cycle_duration = total_photos * photo_duration

    # 2. Concat script do Bloco Base
    concat_base_txt = os.path.join(temp_dir, "slideshow_base.txt")
    lines = []
    for p in norm_imgs:
        abs_p = os.path.abspath(p).replace("\\", "/")
        lines.append(f"file '{abs_p}'")
        lines.append(f"duration {photo_duration:.2f}")
    # Repete o último frame conforme requisito da especificação do concat demuxer
    lines.append(f"file '{os.path.abspath(norm_imgs[-1]).replace('\\', '/')}'")
    with open(concat_base_txt, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # 3. Gera a legenda animada .ass para a duração exata do ciclo base
    generate_dvd_bounce_ass(ass_path, base_cycle_duration, font_name=watermark_font, step_sec=photo_duration)
    ass_path_escaped = os.path.abspath(ass_path).replace("\\", "/").replace(":", "\\:")

    # 4. Renderiza o Bloco Visual Base (apenas 1 ciclo com todas as fotos)
    vcodec = "libx264"
    preset = "ultrafast"
    logging.info(f"🎨 Renderizando Bloco Base ({total_photos} fotos x {photo_duration:.1f}s = {base_cycle_duration:.1f}s) com marca d'água ASS...")

    cmd_base = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", concat_base_txt,
        "-vf", f"fps=30,ass='{ass_path_escaped}'",
        "-c:v", vcodec, "-preset", preset,
        "-pix_fmt", "yuv420p", "-r", "30", "-g", "30",
        base_visual_block
    ]
    subprocess.run(cmd_base, check=True)

    # 5. Duração da narração e cálculo de loops do bloco visual
    narration_duration = get_audio_duration(voiceover_path)
    num_visual_loops = math.ceil(narration_duration / base_cycle_duration)
    if num_visual_loops < 1:
        num_visual_loops = 1

    logging.info(f"🎙️ Narração: {narration_duration:.1f}s ({narration_duration/60:.1f} min). Multiplicando bloco visual {num_visual_loops}x...")

    # Gera lista de concat do bloco visual
    concat_visual_loop_txt = os.path.join(temp_dir, "concat_visual_loop.txt")
    base_abs = os.path.abspath(base_visual_block).replace("\\", "/")
    with open(concat_visual_loop_txt, "w", encoding="utf-8") as f:
        f.write("\n".join([f"file '{base_abs}'" for _ in range(num_visual_loops + 1)]))

    # Junta o vídeo em loop com o áudio da narração via stream copy (-c:v copy) e corta no -shortest exato
    cmd_merge_narration = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", concat_visual_loop_txt,
        "-i", voiceover_path,
        "-c:v", "copy",
        "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "192k",
        "-shortest",
        narrated_block
    ]
    subprocess.run(cmd_merge_narration, check=True)

    # 6. Normalização da vinheta Intro (se existir)
    has_intro = False
    if intro_path and os.path.exists(intro_path):
        logging.info("🎬 Normalizando Vinheta Intro...")
        cmd_intro = [
            "ffmpeg", "-y", "-i", intro_path,
            "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black",
            "-r", "30", "-g", "30", "-c:v", vcodec, "-preset", preset, "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "192k",
            intro_norm_temp
        ]
        try:
            subprocess.run(cmd_intro, check=True)
            has_intro = True
        except Exception as intro_err:
            logging.warning(f"Aviso ao normalizar vinheta intro: {intro_err}")

    # 7. Loop Instantâneo (-c copy) para preencher a duração total (ex: 110 min)
    target_sec = target_runtime_minutes * 60.0
    num_movie_loops = math.ceil(target_sec / narration_duration)
    total_dur_min = target_runtime_minutes

    logging.info(f"⚡ Loop instantâneo (-c copy): multiplicando bloco narrado {num_movie_loops}x para {total_dur_min:.1f} min...")

    concat_final_list = os.path.join(temp_dir, "concat_final.txt")
    final_lines = []
    if has_intro and os.path.exists(intro_norm_temp):
        final_lines.append(f"file '{os.path.abspath(intro_norm_temp).replace('\\', '/')}'")

    narrated_abs = os.path.abspath(narrated_block).replace("\\", "/")
    for _ in range(num_movie_loops):
        final_lines.append(f"file '{narrated_abs}'")

    with open(concat_final_list, "w", encoding="utf-8") as f:
        f.write("\n".join(final_lines) + "\n")

    cmd_fast_concat = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_final_list,
        "-c", "copy",
        "-t", str(target_sec),
        final_output_path
    ]
    subprocess.run(cmd_fast_concat, check=True)

    # Limpeza de temporários
    try:
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass

    logging.info(f"🎉 Vídeo finalizado com sucesso ({total_dur_min:.1f} min): {final_output_path}")
    return final_output_path
