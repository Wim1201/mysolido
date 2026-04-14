"""
Watermark module for MySolido share links.
Adds traceable watermarks to PDFs and images when viewed via share links.
Original files in the pod are never modified.
"""

import os
import io
import math
from datetime import datetime

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import Color

try:
    from PyPDF2 import PdfReader, PdfWriter
    HAS_PYPDF2 = True
except ImportError:
    HAS_PYPDF2 = False

from PIL import Image, ImageDraw, ImageFont


def get_watermark_text():
    """Generate watermark text for a share link"""
    date_str = datetime.now().strftime('%d-%m-%Y')
    return f"Gedeeld via MySolido \u2014 {date_str}"


def _create_watermark_overlay(width, height, text):
    """Create a single-page PDF watermark overlay using reportlab"""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))
    c.saveState()

    # Semi-transparent light grey diagonal text
    c.setFillColor(Color(0.5, 0.5, 0.5, alpha=0.15))

    # Calculate font size relative to page diagonal
    diagonal = math.sqrt(width ** 2 + height ** 2)
    font_size = diagonal / max(len(text) * 0.6, 10)
    font_size = min(font_size, 72)
    font_size = max(font_size, 14)

    c.setFont("Helvetica", font_size)

    # Rotate and center
    c.translate(width / 2, height / 2)
    angle = math.degrees(math.atan2(height, width))
    c.rotate(angle)

    text_width = c.stringWidth(text, "Helvetica", font_size)
    c.drawString(-text_width / 2, -font_size / 3, text)

    c.restoreState()
    c.save()
    buf.seek(0)
    return buf


def watermark_pdf(input_path, output_path, watermark_text):
    """
    Add a semi-transparent diagonal watermark to every page of a PDF.
    Returns True on success, False on error.
    """
    if not HAS_PYPDF2:
        return False

    try:
        reader = PdfReader(input_path)
        writer = PdfWriter()

        for page in reader.pages:
            # Get page dimensions
            media_box = page.mediabox
            width = float(media_box.width)
            height = float(media_box.height)

            # Create watermark overlay matching page size
            overlay_buf = _create_watermark_overlay(width, height, watermark_text)
            overlay_reader = PdfReader(overlay_buf)
            overlay_page = overlay_reader.pages[0]

            # Merge watermark onto original page
            page.merge_page(overlay_page)
            writer.add_page(page)

        with open(output_path, 'wb') as f:
            writer.write(f)

        return True
    except Exception as e:
        print(f"[watermark] PDF watermark failed: {e}")
        return False


def watermark_image(input_path, output_path, watermark_text):
    """
    Add a semi-transparent repeating diagonal watermark to an image.
    Returns True on success, False on error.
    """
    try:
        img = Image.open(input_path).convert('RGBA')
        width, height = img.size

        # Create transparent overlay
        overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # Calculate font size based on image dimensions
        font_size = max(int(min(width, height) / 25), 16)
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except (OSError, IOError):
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
            except (OSError, IOError):
                font = ImageFont.load_default()
                font_size = 16

        # Semi-transparent white text
        fill = (255, 255, 255, 38)  # ~15% opacity

        # Measure text
        bbox = draw.textbbox((0, 0), watermark_text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        # Create a rotated text tile
        tile_w = text_w + font_size * 4
        tile_h = text_h + font_size * 6
        tile = Image.new('RGBA', (tile_w, tile_h), (0, 0, 0, 0))
        tile_draw = ImageDraw.Draw(tile)
        tile_draw.text(
            ((tile_w - text_w) / 2, (tile_h - text_h) / 2),
            watermark_text, font=font, fill=fill
        )
        tile = tile.rotate(35, expand=True, resample=Image.BICUBIC)

        # Tile the watermark across the image
        tw, th = tile.size
        for x in range(-tw, width + tw, tw):
            for y in range(-th, height + th, th):
                overlay.paste(tile, (x, y), tile)

        # Composite watermark onto image
        watermarked = Image.alpha_composite(img, overlay)

        # Determine output format from extension
        ext = os.path.splitext(output_path)[1].lower()
        format_map = {
            '.jpg': 'JPEG', '.jpeg': 'JPEG',
            '.png': 'PNG', '.gif': 'GIF',
            '.bmp': 'BMP', '.webp': 'WEBP',
        }
        out_format = format_map.get(ext, 'PNG')

        if out_format == 'JPEG':
            watermarked = watermarked.convert('RGB')
            watermarked.save(output_path, format=out_format, quality=90)
        elif out_format == 'GIF':
            watermarked = watermarked.convert('RGBA')
            watermarked.save(output_path, format=out_format)
        else:
            watermarked.save(output_path, format=out_format)

        return True
    except Exception as e:
        print(f"[watermark] Image watermark failed: {e}")
        return False
