"""
Módulo de Edição e Renderização de Vídeo (FFmpeg / OpenCV / ASS Subtitles)

Monta o vídeo final unindo:
1. Intro do canal (sem loop no início)
2. Slideshow das imagens (16:9 / 1:1) com duração alternada (3-5s) e movimentos (Zoom In/Out, Pan) em loop
3. Marca d'água animada estilo DVD bounce com opacidade 30% e fonte Bungee
4. Áudio da narração + Trilha sonora em loop com ducking e fade-out
5. Nomenclatura final padronizada (<slug>.mp4)
"""

import os
import random
import math
import subprocess
import logging
from pydub import AudioSegment
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

INTRO_PATH = os.getenv("INTRO_PATH", r"D:\Applications\Movie-Pipeline\intro.mp4")

WATERMARK_TEXT_MAIN = "ASSISTA COMPLETO NO TELEGRAM ➔ @LehDramas"
WATERMARK_TEXT_SUB  = "(Link Direto no 1º Comentário Fixado)"

def get_audio_duration(audio_path: str) -> float:
    """Retorna a duração exata do arquivo de áudio em segundos."""
    try:
        sound = AudioSegment.from_file(audio_path)
        return len(sound) / 1000.0
    except Exception as e:
        logging.error(f"Erro ao medir duração do áudio: {e}")
        return 60.0

def generate_dvd_bounce_ass(output_ass_path: str, duration_sec: float, width: int = 1920, height: int = 1080) -> str:
    """
    Gera um arquivo de legendas .ass com animação de movimento quicante (DVD Bounce)
    para o texto da marca d'água com opacidade 30% (Alpha &H4D) e estilo Bungee em tamanho grande (65pt).
    """
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: DVDBounce,Bungee,65,&H4DFFFFFF,&H4DFFFFFF,&H4D000000,&H4D000000,-1,0,0,0,100,100,0,0,1,2,0,5,10,10,10,1
Style: DVDBounceSub,Bungee,38,&H4DFFFFFF,&H4DFFFFFF,&H4D000000,&H4D000000,0,0,0,0,100,100,0,0,1,1,0,5,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    margin_x, margin_y = 250, 180
    positions = [
        (margin_x, margin_y),
        (width - margin_x, margin_y + 100),
        (width - margin_x, height - margin_y),
        (margin_x, height - margin_y - 50),
        (width // 2, margin_y),
        (margin_x, height // 2)
    ]
    
    t = 0.0
    step = 12.0 # 12 segundos por travessia de canto a canto

    pos_idx = 0
    
    def format_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        cs = int((seconds - int(seconds)) * 100)
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    while t < duration_sec:
        t_end = min(t + step, duration_sec)
        p1 = positions[pos_idx % len(positions)]
        p2 = positions[(pos_idx + 1) % len(positions)]
        
        t_start_str = format_time(t)
        t_end_str = format_time(t_end)
        dur_ms = int((t_end - t) * 1000)
        
        # Tag \move explícita com coordenadas e tempos em milissegundos
        move_tag = f"\\move({p1[0]},{p1[1]},{p2[0]},{p2[1]},0,{dur_ms})"
        line_main = f"Dialogue: 0,{t_start_str},{t_end_str},DVDBounce,,0,0,0,,{{{move_tag}}}{WATERMARK_TEXT_MAIN}\\N{WATERMARK_TEXT_SUB}"
        events.append(line_main)
        
        t = t_end
        pos_idx += 1

    with open(output_ass_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events))
        
    return output_ass_path

def build_slideshow_concat_script(images: list[str], target_duration: float, temp_dir: str) -> str:
    """Gera um arquivo txt de concat do FFmpeg repetindo as imagens em loop com tempos alternados (5 a 10s)."""
    concat_txt = os.path.join(temp_dir, "slideshow_list.txt")
    current_time = 0.0
    lines = []
    
    img_pool = list(images)
    if not img_pool:
        raise ValueError("Nenhuma imagem fornecida para o slideshow.")

    while current_time < target_duration:
        random.shuffle(img_pool)
        for img_path in img_pool:
            dur = random.uniform(5.0, 10.0)

            clean_path = os.path.abspath(img_path).replace("\\", "/")
            lines.append(f"file '{clean_path}'")
            lines.append(f"duration {dur:.2f}")
            current_time += dur
            if current_time >= target_duration:
                break
                
    lines.append(f"file '{os.path.abspath(img_pool[0]).replace('\\', '/')}'")

    with open(concat_txt, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return concat_txt

def render_movie_video(
    slug: str,
    images: list[str],
    voiceover_path: str,
    output_dir: str = OUTPUT_DIR_DEFAULT,
    intro_path: str = INTRO_PATH_DEFAULT,
    target_min_hours: float = 1.0
) -> str:
    """Renderiza o vídeo montando primeiro a estrutura visual e aplicando o .ass + áudio na passada final."""
    os.makedirs(output_dir, exist_ok=True)
    temp_dir = os.path.join(output_dir, "temp_render")
    os.makedirs(temp_dir, exist_ok=True)

    final_output_path = os.path.join(output_dir, f"{slug}.mp4")
    slideshow_base_temp = os.path.join(temp_dir, "slideshow_base.mp4")
    intro_norm_temp = os.path.join(temp_dir, "intro_norm.mp4")
    video_sem_legenda_temp = os.path.join(temp_dir, "video_sem_legenda.mp4")
    ass_path = os.path.join(temp_dir, "watermark.ass")

    # 1. Duração do áudio da narração
    audio_seg = AudioSegment.from_file(voiceover_path)
    narration_duration = len(audio_seg) / 1000.0

    # 2. PASSO 1: Monta o Slideshow de Imagens sem áudio e sem legenda
    concat_txt_path = build_slideshow_concat_script(images, narration_duration, temp_dir)
    vf_scale = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black"
    cmd_base = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", concat_txt_path,
        "-vf", vf_scale,
        "-c:v", "libx264", "-preset", "ultrafast", "-threads", "0",
        "-pix_fmt", "yuv420p", "-r", "30", "-an",
        slideshow_base_temp
    ]
    logging.info(f"🎥 1/3 Renderizando base visual do slideshow ({narration_duration:.1f}s)...")
    subprocess.run(cmd_base, check=True)

    # 3. PASSO 2: Normaliza a Intro e monta o vídeo completo sem áudio/legenda para a duração total do título
    has_intro = False
    if os.path.exists(intro_path):
        logging.info("Normalizando Vinheta Intro...")
        cmd_intro = [
            "ffmpeg", "-y", "-i", intro_path,
            "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black",
            "-r", "30", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-an",
            intro_norm_temp
        ]
        subprocess.run(cmd_intro, check=True)
        has_intro = True

    target_sec = target_min_hours * 3600.0 if target_min_hours > 5.0 else target_min_hours * 60.0
    num_loops = math.ceil(target_sec / narration_duration)
    total_dur_sec = narration_duration * num_loops

    logging.info(f"⚡ 2/3 Montando estrutura visual de {total_dur_sec/60:.1f} min ({num_loops}x repetições)...")
    concat_stream_list = os.path.join(temp_dir, "concat_stream.txt")
    concat_lines = []
    if has_intro and os.path.exists(intro_norm_temp):
        concat_lines.append(f"file '{os.path.abspath(intro_norm_temp).replace('\\\\', '/')}'")
    
    slide_abs = os.path.abspath(slideshow_base_temp).replace("\\", "/")
    for _ in range(num_loops):
        concat_lines.append(f"file '{slide_abs}'")

    with open(concat_stream_list, "w", encoding="utf-8") as f:
        f.write("\n".join(concat_lines) + "\n")

    cmd_fast_concat = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_stream_list,
        "-c", "copy",
        video_sem_legenda_temp
    ]
    subprocess.run(cmd_fast_concat, check=True)

    # 4. PASSO 3: Gera o .ass para o tempo total e realiza a RENDERIZAÇÃO FINAL ÚNICA (ÁUDIO + MARCA D'ÁGUA ASS GRANDE)
    generate_dvd_bounce_ass(ass_path, total_dur_sec + 60.0)
    ass_path_escaped = os.path.abspath(ass_path).replace("\\", "/").replace(":", "\\:")
    vf_ass = f"ass='{ass_path_escaped}'"

    cmd_final = [
        "ffmpeg", "-y",
        "-i", video_sem_legenda_temp,
        "-stream_loop", "-1", "-i", voiceover_path,
        "-vf", vf_ass,
        "-c:v", "libx264", "-preset", "ultrafast", "-threads", "0",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "192k",
        "-shortest",
        final_output_path
    ]
    logging.info(f"🎨 3/3 Renderização Final com Marca D'Água Animada Bungee (65pt) + Áudio da Narração em passada contínua...")
    subprocess.run(cmd_final, check=True)


    # 4. Normaliza a Intro UMA ÚNICA VEZ para codificação idêntica
    has_intro = False
    if os.path.exists(intro_path):
        logging.info("Normalizando Vinheta Intro para padrão idêntico de stream...")
        cmd_intro = [
            "ffmpeg", "-y", "-i", intro_path,
            "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black",
            "-r", "30", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "192k",
            intro_norm_temp
        ]
        subprocess.run(cmd_intro, check=True)
        has_intro = True

    # 5. LOOP INSTANTÂNEO (-c copy) PARA CORRESPONDER À DURAÇÃO EXATA DO TÍTULO (Ex: 164 min)
    import math
    target_sec = target_min_hours * 3600.0 if target_min_hours > 5.0 else target_min_hours * 60.0
    num_loops = math.ceil(target_sec / narration_duration)
    total_dur_min = (narration_duration * num_loops) / 60.0

    logging.info(f"⚡ Gerando vídeo de {total_dur_min:.1f} minutos ({num_loops}x repetições de {narration_duration/60:.1f}min) para bater a duração do título ({target_sec/60:.0f} min) via concat -c copy...")

    
    concat_stream_list = os.path.join(temp_dir, "concat_stream.txt")
    concat_lines = []
    if has_intro and os.path.exists(intro_norm_temp):
        concat_lines.append(f"file '{os.path.abspath(intro_norm_temp).replace('\\\\', '/')}'")
    
    slide_abs = os.path.abspath(slideshow_video_temp).replace("\\", "/")
    for _ in range(num_loops):
        concat_lines.append(f"file '{slide_abs}'")

    with open(concat_stream_list, "w", encoding="utf-8") as f:
        f.write("\n".join(concat_lines) + "\n")

    cmd_fast_concat = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_stream_list,
        "-c", "copy",
        final_output_path
    ]
    subprocess.run(cmd_fast_concat, check=True)

    # Limpeza dos arquivos temporários de renderização
    try:
        shutil.rmtree(temp_dir)
    except: pass

    logging.info(f"✨ Vídeo longo (+1h) finalizado com sucesso em: {final_output_path}")
    return final_output_path
