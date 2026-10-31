"""
CoralineTextureTool.py - Extrator e Injetor de Texturas para Coraline DS (NDS)
Compatível com arquivos NITRO-CHARACTER 2D: .NCGR, .NCBR, .NCLR, .NSCR.

Recursos:
1. Interface Gráfica Moderna (Tkinter Dark Theme):
   - Exportação para pasta de nome fixo: 'texturas_exportadas'.
   - Importação e injeção automática de PNGs modificados da pasta fixa com backup .bak.
   - Prévia em tempo real das 682 texturas com suporte a zoom e fundo xadrez.
   - Recompilação da ROM (current.nds) com ndstool e preservação de header de 64 MB.
2. Modo CLI completo para automações, scripts e integração com IA / nanobanana.
3. Modular para acoplamento direto com o CoralineTextEditor.
"""

import os
import sys
import glob
import json
import shutil
import struct
import argparse
import subprocess
import threading
import time
from typing import List, Tuple, Dict, Optional
from PIL import Image, ImageTk, ImageDraw

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.scrolledtext import ScrolledText

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# Ativar DPI Awareness no Windows
try:
    from ctypes import windll
    windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

# ==============================================================================
# CONFIGURAÇÕES E CONSTANTES PADRÃO
# ==============================================================================
DEFAULT_UNPACK_ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA_DIR = os.path.join(DEFAULT_UNPACK_ROOT, "data", "data")
DEFAULT_FIXED_EXPORT_DIR = os.path.join(DEFAULT_UNPACK_ROOT, "texturas_exportadas")


# ==============================================================================
# 1. PARSERS DE FORMATOS NITRO 2D (.NCLR, .NCGR, .NCBR, .NSCR)
# ==============================================================================

class NitroPalette:
    """Gerenciador de Paletas de Cores Nintendo DS (.NCLR / TTLP)."""
    def __init__(self, filepath: Optional[str] = None):
        self.filepath = filepath
        self.colors: List[Tuple[int, int, int]] = [] # RGB888
        self.is_4bpp = True
        self.raw_data = bytearray()
        self.pal_offset = 0x28
        if filepath:
            self.load(filepath)

    def load(self, filepath: str):
        self.filepath = filepath
        with open(filepath, 'rb') as f:
            self.raw_data = bytearray(f.read())
            
        ttlp_idx = self.raw_data.find(b'TTLP')
        if ttlp_idx == -1:
            raise ValueError(f"Bloco TTLP (PLTT) não encontrado em {filepath}")
            
        # Cabeçalho Nitro TTLP:
        # offset 0x08: bpp (uint16) (3 = 4bpp, 4 = 8bpp)
        # offset 0x0a: pad16 (uint16)
        # offset 0x0c: pad32 (uint32)
        # offset 0x10: pal_sz (uint32)
        # offset 0x14: pal_off (uint32)
        bpp, pad16, pad32, pal_sz, pal_off = struct.unpack('<HHIII', self.raw_data[ttlp_idx+8:ttlp_idx+24])
        self.is_4bpp = (bpp == 3)
        self.pal_offset = ttlp_idx + 8 + pal_off
        
        pal_len = pal_sz if pal_sz > 0 else (len(self.raw_data) - self.pal_offset)
        pal_bytes = self.raw_data[self.pal_offset : self.pal_offset + pal_len]
        self.colors = []
        for i in range(0, len(pal_bytes) - 1, 2):
            c16 = struct.unpack('<H', pal_bytes[i:i+2])[0]
            r = (c16 & 0x1f) * 255 // 31
            g = ((c16 >> 5) & 0x1f) * 255 // 31
            b = ((c16 >> 10) & 0x1f) * 255 // 31
            self.colors.append((r, g, b))

    def get_color(self, index: int, bank: int = 0) -> Tuple[int, int, int]:
        if self.is_4bpp:
            real_idx = bank * 16 + index
        else:
            real_idx = index
        if 0 <= real_idx < len(self.colors):
            return self.colors[real_idx]
        return (0, 0, 0)

    def match_color(self, r: int, g: int, b: int, bank: int = 0) -> int:
        """Encontra o índice mais próximo na paleta para uma cor RGB."""
        start = bank * 16 + 1 if self.is_4bpp else 1 # cor 0 é transparente
        end = bank * 16 + 16 if self.is_4bpp else min(256, len(self.colors))
        
        best_idx = 1
        best_dist = float('inf')
        for i in range(start, min(end, len(self.colors))):
            pr, pg, pb = self.colors[i]
            # Distância euclidiana com peso perceptual (Redmean)
            dist = 2 * (r - pr)**2 + 4 * (g - pg)**2 + 3 * (b - pb)**2
            if dist < best_dist:
                best_dist = dist
                best_idx = i - (bank * 16 if self.is_4bpp else 0)
        return best_idx


class NitroTiles:
    """Gerenciador de Tiles Nintendo DS (.NCGR / .NCBR / RAHC)."""
    def __init__(self, filepath: Optional[str] = None):
        self.filepath = filepath
        self.is_4bpp = True
        self.tw = 0xFFFF
        self.th = 0xFFFF
        self.tile_data = bytearray()
        self.raw_data = bytearray()
        self.data_offset = 0x20
        self.rahc_idx = 0
        self.rahc_sz = 0
        self.trailing_data = bytearray()
        if filepath:
            self.load(filepath)

    def load(self, filepath: str):
        self.filepath = filepath
        with open(filepath, 'rb') as f:
            self.raw_data = bytearray(f.read())
            
        rahc_idx = self.raw_data.find(b'RAHC')
        if rahc_idx == -1:
            raise ValueError(f"Bloco RAHC (CHAR) não encontrado em {filepath}")
            
        # Estrutura do cabeçalho NITRO RAHC:
        # 0x08: th (uint16)
        # 0x0A: tw (uint16)
        # 0x0C: bpp (uint16) (3 = 4bpp, 4 = 8bpp)
        # 0x0E: mapping (uint16)
        # 0x10: pad1 (uint32)
        # 0x14: pad2 (uint32)
        # 0x18: data_sz (uint32)
        # 0x1C: data_off (uint32, offset dos tiles a partir de rahc_idx + 8, padrão = 0x18 = 24)
        th, tw, bpp, mapping, pad1, pad2, data_sz, data_off = struct.unpack('<HHHHIIII', self.raw_data[rahc_idx+8:rahc_idx+32])
        self.th = th
        self.tw = tw
        self.is_4bpp = (bpp == 3)
        self.rahc_idx = rahc_idx
        self.rahc_sz = struct.unpack('<I', self.raw_data[rahc_idx+4:rahc_idx+8])[0]
        
        # O offset dos tiles é rahc_idx + 8 + data_off (geralmente rahc_idx + 32)
        if data_off > 0:
            self.data_offset = rahc_idx + 8 + data_off
        else:
            self.data_offset = rahc_idx + 32
            
        tile_bytes_len = data_sz if data_sz > 0 else (self.rahc_sz - (self.data_offset - rahc_idx))
        self.tile_data = bytearray(self.raw_data[self.data_offset : self.data_offset + tile_bytes_len])
        self.trailing_data = bytearray(self.raw_data[rahc_idx + self.rahc_sz :])

    @property
    def bytes_per_tile(self) -> int:
        return 32 if self.is_4bpp else 64

    @property
    def num_tiles(self) -> int:
        return len(self.tile_data) // self.bytes_per_tile

    def get_tile_pixels(self, tile_id: int) -> List[int]:
        bpt = self.bytes_per_tile
        if tile_id >= self.num_tiles:
            return [0] * 64
        t_raw = self.tile_data[tile_id * bpt : (tile_id + 1) * bpt]
        pixels = [0] * 64
        if self.is_4bpp:
            for py in range(8):
                row_bytes = t_raw[py*4 : (py+1)*4]
                for px in range(8):
                    b = row_bytes[px // 2]
                    p_idx = (b & 0x0f) if (px % 2 == 0) else ((b >> 4) & 0x0f)
                    pixels[py * 8 + px] = p_idx
        else:
            for py in range(8):
                for px in range(8):
                    pixels[py * 8 + px] = t_raw[py * 8 + px]
        return pixels

    def save(self, filepath: Optional[str] = None):
        target = filepath or self.filepath
        out = bytearray(self.raw_data[:self.data_offset])
        # Atualizar data_sz no cabeçalho RAHC (offset rahc + 24)
        struct.pack_into('<I', out, self.rahc_idx + 24, len(self.tile_data))
        out.extend(self.tile_data)
        
        # Preservar alinhamento original do bloco RAHC
        expected_rahc_end = self.rahc_idx + self.rahc_sz
        if len(out) < expected_rahc_end:
            out.extend(b'\x00' * (expected_rahc_end - len(out)))
        
        # Ajustar tamanho do bloco RAHC (offset rahc + 4)
        new_rahc_sz = len(out) - self.rahc_idx
        struct.pack_into('<I', out, self.rahc_idx + 4, new_rahc_sz)
        
        # Preservar blocos subsequentes (ex: SOPC)
        out.extend(self.trailing_data)
        # Ajustar tamanho total no cabeçalho Nitro (offset 0x08)
        struct.pack_into('<I', out, 0x08, len(out))
            
        with open(target, 'wb') as f:
            f.write(out)


class NitroScreen:
    """Gerenciador de Tilemaps Nintendo DS (.NSCR / NRCS)."""
    def __init__(self, filepath: Optional[str] = None):
        self.filepath = filepath
        self.width = 256
        self.height = 256
        self.entries: List[int] = [] # 16-bit entries
        self.raw_data = bytearray()
        if filepath:
            self.load(filepath)

    def load(self, filepath: str):
        self.filepath = filepath
        with open(filepath, 'rb') as f:
            self.raw_data = bytearray(f.read())
            
        nrcs_idx = self.raw_data.find(b'NRCS')
        if nrcs_idx == -1:
            raise ValueError(f"Bloco NRCS (SCRN) não encontrado em {filepath}")
            
        w, h, fmt, data_sz = struct.unpack('<HHII', self.raw_data[nrcs_idx+8:nrcs_idx+20])
        self.width = w
        self.height = h
        scr_bytes = self.raw_data[nrcs_idx+20 : nrcs_idx+20+data_sz]
        self.entries = [struct.unpack('<H', scr_bytes[i:i+2])[0] for i in range(0, len(scr_bytes)-1, 2)]


# ==============================================================================
# 2. GERENCIADOR CENTRAL DE TEXTURAS (BACKEND)
# ==============================================================================

class CoralineTextureManager:
    """Gerenciador central de extração, conversão, injeção e recompilação de ROM."""

    def __init__(self, root_dir: str = DEFAULT_DATA_DIR, unpack_root: str = DEFAULT_UNPACK_ROOT):
        self.root_dir = root_dir
        self.unpack_root = unpack_root
        self.fixed_export_dir = os.path.join(self.unpack_root, "texturas_exportadas")

    def find_palette_for_texture(self, ncgr_path: str) -> Optional[str]:
        folder = os.path.dirname(ncgr_path)
        base = os.path.splitext(os.path.basename(ncgr_path))[0]
        for ext in ['.NCLR', '.nclr']:
            cand = os.path.join(folder, base + ext)
            if os.path.exists(cand): return cand
        parts = base.split('_')
        if parts[0].upper() in ['DE', 'FR', 'IT', 'SPA', 'JP']:
            stripped = '_'.join(parts[1:])
            for ext in ['.NCLR', '.nclr']:
                cand = os.path.join(folder, stripped + ext)
                if os.path.exists(cand): return cand
        if len(parts) > 2:
            group_prefix = '_'.join(parts[:-1])
            for ext in ['.NCLR', '.nclr']:
                cand = os.path.join(folder, group_prefix + ext)
                if os.path.exists(cand): return cand
        any_nclr = glob.glob(os.path.join(folder, '*.NCLR')) + glob.glob(os.path.join(folder, '*.nclr'))
        if any_nclr: return any_nclr[0]
        return None

    def find_screen_for_texture(self, ncgr_path: str) -> Optional[str]:
        folder = os.path.dirname(ncgr_path)
        base = os.path.splitext(os.path.basename(ncgr_path))[0]
        
        # 1. Correspondência direta
        for ext in ['.NSCR', '.nscr']:
            cand = os.path.join(folder, base + ext)
            if os.path.exists(cand): return cand
            
        # 2. Sufixos numéricos comuns (ex: stm_bg -> stm_bg01.NSCR)
        for ext in ['.NSCR', '.nscr']:
            for sfx in ['01', '02', '_01', '_02', '_a', '_b', '_c']:
                cand = os.path.join(folder, base + sfx + ext)
                if os.path.exists(cand): return cand

        # 3. Remoção de prefixo de idioma (DE_, FR_, IT_, SPA_, JP_)
        parts = base.split('_')
        if parts[0].upper() in ['DE', 'FR', 'IT', 'SPA', 'JP']:
            stripped = '_'.join(parts[1:])
            for ext in ['.NSCR', '.nscr']:
                cand = os.path.join(folder, stripped + ext)
                if os.path.exists(cand): return cand
                for sfx in ['01', '02', '_01', '_02']:
                    cand = os.path.join(folder, stripped + sfx + ext)
                    if os.path.exists(cand): return cand

        # 4. Remoção de dígitos finais
        import re
        m = re.match(r'^(.*?)(\d+)$', base)
        if m:
            root_no_digit = m.group(1)
            for ext in ['.NSCR', '.nscr']:
                cand = os.path.join(folder, root_no_digit + ext)
                if os.path.exists(cand): return cand

        return None

    def render_texture_to_image(self, ncgr_path: str,
                                palette_path: Optional[str] = None,
                                screen_path: Optional[str] = None) -> Tuple[Optional[Image.Image], Dict]:
        """Renderiza textura na memória retornando objeto PIL.Image e dicionário de informações."""
        tiles = NitroTiles(ncgr_path)
        pal_path = palette_path or self.find_palette_for_texture(ncgr_path)
        palette = NitroPalette(pal_path) if pal_path else None
        
        scr_path = screen_path or self.find_screen_for_texture(ncgr_path)
        screen = NitroScreen(scr_path) if scr_path else None

        if not palette:
            palette = NitroPalette()
            palette.is_4bpp = tiles.is_4bpp
            palette.colors = [(i * 16, i * 16, i * 16) for i in range(16 if tiles.is_4bpp else 256)]

        info = {
            "is_4bpp": tiles.is_4bpp,
            "num_tiles": tiles.num_tiles,
            "tw": tiles.tw,
            "th": tiles.th,
            "palette_path": pal_path,
            "screen_path": scr_path,
            "has_screen": screen is not None
        }

        # Modo A: Com Tilemap (.NSCR)
        if screen:
            img = Image.new('RGBA', (screen.width, screen.height), (0, 0, 0, 0))
            tiles_x = screen.width // 8
            tiles_y = screen.height // 8
            for ty in range(tiles_y):
                for tx in range(tiles_x):
                    idx = ty * tiles_x + tx
                    if idx >= len(screen.entries): break
                    entry = screen.entries[idx]
                    tile_id = entry & 0x3ff
                    flip_x = bool(entry & 0x400)
                    flip_y = bool(entry & 0x800)
                    pal_bank = (entry >> 12) & 0x0f

                    t_pix = tiles.get_tile_pixels(tile_id)
                    tile_img = Image.new('RGBA', (8, 8))
                    for py in range(8):
                        for px in range(8):
                            p_idx = t_pix[py * 8 + px]
                            if p_idx == 0:
                                tile_img.putpixel((px, py), (0, 0, 0, 0))
                            else:
                                c = palette.get_color(p_idx, pal_bank)
                                tile_img.putpixel((px, py), (c[0], c[1], c[2], 255))
                                
                    if flip_x: tile_img = tile_img.transpose(Image.FLIP_LEFT_RIGHT)
                    if flip_y: tile_img = tile_img.transpose(Image.FLIP_TOP_BOTTOM)
                    img.paste(tile_img, (tx * 8, ty * 8))
        else:
            # Modo B: Tilesheet direta
            if tiles.tw != 0xFFFF and tiles.th != 0xFFFF and tiles.tw > 0 and tiles.th > 0:
                tw = tiles.tw
                th = max(tiles.th, (tiles.num_tiles + tw - 1) // tw)
            else:
                tw = 16 if tiles.num_tiles >= 16 else max(1, tiles.num_tiles)
                th = (tiles.num_tiles + tw - 1) // tw

            img = Image.new('RGBA', (tw * 8, th * 8), (0, 0, 0, 0))
            for tile_id in range(tiles.num_tiles):
                tx = tile_id % tw
                ty = tile_id // tw
                t_pix = tiles.get_tile_pixels(tile_id)
                tile_img = Image.new('RGBA', (8, 8))
                for py in range(8):
                    for px in range(8):
                        p_idx = t_pix[py * 8 + px]
                        if p_idx == 0:
                            tile_img.putpixel((px, py), (0, 0, 0, 0))
                        else:
                            c = palette.get_color(p_idx, 0)
                            tile_img.putpixel((px, py), (c[0], c[1], c[2], 255))
                img.paste(tile_img, (tx * 8, ty * 8))

        info["width"] = img.width
        info["height"] = img.height
        return img, info

    def export_texture(self, ncgr_path: str, png_out_path: str,
                       palette_path: Optional[str] = None,
                       screen_path: Optional[str] = None) -> bool:
        try:
            img, info = self.render_texture_to_image(ncgr_path, palette_path, screen_path)
            if not img: return False
            os.makedirs(os.path.dirname(os.path.abspath(png_out_path)), exist_ok=True)
            img.save(png_out_path)

            meta_path = os.path.splitext(png_out_path)[0] + '.meta.json'
            meta = {
                "source_ncgr": os.path.abspath(ncgr_path),
                "target_ncgr": os.path.abspath(ncgr_path),
                "palette_path": os.path.abspath(info["palette_path"]) if info["palette_path"] else None,
                "screen_path": os.path.abspath(info["screen_path"]) if info["screen_path"] else None,
                "is_4bpp": info["is_4bpp"],
                "tw": info["tw"],
                "th": info["th"],
                "num_tiles": info["num_tiles"],
                "image_width": info["width"],
                "image_height": info["height"]
            }
            with open(meta_path, 'w', encoding='utf-8') as f_meta:
                json.dump(meta, f_meta, indent=2)
            return True
        except Exception as e:
            print(f"Erro ao exportar {ncgr_path}: {e}")
            return False

    def import_texture(self, png_in_path: str, ncgr_target_path: str,
                       palette_path: Optional[str] = None,
                       backup: bool = True) -> bool:
        try:
            if not os.path.exists(png_in_path):
                raise FileNotFoundError(f"PNG não encontrado: {png_in_path}")

            if backup:
                bak_path = ncgr_target_path + '.bak'
                if not os.path.exists(bak_path):
                    shutil.copy2(ncgr_target_path, bak_path)

            meta_path = os.path.splitext(png_in_path)[0] + '.meta.json'
            meta = {}
            if os.path.exists(meta_path):
                with open(meta_path, 'r', encoding='utf-8') as f_meta:
                    meta = json.load(f_meta)

            tiles = NitroTiles(ncgr_target_path)
            pal_path = palette_path or meta.get("palette_path") or self.find_palette_for_texture(ncgr_target_path)
            palette = NitroPalette(pal_path) if pal_path else None
            if not palette:
                raise ValueError("Paleta não encontrada para quantização.")

            scr_path = meta.get("screen_path") or self.find_screen_for_texture(ncgr_target_path)
            screen = NitroScreen(scr_path) if (scr_path and os.path.exists(scr_path)) else None

            img = Image.open(png_in_path).convert('RGBA')

            new_tile_data = bytearray()
            is_4bpp = tiles.is_4bpp
            bytes_per_tile = 32 if is_4bpp else 64

            # Se temos tela (.NSCR), remapeia considerando flip_x/flip_y/bank
            if screen:
                tiles_x = screen.width // 8
                tiles_y = screen.height // 8
                tile_dict = {}
                for idx, entry in enumerate(screen.entries):
                    tile_id = entry & 0x3ff
                    if tile_id >= tiles.num_tiles: continue
                    flip_x = bool(entry & 0x400)
                    flip_y = bool(entry & 0x800)
                    pal_bank = (entry >> 12) & 0x0f
                    tx = idx % tiles_x
                    ty = idx // tiles_x

                    tile_img = img.crop((tx * 8, ty * 8, tx * 8 + 8, ty * 8 + 8))
                    if flip_y: tile_img = tile_img.transpose(Image.FLIP_TOP_BOTTOM)
                    if flip_x: tile_img = tile_img.transpose(Image.FLIP_LEFT_RIGHT)

                    tile_bytes = bytearray(bytes_per_tile)
                    for py in range(8):
                        for px in range(8):
                            r, g, b, a = tile_img.getpixel((px, py))
                            p_idx = 0 if a < 128 else palette.match_color(r, g, b, bank=pal_bank)
                            if is_4bpp:
                                byte_off = py * 4 + (px // 2)
                                if px % 2 == 0:
                                    tile_bytes[byte_off] |= (p_idx & 0x0f)
                                else:
                                    tile_bytes[byte_off] |= ((p_idx & 0x0f) << 4)
                            else:
                                tile_bytes[py * 8 + px] = p_idx & 0xff
                    tile_dict[tile_id] = tile_bytes

                for tile_id in range(tiles.num_tiles):
                    if tile_id in tile_dict:
                        new_tile_data.extend(tile_dict[tile_id])
                    else:
                        new_tile_data.extend(bytearray(bytes_per_tile))
            else:
                # Tilesheet linear
                tw = tiles.tw if tiles.tw != 0xFFFF else (meta.get("tw") or (img.width // 8) or 16)
                for tile_id in range(tiles.num_tiles):
                    tx = tile_id % tw
                    ty = tile_id // tw
                    tile_bytes = bytearray(bytes_per_tile)
                    for py in range(8):
                        for px in range(8):
                            img_x = tx * 8 + px
                            img_y = ty * 8 + py
                            if img_x < img.width and img_y < img.height:
                                r, g, b, a = img.getpixel((img_x, img_y))
                                p_idx = 0 if a < 128 else palette.match_color(r, g, b, bank=0)
                            else:
                                p_idx = 0

                            if is_4bpp:
                                byte_off = py * 4 + (px // 2)
                                if px % 2 == 0:
                                    tile_bytes[byte_off] |= (p_idx & 0x0f)
                                else:
                                    tile_bytes[byte_off] |= ((p_idx & 0x0f) << 4)
                            else:
                                tile_bytes[py * 8 + px] = p_idx & 0xff
                    new_tile_data.extend(tile_bytes)

            tiles.tile_data = new_tile_data
            tiles.save(ncgr_target_path)
            return True
        except Exception as e:
            print(f"Erro ao importar {png_in_path} para {ncgr_target_path}: {e}")
            return False

    def scan_all_textures(self) -> List[Dict]:
        results = []
        for root, _, files in os.walk(self.root_dir):
            if 'backup' in root or 'txt_json_dumps' in root: continue
            for f in files:
                if f.lower().endswith(('.ncgr', '.ncbr')):
                    fpath = os.path.join(root, f)
                    pal = self.find_palette_for_texture(fpath)
                    scr = self.find_screen_for_texture(fpath)
                    rel_p = os.path.relpath(fpath, self.root_dir)
                    subfolder = rel_p.split(os.sep)[0] if os.sep in rel_p else 'raiz'
                    results.append({
                        "file": f,
                        "path": fpath,
                        "rel_path": rel_p,
                        "subfolder": subfolder,
                        "palette": pal,
                        "screen": scr
                    })
        return results

    def batch_export(self, output_dir: str, progress_callback=None) -> int:
        textures = self.scan_all_textures()
        count = 0
        os.makedirs(output_dir, exist_ok=True)
        total = len(textures)
        for i, item in enumerate(textures):
            rel_no_ext = os.path.splitext(item['rel_path'])[0]
            out_png = os.path.join(output_dir, rel_no_ext + '.png')
            if self.export_texture(item['path'], out_png, item['palette'], item['screen']):
                count += 1
            if progress_callback:
                progress_callback(i + 1, total, item['file'])
        return count

    def batch_import_from_dir(self, fixed_dir: str, only_modified: bool = True, log_callback=None) -> Dict:
        """Varre fixed_dir recursivamente e injeta todos os PNGs encontrados."""
        if not os.path.exists(fixed_dir):
            return {"injected": 0, "skipped": 0, "errors": 0, "msg": "Pasta não encontrada."}

        png_files = []
        for r, _, files in os.walk(fixed_dir):
            for f in files:
                if f.lower().endswith('.png'):
                    png_files.append(os.path.join(r, f))

        if not png_files:
            return {"injected": 0, "skipped": 0, "errors": 0, "msg": "Nenhum arquivo PNG encontrado."}

        all_tex = self.scan_all_textures()
        injected = 0
        skipped = 0
        errors = 0

        for png_path in png_files:
            meta_path = os.path.splitext(png_path)[0] + '.meta.json'
            target_ncgr = None
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, 'r', encoding='utf-8') as fm:
                        meta = json.load(fm)
                        target_ncgr = meta.get('target_ncgr') or meta.get('source_ncgr')
                except Exception:
                    pass

            if not target_ncgr or not os.path.exists(target_ncgr):
                base = os.path.splitext(os.path.basename(png_path))[0]
                matched = [t['path'] for t in all_tex if os.path.splitext(t['file'])[0].lower() == base.lower()]
                if len(matched) == 1:
                    target_ncgr = matched[0]
                else:
                    rel = os.path.relpath(png_path, fixed_dir)
                    cand = os.path.join(self.root_dir, os.path.splitext(rel)[0] + '.NCGR')
                    if os.path.exists(cand): target_ncgr = cand

            if not target_ncgr or not os.path.exists(target_ncgr):
                if log_callback: log_callback(f"[PULADO] {os.path.basename(png_path)}: Não encontrou .NCGR alvo na ROM.")
                skipped += 1
                continue

            # Checar modificação se only_modified for True
            if only_modified:
                png_mtime = os.path.getmtime(png_path)
                ncgr_mtime = os.path.getmtime(target_ncgr)
                if png_mtime <= ncgr_mtime:
                    skipped += 1
                    continue

            ok = self.import_texture(png_path, target_ncgr, backup=True)
            if ok:
                injected += 1
                if log_callback: log_callback(f"[INJETADO] {os.path.basename(png_path)} -> {os.path.relpath(target_ncgr, self.root_dir)}")
            else:
                errors += 1
                if log_callback: log_callback(f"[ERRO] Falha ao injetar {os.path.basename(png_path)}")

        return {"injected": injected, "skipped": skipped, "errors": errors, "msg": f"{injected} texturas injetadas."}

    def repack_rom(self) -> Tuple[bool, str]:
        ndstool = os.path.join(os.path.dirname(self.unpack_root), "ndstool.exe")
        target_nds = os.path.join(os.path.dirname(self.unpack_root), "current.nds")
        if not os.path.exists(ndstool):
            return False, f"ndstool.exe não encontrado em {ndstool}"
        
        cmd = [
            ndstool,
            "-c", target_nds,
            "-9", "NDS_UNPACK/arm9.bin",
            "-7", "NDS_UNPACK/arm7.bin",
            "-y9", "NDS_UNPACK/y9.bin",
            "-y7", "NDS_UNPACK/y7.bin",
            "-d", "NDS_UNPACK/data",
            "-y", "NDS_UNPACK/overlay",
            "-t", "NDS_UNPACK/banner.bin",
            "-h", "NDS_UNPACK/header.bin"
        ]
        res = subprocess.run(cmd, cwd=os.path.dirname(self.unpack_root), capture_output=True, text=True)
        if res.returncode != 0:
            return False, f"Erro no ndstool: {res.stderr}"

        # Preserva header de 64 MB (0x14 = 0x09)
        with open(target_nds, "r+b") as f:
            f.seek(0x14)
            f.write(bytes([0x09]))

        sz_mb = os.path.getsize(target_nds) / (1024 * 1024)
        return True, f"ROM recompilada com sucesso em current.nds ({sz_mb:.2f} MB, cabeçalho de 64 MB garantido)!"


# ==============================================================================
# 3. INTERFACE GRÁFICA MODERNA (TKINTER DARK THEME)
# ==============================================================================

class CoralineTextureToolGUI:
    """GUI de Alta Performance para visualização, extração e injeção de texturas."""

    def __init__(self, root: tk.Tk, manager: CoralineTextureManager):
        self.root = root
        self.mgr = manager
        self.root.title("Coraline DS - Gerenciador & Injetor de Texturas 2D")
        self.root.geometry("1240x820")
        self.root.minsize(1020, 680)
        self.root.configure(bg="#12131C")

        # Dados
        self.all_textures: List[Dict] = []
        self.filtered_textures: List[Dict] = []
        self.selected_item: Optional[Dict] = None
        self.current_preview_img: Optional[Image.Image] = None
        self.current_preview_photo: Optional[ImageTk.PhotoImage] = None
        self.zoom_level: int = 2

        # Variáveis de UI
        self.only_modified_var = tk.BooleanVar(value=True)
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", self.apply_filter)
        self.folder_filter_var = tk.StringVar(value="Todas as Pastas")

        self.setup_theme()
        self.build_ui()
        self.load_textures()

    def setup_theme(self):
        self.style = ttk.Style()
        self.style.theme_use("clam")

        self.BG_MAIN = "#12131C"
        self.BG_CARD = "#1A1B26"
        self.BG_CARD_LIGHT = "#24283B"
        self.ACCENT = "#7AA2F7"
        self.ACCENT_PURPLE = "#BB9AF7"
        self.TEXT_MAIN = "#C0CAF5"
        self.TEXT_MUTED = "#7982A9"
        self.COLOR_SUCCESS = "#9ECE6A"
        self.COLOR_WARN = "#E0AF68"
        self.COLOR_DANGER = "#F7768E"

        self.style.configure(".", background=self.BG_MAIN, foreground=self.TEXT_MAIN, font=("Segoe UI", 10))
        self.style.configure("TFrame", background=self.BG_MAIN)
        self.style.configure("Card.TFrame", background=self.BG_CARD)

        self.style.configure("Action.TButton", background="#3B4261", foreground="#FFFFFF", 
                             font=("Segoe UI", 9, "bold"), borderwidth=0, padding=6)
        self.style.map("Action.TButton", background=[("active", "#7AA2F7"), ("pressed", "#565F89")])

        self.style.configure("Primary.TButton", background="#7AA2F7", foreground="#0F101A", 
                             font=("Segoe UI", 9, "bold"), borderwidth=0, padding=7)
        self.style.map("Primary.TButton", background=[("active", "#89B4FA"), ("pressed", "#5E81AC")])

        self.style.configure("Success.TButton", background="#9ECE6A", foreground="#0F101A", 
                             font=("Segoe UI", 9, "bold"), borderwidth=0, padding=7)
        self.style.map("Success.TButton", background=[("active", "#B9F27C"), ("pressed", "#73DACA")])

        self.style.configure("Magic.TButton", background="#BB9AF7", foreground="#0F101A", 
                             font=("Segoe UI", 9, "bold"), borderwidth=0, padding=7)
        self.style.map("Magic.TButton", background=[("active", "#DDB6F2"), ("pressed", "#9D7CD8")])

        self.style.configure("Treeview", background="#1A1B26", foreground="#C0CAF5", 
                             fieldbackground="#1A1B26", rowheight=26, borderwidth=0, font=("Segoe UI", 9))
        self.style.map("Treeview", background=[("selected", "#3B4261")], foreground=[("selected", "#FFFFFF")])
        self.style.configure("Treeview.Heading", background="#24283B", foreground="#7AA2F7", 
                             font=("Segoe UI", 9, "bold"), borderwidth=0)
        self.style.map("Treeview.Heading", background=[("active", "#2E3440")])

        self.style.configure("TCombobox", fieldbackground="#24283B", background="#24283B", foreground="#FFFFFF")
        self.style.configure("TCheckbutton", background=self.BG_CARD, foreground=self.TEXT_MAIN, font=("Segoe UI", 9))

    def build_ui(self):
        # 1. HEADER
        header = tk.Frame(self.root, bg=self.BG_CARD, height=60)
        header.pack(side="top", fill="x")

        title_box = tk.Frame(header, bg=self.BG_CARD)
        title_box.pack(side="left", padx=20, pady=10)
        tk.Label(title_box, text="🎨 CORALINE DS", fg=self.ACCENT_PURPLE, bg=self.BG_CARD, font=("Segoe UI", 14, "bold")).pack(side="left")
        tk.Label(title_box, text=" | Gerenciador & Injetor de Texturas 2D", fg=self.TEXT_MUTED, bg=self.BG_CARD, font=("Segoe UI", 10)).pack(side="left")

        # Botão Recompilar ROM no Header
        btn_repack = ttk.Button(header, text="📦 Recompilar ROM (current.nds)", style="Magic.TButton", command=self.action_repack_rom)
        btn_repack.pack(side="right", padx=20, pady=10)

        # 2. BARRA DE CONTROLE DA PASTA FIXA
        ctrl_bar = tk.Frame(self.root, bg=self.BG_CARD)
        ctrl_bar.pack(fill="x", padx=15, pady=(10, 5))

        tk.Label(ctrl_bar, text="📁 Pasta Fixa de Exportação/Injeção:", fg=self.ACCENT, bg=self.BG_CARD, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(15, 6), pady=8)
        
        lbl_fixed_path = tk.Label(ctrl_bar, text=self.mgr.fixed_export_dir, fg="#FFFFFF", bg=self.BG_CARD_LIGHT, font=("Segoe UI", 9), padx=8, pady=3)
        lbl_fixed_path.pack(side="left", fill="x", expand=True, padx=4, pady=8)

        btn_open_folder = ttk.Button(ctrl_bar, text="Abrir Pasta no Explorer", style="Action.TButton", command=self.action_open_fixed_folder)
        btn_open_folder.pack(side="left", padx=(6, 15), pady=8)

        # 3. BARRA DE AÇÕES RÁPIDAS
        action_bar = tk.Frame(self.root, bg=self.BG_CARD)
        action_bar.pack(fill="x", padx=15, pady=(0, 10))

        btn_export_sel = ttk.Button(action_bar, text="📤 Exportar Selecionada", style="Success.TButton", command=self.action_export_selected)
        btn_export_sel.pack(side="left", padx=(15, 6), pady=8)

        btn_export_all = ttk.Button(action_bar, text="🚀 Exportar TODAS (682 Texturas)", style="Action.TButton", command=self.action_export_all)
        btn_export_all.pack(side="left", padx=6, pady=8)

        btn_import_fixed = ttk.Button(action_bar, text="📥 Importar & Injetar da Pasta Fixa", style="Primary.TButton", command=self.action_import_from_fixed_dir)
        btn_import_fixed.pack(side="left", padx=6, pady=8)

        btn_import_single = ttk.Button(action_bar, text="🔄 Injetar PNG Específico...", style="Action.TButton", command=self.action_import_single_file)
        btn_import_single.pack(side="left", padx=6, pady=8)

        chk_mod = ttk.Checkbutton(action_bar, text="Injetar apenas PNGs modificados", variable=self.only_modified_var, style="TCheckbutton")
        chk_mod.pack(side="right", padx=15, pady=8)

        # 4. CORPO PRINCIPAL (LISTA À ESQUERDA, PRÉVIA À DIREITA)
        body = tk.Frame(self.root, bg=self.BG_MAIN)
        body.pack(fill="both", expand=True, padx=15, pady=0)

        # PAINEL ESQUERDO: LISTA DE TEXTURAS
        left_panel = tk.Frame(body, bg=self.BG_CARD, width=620)
        left_panel.pack(side="left", fill="both", expand=True, padx=(0, 10))

        # Filtros
        filter_box = tk.Frame(left_panel, bg=self.BG_CARD)
        filter_box.pack(fill="x", padx=12, pady=10)

        tk.Label(filter_box, text="🔍 Buscar:", fg=self.TEXT_MUTED, bg=self.BG_CARD, font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))
        entry_search = tk.Entry(filter_box, textvariable=self.filter_var, bg=self.BG_CARD_LIGHT, fg="#FFFFFF",
                                insertbackground="#FFFFFF", relief="flat", font=("Segoe UI", 9), width=24)
        entry_search.pack(side="left", padx=(0, 10), ipady=3)

        tk.Label(filter_box, text="Pasta:", fg=self.TEXT_MUTED, bg=self.BG_CARD, font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))
        self.combo_folder = ttk.Combobox(filter_box, values=["Todas as Pastas", "cinema", "info", "kizu", "map2D"],
                                         textvariable=self.folder_filter_var, state="readonly", width=16)
        self.combo_folder.pack(side="left", padx=(0, 10))
        self.combo_folder.bind("<<ComboboxSelected>>", self.apply_filter)

        self.lbl_count = tk.Label(filter_box, text="0 texturas", fg=self.ACCENT, bg=self.BG_CARD, font=("Segoe UI", 9, "bold"))
        self.lbl_count.pack(side="right")

        # Treeview de Texturas
        tree_scroll = ttk.Scrollbar(left_panel, orient="vertical")
        self.tree = ttk.Treeview(left_panel, columns=("file", "folder", "palette", "status"), show="headings",
                                 selectmode="browse", yscrollcommand=tree_scroll.set)
        tree_scroll.config(command=self.tree.yview)

        self.tree.heading("file", text="Arquivo Proprietário")
        self.tree.heading("folder", text="Pasta")
        self.tree.heading("palette", text="Paleta (.NCLR)")
        self.tree.heading("status", text="Status")

        self.tree.column("file", width=220, anchor="w")
        self.tree.column("folder", width=80, anchor="center")
        self.tree.column("palette", width=180, anchor="w")
        self.tree.column("status", width=100, anchor="center")

        self.tree.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=(0, 12))
        tree_scroll.pack(side="right", fill="y", pady=(0, 12), padx=(0, 6))
        self.tree.bind("<<TreeviewSelect>>", self.on_item_selected)

        # PAINEL DIREITO: PRÉVIA E DETALHES
        right_panel = tk.Frame(body, bg=self.BG_CARD, width=540)
        right_panel.pack(side="right", fill="both", padx=0)
        right_panel.pack_propagate(False)

        # Cabeçalho da Prévia
        prev_header = tk.Frame(right_panel, bg=self.BG_CARD)
        prev_header.pack(fill="x", padx=15, pady=(12, 6))
        tk.Label(prev_header, text="PRÉVIA DA TEXTURA", fg=self.ACCENT, bg=self.BG_CARD, font=("Segoe UI", 10, "bold")).pack(side="left")

        # Controles de Zoom
        zoom_box = tk.Frame(prev_header, bg=self.BG_CARD)
        zoom_box.pack(side="right")
        tk.Label(zoom_box, text="Zoom:", fg=self.TEXT_MUTED, bg=self.BG_CARD, font=("Segoe UI", 8)).pack(side="left", padx=2)
        for z in [1, 2, 3, 4]:
            btn_z = tk.Button(zoom_box, text=f"{z}x", bg=self.BG_CARD_LIGHT, fg="#FFFFFF", relief="flat",
                              font=("Segoe UI", 8, "bold"), padx=5, pady=1,
                              command=lambda val=z: self.set_zoom(val))
            btn_z.pack(side="left", padx=1)

        # Área de Visualização com Fundo Xadrez
        self.canvas_preview = tk.Canvas(right_panel, bg="#161722", highlightthickness=0, height=280)
        self.canvas_preview.pack(fill="x", padx=15, pady=6)

        # Informações da Imagem
        self.lbl_dimensions = tk.Label(right_panel, text="Dimensões: -", fg=self.TEXT_MAIN, bg=self.BG_CARD, font=("Segoe UI", 9, "bold"))
        self.lbl_dimensions.pack(anchor="w", padx=15, pady=(4, 2))

        # Detalhes Técnicos
        info_card = tk.Frame(right_panel, bg=self.BG_CARD_LIGHT)
        info_card.pack(fill="x", padx=15, pady=6)

        self.lbl_det_path = tk.Label(info_card, text="Arquivo: -", fg=self.TEXT_MUTED, bg=self.BG_CARD_LIGHT, font=("Segoe UI", 9), anchor="w")
        self.lbl_det_path.pack(fill="x", padx=10, pady=2)

        self.lbl_det_pal = tk.Label(info_card, text="Paleta: -", fg=self.TEXT_MUTED, bg=self.BG_CARD_LIGHT, font=("Segoe UI", 9), anchor="w")
        self.lbl_det_pal.pack(fill="x", padx=10, pady=2)

        self.lbl_det_scr = tk.Label(info_card, text="Tilemap (.NSCR): -", fg=self.TEXT_MUTED, bg=self.BG_CARD_LIGHT, font=("Segoe UI", 9), anchor="w")
        self.lbl_det_scr.pack(fill="x", padx=10, pady=2)

        self.lbl_det_status = tk.Label(info_card, text="Status na Pasta Fixa: Não exportado", fg=self.COLOR_WARN, bg=self.BG_CARD_LIGHT, font=("Segoe UI", 9, "bold"), anchor="w")
        self.lbl_det_status.pack(fill="x", padx=10, pady=2)

        # Botões de Ação Específica da Textura
        btn_box = tk.Frame(right_panel, bg=self.BG_CARD)
        btn_box.pack(fill="x", padx=15, pady=8)

        btn_exp_this = ttk.Button(btn_box, text="📤 Exportar Esta", style="Success.TButton", command=self.action_export_selected)
        btn_exp_this.pack(side="left", padx=(0, 6), expand=True, fill="x")

        btn_open_img = ttk.Button(btn_box, text="🎨 Abrir PNG no Editor", style="Action.TButton", command=self.action_open_image_in_editor)
        btn_open_img.pack(side="left", padx=6, expand=True, fill="x")

        btn_inj_this = ttk.Button(btn_box, text="📥 Reinjetar Esta", style="Primary.TButton", command=self.action_inject_current_texture)
        btn_inj_this.pack(side="left", padx=(6, 0), expand=True, fill="x")

        # 5. CONSOLE DE LOG INFERIOR
        bottom_frame = tk.Frame(self.root, bg=self.BG_CARD, height=130)
        bottom_frame.pack(fill="x", padx=15, pady=10)

        log_hdr = tk.Frame(bottom_frame, bg=self.BG_CARD)
        log_hdr.pack(fill="x", padx=12, pady=(6, 2))
        tk.Label(log_hdr, text="HISTÓRICO DE ATIVIDADES & STATUS", fg=self.ACCENT, bg=self.BG_CARD, font=("Segoe UI", 9, "bold")).pack(side="left")
        
        btn_clear = tk.Button(log_hdr, text="Limpar", bg=self.BG_CARD_LIGHT, fg=self.TEXT_MUTED, relief="flat",
                              font=("Segoe UI", 8), command=self.clear_log)
        btn_clear.pack(side="right")

        self.txt_log = ScrolledText(bottom_frame, height=5, bg="#0F101A", fg="#C0CAF5", relief="flat",
                                    font=("Consolas", 9), insertbackground="#FFFFFF")
        self.txt_log.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        self.txt_log.tag_config("success", foreground=self.COLOR_SUCCESS)
        self.txt_log.tag_config("error", foreground=self.COLOR_DANGER)
        self.txt_log.tag_config("warn", foreground=self.COLOR_WARN)
        self.txt_log.tag_config("info", foreground=self.ACCENT)

        self.log("Sistema iniciado. Pronto para extrair e injetar texturas.", "info")

    # ==========================================================================
    # LOGGING & FEEDBACK
    # ==========================================================================
    def log(self, text: str, tag: str = "info"):
        t_str = time.strftime("[%H:%M:%S] ")
        self.txt_log.insert(tk.END, t_str + text + "\n", tag)
        self.txt_log.see(tk.END)

    def clear_log(self):
        self.txt_log.delete("1.0", tk.END)

    # ==========================================================================
    # CARREGAMENTO E FILTRAGEM
    # ==========================================================================
    def load_textures(self):
        self.log("Escaneando arquivos .NCGR na ROM...", "info")
        self.all_textures = self.mgr.scan_all_textures()
        self.log(f"{len(self.all_textures)} texturas carregadas com sucesso.", "success")
        self.apply_filter()

    def apply_filter(self, *args):
        query = self.filter_var.get().strip().lower()
        folder_filter = self.folder_filter_var.get()

        self.filtered_textures = []
        for t in self.all_textures:
            if folder_filter != "Todas as Pastas" and t["subfolder"] != folder_filter:
                continue
            if query and (query not in t["file"].lower() and query not in t["rel_path"].lower()):
                continue
            self.filtered_textures.append(t)

        self.tree.delete(*self.tree.get_children())
        for t in self.filtered_textures:
            pal_name = os.path.basename(t["palette"]) if t["palette"] else "Nenhuma"
            # Checar se já foi exportado na pasta fixa
            base_png = os.path.splitext(t["file"])[0] + ".png"
            fixed_png = os.path.join(self.mgr.fixed_export_dir, base_png)
            status_str = "Exportado" if os.path.exists(fixed_png) else "Original"

            self.tree.insert("", "end", iid=t["path"], values=(t["file"], t["subfolder"], pal_name, status_str))

        self.lbl_count.config(text=f"{len(self.filtered_textures)} texturas exibidas")

    # ==========================================================================
    # PRÉVIA DA TEXTURA & ZOOM
    # ==========================================================================
    def set_zoom(self, zoom: int):
        self.zoom_level = zoom
        if self.current_preview_img:
            self.render_preview(self.current_preview_img)

    def on_item_selected(self, event):
        sel = self.tree.selection()
        if not sel: return
        ncgr_path = sel[0]
        matched = [t for t in self.all_textures if t["path"] == ncgr_path]
        if not matched: return
        self.selected_item = matched[0]

        t = self.selected_item
        img, info = self.mgr.render_texture_to_image(t["path"], t["palette"], t["screen"])
        if img:
            self.current_preview_img = img
            self.render_preview(img)
            bpp_str = "4bpp (16 cores)" if info["is_4bpp"] else "8bpp (256 cores)"
            scr_str = os.path.basename(info["screen_path"]) if info["screen_path"] else "Nenhum (Tilesheet)"
            self.lbl_dimensions.config(text=f"Dimensões: {info['width']} x {info['height']} px | {info['num_tiles']} Tiles | {bpp_str}")
            self.lbl_det_path.config(text=f"Arquivo: {t['rel_path']}")
            self.lbl_det_pal.config(text=f"Paleta: {os.path.basename(info['palette_path']) if info['palette_path'] else 'Padrão'}")
            self.lbl_det_scr.config(text=f"Tilemap: {scr_str}")

            # Status na pasta fixa
            base_png = os.path.splitext(t["file"])[0] + ".png"
            fixed_png = os.path.join(self.mgr.fixed_export_dir, base_png)
            if os.path.exists(fixed_png):
                mtime_str = time.strftime("%d/%m/%Y %H:%M", time.localtime(os.path.getmtime(fixed_png)))
                self.lbl_det_status.config(text=f"Status na Pasta Fixa: Exportado ({mtime_str})", fg=self.COLOR_SUCCESS)
            else:
                self.lbl_det_status.config(text="Status na Pasta Fixa: Não exportado", fg=self.COLOR_WARN)

    def render_preview(self, img: Image.Image):
        self.canvas_preview.delete("all")
        cw = max(200, self.canvas_preview.winfo_width())
        ch = max(150, self.canvas_preview.winfo_height())

        # Desenhar xadrez de transparência (checkerboard)
        tile_sz = 16
        for y in range(0, ch, tile_sz):
            for x in range(0, cw, tile_sz):
                c = "#1C1E2D" if ((x // tile_sz + y // tile_sz) % 2 == 0) else "#141520"
                self.canvas_preview.create_rectangle(x, y, x + tile_sz, y + tile_sz, fill=c, outline="")

        # Escalar com interpolação Nearest Neighbor para pixel art impecável
        scale = max(1, self.zoom_level)
        sw = img.width * scale
        sh = img.height * scale
        if sw > cw or sh > ch:
            # Auto-fit se maior que o canvas
            scale = min(cw / img.width, ch / img.height)
            sw = max(1, int(img.width * scale))
            sh = max(1, int(img.height * scale))

        scaled_img = img.resize((sw, sh), Image.Resampling.NEAREST)
        self.current_preview_photo = ImageTk.PhotoImage(scaled_img)

        # Centralizar no Canvas
        cx = (cw - sw) // 2
        cy = (ch - sh) // 2
        self.canvas_preview.create_image(cx, cy, anchor="nw", image=self.current_preview_photo)

    # ==========================================================================
    # AÇÕES PRINCIPAIS
    # ==========================================================================
    def action_open_fixed_folder(self):
        os.makedirs(self.mgr.fixed_export_dir, exist_ok=True)
        try:
            os.startfile(self.mgr.fixed_export_dir)
            self.log(f"Pasta aberta no Explorer: {self.mgr.fixed_export_dir}", "info")
        except Exception as e:
            self.log(f"Erro ao abrir pasta: {e}", "error")

    def action_export_selected(self):
        if not self.selected_item:
            messagebox.showinfo("Aviso", "Por favor, selecione uma textura na lista primeiro.")
            return

        t = self.selected_item
        os.makedirs(self.mgr.fixed_export_dir, exist_ok=True)
        base_png = os.path.splitext(t["file"])[0] + ".png"
        out_png = os.path.join(self.mgr.fixed_export_dir, base_png)

        ok = self.mgr.export_texture(t["path"], out_png, t["palette"], t["screen"])
        if ok:
            self.log(f"Exportado com sucesso: {base_png} para {self.mgr.fixed_export_dir}", "success")
            self.lbl_det_status.config(text=f"Status na Pasta Fixa: Exportado agora", fg=self.COLOR_SUCCESS)
            self.tree.set(t["path"], "status", "Exportado")
        else:
            self.log(f"Falha ao exportar {t['file']}", "error")

    def action_export_all(self):
        if not messagebox.askyesno("Confirmar Exportação", "Deseja exportar todas as 682 texturas para a pasta fixa?\nIsso levará cerca de 30 segundos."):
            return

        def run_thread():
            self.log("Iniciando exportação em lote de todas as texturas...", "info")
            def prog(cur, tot, fname):
                if cur % 50 == 0 or cur == tot:
                    self.root.after(0, lambda: self.log(f"Progresso: {cur}/{tot} texturas exportadas ({fname})...", "info"))
            
            count = self.mgr.batch_export(self.mgr.fixed_export_dir, progress_callback=prog)
            self.root.after(0, lambda: self.log(f"Exportação em lote concluída! {count} texturas exportadas com sucesso.", "success"))
            self.root.after(0, lambda: messagebox.showinfo("Sucesso", f"{count} texturas foram exportadas para:\n{self.mgr.fixed_export_dir}"))
            self.root.after(0, self.apply_filter)

        threading.Thread(target=run_thread, daemon=True).start()

    def action_import_from_fixed_dir(self):
        only_mod = self.only_modified_var.get()
        fixed_dir = self.mgr.fixed_export_dir

        if not os.path.exists(fixed_dir):
            messagebox.showinfo("Aviso", f"A pasta fixa '{fixed_dir}' ainda não existe.\nExporte alguma textura primeiro.")
            return

        def run_import():
            self.log("Varrendo pasta fixa e reinjetando imagens na ROM...", "info")
            res = self.mgr.batch_import_from_dir(fixed_dir, only_modified=only_mod,
                                                 log_callback=lambda m: self.root.after(0, lambda: self.log(m, "info")))
            
            injected = res["injected"]
            msg = f"Injeção concluída!\n\n• Texturas injetadas: {injected}\n• Puladas (não modificadas): {res['skipped']}\n• Erros: {res['errors']}"
            if injected > 0:
                self.root.after(0, lambda: self.log(f"Sucesso: {injected} texturas reinjetadas na ROM!", "success"))
                self.root.after(0, lambda: messagebox.showinfo("Injeção Concluída", msg))
            else:
                self.root.after(0, lambda: self.log("Nenhuma textura necessitou de injeção.", "warn"))
                self.root.after(0, lambda: messagebox.showinfo("Injeção", msg))

        threading.Thread(target=run_import, daemon=True).start()

    def action_import_single_file(self):
        file_path = filedialog.askopenfilename(title="Selecione a Imagem PNG Editada",
                                               filetypes=[("Imagens PNG", "*.png"), ("Todos os Arquivos", "*.*")])
        if not file_path: return

        # Determinar alvo
        target_ncgr = None
        meta_file = os.path.splitext(file_path)[0] + ".meta.json"
        if os.path.exists(meta_file):
            try:
                with open(meta_file, 'r', encoding='utf-8') as fm:
                    meta = json.load(fm)
                    target_ncgr = meta.get("target_ncgr") or meta.get("source_ncgr")
            except Exception:
                pass

        if not target_ncgr and self.selected_item:
            target_ncgr = self.selected_item["path"]

        if not target_ncgr:
            messagebox.showerror("Erro", "Não foi possível determinar o arquivo .NCGR de destino.\nSelecione a textura na lista antes de injetar.")
            return

        ok = self.mgr.import_texture(file_path, target_ncgr, backup=True)
        if ok:
            self.log(f"Sucesso: {os.path.basename(file_path)} injetado em {os.path.basename(target_ncgr)}!", "success")
            messagebox.showinfo("Sucesso", f"Imagem reinjetada com sucesso em:\n{target_ncgr}")
            # Atualiza prévia
            if self.selected_item and self.selected_item["path"] == target_ncgr:
                self.on_item_selected(None)
        else:
            self.log(f"Falha ao injetar {file_path}", "error")
            messagebox.showerror("Erro", "Ocorreu um erro durante a reinjeção da textura.")

    def action_inject_current_texture(self):
        if not self.selected_item: return
        t = self.selected_item
        base_png = os.path.splitext(t["file"])[0] + ".png"
        fixed_png = os.path.join(self.mgr.fixed_export_dir, base_png)

        if not os.path.exists(fixed_png):
            messagebox.showwarning("Aviso", f"O arquivo PNG correspondente não foi encontrado na pasta fixa:\n{fixed_png}\n\nExporte-o primeiro e faça suas edições.")
            return

        ok = self.mgr.import_texture(fixed_png, t["path"], backup=True)
        if ok:
            self.log(f"Textura reinjetada com sucesso a partir de: {base_png}", "success")
            messagebox.showinfo("Sucesso", f"Textura reinjetada com sucesso em:\n{t['file']}")
            self.on_item_selected(None)
        else:
            self.log(f"Erro ao reinjetar {base_png}", "error")

    def action_open_image_in_editor(self):
        if not self.selected_item: return
        t = self.selected_item
        base_png = os.path.splitext(t["file"])[0] + ".png"
        fixed_png = os.path.join(self.mgr.fixed_export_dir, base_png)

        if not os.path.exists(fixed_png):
            # Se não existir ainda, exporta automaticamente antes de abrir!
            self.action_export_selected()

        if os.path.exists(fixed_png):
            try:
                os.startfile(fixed_png)
                self.log(f"Abrindo imagem no editor padrão: {base_png}", "info")
            except Exception as e:
                self.log(f"Erro ao abrir imagem: {e}", "error")

    def action_repack_rom(self):
        def run_repack():
            self.log("Recompilando ROM com ndstool...", "info")
            ok, msg = self.mgr.repack_rom()
            if ok:
                self.root.after(0, lambda: self.log(msg, "success"))
                self.root.after(0, lambda: messagebox.showinfo("ROM Recompilada", msg))
            else:
                self.root.after(0, lambda: self.log(msg, "error"))
                self.root.after(0, lambda: messagebox.showerror("Erro na Recompilação", msg))

        threading.Thread(target=run_repack, daemon=True).start()


# ==============================================================================
# 4. ENTRYPOINT PRINCIPAL (CLI & GUI)
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="CoralineTextureTool - Extrator e Injetor de Texturas para Coraline DS")
    parser.add_argument('--gui', action='store_true', help="Abrir a interface gráfica (GUI)")
    parser.add_argument('--scan', action='store_true', help="Escanear e listar todas as texturas da ROM")
    parser.add_argument('--export', type=str, help="Caminho do arquivo .NCGR/.NCBR para exportar")
    parser.add_argument('--out', type=str, help="Caminho de saída para o .PNG")
    parser.add_argument('--export-all', type=str, nargs='?', const=DEFAULT_FIXED_EXPORT_DIR, help="Exportar todas as texturas para pasta")
    parser.add_argument('--import-png', type=str, help="Caminho do arquivo .PNG editado para importar")
    parser.add_argument('--target', type=str, help="Caminho do arquivo proprietário .NCGR de destino")
    parser.add_argument('--ai-export', type=str, help="Nome ou palavra-chave da textura para exportar rapidamente para a IA")
    parser.add_argument('--ai-import', type=str, help="Caminho da imagem PNG gerada pela IA para reinjetar na ROM")
    parser.add_argument('--repack', action='store_true', help="Recompilar a ROM current.nds após editar texturas")

    args = parser.parse_args()
    mgr = CoralineTextureManager()

    # Se nenhum argumento for passado, ou --gui for especificado: Abre a interface gráfica
    if len(sys.argv) == 1 or args.gui:
        root = tk.Tk()
        app = CoralineTextureToolGUI(root, mgr)
        root.mainloop()
        return

    if args.scan:
        textures = mgr.scan_all_textures()
        print(f"=== {len(textures)} TEXTURAS ENCONTRADAS NA ROM ===")
        for t in textures[:30]:
            print(f"  [{t['file']}] Paleta: {os.path.basename(t['palette']) if t['palette'] else 'Nenhuma'}")
        if len(textures) > 30:
            print(f"  ... e mais {len(textures) - 30} texturas.")

    elif args.export:
        out_png = args.out or (os.path.splitext(args.export)[0] + '.png')
        ok = mgr.export_texture(args.export, out_png)
        if ok:
            print(f"Textura exportada com sucesso para: {out_png}")

    elif args.export_all:
        out_dir = args.export_all
        mgr.batch_export(out_dir)

    elif args.import_png:
        if not args.target:
            print("Erro: especifique o alvo proprietário com --target <arquivo.NCGR>")
            return
        ok = mgr.import_texture(args.import_png, args.target)
        if ok:
            print(f"Textura reinjetada com sucesso em: {args.target}")

    elif args.ai_export:
        query = args.ai_export.lower()
        textures = mgr.scan_all_textures()
        matched = [t for t in textures if query in t['file'].lower()]
        if not matched:
            print(f"Nenhuma textura encontrada com o termo '{query}'.")
            return
        target = matched[0]
        out_png = args.out or f"ai_edit_{target['file']}.png"
        ok = mgr.export_texture(target['path'], out_png, target['palette'], target['screen'])
        if ok:
            print(f"Sucesso! Imagem pronta para IA / nanobanana em: {os.path.abspath(out_png)}")

    elif args.ai_import:
        meta_file = os.path.splitext(args.ai_import)[0] + '.meta.json'
        target_path = None
        if os.path.exists(meta_file):
            try:
                with open(meta_file, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                    target_path = meta.get('target_ncgr') or meta.get('source_ncgr')
            except Exception:
                pass
        if not target_path and args.target:
            target_path = args.target
        if not target_path:
            print("Erro: Não foi possível determinar o arquivo de destino (.NCGR). Use --target <arquivo.NCGR>.")
            return
        ok = mgr.import_texture(args.ai_import, target_path)
        if ok:
            print(f"Textura reinjetada com sucesso em: {target_path}")

    elif args.repack:
        print("Recompilando ROM com ndstool...")
        ok, msg = mgr.repack_rom()
        print(msg)

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
