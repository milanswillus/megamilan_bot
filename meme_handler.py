import os
import random
import PIL.Image
from PIL import ImageDraw, ImageFont
from pathlib import Path
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
from config import TEMPLATE_DIR, OUTPUT_DIR

# --- MOVIEPY & PILLOW FIX ---
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

# --- TEMPLATE CONFIGURATIONS ---
TEMPLATE_CONFIGS = {
    "sad_megamind": {
        "position": "top"
    }
}

def normalize_template_key(name: str) -> str:
    """Normiert den Ordner- oder Dateinamen auf einen Command-Key."""
    name = name.lower()
    for suffix in ['_templates', '_template', '-templates', '-template']:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    return name

def get_available_templates():
    """Scannt den templates-Ordner und gibt eine Map der verfügbaren Templates zurück."""
    templates = {}
    if not TEMPLATE_DIR.exists():
        return templates
        
    for item in TEMPLATE_DIR.iterdir():
        if item.name.startswith('.'):
            continue
            
        if item.is_dir():
            key = normalize_template_key(item.name)
            templates[key] = {
                "type": "folder",
                "path": item,
                "display_name": key.replace('_', ' ').title()
            }
        elif item.is_file():
            key = normalize_template_key(item.stem)
            templates[key] = {
                "type": "file",
                "path": item,
                "display_name": key.replace('_', ' ').title()
            }
    return templates

def is_video_file(file_path: Path) -> bool:
    """Prüft, ob es sich um eine Videodatei handelt."""
    video_extensions = {'.mp4', '.mov', '.avi', '.mkv', '.gif'}
    return file_path.suffix.lower() in video_extensions

def clean_filename_text(text: str) -> str:
    """Bereinigt den Text für die Verwendung im Dateinamen."""
    clean = "".join(c if c.isalnum() else "_" for c in text).strip("_")
    while "__" in clean:
        clean = clean.replace("__", "_")
    return clean or "meme"

def wrap_text_pil(text: str, font: ImageFont.ImageFont, max_width: int) -> str:
    """Bricht Text in Zeilen um, damit er in die maximale Breite passt."""
    words = text.split()
    lines = []
    current_line = []
    
    for word in words:
        test_line = ' '.join(current_line + [word])
        # Verwende getbbox() für moderne Pillow-Versionen
        bbox = font.getbbox(test_line)
        width = bbox[2] - bbox[0]
        
        if width <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
                current_line = [word]
            else:
                lines.append(word)
                current_line = []
                
    if current_line:
        lines.append(' '.join(current_line))
        
    return '\n'.join(lines)

def generate_video_meme(input_path: Path, text: str, output_path: Path, position: str = "center") -> bool:
    """Erstellt ein Video-Meme mit moviepy."""
    video = None
    txt_clip = None
    final_video = None
    try:
        video = VideoFileClip(str(input_path))
        
        # Auf Quadrat zuschneiden
        min_dim = min(video.w, video.h)
        video = video.crop(width=min_dim, height=min_dim, x_center=video.w/2, y_center=video.h/2)

        upscale_factor = 2
        target_width = video.w * 0.9

        # Position bestimmen
        if position == "top":
            pos = ('center', int(min_dim * 0.05))
        elif position == "bottom":
            pos = ('center', int(min_dim * 0.95 - (50 / upscale_factor)))
        else:
            pos = 'center'

        txt_clip = TextClip(
            text,
            fontsize=50,             
            color='white',
            font='DejaVu-Sans-Bold',
            stroke_color='black',
            stroke_width=2,
            method='caption',
            size=(target_width * upscale_factor, None),
            align='Center'
        ).resize(1/upscale_factor).set_position(pos).set_duration(video.duration)

        final_video = CompositeVideoClip([video, txt_clip])
        
        final_video.write_videofile(
            str(output_path),
            fps=24,
            codec='libx264',
            audio_codec='aac',
            preset='ultrafast',
            threads=4,
            logger=None
        )
        return True
    except Exception as e:
        print(f"Fehler bei Video-Generierung: {e}")
        return False
    finally:
        # Ressourcen freigeben
        if video:
            video.close()
        if txt_clip:
            txt_clip.close()
        if final_video:
            final_video.close()

def generate_image_meme(input_path: Path, text: str, output_path: Path, position: str = "center") -> bool:
    """Erstellt ein Bild-Meme mit Pillow."""
    try:
        with PIL.Image.open(input_path) as img:
            # Auf Quadrat zuschneiden (vom Zentrum)
            min_dim = min(img.width, img.height)
            left = (img.width - min_dim) / 2
            top = (img.height - min_dim) / 2
            right = (img.width + min_dim) / 2
            bottom = (img.height + min_dim) / 2
            img = img.crop((left, top, right, bottom))
            
            # Neue Zeichenfläche
            draw = ImageDraw.Draw(img)
            
            # Schriftart laden (verschiedene Fallbacks)
            font_size = int(min_dim * 0.08) # Schriftgröße ca. 8% der Bildbreite
            font = None
            font_names = ["DejaVuSans-Bold.ttf", "DejaVuSans.ttf", "Arial Bold.ttf", "Arial.ttf", "Helvetica-Bold.ttf"]
            
            for font_name in font_names:
                try:
                    font = ImageFont.truetype(font_name, font_size)
                    break
                except IOError:
                    continue
            
            if font is None:
                font = ImageFont.load_default()
            
            # Text umbrechen
            max_width = int(min_dim * 0.9)
            wrapped_text = wrap_text_pil(text, font, max_width)
            
            # Textposition berechnen
            # getbbox() liefert (left, top, right, bottom)
            text_bbox = draw.multiline_textbbox((0, 0), wrapped_text, font=font)
            text_w = text_bbox[2] - text_bbox[0]
            text_h = text_bbox[3] - text_bbox[1]
            
            x = (min_dim - text_w) / 2
            
            if position == "top":
                y = min_dim * 0.05
            elif position == "bottom":
                y = min_dim - text_h - min_dim * 0.05
            else:
                y = (min_dim - text_h) / 2
            
            # Zeichnen mit weißem Text und schwarzem Rand (stroke)
            draw.multiline_text(
                (x, y),
                wrapped_text,
                font=font,
                fill="white",
                stroke_width=max(2, int(min_dim * 0.004)), # Dynamische Randdicke
                stroke_fill="black",
                align="center"
            )
            
            img.save(output_path)
            return True
            
    except Exception as e:
        print(f"Fehler bei Bild-Generierung: {e}")
        return False

def create_meme(template_key: str, text: str) -> Path | None:
    """Wählt das Template, wendet den Text an und gibt den Pfad zum Meme zurück."""
    templates = get_available_templates()
    if template_key not in templates:
        print(f"Template '{template_key}' nicht gefunden.")
        return None
        
    template = templates[template_key]
    
    # 1. Quelldatei bestimmen
    if template["type"] == "folder":
        folder_path = template["path"]
        files = [f for f in folder_path.iterdir() if f.is_file() and not f.name.startswith('.')]
        if not files:
            print(f"Keine Dateien im Ordner {folder_path} gefunden.")
            return None
        input_path = random.choice(files)
    else:
        input_path = template["path"]
        
    # 2. Outputpfad bestimmen
    clean_text = clean_filename_text(text)
    suffix = input_path.suffix
    output_filename = f"meme_{template_key}_{clean_text}{suffix}"
    output_path = OUTPUT_DIR / output_filename
    
    # Sicherstellen, dass Output-Ordner existiert
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # 3. Position bestimmen
    config = TEMPLATE_CONFIGS.get(template_key, {})
    position = config.get("position", "center")
    
    # 4. Generieren basierend auf Dateityp
    success = False
    if is_video_file(input_path):
        success = generate_video_meme(input_path, text, output_path, position=position)
    else:
        success = generate_image_meme(input_path, text, output_path, position=position)
        
    return output_path if success else None
