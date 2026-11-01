"""
Coraline (Nintendo DS) - Tradutor & Editor de Textos Profissional
Autor: Ferramenta desenvolvida para ROMhacking e Tradução Fiel
Compatível com todos os 38 arquivos eve_*.bin e overlays.
"""

import os
import sys
import struct
import json
import re
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk

# Ativar DPI Awareness no Windows para gráficos e fontes nítidas
try:
    from ctypes import windll
    windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

# ==============================================================================
# CONFIGURAÇÕES E CONSTANTES
# ==============================================================================
# Diretório base dinâmico (permite rodar de qualquer pasta ou clone do repositório)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if os.path.exists(os.path.join(SCRIPT_DIR, "data", "data", "txt")):
    DEFAULT_ROOT = SCRIPT_DIR
else:
    DEFAULT_ROOT = r"C:\Users\Kassio\Downloads\dslazy\NDS_UNPACK"
TXT_DIR = os.path.join(DEFAULT_ROOT, "data", "data", "txt")
TXT_ORIGINAL_DIR = os.path.join(DEFAULT_ROOT, "data", "data", "txt_backup_original")
OVERLAY_DIR = os.path.join(DEFAULT_ROOT, "overlay")
FONT_PATH = os.path.join(DEFAULT_ROOT, "data", "data", "coraline_font.NFTR")
FONT_PATH_JP = os.path.join(DEFAULT_ROOT, "data", "data", "coraline_font2.NFTR")
CONFIG_PATH = os.path.join(DEFAULT_ROOT, "coraline_editor_layout.json")

LANG_NAMES = ["0: Japonês (JA)", "1: Inglês (EN)", "2: Francês (FR)", 
              "3: Alemão (DE)", "4: Espanhol (ES)", "5: Italiano (IT)"]
LANG_CODES = ["JA", "EN", "FR", "DE", "ES", "IT"]

# ------------------------------------------------------------------------------
# GEOMETRIA REAL DA TELA E DA CAIXA DE TEXTO
# ------------------------------------------------------------------------------
# O tela do DS é 256x192. A fonte do diálogo é a NFTR do próprio jogo:
# célula de 15x16 px, 3 bits por pixel, avanço variável por caractere.
SCREEN_W, SCREEN_H = 256, 192

# A área útil de texto do Coraline foi medida no próprio texto original do
# jogo (slot EN): a MAIOR linha de diálogo que o jogo exibe ocupa 140 px na
# fonte real. Nenhuma linha da tradução deve passar disso.
# (o valor é recalculado automaticamente a partir dos .bin originais e pode
#  ser ajustado no painel "Caixa de texto", no canto do simulador)
DEFAULT_BOX_WIDTH_PX = 140
DEFAULT_BOX_LINES = 3
WARN_MARGIN_PX = 4          # faixa de atenção antes do limite

# ==============================================================================
# MOTOR DE FONTE NFTR — MÉTRICAS E GLIFOS REAIS DO JOGO
# ==============================================================================
def decode_game_text(raw):
    """
    Decodifica o texto do Coraline.
    Os arquivos são UTF-8 nos idiomas europeus, mas o texto inglês carrega
    alguns caracteres de pontuação em Shift-JIS (ex.: "！", "…").
    """
    if isinstance(raw, str):
        return raw
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    out = []
    i, n = 0, len(raw)
    while i < n:
        b = raw[i]
        if b < 0x80:
            out.append(chr(b))
            i += 1
            continue
        for ln in (2, 3, 4):
            if i + ln <= n:
                try:
                    out.append(raw[i:i + ln].decode("utf-8"))
                    i += ln
                    break
                except UnicodeDecodeError:
                    continue
        else:
            try:
                out.append(raw[i:i + 2].decode("shift_jis"))
                i += 2
            except Exception:
                out.append("\ufffd")
                i += 1
    return "".join(out)


class NitroFont:
    """
    Leitor completo de fonte NFTR (Nitro Font Resource):

      FNIF = informações gerais (altura da linha, largura, encoding)
      PLGC = bitmaps dos glifos  (CGLP nas versões antigas)
      HDWC = larguras por glifo  (CWDH)
      PAMC = mapa caractere -> glifo (CMAP)

    Com as larguras reais (CWDH) o editor mede o texto em PIXELS, do mesmo
    jeito que o jogo desenha, em vez de contar caracteres.
    """

    def __init__(self, path):
        self.path = path
        self.ok = False
        self.data = b""
        self.height = 16
        self.width = 15
        self.tile_w = 15
        self.tile_h = 16
        self.bpp = 1
        self.tile_size = 0
        self.encoding = 1
        self.cmap = {}
        self.widths = []
        self.glyph_base = 0
        self.underline = 0
        self._bitmap_cache = {}
        self.load()

    # -- leitura ---------------------------------------------------------------
    def load(self):
        if not os.path.exists(self.path):
            print(f"Aviso: fonte NFTR não encontrada: {self.path}")
            return
        try:
            data = open(self.path, "rb").read()
            if data[:4] != b"RTFN":
                print("Aviso: arquivo não parece ser uma fonte NFTR.")
                return
            self.data = data
            chunks = {}
            off = 16
            while off + 8 <= len(data):
                magic = data[off:off + 4].decode("ascii", "replace")
                size = struct.unpack_from("<I", data, off + 4)[0]
                if size <= 0:
                    break
                chunks.setdefault(magic, []).append(off)
                off += size

            info = (chunks.get("FNIF") or chunks.get("FINF") or [None])[0]
            if info is not None:
                self.height = data[info + 0x09] or 16
                self.width = data[info + 0x0D] or 15
                self.encoding = data[info + 0x0F]

            glyphs = (chunks.get("PLGC") or chunks.get("CGLP") or [None])[0]
            if glyphs is None:
                return
            self.tile_w = data[glyphs + 0x08] or self.width
            self.tile_h = data[glyphs + 0x09] or self.height
            self.tile_size = struct.unpack_from("<H", data, glyphs + 0x0A)[0]
            self.underline = data[glyphs + 0x0C]
            self.bpp = data[glyphs + 0x0E] or 1
            self.glyph_base = glyphs + 0x10
            if self.tile_size <= 0:
                self.tile_size = (self.tile_w * self.tile_h * self.bpp + 7) // 8

            widths = (chunks.get("HDWC") or chunks.get("CWDH") or [None])[0]
            if widths is not None:
                wsize = struct.unpack_from("<I", data, widths + 4)[0]
                count = max(0, (wsize - 0x10) // 3)
                base = widths + 0x10
                self.widths = [tuple(data[base + i * 3: base + i * 3 + 3]) for i in range(count)]

            for co in (chunks.get("PAMC") or []) + (chunks.get("CMAP") or []):
                self._load_cmap(co)

            self.ok = bool(self.widths)
        except Exception as e:
            print(f"Aviso ao carregar fonte NFTR: {e}")

    def _load_cmap(self, off):
        d = self.data
        first = struct.unpack_from("<H", d, off + 0x08)[0]
        last = struct.unpack_from("<H", d, off + 0x0A)[0]
        mtype = struct.unpack_from("<I", d, off + 0x0C)[0]
        base = off + 0x14
        if mtype == 0:
            g = struct.unpack_from("<H", d, base)[0]
            for c in range(first, last + 1):
                self.cmap[c] = g + (c - first)
        elif mtype == 1:
            for i, c in enumerate(range(first, last + 1)):
                if base + i * 2 + 2 <= len(d):
                    g = struct.unpack_from("<H", d, base + i * 2)[0]
                    if g != 0xFFFF:
                        self.cmap[c] = g
        elif mtype == 2:
            if base + 2 > len(d):
                return
            count = struct.unpack_from("<H", d, base)[0]
            for i in range(count):
                if base + 4 + i * 4 + 4 <= len(d):
                    c = struct.unpack_from("<H", d, base + 2 + i * 4)[0]
                    g = struct.unpack_from("<H", d, base + 4 + i * 4)[0]
                    self.cmap[c] = g

    # -- métricas --------------------------------------------------------------
    @property
    def line_height(self):
        return self.tile_h or self.height or 16

    def metrics(self, glyph):
        """(espaço esquerdo, largura da tinta, avanço total) em pixels."""
        if 0 <= glyph < len(self.widths):
            left, ink, total = self.widths[glyph]
            return left, ink, (total or (left + ink))
        return 0, self.width, self.width

    def glyph_for(self, ch):
        g = self.cmap.get(ord(ch))
        if g is None:
            try:
                b = ch.encode("shift_jis")
            except Exception:
                b = b""
            if len(b) == 2:
                g = self.cmap.get((b[0] << 8) | b[1])
        return g

    def advance(self, ch):
        g = self.glyph_for(ch)
        return None if g is None else self.metrics(g)[2]

    def text_width(self, text, missing=None):
        """Largura real, em pixels, de uma linha de texto."""
        total = 0
        for ch in text:
            if ch in "\n\r\t":
                continue
            a = self.advance(ch)
            if a is None:
                if missing is not None and ch not in missing:
                    missing.append(ch)
                a = 7
            total += a
        return total

    def bitmap(self, glyph):
        """Matriz de pixels do glifo (valores 0..(2^bpp-1))."""
        if glyph in self._bitmap_cache:
            return self._bitmap_cache[glyph]
        w, h, bpp = self.tile_w, self.tile_h, self.bpp
        mask = (1 << bpp) - 1
        bits_per_row = w * bpp
        base = self.glyph_base + max(0, glyph) * self.tile_size
        rows = []
        d = self.data
        for y in range(h):
            row = []
            for x in range(w):
                bit = y * bits_per_row + x * bpp
                bi = base + bit // 8
                window = int.from_bytes(d[bi:bi + 3].ljust(3, b"\x00"), "big")
                shift = 24 - bpp - (bit % 8)
                row.append((window >> shift) & mask if shift >= 0 else 0)
            rows.append(row)
        self._bitmap_cache[glyph] = rows
        return rows

    # -- compatibilidade com o validador antigo -------------------------------
    def check_text(self, text):
        """Caracteres do texto que não existem na fonte do jogo."""
        if not self.ok:
            return []
        missing = []
        for ch in text:
            if ch in "\n\r\t":
                continue
            if self.glyph_for(ch) is None and ch not in missing:
                missing.append(ch)
        return missing


# ==============================================================================
# MEDIÇÃO DA CAIXA DE TEXTO (PIXELS REAIS) E AUTO-QUEBRA
# ==============================================================================
class TextBoxLayout:
    """Geometria da área útil de texto + diagnóstico em pixels."""

    def __init__(self, font, width_px=DEFAULT_BOX_WIDTH_PX, lines=DEFAULT_BOX_LINES):
        self.font = font
        self.width_px = int(width_px)
        self.lines = int(lines)

    def measure(self, text):
        """
        Retorna dict:
          lines, widths (px por linha), max_width, missing,
          status (0=seguro, 1=atenção, 2=perigo), message
        """
        raw_lines = text.split("\n")
        missing = []
        widths = [self.font.text_width(ln, missing) for ln in raw_lines]
        max_width = max(widths) if widths else 0
        n_lines = len(raw_lines)

        if missing:
            chars = "".join(missing[:6])
            return dict(lines=n_lines, widths=widths, max_width=max_width, missing=missing,
                        status=2,
                        message=f"Caractere(s) fora da fonte: '{chars}' — o jogo desenha vazio.")

        if max_width > self.width_px:
            idx = widths.index(max_width) + 1
            return dict(lines=n_lines, widths=widths, max_width=max_width, missing=[],
                        status=2,
                        message=(f"Linha {idx} com {max_width} px — "
                                 f"ultrapassa os {self.width_px} px da caixa em "
                                 f"{max_width - self.width_px} px."))

        # Mais linhas que a caixa NÃO perde texto: o jogo pagina de 3 em 3.
        if n_lines > self.lines:
            pages = (n_lines + self.lines - 1) // self.lines
            return dict(lines=n_lines, widths=widths, max_width=max_width, missing=[],
                        status=1,
                        message=(f"Cabe na largura ({max_width}/{self.width_px} px), "
                                 f"mas ocupa {pages} páginas de {self.lines} linhas."))

        if max_width > self.width_px - WARN_MARGIN_PX:
            return dict(lines=n_lines, widths=widths, max_width=max_width, missing=[],
                        status=1,
                        message=(f"{max_width}/{self.width_px} px — no limite. "
                                 f"Sobra só {self.width_px - max_width} px."))

        return dict(lines=n_lines, widths=widths, max_width=max_width, missing=[],
                    status=0,
                    message=(f"Cabe: maior linha {max_width}/{self.width_px} px "
                             f"({n_lines}/{self.lines} linhas)."))


class TextWrapHelper:
    """Quebra de linha por PIXELS, usando as larguras reais da fonte."""

    @staticmethod
    def auto_wrap(text, font, width_px=DEFAULT_BOX_WIDTH_PX, max_lines=None):
        clean = " ".join(text.split())
        if not clean:
            return ""
        words = clean.split(" ")
        lines = []
        cur = ""

        def line_w(s):
            return font.text_width(s)

        for word in words:
            cand = word if not cur else cur + " " + word
            if line_w(cand) <= width_px or not cur:
                cur = cand
                continue
            lines.append(cur)
            cur = word
        if cur:
            lines.append(cur)

        # Palavras maiores que a caixa: quebra dura com hífen
        final = []
        for ln in lines:
            if line_w(ln) <= width_px:
                final.append(ln)
                continue
            part = ""
            for ch in ln:
                if line_w(part + ch + "-") > width_px and part:
                    final.append(part + "-")
                    part = ""
                part += ch
            if part:
                final.append(part)

        if max_lines and len(final) > max_lines:
            # Não corta nem espreme: devolve as linhas reais para o medidor
            # acusar exatamente quanto passou do limite vertical.
            pass
        return "\n".join(final)

    @staticmethod
    def analyze_lines(text, font, width_px=DEFAULT_BOX_WIDTH_PX, max_lines=DEFAULT_BOX_LINES):
        """Compatibilidade: devolve (n_linhas, larguras, status, mensagem)."""
        layout = TextBoxLayout(font, width_px, max_lines)
        m = layout.measure(text)
        return m["lines"], m["widths"], m["status"], m["message"]


def scan_original_limit(font, folder):
    """
    Mede todas as linhas de diálogo do texto ORIGINAL do jogo (slot EN).

    Devolve (limite_px, maior_px, arquivo_da_maior_linha, n_linhas).
    O limite é o percentil 99,5 das larguras (os créditos finais usam outra
    tela e distorcem o máximo absoluto), arredondado para múltiplos de 4 px.
    """
    if not font.ok or not os.path.isdir(folder):
        return None
    widths = []
    try:
        for name in sorted(os.listdir(folder)):
            if not name.endswith(".bin"):
                continue
            raw = open(os.path.join(folder, name), "rb").read()
            if len(raw) < 4:
                continue
            n = struct.unpack_from("<I", raw, 0)[0] // 4
            if n <= 0 or n * 4 > len(raw):
                continue
            ptrs = [struct.unpack_from("<I", raw, i * 4)[0] for i in range(n)]
            i = 0
            while i + 5 < n:
                try:
                    if raw[ptrs[i]:ptrs[i] + 2] != b"\x05\xff":
                        i += 1
                        continue
                    if not all(raw[ptrs[i + k]:ptrs[i + k] + 2] == b"\x05\xff" for k in range(6)):
                        i += 1
                        continue
                except Exception:
                    i += 1
                    continue
                end = ptrs[i + 2] if i + 2 < n else len(raw)
                content = raw[ptrs[i + 1] + 2:end]
                if content.endswith(b"\x00"):
                    content = content[:-1]
                text = decode_game_text(content)
                for ln in text.split("\n"):
                    widths.append((font.text_width(ln), name, ln))
                i += 6
    except Exception as e:
        print(f"Aviso ao medir o limite original: {e}")
        return None
    if not widths:
        return None
    widths.sort(key=lambda t: t[0])
    top_w, top_file, top_line = widths[-1]
    robust = widths[int(len(widths) * 0.995)][0]
    limit = int((robust + 3) // 4 * 4)
    return limit, robust, top_w, top_file, len(widths)

# ==============================================================================
# MOTOR DE ARQUIVOS BINÁRIOS DE SCRIPTS (eve_*.bin)
# ==============================================================================
class BinScriptArchive:
    def __init__(self, filepath):
        self.filepath = filepath
        self.filename = os.path.basename(filepath)
        self.raw_data = b""
        self.chunks = []       # lista de bytearrays
        self.dialogues = []    # lista de dicionários de falas agrupadas
        self.is_modified = False
        self.load()

    def load(self):
        with open(self.filepath, "rb") as f:
            self.raw_data = f.read()

        if len(self.raw_data) < 4:
            return

        first_ptr = struct.unpack_from("<I", self.raw_data, 0)[0]
        num_ptrs = first_ptr // 4
        ptrs = [struct.unpack_from("<I", self.raw_data, i*4)[0] for i in range(num_ptrs)]

        self.chunks = []
        for i in range(num_ptrs):
            start = ptrs[i]
            end = ptrs[i+1] if i+1 < num_ptrs else len(self.raw_data)
            self.chunks.append(bytearray(self.raw_data[start:end]))

        self.parse_dialogues()
        self.is_modified = False

    def parse_dialogues(self):
        """Identifica chunks de texto e agrupa em linhas de 6 idiomas quando aplicável."""
        self.dialogues = []
        i = 0
        while i < len(self.chunks):
            chunk = self.chunks[i]
            if chunk.startswith(b"\x05\xff"):
                # Verifica se é o início de um grupo de 6 idiomas
                is_group_of_6 = True
                if i + 5 < len(self.chunks):
                    for j in range(i, i + 6):
                        if not self.chunks[j].startswith(b"\x05\xff"):
                            is_group_of_6 = False
                            break
                else:
                    is_group_of_6 = False

                if is_group_of_6:
                    texts = {}
                    for lang_idx in range(6):
                        c_idx = i + lang_idx
                        raw_c = self.chunks[c_idx]
                        content = raw_c[2:-1] if raw_c.endswith(b"\x00") else raw_c[2:]
                        if lang_idx == 0:
                            # Japonês é Shift-JIS
                            try:
                                t = content.decode("shift_jis")
                            except:
                                t = decode_game_text(content)
                        else:
                            # Europeu é UTF-8 (com pontuação SJIS ocasional)
                            t = decode_game_text(content)
                        texts[lang_idx] = t

                    self.dialogues.append({
                        "base_chunk": i,
                        "type": "group_6",
                        "texts": texts,
                        "chunk_indices": [i + k for k in range(6)]
                    })
                    i += 6
                else:
                    # Chunk de texto avulso (ex: créditos ou falas individuais)
                    raw_c = chunk
                    content = raw_c[2:-1] if raw_c.endswith(b"\x00") else raw_c[2:]
                    t = decode_game_text(content)

                    self.dialogues.append({
                        "base_chunk": i,
                        "type": "single",
                        "texts": {1: t}, # Mapeia para slot de texto
                        "chunk_indices": [i]
                    })
                    i += 1
            else:
                i += 1

    def update_dialogue(self, diag_idx, lang_slot, new_text):
        """Atualiza o texto em memória de um diálogo específico."""
        if diag_idx < 0 or diag_idx >= len(self.dialogues):
            return
        diag = self.dialogues[diag_idx]
        diag["texts"][lang_slot] = new_text

        # Atualiza o chunk correspondente
        if diag["type"] == "group_6":
            target_chunk_idx = diag["base_chunk"] + lang_slot
        else:
            target_chunk_idx = diag["base_chunk"]

        if lang_slot == 0:
            # Codifica Japonês em Shift-JIS se possível
            try:
                encoded = new_text.encode("shift_jis")
            except:
                encoded = new_text.encode("utf-8")
        else:
            # Demais idiomas em UTF-8 com terminação nula
            encoded = new_text.encode("utf-8")

        new_chunk_data = b"\x05\xff" + encoded + b"\x00"
        self.chunks[target_chunk_idx] = bytearray(new_chunk_data)
        self.is_modified = True

    def save(self, backup=True):
        """Reconstrói o arquivo com recálculo total de ponteiros de 32 bits."""
        num_ptrs = len(self.chunks)
        new_ptrs = []
        curr_offset = num_ptrs * 4

        for c in self.chunks:
            new_ptrs.append(curr_offset)
            curr_offset += len(c)

        header = b"".join(struct.pack("<I", p) for p in new_ptrs)
        body = b"".join(self.chunks)
        final_data = header + body

        if backup and os.path.exists(self.filepath):
            bak_path = self.filepath + ".bak"
            if not os.path.exists(bak_path):
                with open(self.filepath, "rb") as src, open(bak_path, "wb") as dst:
                    dst.write(src.read())

        with open(self.filepath, "wb") as f:
            f.write(final_data)

        self.raw_data = final_data
        self.is_modified = False

    def export_json(self, out_path):
        """Exporta todos os diálogos para um arquivo JSON legível."""
        export_data = {
            "file": self.filename,
            "total_dialogues": len(self.dialogues),
            "dialogues": []
        }
        for idx, d in enumerate(self.dialogues):
            export_data["dialogues"].append({
                "id": idx,
                "base_chunk": d["base_chunk"],
                "type": d["type"],
                "texts": {LANG_CODES[k]: v for k, v in d["texts"].items()}
            })
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)

    def import_json(self, in_path, target_lang_slot=1):
        """Importa traduções de um arquivo JSON."""
        with open(in_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        target_code = LANG_CODES[target_lang_slot]
        count = 0
        for item in data.get("dialogues", []):
            diag_id = item["id"]
            if diag_id < len(self.dialogues):
                texts = item.get("texts", {})
                if target_code in texts:
                    self.update_dialogue(diag_id, target_lang_slot, texts[target_code])
                    count += 1
                elif "PT" in texts:
                    self.update_dialogue(diag_id, target_lang_slot, texts["PT"])
                    count += 1
        return count

# ==============================================================================
# MOTOR DE ARQUIVOS OVERLAY (ITENS & MINIJOGOS)
# ==============================================================================
class OverlayArchive:
    def __init__(self, filepath, overlay_type="items"):
        self.filepath = filepath
        self.filename = os.path.basename(filepath)
        self.overlay_type = overlay_type  # "items" (overlay_0000) ou "minigames" (overlay_0001)
        self.raw_data = bytearray()
        self.base_ram = 0x02183ac0
        self.items = []
        self.dialogues = []
        self.is_modified = False
        self.load()

    def load(self):
        with open(self.filepath, "rb") as f:
            self.raw_data = bytearray(f.read())
        self.items = []
        self.dialogues = []

        if self.overlay_type == "items":
            # Tabela de nomes em overlay_0000.bin (0x82cc..0x8438)
            t_start, t_end = 0x82cc, 0x8438
            for p_off in range(t_start, t_end + 4, 4):
                ram_ptr = struct.unpack_from("<I", self.raw_data, p_off)[0]
                foff = ram_ptr - self.base_ram
                if 0 <= foff < len(self.raw_data):
                    s_bytes = self.raw_data[foff:].split(b"\x00")[0]
                    try:
                        st = s_bytes.decode("utf-8")
                    except:
                        st = s_bytes.decode("shift_jis", errors="replace")
                    self.items.append({
                        "table_offset": p_off,
                        "ram_ptr": ram_ptr,
                        "file_offset": foff,
                        "text": st,
                        "orig_len": len(s_bytes)
                    })
        elif self.overlay_type == "minigames":
            # Tabela em overlay_0001.bin (0x48cc..0x493c)
            t_start, t_end = 0x48cc, 0x493c
            for p_off in range(t_start, t_end + 4, 4):
                ram_ptr = struct.unpack_from("<I", self.raw_data, p_off)[0]
                foff = ram_ptr - self.base_ram
                if 0 <= foff < len(self.raw_data):
                    s_bytes = self.raw_data[foff:].split(b"\x00")[0]
                    try:
                        st = s_bytes.decode("utf-8")
                    except:
                        st = s_bytes.decode("shift_jis", errors="replace")
                    self.items.append({
                        "table_offset": p_off,
                        "ram_ptr": ram_ptr,
                        "file_offset": foff,
                        "text": st,
                        "orig_len": len(s_bytes)
                    })

        # Mapeia items para self.dialogues para compatibilidade total com a interface gráfica
        for idx, itm in enumerate(self.items):
            self.dialogues.append({
                "base_chunk": idx,
                "type": "single",
                "texts": {0: itm["text"], 1: itm["text"], 2: itm["text"], 3: itm["text"], 4: itm["text"], 5: itm["text"]},
                "chunk_indices": [idx]
            })
        self.is_modified = False

    def update_dialogue(self, diag_idx, lang_slot, new_text):
        if diag_idx < 0 or diag_idx >= len(self.items):
            return
        item = self.items[diag_idx]
        self.dialogues[diag_idx]["texts"][lang_slot] = new_text
        encoded = new_text.encode("utf-8")
        foff = item["file_offset"]
        # Se couber no espaço original com folga
        if len(encoded) <= item["orig_len"]:
            self.raw_data[foff:foff + len(encoded)] = encoded
            self.raw_data[foff + len(encoded):foff + item["orig_len"] + 1] = b"\x00" * (item["orig_len"] + 1 - len(encoded))
            item["text"] = new_text
            self.is_modified = True
        else:
            # Texto excedeu espaço original - grava truncando suavemente para segurança
            enc_trunc = encoded[:item["orig_len"]]
            self.raw_data[foff:foff + len(enc_trunc)] = enc_trunc
            self.raw_data[foff + len(enc_trunc)] = 0
            item["text"] = enc_trunc.decode("utf-8", errors="replace")
            self.is_modified = True

    def save(self, backup=True):
        if backup and os.path.exists(self.filepath):
            bak_path = self.filepath + ".bak"
            if not os.path.exists(bak_path):
                with open(self.filepath, "rb") as src, open(bak_path, "wb") as dst:
                    dst.write(src.read())
        with open(self.filepath, "wb") as f:
            f.write(self.raw_data)
        self.is_modified = False

    def export_json(self, out_path):
        export_data = {
            "file": self.filename,
            "type": self.overlay_type,
            "total_items": len(self.items),
            "items": []
        }
        for idx, itm in enumerate(self.items):
            export_data["items"].append({
                "id": idx,
                "text": itm["text"],
                "max_bytes": itm["orig_len"]
            })
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)

    def import_json(self, in_path, target_lang_slot=1):
        with open(in_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        count = 0
        for itm in data.get("items", []):
            i_id = itm["id"]
            if i_id < len(self.items):
                self.update_dialogue(i_id, target_lang_slot, itm["text"])
                count += 1
        return count


# ==============================================================================
# GERENCIADOR DO EXECUTÁVEL ARM9 (MENUS, SALVAMENTO, BOTÕES E PERSONAGENS)
# ==============================================================================
class Arm9Archive:
    """
    Gerenciador e editor das 54 entradas mestre do executável ARM9 (arm9.bin):
      - Botões do Menu de Pausa (SALVAR, SAIR, ITENS, ROUPAS)
      - Mensagens e Telas de Salvamento (DADOS 1, 2, 3, SEM DADOS, Sobrescrever, etc.)
      - Nomes de Personagens e Tags de Fala (Gigante Azul, O Gato, A Beldam, etc.)
      - Tabela de ponteiros de 32-bit (0x5E080) e String Pool seguro (0x5E630)
      - Auto-ajuste de espaçamento horizontal (0x5E014) para evitar sobreposição 'SALVARSAIR'
      - Compatível com a interface de diálogos do editor.
    """
    RAM_BASE = 0x02000000
    TABLE_BASE = 0x5E080
    TOTAL_GROUPS = 54
    POOL_START = 0x5E630
    POOL_MAX = 0x5F000
    SAVE_X_TABLE = 0x5E014

    GROUP_DESCRIPTIONS = [
        "Personagem: Vênus",
        "Personagem: Outra Spink?",
        "Personagem: Menino fantasma",
        "Personagem: Garota Alta fantasma",
        "Personagem: Doce Menina fantasma",
        "Tag de Fala: A voz do Menino fantasma",
        "Tag de Fala: A voz da Garota Alta fantasma",
        "Tag de Fala: A voz da Doce Menina fantasma",
        "Personagem: Menino anjo",
        "Personagem: Garota Alta anjo",
        "Personagem: Doce Menina anjo",
        "Personagem: Papagaio de Brinquedo",
        "Personagem: Libélula de Brinquedo",
        "Personagem: Esqueleto de Dinossauro",
        "Personagem: Tanque de Brinquedo",
        "Personagem: Casco de Tartaruga",
        "Personagem: Outro Wybie",
        "Salvamento: Slot 1 (DADOS 1:)",
        "Salvamento: Slot 2 (DADOS 2:)",
        "Salvamento: Slot 3 (DADOS 3:)",
        "Salvamento: Slot Vazio (SEM DADOS)",
        "Mensagem: Você está bem?",
        "Confirmação: Sobrescrever dados de Coraline?",
        "Confirmação: Voltar ao início sem salvar?",
        "Menu Pausa: Botão ITENS",
        "Menu Pausa: Botão ROUPAS (FIGURINOS)",
        "Menu Pausa: Botão SALVAR",
        "Menu Pausa: Botão SAIR",
        "Personagem: Coraline",
        "Personagem: Mel",
        "Tag de Fala: Voz da Mel",
        "Personagem: Charlie",
        "Personagem: Gigante Azul (Bobinsky)",
        "Tag de Fala: A voz do Gigante Azul",
        "Personagem: Sr. Bobinsky",
        "Tag de Fala: A voz do menino",
        "Personagem: Wybie",
        "Tag de Fala: Voz",
        "Tag de Fala: A voz da senhora",
        "Personagem: Senhora",
        "Personagem: Srta. Spink",
        "Personagem: Srta. Forcible",
        "Personagem: O Gato",
        "Tag de Fala: Voz Familiar",
        "Tag de Fala: Voz da Mel?",
        "Personagem: Mel?",
        "Personagem: Outra Mãe",
        "Tag de Fala: A voz da Outra Mãe",
        "Personagem: Outra Mãe?",
        "Personagem: A Beldam",
        "Personagem: Outro Pai",
        "Personagem: Outro Sr. Bobinsky",
        "Personagem: Cão de olhos de botão",
        "Personagem: Sereia",
    ]

    def __init__(self, filepath):
        self.filepath = filepath
        self.filename = os.path.basename(filepath)
        self.raw_data = bytearray()
        self.dialogues = []
        self.is_modified = False
        self.load()

    def load(self):
        with open(self.filepath, "rb") as f:
            self.raw_data = bytearray(f.read())

        # Tenta carregar referência original limpa
        orig_raw = None
        for cand in [self.filepath + ".bak_pre_menu_trans",
                     self.filepath + ".bak",
                     os.path.join(os.path.dirname(self.filepath), "CLEAN_USA_UNPACK", "arm9.bin")]:
            if os.path.exists(cand):
                try:
                    with open(cand, "rb") as f:
                        orig_raw = bytearray(f.read())
                    break
                except Exception:
                    pass

        self.dialogues = []
        for g in range(self.TOTAL_GROUPS):
            group_off = self.TABLE_BASE + g * 24
            slot_texts = {}
            for slot in range(6):
                ptr_off = group_off + slot * 4
                ram_ptr = struct.unpack_from("<I", self.raw_data, ptr_off)[0]
                foff = ram_ptr - self.RAM_BASE
                if 0 <= foff < len(self.raw_data):
                    s_bytes = self.raw_data[foff:].split(b"\x00")[0]
                    try:
                        s_txt = s_bytes.decode("utf-8")
                    except Exception:
                        s_txt = s_bytes.decode("shift_jis", errors="replace")
                else:
                    s_txt = ""
                slot_texts[slot] = s_txt

            orig_slot_texts = {}
            if orig_raw:
                for slot in range(6):
                    ptr_off = group_off + slot * 4
                    ram_ptr = struct.unpack_from("<I", orig_raw, ptr_off)[0]
                    foff = ram_ptr - self.RAM_BASE
                    if 0 <= foff < len(orig_raw):
                        s_bytes = orig_raw[foff:].split(b"\x00")[0]
                        try:
                            s_txt = s_bytes.decode("utf-8")
                        except Exception:
                            s_txt = s_bytes.decode("shift_jis", errors="replace")
                    else:
                        s_txt = ""
                    orig_slot_texts[slot] = s_txt
            else:
                orig_slot_texts = dict(slot_texts)

            desc = self.GROUP_DESCRIPTIONS[g] if g < len(self.GROUP_DESCRIPTIONS) else f"Grupo #{g}"

            self.dialogues.append({
                "base_chunk": g,
                "type": "group_6",
                "texts": slot_texts,
                "orig_texts": orig_slot_texts,
                "chunk_indices": [g],
                "description": desc,
            })
        self.is_modified = False

    def update_dialogue(self, diag_idx, lang_slot, new_text):
        if diag_idx < 0 or diag_idx >= len(self.dialogues):
            return
        self.dialogues[diag_idx]["texts"][lang_slot] = new_text
        self.is_modified = True

    def save(self, backup=True):
        if backup and os.path.exists(self.filepath):
            bak = self.filepath + ".bak"
            if not os.path.exists(bak):
                with open(self.filepath, "rb") as s, open(bak, "wb") as d:
                    d.write(s.read())

        # Reconstrói o pool de strings em POOL_START
        cursor = self.POOL_START
        group_ram_addrs = []

        for g in range(self.TOTAL_GROUPS):
            text = self.dialogues[g]["texts"].get(1, "")
            raw = text.encode("utf-8") + b"\x00"
            if cursor + len(raw) > self.POOL_MAX:
                raise ValueError(f"String pool do arm9.bin estourou em 0x{cursor:x} (máximo: 0x{self.POOL_MAX:x})!")
            self.raw_data[cursor:cursor + len(raw)] = raw
            group_ram_addrs.append(cursor + self.RAM_BASE)
            cursor += len(raw)

        # Atualiza a tabela de ponteiros (todos os 6 slots apontam para a string)
        for g, ram_ptr in enumerate(group_ram_addrs):
            group_off = self.TABLE_BASE + g * 24
            for slot in range(6):
                ptr_off = group_off + slot * 4
                struct.pack_into("<I", self.raw_data, ptr_off, ram_ptr)

        # Ajusta posição X de SAVE (128) para não colidir com SAIR
        for slot in range(6):
            struct.pack_into("<H", self.raw_data, self.SAVE_X_TABLE + slot * 2, 128)

        # Garante UTF-8 no slot Inglês (byte 0x0e04 = 0x01)
        if len(self.raw_data) > 0x0e04:
            self.raw_data[0x0e04] = 0x01

        with open(self.filepath, "wb") as f:
            f.write(self.raw_data)
        self.is_modified = False

    def export_json(self, out_path):
        export_data = {
            "file": self.filename,
            "type": "arm9_menus_and_system",
            "total_groups": len(self.dialogues),
            "groups": []
        }
        for idx, d in enumerate(self.dialogues):
            export_data["groups"].append({
                "id": idx,
                "description": d.get("description", ""),
                "orig_en": d.get("orig_texts", {}).get(1, ""),
                "text": d["texts"].get(1, "")
            })
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)

    def import_json(self, in_path, target_lang_slot=1):
        with open(in_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        count = 0
        for grp in data.get("groups", []):
            g_id = grp["id"]
            if g_id < len(self.dialogues):
                self.update_dialogue(g_id, target_lang_slot, grp["text"])
                count += 1
        return count

# ==============================================================================
# SIMULADOR VISUAL DA TELA NINTENDO DS (CANVAS 256x192)
# ==============================================================================
# SIMULADOR VISUAL DA TELA NINTENDO DS (CANVAS 256x192 COM FONTE REAL NFTR)
# ==============================================================================
class DSPreviewCanvas(tk.Canvas):
    """
    Simulador da tela do DS (256x192) desenhado 1:1 com os GLIFOS REAIS da
    fonte NFTR do jogo, caixa de diálogo autêntica e métricas reais de kerning.
    Escala 2x: cada pixel do DS vira um bloco 2x2 nítido via Pillow RGBA.
    """

    SCALE = 2
    BG_SCREEN = "#0D0E16"
    BG_BOX = "#121420"
    BG_BOX_INNER = "#171A29"

    def __init__(self, parent, font, layout, **kwargs):
        self.font = font
        self.layout = layout
        self.scale = self.SCALE
        self.ds_w = SCREEN_W * self.scale
        self.ds_h = SCREEN_H * self.scale
        super().__init__(parent, width=self.ds_w, height=self.ds_h,
                         bg="#0A0B10", highlightthickness=2, highlightbackground="#2E3440", **kwargs)
        self.current_text = ""
        self.current_title = ""
        self.show_guides = True
        self._glyph_cache = {}
        self._images = []
        self.draw_screen()

    # -- API -------------------------------------------------------------------
    def set_layout(self, layout):
        self.layout = layout
        self.draw_screen()

    def update_preview(self, text, title=""):
        self.current_text = text
        if title:
            self.current_title = title
        self.draw_screen()

    def recompile_rom_action(self):
        """Recompila a ROM (current.nds) usando ndstool preservando o cabeçalho de 64 MB."""
        ndstool = os.path.join(os.path.dirname(DEFAULT_ROOT), "ndstool.exe")
        target_nds = os.path.join(os.path.dirname(DEFAULT_ROOT), "current.nds")
        if not os.path.exists(ndstool):
            messagebox.showerror("Erro", f"ndstool.exe não encontrado em:\n{ndstool}")
            return

        try:
            if self.current_archive and self.current_archive.is_modified:
                self.save_current_file()

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
            res = subprocess.run(cmd, cwd=os.path.dirname(DEFAULT_ROOT), capture_output=True, text=True)
            if res.returncode != 0:
                messagebox.showerror("Erro na Recompilação", f"Erro no ndstool:\n{res.stderr}")
                return

            # Preserva cabeçalho de 64 MB (0x14 = 0x09)
            with open(target_nds, "r+b") as f:
                f.seek(0x14)
                f.write(bytes([0x09]))

            sz_mb = os.path.getsize(target_nds) / (1024 * 1024)
            messagebox.showinfo("ROM Recompilada!",
                                f"ROM recompilada com sucesso em:\n{target_nds}\n\n"
                                f"Tamanho: {sz_mb:.2f} MB\n"
                                f"Cabeçalho de 64 MB preservado (compatível com DeSmuME e Flashcards)!")
        except Exception as e:
            messagebox.showerror("Erro ao Recompilar", f"Falha na recompilação:\n{e}")

    def toggle_guides(self):
        self.show_guides = not self.show_guides
        self.draw_screen()

    # -- Glifos Reais com Alpha e Drop Shadow via Pillow -----------------------
    def _glyph_photo(self, glyph, color_hex):
        font = self.layout.font
        key = (id(font), glyph, color_hex)
        if key in self._glyph_cache:
            return self._glyph_cache[key]

        rows = font.bitmap(glyph)
        w, h = font.tile_w, font.tile_h
        maxv = (1 << max(1, font.bpp)) - 1

        c = color_hex.lstrip("#")
        cr, cg, cb = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)

        # Imagem RGBA com 1px extra para sombra projetada
        im = Image.new("RGBA", (w + 1, h + 1), (0, 0, 0, 0))

        # 1. Sombra sutil (1px deslocada para direita e baixo)
        for gy, row in enumerate(rows):
            for gx, v in enumerate(row):
                if v:
                    a = int((v / maxv) * 160)
                    im.putpixel((gx + 1, gy + 1), (0, 0, 0, a))

        # 2. Glifo principal com anti-aliasing nativo (3 bpp / 8 tons de alpha)
        for gy, row in enumerate(rows):
            for gx, v in enumerate(row):
                if v:
                    a = int((v / maxv) * 255)
                    im.putpixel((gx, gy), (cr, cg, cb, a))

        # Escalonamento 2x Nearest Neighbor impecável (sem borrão)
        scaled = im.resize(((w + 1) * self.scale, (h + 1) * self.scale), Image.Resampling.NEAREST)
        photo = ImageTk.PhotoImage(scaled)
        self._glyph_cache[key] = photo
        return photo

    def _draw_text_line(self, start_x, y, line, box_limit_x):
        """
        Desenha linha caractere a caractere respeitando kerning e avanço real.
        Destaca automaticamente em vermelho vivo (#FF5555) qualquer caractere que estourar a caixa.
        """
        s = self.scale
        font = self.layout.font
        cur_x = start_x
        for ch in line:
            g = font.glyph_for(ch)
            if g is None:
                continue
            left, ink, adv = font.metrics(g)
            is_overflow = (cur_x + left + ink) > box_limit_x
            color = "#FF5555" if is_overflow else "#FFFFFF"
            if ink > 0:
                img = self._glyph_photo(g, color)
                self._images.append(img)
                self.create_image((cur_x + left) * s, y * s, image=img, anchor="nw")
            cur_x += adv
        return cur_x

    # -- Desenho da Tela do Nintendo DS ----------------------------------------
    def draw_screen(self):
        self.delete("all")
        self._images = []
        s = self.scale
        W, H = SCREEN_W, SCREEN_H

        # Fundo: Cena estilizada da tela inferior do DS
        self.create_rectangle(0, 0, self.ds_w, self.ds_h, fill=self.BG_SCREEN, outline="")
        for y in range(0, H, 12):
            self.create_line(0, y * s, W * s, y * s, fill="#111420")
        self.create_text(W * s // 2, 8 * s, text="SIMULADOR DA TELA NDS 256×192 (FONTE NFTR REAL)",
                         fill="#3B4261", font=("Segoe UI", 8, "bold"))

        layout = self.layout
        font = layout.font
        lh = font.line_height
        box_w = layout.width_px
        box_h = layout.lines * lh

        # Geometria da Caixa de Diálogo do Coraline DS
        frame_x1 = max(8, (W - max(box_w + 24, 216)) // 2)
        frame_x2 = min(W - 8, frame_x1 + max(box_w + 24, 216))
        frame_y1 = H - box_h - 26
        frame_y2 = H - 8

        text_x1 = frame_x1 + 12
        text_x2 = text_x1 + box_w
        text_y1 = frame_y1 + 12

        # 1. Sombra da caixa de diálogo
        self.create_rectangle((frame_x1 + 2) * s, (frame_y1 + 2) * s,
                              (frame_x2 + 2) * s, (frame_y2 + 2) * s,
                              fill="#06070B", outline="")

        # 2. Moldura gótica dupla
        self.create_rectangle(frame_x1 * s, frame_y1 * s,
                              frame_x2 * s, frame_y2 * s,
                              fill=self.BG_BOX, outline="#2E384D", width=2)
        self.create_rectangle((frame_x1 + 3) * s, (frame_y1 + 3) * s,
                              (frame_x2 - 3) * s, (frame_y2 - 3) * s,
                              fill=self.BG_BOX_INNER, outline="#1E2638", width=1)

        # 3. Rebites metálicos nos cantos
        for cx, cy in [(frame_x1+5, frame_y1+5), (frame_x2-5, frame_y1+5),
                       (frame_x1+5, frame_y2-5), (frame_x2-5, frame_y2-5)]:
            self.create_oval((cx-2)*s, (cy-2)*s, (cx+2)*s, (cy+2)*s, fill="#4E5A73", outline="#7AA2F7", width=1)

        # 4. Aba de Título / Personagem
        title_text = self.current_title if self.current_title else "[ DIÁLOGO ]"
        tab_w = max(70, len(title_text) * 6 + 12)
        self.create_rectangle((frame_x1 + 10) * s, (frame_y1 - 7) * s,
                              (frame_x1 + 10 + tab_w) * s, (frame_y1 + 3) * s,
                              fill="#1F2335", outline="#3D59A1", width=1)
        self.create_text((frame_x1 + 14) * s, (frame_y1 - 2) * s,
                         text=title_text, fill="#7AA2F7", anchor="w",
                         font=("Segoe UI", 7, "bold"))

        # 5. Texto com Glifos Reais e Métricas da ROM
        all_lines = self.current_text.split("\n") if self.current_text else []
        widths = [font.text_width(l) for l in all_lines]
        big = max(widths) if widths else 0
        pages = max(1, (len(all_lines) + layout.lines - 1) // layout.lines)

        for idx, line in enumerate(all_lines[:layout.lines]):
            ly = text_y1 + idx * lh
            self._draw_text_line(text_x1, ly, line, text_x2)

        # 6. Indicadores e Guias de Limite
        if self.show_guides:
            # Linha vertical tracejada no limite exato
            self.create_line(text_x2 * s, (frame_y1 + 4) * s,
                             text_x2 * s, (frame_y2 - 4) * s,
                             fill="#FF5555" if big > box_w else "#7AA2F7",
                             dash=(2, 2), width=1)
            # Régua superior
            for gx in range(0, box_w + 1, 20):
                self.create_line((text_x1 + gx) * s, (text_y1 - 3) * s,
                                 (text_x1 + gx) * s, (text_y1 - 1) * s, fill="#3B4261")
            self.create_text(text_x2 * s, (text_y1 - 5) * s,
                             text=f"{box_w}px", fill="#FF5555" if big > box_w else "#7AA2F7",
                             anchor="s", font=("Segoe UI", 7, "bold"))

        # 7. Badge de Status (CABE / CORTA / PÁGINAS)
        if big > box_w:
            overflow_px = big - box_w
            badge_text = f"⚠ CORTA (+{overflow_px}px)"
            badge_fg = "#FF5555"
            badge_bg = "#36151B"
        elif len(all_lines) > layout.lines:
            badge_text = f"📄 {pages} PÁGINAS"
            badge_fg = "#FFB86C"
            badge_bg = "#2A2418"
        else:
            badge_text = "✓ CABE"
            badge_fg = "#9ECE6A"
            badge_bg = "#16281E"

        self.create_rectangle((frame_x2 - 76) * s, (frame_y1 - 7) * s,
                              (frame_x2 - 6) * s, (frame_y1 + 3) * s,
                              fill=badge_bg, outline=badge_fg, width=1)
        self.create_text((frame_x2 - 41) * s, (frame_y1 - 2) * s,
                         text=badge_text, fill=badge_fg, anchor="center",
                         font=("Segoe UI", 7, "bold"))

        # 8. Seta de Continuação do Diálogo no canto inferior direito
        self.create_text((frame_x2 - 12) * s, (frame_y2 - 8) * s,
                         text="▶", fill="#7AA2F7", font=("Segoe UI", 8, "bold"))

        # 9. Barra Medidora de Largura (Gauge)
        used_w = min(big, box_w)
        gauge_y = frame_y2 + 3
        gauge_h = 3
        if gauge_y + gauge_h < H:
            self.create_rectangle(text_x1 * s, gauge_y * s,
                                  text_x2 * s, (gauge_y + gauge_h) * s,
                                  fill="#1A1B26", outline="#24283B")
            if used_w > 0:
                gauge_color = "#FF5555" if big > box_w else "#9ECE6A"
                self.create_rectangle(text_x1 * s, gauge_y * s,
                                      (text_x1 + used_w) * s, (gauge_y + gauge_h) * s,
                                      fill=gauge_color, outline="")

# ==============================================================================
# INTERFACE GRÁFICA PRINCIPAL (MODERN DARK THEME)
# ==============================================================================
class CoralineTextEditorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Coraline DS - Editor & Tradutor de Textos Profissional")
        self.root.geometry("1400x880")
        self.root.minsize(1100, 720)
        self.root.configure(bg="#12131C")

        # Dados e Motores
        self.font = NitroFont(FONT_PATH)
        self.font_validator = self.font          # compatibilidade
        self.font_jp = NitroFont(FONT_PATH_JP)
        self.box_width = DEFAULT_BOX_WIDTH_PX
        self.box_lines = DEFAULT_BOX_LINES
        self.limit_source = ""
        self._load_config()
        self.layout = TextBoxLayout(self.font, self.box_width, self.box_lines)
        self.current_archive = None
        self.original_archive = None
        self.current_file_path = ""
        self.current_diag_idx = 0
        self.ref_lang = 1    # 1 = Inglês
        self.target_lang = 1 # 1 = Inglês (padrão de tradução)

        # Calibra a largura da caixa com o próprio texto original do jogo
        self._auto_calibrate_limit()

        # Inicializa Estilo Moderno
        self.setup_theme()
        # Constrói UI
        self.build_ui()
        # Carrega pasta padrão
        self.load_directory(TXT_DIR)

    # ==========================================================================
    # CONFIGURAÇÃO DA CAIXA DE TEXTO (PIXELS REAIS)
    # ==========================================================================
    def _load_config(self):
        """Lê a largura/altura da caixa salva pelo usuário (se existir)."""
        try:
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                self.box_width = int(cfg.get("box_width_px", self.box_width))
                self.box_lines = int(cfg.get("box_lines", self.box_lines))
                self.limit_source = cfg.get("limit_source", "config salva")
        except Exception as e:
            print(f"Aviso ao ler configuração: {e}")

    def _save_config(self):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump({"box_width_px": self.box_width,
                           "box_lines": self.box_lines,
                           "limit_source": self.limit_source}, f, indent=2)
        except Exception as e:
            print(f"Aviso ao salvar configuração: {e}")

    def _auto_calibrate_limit(self):
        """Mede a maior linha do texto original do jogo e usa como limite."""
        folder = TXT_ORIGINAL_DIR if os.path.isdir(TXT_ORIGINAL_DIR) else TXT_DIR
        result = scan_original_limit(self.font, folder)
        if result:
            limit, robust, top_w, top_file, n_lines = result
            # Só sobrescreve o padrão se o usuário nunca ajustou manualmente
            if not os.path.exists(CONFIG_PATH):
                self.box_width = limit
                self.limit_source = (f"medido em {n_lines} linhas do texto original: "
                                     f"P99,5 = {robust} px → {limit} px "
                                     f"(maior isolada {top_w} px)")
            else:
                self.limit_source = (f"salvo pelo usuário ({self.box_width} px); "
                                     f"medido no original: {limit} px")
        self.layout = TextBoxLayout(self.font, self.box_width, self.box_lines)

    def setup_theme(self):
        self.style = ttk.Style()
        self.style.theme_use("clam")

        # Cores da Paleta
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

        # Configuração de componentes ttk
        self.style.configure(".", background=self.BG_MAIN, foreground=self.TEXT_MAIN, font=("Segoe UI", 10))
        self.style.configure("TFrame", background=self.BG_MAIN)
        self.style.configure("Card.TFrame", background=self.BG_CARD)
        self.style.configure("CardLight.TFrame", background=self.BG_CARD_LIGHT)

        self.style.configure("TLabel", background=self.BG_MAIN, foreground=self.TEXT_MAIN)
        self.style.configure("Card.TLabel", background=self.BG_CARD, foreground=self.TEXT_MAIN)
        self.style.configure("Muted.TLabel", background=self.BG_CARD, foreground=self.TEXT_MUTED, font=("Segoe UI", 9))
        self.style.configure("Title.TLabel", background=self.BG_CARD, foreground=self.TEXT_MAIN, font=("Segoe UI", 12, "bold"))

        # Botões modernos
        self.style.configure("Action.TButton", background="#3B4261", foreground="#FFFFFF", 
                             font=("Segoe UI", 9, "bold"), borderwidth=0, padding=6)
        self.style.map("Action.TButton", background=[("active", "#7AA2F7"), ("pressed", "#565F89")])

        self.style.configure("Primary.TButton", background="#7AA2F7", foreground="#0F101A", 
                             font=("Segoe UI", 9, "bold"), borderwidth=0, padding=7)
        self.style.map("Primary.TButton", background=[("active", "#89B4FA"), ("pressed", "#5E81AC")])

        self.style.configure("Magic.TButton", background="#BB9AF7", foreground="#0F101A", 
                             font=("Segoe UI", 9, "bold"), borderwidth=0, padding=7)
        self.style.map("Magic.TButton", background=[("active", "#DDB6F2"), ("pressed", "#9D7CD8")])

        self.style.configure("Success.TButton", background="#9ECE6A", foreground="#0F101A", 
                             font=("Segoe UI", 9, "bold"), borderwidth=0, padding=7)
        self.style.map("Success.TButton", background=[("active", "#B9F27C"), ("pressed", "#73DACA")])

        # Treeview escuro estilizado
        self.style.configure("Treeview", background="#1A1B26", foreground="#C0CAF5", 
                             fieldbackground="#1A1B26", rowheight=28, borderwidth=0, font=("Segoe UI", 9))
        self.style.map("Treeview", background=[("selected", "#3B4261")], foreground=[("selected", "#FFFFFF")])
        self.style.configure("Treeview.Heading", background="#24283B", foreground="#7AA2F7", 
                             font=("Segoe UI", 9, "bold"), borderwidth=0)
        self.style.map("Treeview.Heading", background=[("active", "#2E3440")])

        # Combobox
        self.style.configure("TCombobox", fieldbackground="#24283B", background="#24283B", foreground="#FFFFFF")

    def build_ui(self):
        # ----------------------------------------------------------------------
        # BARRA SUPERIOR (HEADER)
        # ----------------------------------------------------------------------
        header = tk.Frame(self.root, bg=self.BG_CARD, height=64)
        header.pack(side="top", fill="x")

        # Título e Logo
        title_box = tk.Frame(header, bg=self.BG_CARD)
        title_box.pack(side="left", padx=20, pady=12)

        lbl_logo = tk.Label(title_box, text="🗝️ CORALINE DS", fg=self.ACCENT_PURPLE, bg=self.BG_CARD, 
                            font=("Segoe UI", 14, "bold"))
        lbl_logo.pack(side="left")

        lbl_sub = tk.Label(title_box, text=" | Editor & Tradutor de Textos Fiel", fg=self.TEXT_MUTED, bg=self.BG_CARD, 
                           font=("Segoe UI", 10))
        lbl_sub.pack(side="left")

        # Seletores de Idiomas no Header
        lang_box = tk.Frame(header, bg=self.BG_CARD)
        lang_box.pack(side="right", padx=20, pady=12)

        tk.Label(lang_box, text="Idioma de Referência:", fg=self.TEXT_MUTED, bg=self.BG_CARD, font=("Segoe UI", 9)).pack(side="left", padx=4)
        self.combo_ref = ttk.Combobox(lang_box, values=LANG_NAMES, state="readonly", width=18)
        self.combo_ref.current(1) # Inglês
        self.combo_ref.pack(side="left", padx=6)
        self.combo_ref.bind("<<ComboboxSelected>>", self.on_ref_lang_changed)

        tk.Label(lang_box, text="Slot de Tradução:", fg=self.TEXT_MUTED, bg=self.BG_CARD, font=("Segoe UI", 9)).pack(side="left", padx=8)
        self.combo_target = ttk.Combobox(lang_box, values=LANG_NAMES, state="readonly", width=18)
        self.combo_target.current(1) # Inglês (ou substituir Espanhol)
        self.combo_target.pack(side="left", padx=6)
        self.combo_target.bind("<<ComboboxSelected>>", self.on_target_lang_changed)

        btn_open_folder = ttk.Button(lang_box, text="📁 Abrir Pasta", style="Action.TButton", command=self.browse_folder)
        btn_open_folder.pack(side="left", padx=(10, 4))

        btn_texture_tool = ttk.Button(lang_box, text="🎨 Editor de Texturas", style="Magic.TButton", command=self.open_texture_tool)
        btn_texture_tool.pack(side="left", padx=4)

        btn_repack = ttk.Button(lang_box, text="⚙ Recompilar ROM (current.nds)", style="Success.TButton", command=self.recompile_rom_action)
        btn_repack.pack(side="left", padx=4)

        # ----------------------------------------------------------------------
        # CORPO PRINCIPAL (3 COLUNAS)
        # ----------------------------------------------------------------------
        main_body = tk.Frame(self.root, bg=self.BG_MAIN)
        main_body.pack(fill="both", expand=True, padx=15, pady=15)

        # COLUNA 1: LISTA DE ARQUIVOS (ESQUERDA, ~260px)
        col_files = tk.Frame(main_body, bg=self.BG_CARD, width=280)
        col_files.pack(side="left", fill="y", padx=(0, 10))
        col_files.pack_propagate(False)

        col_files_header = tk.Frame(col_files, bg=self.BG_CARD)
        col_files_header.pack(fill="x", padx=12, pady=(12, 6))
        tk.Label(col_files_header, text="ARQUIVOS (.BIN)", fg=self.ACCENT, bg=self.BG_CARD, font=("Segoe UI", 10, "bold")).pack(side="left")
        self.lbl_file_count = tk.Label(col_files_header, text="0 arquivos", fg=self.TEXT_MUTED, bg=self.BG_CARD, font=("Segoe UI", 8))
        self.lbl_file_count.pack(side="right")

        # Campo de busca de arquivos
        self.file_search_var = tk.StringVar()
        self.file_search_var.trace_add("write", self.filter_files)
        entry_fsearch = tk.Entry(col_files, textvariable=self.file_search_var, bg=self.BG_CARD_LIGHT, 
                                 fg="#FFFFFF", insertbackground="#FFFFFF", relief="flat", font=("Segoe UI", 9))
        entry_fsearch.pack(fill="x", padx=12, pady=6, ipady=4)

        # Lista de arquivos (Treeview)
        files_scroll = ttk.Scrollbar(col_files, orient="vertical")
        self.tree_files = ttk.Treeview(col_files, columns=("name", "diags"), show="headings", 
                                       selectmode="browse", yscrollcommand=files_scroll.set)
        files_scroll.config(command=self.tree_files.yview)
        self.tree_files.heading("name", text="Arquivo")
        self.tree_files.heading("diags", text="Falas")
        self.tree_files.column("name", width=190, anchor="w")
        self.tree_files.column("diags", width=50, anchor="center")
        self.tree_files.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=(0, 12))
        files_scroll.pack(side="right", fill="y", pady=(0, 12), padx=(0, 6))
        self.tree_files.bind("<<TreeviewSelect>>", self.on_file_selected)

        # COLUNA 2: LISTA DE FALAS & EDITOR CENTRAL
        col_editor = tk.Frame(main_body, bg=self.BG_MAIN)
        col_editor.pack(side="left", fill="both", expand=True, padx=(0, 10))

        # Painel Superior do Editor: Tabela de Diálogos do Arquivo
        panel_diags = tk.Frame(col_editor, bg=self.BG_CARD, height=260)
        panel_diags.pack(fill="x", pady=(0, 10))
        panel_diags.pack_propagate(False)

        diag_hdr = tk.Frame(panel_diags, bg=self.BG_CARD)
        diag_hdr.pack(fill="x", padx=12, pady=(10, 4))
        self.lbl_current_file_title = tk.Label(diag_hdr, text="Nenhum arquivo carregado", 
                                               fg=self.TEXT_MAIN, bg=self.BG_CARD, font=("Segoe UI", 11, "bold"))
        self.lbl_current_file_title.pack(side="left")

        # Busca rápida de texto nas falas
        self.diag_search_var = tk.StringVar()
        self.diag_search_var.trace_add("write", self.filter_dialogues)
        tk.Label(diag_hdr, text="🔍 Buscar fala:", fg=self.TEXT_MUTED, bg=self.BG_CARD, font=("Segoe UI", 9)).pack(side="left", padx=(20, 4))
        entry_diag_search = tk.Entry(diag_hdr, textvariable=self.diag_search_var, bg=self.BG_CARD_LIGHT, 
                                     fg="#FFFFFF", insertbackground="#FFFFFF", relief="flat", font=("Segoe UI", 9), width=24)
        entry_diag_search.pack(side="left", ipady=2)

        # Treeview de Diálogos
        diag_scroll = ttk.Scrollbar(panel_diags, orient="vertical")
        self.tree_diags = ttk.Treeview(panel_diags, columns=("id", "ref", "target", "status"), show="headings", 
                                       selectmode="browse", yscrollcommand=diag_scroll.set)
        diag_scroll.config(command=self.tree_diags.yview)
        self.tree_diags.heading("id", text="#")
        self.tree_diags.heading("ref", text="Original (Referência)")
        self.tree_diags.heading("target", text="Tradução")
        self.tree_diags.heading("status", text="Status")
        self.tree_diags.column("id", width=45, anchor="center")
        self.tree_diags.column("ref", width=250, anchor="w")
        self.tree_diags.column("target", width=250, anchor="w")
        self.tree_diags.column("status", width=75, anchor="center")
        self.tree_diags.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=(0, 10))
        diag_scroll.pack(side="right", fill="y", pady=(0, 10), padx=(0, 6))
        self.tree_diags.bind("<<TreeviewSelect>>", self.on_dialogue_selected)
        self.tree_diags.tag_configure("bad", foreground="#F7768E")
        self.tree_diags.tag_configure("warn", foreground="#E0AF68")
        self.tree_diags.tag_configure("good", foreground="#9ECE6A")

        # Painel Inferior do Editor: Caixa de Edição & Ferramentas
        panel_edit_box = tk.Frame(col_editor, bg=self.BG_CARD)
        panel_edit_box.pack(fill="both", expand=True)

        edit_top_bar = tk.Frame(panel_edit_box, bg=self.BG_CARD)
        edit_top_bar.pack(fill="x", padx=15, pady=(12, 6))

        self.lbl_editing_diag_info = tk.Label(edit_top_bar, text="Fala #0 - Chunk: 0", 
                                              fg=self.ACCENT, bg=self.BG_CARD, font=("Segoe UI", 10, "bold"))
        self.lbl_editing_diag_info.pack(side="left")

        # Botões de Navegação rápida (Anterior / Próximo)
        nav_box = tk.Frame(edit_top_bar, bg=self.BG_CARD)
        nav_box.pack(side="right")
        btn_prev = ttk.Button(nav_box, text="◀ Anterior (Ctrl+Up)", style="Action.TButton", command=self.prev_dialogue)
        btn_prev.pack(side="left", padx=3)
        btn_next = ttk.Button(nav_box, text="Próximo (Ctrl+Down) ▶", style="Action.TButton", command=self.next_dialogue)
        btn_next.pack(side="left", padx=3)

        # Caixa do Texto de Referência (Somente Leitura)
        tk.Label(panel_edit_box, text="TEXTO ORIGINAL DE REFERÊNCIA:", fg=self.TEXT_MUTED, bg=self.BG_CARD, 
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=15, pady=(4, 2))
        self.txt_ref = tk.Text(panel_edit_box, height=3, bg=self.BG_CARD_LIGHT, fg="#9AA5CE", 
                               relief="flat", font=("Consolas", 10), padx=8, pady=6)
        self.txt_ref.pack(fill="x", padx=15, pady=(0, 8))
        self.txt_ref.config(state="disabled")

        # Caixa do Texto Traduzido (Editável)
        tk.Label(panel_edit_box, text="TEXTO TRADUZIDO (EDITÁVEL):", fg=self.COLOR_SUCCESS, bg=self.BG_CARD, 
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=15, pady=(4, 2))
        self.txt_target = tk.Text(panel_edit_box, height=4, bg="#13141F", fg="#FFFFFF", 
                                  insertbackground="#FFFFFF", relief="flat", font=("Consolas", 11, "bold"), 
                                  padx=8, pady=6)
        self.txt_target.pack(fill="x", padx=15, pady=(0, 6))
        self.txt_target.bind("<KeyRelease>", self.on_text_edited)

        # Barra de Status de Limites e Segurança do Texto
        self.safety_card = tk.Frame(panel_edit_box, bg="#1E2030", padx=10, pady=6)
        self.safety_card.pack(fill="x", padx=15, pady=4)
        self.lbl_safety_status = tk.Label(self.safety_card, text="● SEGURO", fg=self.COLOR_SUCCESS, 
                                          bg="#1E2030", font=("Segoe UI", 9, "bold"))
        self.lbl_safety_status.pack(side="left")
        self.lbl_safety_detail = tk.Label(self.safety_card, text="0 px", 
                                          fg=self.TEXT_MUTED, bg="#1E2030", font=("Segoe UI", 9))
        self.lbl_safety_detail.pack(side="left", padx=12)
        self.lbl_line_breakdown = tk.Label(self.safety_card, text="L1: 0px", fg="#89B4FA", 
                                           bg="#1E2030", font=("Consolas", 9))
        self.lbl_line_breakdown.pack(side="right")

        # Barra de Ferramentas e Ações
        action_bar = tk.Frame(panel_edit_box, bg=self.BG_CARD)
        action_bar.pack(fill="x", padx=15, pady=10)

        # Botão Mágico de Auto-Quebra de Linhas
        btn_autowrap = ttk.Button(action_bar, text="⚡ Auto-Quebrar Linhas (\\n)", 
                                  style="Magic.TButton", command=self.apply_auto_wrap)
        btn_autowrap.pack(side="left", padx=(0, 8))

        btn_copy_orig = ttk.Button(action_bar, text="📋 Copiar do Original", 
                                   style="Action.TButton", command=self.copy_original_to_target)
        btn_copy_orig.pack(side="left", padx=4)

        btn_save_diag = ttk.Button(action_bar, text="💾 Salvar Fala (Ctrl+S)", 
                                   style="Primary.TButton", command=self.save_current_dialogue)
        btn_save_diag.pack(side="right", padx=4)

        # COLUNA 3: SIMULADOR DE TELA DO NINTENDO DS & GERENCIAMENTO (DIREITA)
        col_preview = tk.Frame(main_body, bg=self.BG_CARD, width=460)
        col_preview.pack(side="left", fill="both", padx=(0, 0))
        col_preview.pack_propagate(False)

        prev_header = tk.Frame(col_preview, bg=self.BG_CARD)
        prev_header.pack(fill="x", padx=15, pady=(12, 6))
        tk.Label(prev_header, text="SIMULADOR DA TELA NDS", fg=self.ACCENT_PURPLE, bg=self.BG_CARD, 
                 font=("Segoe UI", 10, "bold")).pack(side="left")

        btn_toggle_guides = ttk.Button(prev_header, text="Linhas Guia", style="Action.TButton", 
                                       command=self.toggle_guides)
        btn_toggle_guides.pack(side="right")

        # Canvas da Tela do NDS
        self.ds_canvas = DSPreviewCanvas(col_preview, self.font, self.layout)
        self.ds_canvas.pack(padx=8, pady=8)

        # ---- Painel de calibração da caixa (pixels reais) -------------------
        box_cfg = tk.Frame(col_preview, bg=self.BG_CARD_LIGHT, padx=10, pady=6)
        box_cfg.pack(fill="x", padx=15, pady=(0, 6))

        tk.Label(box_cfg, text="CAIXA DE TEXTO (PIXELS REAIS)", fg=self.ACCENT,
                 bg=self.BG_CARD_LIGHT, font=("Segoe UI", 8, "bold")).grid(row=0, column=0, columnspan=6, sticky="w")

        tk.Label(box_cfg, text="Largura útil:", fg=self.TEXT_MUTED, bg=self.BG_CARD_LIGHT,
                 font=("Segoe UI", 8)).grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.var_box_width = tk.IntVar(value=self.box_width)
        self.spin_width = tk.Spinbox(box_cfg, from_=80, to=256, increment=2, width=5,
                                     textvariable=self.var_box_width,
                                     bg=self.BG_CARD, fg="#FFFFFF", relief="flat",
                                     buttonbackground=self.BG_CARD_LIGHT,
                                     command=self.on_box_settings_changed)
        self.spin_width.grid(row=1, column=1, padx=(4, 2), pady=(4, 0), ipady=1)
        self.spin_width.bind("<Return>", self.on_box_settings_changed)
        self.spin_width.bind("<FocusOut>", self.on_box_settings_changed)
        tk.Label(box_cfg, text="px", fg=self.TEXT_MUTED, bg=self.BG_CARD_LIGHT,
                 font=("Segoe UI", 8)).grid(row=1, column=2, sticky="w", pady=(4, 0))

        tk.Label(box_cfg, text="Linhas:", fg=self.TEXT_MUTED, bg=self.BG_CARD_LIGHT,
                 font=("Segoe UI", 8)).grid(row=1, column=3, sticky="e", padx=(10, 0), pady=(4, 0))
        self.var_box_lines = tk.IntVar(value=self.box_lines)
        self.spin_lines = tk.Spinbox(box_cfg, from_=1, to=6, increment=1, width=3,
                                     textvariable=self.var_box_lines,
                                     bg=self.BG_CARD, fg="#FFFFFF", relief="flat",
                                     buttonbackground=self.BG_CARD_LIGHT,
                                     command=self.on_box_settings_changed)
        self.spin_lines.grid(row=1, column=4, padx=4, pady=(4, 0), ipady=1)
        self.spin_lines.bind("<Return>", self.on_box_settings_changed)
        self.spin_lines.bind("<FocusOut>", self.on_box_settings_changed)

        btn_recal = ttk.Button(box_cfg, text="↺ Medir do jogo", style="Action.TButton",
                               command=self.recalibrate_from_rom)
        btn_recal.grid(row=1, column=5, padx=(8, 0), pady=(4, 0))

        self.lbl_box_source = tk.Label(box_cfg, text=self.limit_source or "", fg=self.TEXT_MUTED,
                                       bg=self.BG_CARD_LIGHT, font=("Segoe UI", 7),
                                       wraplength=390, justify="left")
        self.lbl_box_source.grid(row=2, column=0, columnspan=6, sticky="w", pady=(3, 0))

        # Informações de Integridade e Ponteiros
        card_info = tk.Frame(col_preview, bg=self.BG_CARD_LIGHT, padx=12, pady=10)
        card_info.pack(fill="x", padx=15, pady=8)

        tk.Label(card_info, text="INFORMAÇÕES DO ARQUIVO & PONTEIROS", fg=self.ACCENT, 
                 bg=self.BG_CARD_LIGHT, font=("Segoe UI", 9, "bold")).pack(anchor="w")

        self.lbl_info_ptrs = tk.Label(card_info, text="Ponteiros 32-bit: Auto-recalculados ao salvar", 
                                      fg=self.TEXT_MUTED, bg=self.BG_CARD_LIGHT, font=("Segoe UI", 9))
        self.lbl_info_ptrs.pack(anchor="w", pady=(4, 0))

        font_desc = (f"Fonte real: NFTR {self.font.tile_w}×{self.font.tile_h} px · "
                     f"{self.font.bpp} bpp · {len(self.font.cmap)} glifos")
        self.lbl_info_font = tk.Label(card_info, text=font_desc,
                                      fg=self.COLOR_SUCCESS, bg=self.BG_CARD_LIGHT, font=("Segoe UI", 9))
        self.lbl_info_font.pack(anchor="w")

        self.lbl_info_expansion = tk.Label(
            card_info,
            text=f"Medição em pixels · caixa {self.box_width}×{self.box_lines * self.font.line_height} px",
            fg=self.TEXT_MAIN, bg=self.BG_CARD_LIGHT, font=("Segoe UI", 9))
        self.lbl_info_expansion.pack(anchor="w")

        # Status do Patch ARM9 para acentos no idioma Inglês
        arm9_status_box = tk.Frame(card_info, bg=self.BG_CARD_LIGHT)
        arm9_status_box.pack(fill="x", pady=(6, 0))

        self.lbl_info_arm9 = tk.Label(arm9_status_box, text="ARM9 UTF-8 (EN): Verificando...", 
                                      fg=self.COLOR_SUCCESS, bg=self.BG_CARD_LIGHT, font=("Segoe UI", 8, "bold"))
        self.lbl_info_arm9.pack(side="left")

        self.btn_patch_arm9 = ttk.Button(arm9_status_box, text="⚡ Corrigir ARM9", style="Action.TButton", 
                                         command=self.patch_arm9_action)
        self.btn_patch_arm9.pack(side="right")
        self.update_arm9_status_ui()

        # Botões Globais de Arquivo
        btn_box = tk.Frame(col_preview, bg=self.BG_CARD)
        btn_box.pack(fill="x", padx=15, pady=10)

        btn_save_file = ttk.Button(btn_box, text="💾 Salvar Arquivo Binário (.bin)", 
                                   style="Success.TButton", command=self.save_current_file)
        btn_save_file.pack(fill="x", pady=4)

        json_box = tk.Frame(btn_box, bg=self.BG_CARD)
        json_box.pack(fill="x", pady=2)
        btn_exp_json = ttk.Button(json_box, text="📤 Exportar JSON", style="Action.TButton", 
                                  command=self.export_json_action)
        btn_exp_json.pack(side="left", fill="x", expand=True, padx=(0, 4))
        btn_imp_json = ttk.Button(json_box, text="📥 Importar JSON", style="Action.TButton", 
                                  command=self.import_json_action)
        btn_imp_json.pack(side="right", fill="x", expand=True, padx=(4, 0))

        btn_audit = ttk.Button(btn_box, text="🔎 Auditar pasta (falas que estouram)",
                               style="Action.TButton", command=self.audit_folder)
        btn_audit.pack(fill="x", pady=(8, 0))

        # Atalhos de teclado
        self.root.bind("<Control-s>", lambda e: self.save_current_dialogue())
        self.root.bind("<Control-Up>", lambda e: self.prev_dialogue())
        self.root.bind("<Control-Down>", lambda e: self.next_dialogue())

    # ==========================================================================
    # CARREGAMENTO E NAVEGAÇÃO DE DIRETÓRIOS E ARQUIVOS
    # ==========================================================================
    def open_texture_tool(self):
        tool_py = os.path.join(DEFAULT_ROOT, "CoralineTextureTool.py")
        if os.path.exists(tool_py):
            import subprocess
            subprocess.Popen([sys.executable, tool_py])
        else:
            messagebox.showwarning("Aviso", f"Arquivo não encontrado:\n{tool_py}")

    def browse_folder(self):
        folder = filedialog.askdirectory(initialdir=TXT_DIR, title="Selecione a pasta de textos do Coraline DS")
        if folder:
            self.load_directory(folder)

    def load_directory(self, folder_path):
        self.all_files = []
        # 1. Carrega o executável principal arm9.bin (Menus, Salvamento, Botões e Personagens)
        arm9_path = os.path.join(DEFAULT_ROOT, "arm9.bin")
        if os.path.exists(arm9_path):
            self.all_files.append(("arm9.bin (Menus & Sistema)", arm9_path))

        # 2. Carrega overlays de overlay/ (Itens e Minijogos)
        if os.path.exists(OVERLAY_DIR):
            for ov in ["overlay_0000.bin", "overlay_0001.bin"]:
                full_ov = os.path.join(OVERLAY_DIR, ov)
                if os.path.exists(full_ov):
                    lbl = f"{ov} (Itens)" if "0000" in ov else f"{ov} (Minijogos)"
                    self.all_files.append((lbl, full_ov))

        # 3. Carrega arquivos de diálogos de data/data/txt
        if os.path.exists(folder_path):
            for f in sorted(os.listdir(folder_path)):
                if f.endswith(".bin") and f.startswith("eve_"):
                    full_p = os.path.join(folder_path, f)
                    self.all_files.append((f, full_p))

        self.filter_files()
        if self.all_files:
            self.open_file(self.all_files[0][1])

    def filter_files(self, *args):
        query = self.file_search_var.get().lower()
        for item in self.tree_files.get_children():
            self.tree_files.delete(item)

        count = 0
        for name, full_p in self.all_files:
            if query in name.lower():
                # Determina contagem aproximada
                self.tree_files.insert("", "end", iid=full_p, values=(name, "-"))
                count += 1
        self.lbl_file_count.config(text=f"{count} arquivos")

    def on_file_selected(self, event):
        selected = self.tree_files.selection()
        if not selected:
            return
        filepath = selected[0]
        if filepath != self.current_file_path:
            # Se havia alterações pendentes, avisa
            if self.current_archive and self.current_archive.is_modified:
                resp = messagebox.askyesno("Alterações não salvas", 
                                           f"O arquivo {self.current_archive.filename} possui alterações não salvas no arquivo binário.\nDeseja salvar antes de trocar?")
                if resp:
                    self.save_current_file()
            self.open_file(filepath)

    def open_file(self, filepath):
        try:
            self.current_file_path = filepath
            fname = os.path.basename(filepath)
            if fname == "arm9.bin":
                self.current_archive = Arm9Archive(filepath)
                self.original_archive = None
                display_title = "arm9.bin (Menus, Salvar, Botões & Personagens)"
            elif fname.startswith("overlay_"):
                ov_type = "items" if "0000" in fname else "minigames"
                self.current_archive = OverlayArchive(filepath, ov_type)
                bak_cand = filepath + ".bak"
                self.original_archive = OverlayArchive(bak_cand, ov_type) if os.path.exists(bak_cand) else None
                display_title = f"{fname} ({'Itens' if '0000' in fname else 'Minijogos'})"
            else:
                self.current_archive = BinScriptArchive(filepath)
                orig_cand = os.path.join(TXT_ORIGINAL_DIR, fname)
                self.original_archive = BinScriptArchive(orig_cand) if os.path.exists(orig_cand) else None
                display_title = fname

            self.lbl_current_file_title.config(text=f"{display_title} ({len(self.current_archive.dialogues)} falas)")
            self.populate_dialogues_list()
        except Exception as e:
            messagebox.showerror("Erro ao abrir arquivo", f"Não foi possível abrir o arquivo:\n{e}")

    # ==========================================================================
    # MANIPULAÇÃO DE DIÁLOGOS
    # ==========================================================================
    def populate_dialogues_list(self):
        for item in self.tree_diags.get_children():
            self.tree_diags.delete(item)

        if not self.current_archive:
            return

        query = self.diag_search_var.get().lower()
        for idx, d in enumerate(self.current_archive.dialogues):
            if self.original_archive and idx < len(self.original_archive.dialogues) and self.ref_lang in self.original_archive.dialogues[idx]["texts"]:
                ref_t = self.original_archive.dialogues[idx]["texts"][self.ref_lang].replace("\n", " ")
            elif "orig_texts" in d and self.ref_lang in d.get("orig_texts", {}):
                ref_t = d["orig_texts"][self.ref_lang].replace("\n", " ")
            else:
                ref_t = d["texts"].get(self.ref_lang, d["texts"].get(1, "")).replace("\n", " ")

            tar_raw = d["texts"].get(self.target_lang, "")
            tar_t = tar_raw.replace("\n", " ")
            desc = d.get("description", "")

            if query and (query not in ref_t.lower() and query not in tar_t.lower() and query not in desc.lower()):
                continue

            # Status: vazio / original / traduzido + encaixe em PIXELS
            tag = ()
            if not tar_t.strip():
                status = "Vazio"
            else:
                m = self.layout.measure(tar_raw)
                if m["status"] == 2:
                    status = "✖ Estoura"
                    tag = ("bad",)
                elif m["status"] == 1:
                    status = "⚠ Páginas" if m["lines"] > self.box_lines else "⚠ Limite"
                    tag = ("warn",)
                else:
                    status = "✔ Cabe"
                    tag = ("good",)

            col_ref = f"[{desc}] {ref_t}" if desc else ref_t
            self.tree_diags.insert("", "end", iid=str(idx), tags=tag,
                                   values=(f"{idx+1}", col_ref[:50], tar_t[:45], status))

        # Seleciona o primeiro diálogo
        children = self.tree_diags.get_children()
        if children:
            self.tree_diags.selection_set(children[0])
            self.on_dialogue_selected(None)

    def filter_dialogues(self, *args):
        self.populate_dialogues_list()

    def on_dialogue_selected(self, event):
        selected = self.tree_diags.selection()
        if not selected:
            return
        idx = int(selected[0])
        self.current_diag_idx = idx
        self.load_dialogue_to_editor(idx)

    def load_dialogue_to_editor(self, idx):
        if not self.current_archive or idx >= len(self.current_archive.dialogues):
            return
        diag = self.current_archive.dialogues[idx]
        if self.original_archive and idx < len(self.original_archive.dialogues) and self.ref_lang in self.original_archive.dialogues[idx]["texts"]:
            ref_text = self.original_archive.dialogues[idx]["texts"][self.ref_lang]
        elif "orig_texts" in diag and self.ref_lang in diag.get("orig_texts", {}):
            ref_text = diag["orig_texts"][self.ref_lang]
        else:
            ref_text = diag["texts"].get(self.ref_lang, diag["texts"].get(1, ""))
        target_text = diag["texts"].get(self.target_lang, "")

        desc_extra = f" | {diag['description']}" if "description" in diag else ""
        self.lbl_editing_diag_info.config(
            text=f"Fala #{idx+1} de {len(self.current_archive.dialogues)} (Base Chunk #{diag['base_chunk']}){desc_extra}"
        )

        # Atualiza caixa de referência
        self.txt_ref.config(state="normal")
        self.txt_ref.delete("1.0", "end")
        self.txt_ref.insert("1.0", ref_text)
        self.txt_ref.config(state="disabled")

        # Atualiza caixa de tradução
        self.txt_target.delete("1.0", "end")
        self.txt_target.insert("1.0", target_text)

        # Atualiza análise e simulador NDS
        title = f"Fala #{idx+1} de {len(self.current_archive.dialogues)}"
        self.update_analysis_and_preview(target_text, title=title)

    def on_text_edited(self, event=None):
        target_text = self.txt_target.get("1.0", "end-1c")
        self.update_analysis_and_preview(target_text)

    def update_analysis_and_preview(self, text, title=None):
        if title:
            self._current_preview_title = title
        title_to_use = getattr(self, "_current_preview_title", "")

        # Fonte correta para o idioma-alvo (JA usa a NFTR Shift-JIS)
        font = self.font_jp if (self.target_lang == 0 and self.font_jp.ok) else self.font
        if self.layout.font is not font:
            self.layout.font = font
            self.ds_canvas._glyph_cache.clear()

        # Medição REAL em pixels (fonte + largura da caixa do jogo)
        m = self.layout.measure(text)
        missing_chars = m["missing"]

        # Atualiza Canvas NDS com título da fala
        self.ds_canvas.update_preview(text, title=title_to_use)

        # Detalhe por linha, em pixels
        breakdown = " | ".join(f"L{i+1}: {w}px" for i, w in enumerate(m["widths"])) if m["widths"] else "L1: 0px"
        self.lbl_line_breakdown.config(text=breakdown)

        if missing_chars:
            chars_str = "".join(missing_chars[:5])
            self.lbl_safety_status.config(text="✖ CARACTERE AUSENTE", fg=self.COLOR_DANGER)
            self.lbl_safety_detail.config(text=f"Caracteres fora da fonte: '{chars_str}' (o jogo desenha vazio)")
        elif m["status"] == 2:
            self.lbl_safety_status.config(text="✖ ALERTA DE CORTE", fg=self.COLOR_DANGER)
            self.lbl_safety_detail.config(text=m["message"])
        elif m["status"] == 1:
            self.lbl_safety_status.config(text="▲ ATENÇÃO", fg=self.COLOR_WARN)
            self.lbl_safety_detail.config(text=m["message"])
        else:
            self.lbl_safety_status.config(text="● SEGURO", fg=self.COLOR_SUCCESS)
            self.lbl_safety_detail.config(text=m["message"])

    def apply_auto_wrap(self):
        """Re-quebra o texto usando a LARGURA REAL em pixels da caixa."""
        curr_text = self.txt_target.get("1.0", "end-1c")
        wrapped = TextWrapHelper.auto_wrap(curr_text, self.layout.font, self.box_width)
        self.txt_target.delete("1.0", "end")
        self.txt_target.insert("1.0", wrapped)
        self.update_analysis_and_preview(wrapped)

    # ==========================================================================
    # PAINEL DA CAIXA (CALIBRAÇÃO)
    # ==========================================================================
    def on_box_settings_changed(self, event=None):
        try:
            w = int(self.var_box_width.get())
            n = int(self.var_box_lines.get())
        except Exception:
            return
        w = max(80, min(256, w))
        n = max(1, min(6, n))
        if w == self.box_width and n == self.box_lines:
            return
        self.box_width, self.box_lines = w, n
        self.limit_source = "ajustado manualmente"
        self._save_config()
        self.lbl_box_source.config(text=self.limit_source)
        self.layout = TextBoxLayout(self.font, w, n)
        self.ds_canvas.set_layout(self.layout)
        self.update_analysis_and_preview(self.txt_target.get("1.0", "end-1c"))
        self.populate_dialogues_list()

    def recalibrate_from_rom(self):
        """Volta a medir a largura útil no texto original do jogo."""
        folder = TXT_ORIGINAL_DIR if os.path.isdir(TXT_ORIGINAL_DIR) else TXT_DIR
        result = scan_original_limit(self.font, folder)
        if not result:
            messagebox.showwarning("Calibração", "Não encontrei o texto original para medir.")
            return
        limit, robust, top_w, top_file, n_lines = result
        self.box_width = limit
        self.var_box_width.set(limit)
        self.limit_source = (f"medido em {n_lines} linhas do original: P99,5 = {robust} px "
                             f"→ {limit} px (maior isolada: {top_w} px em {top_file})")
        self._save_config()
        self.lbl_box_source.config(text=self.limit_source)
        self.layout = TextBoxLayout(self.font, self.box_width, self.box_lines)
        self.ds_canvas.set_layout(self.layout)
        self.update_analysis_and_preview(self.txt_target.get("1.0", "end-1c"))
        self.populate_dialogues_list()

    # ==========================================================================
    # AUDITORIA: TODAS AS FALAS DA PASTA
    # ==========================================================================
    def audit_folder(self):
        """Varre a pasta e lista todas as falas que não cabem na caixa."""
        folder = filedialog.askdirectory(initialdir=TXT_DIR,
                                         title="Pasta para auditar (ex.: data/data/txt)")
        if not folder:
            return
        total = 0
        bad = 0
        paginadas = 0
        by_file = {}
        rows = []
        for name in sorted(os.listdir(folder)):
            if not name.endswith(".bin") or not name.startswith("eve_"):
                continue
            try:
                arc = BinScriptArchive(os.path.join(folder, name))
            except Exception:
                continue
            for idx, d in enumerate(arc.dialogues):
                t = d["texts"].get(self.target_lang, "")
                if not t.strip():
                    continue
                total += 1
                m = self.layout.measure(t)
                if m["lines"] > self.box_lines:
                    paginadas += 1
                if m["status"] == 2:
                    bad += 1
                    by_file[name] = by_file.get(name, 0) + 1
                    rows.append((m["max_width"] - self.box_width, m["max_width"],
                                 m["lines"], name, idx + 1, t.replace("\n", " ")))
        rows.sort(reverse=True)
        report = os.path.join(folder, "auditoria_caixa_pixels.txt")
        try:
            with open(report, "w", encoding="utf-8") as f:
                f.write("AUDITORIA DA CAIXA DE TEXTO - Coraline DS\n")
                f.write(f"Caixa: {self.box_width} px x {self.box_lines} linhas | "
                        f"fonte {self.font.tile_w}x{self.font.tile_h}\n")
                f.write(f"Falas verificadas: {total} | estouram a largura: {bad} | "
                        f"com mais de {self.box_lines} linhas (pagina): {paginadas}\n\n")
                for excess, w, n, name, idx, txt in rows:
                    f.write(f"[{w}px, {n} linhas] {name} #{idx}: {txt}\n")
        except Exception as e:
            messagebox.showerror("Auditoria", f"Não consegui gravar o relatório:\n{e}")
            return

        top = sorted(by_file.items(), key=lambda kv: -kv[1])[:8]
        resumo = "\n".join(f"  {n}: {c} fala(s)" for n, c in top) if top else "  (nenhuma)"
        messagebox.showinfo(
            "Auditoria concluída",
            f"{total} falas verificadas com a fonte e a largura reais.\n\n"
            f"✔ Cabem na largura: {total - bad}\n"
            f"✖ Estouram a largura: {bad}\n"
            f"↻ Viram 2+ páginas (não perde texto): {paginadas}\n\n"
            f"Arquivos com mais estouros:\n{resumo}\n\n"
            f"Relatório completo:\n{report}")

    def copy_original_to_target(self):
        ref_text = self.txt_ref.get("1.0", "end-1c")
        self.txt_target.delete("1.0", "end")
        self.txt_target.insert("1.0", ref_text)
        self.update_analysis_and_preview(ref_text)

    def save_current_dialogue(self):
        """Salva a alteração da fala atual em memória."""
        if not self.current_archive:
            return
        new_text = self.txt_target.get("1.0", "end-1c")
        self.current_archive.update_dialogue(self.current_diag_idx, self.target_lang, new_text)

        # Atualiza a Treeview (status medido em pixels)
        sel_id = str(self.current_diag_idx)
        if self.tree_diags.exists(sel_id):
            ref_t = self.current_archive.dialogues[self.current_diag_idx]["texts"].get(self.ref_lang, "").replace("\n", " ")
            tar_t = new_text.replace("\n", " ")
            tag = ()
            if not tar_t.strip():
                status = "Vazio"
            else:
                m = self.layout.measure(new_text)
                if m["status"] == 2:
                    status, tag = "✖ Estoura", ("bad",)
                elif m["status"] == 1:
                    status = "⚠ Páginas" if m["lines"] > self.box_lines else "⚠ Limite"
                    tag = ("warn",)
                else:
                    status, tag = "✔ Cabe", ("good",)
            self.tree_diags.item(sel_id, tags=tag,
                                 values=(f"{self.current_diag_idx+1}", ref_t[:45], tar_t[:45], status))

        # Feedback sonoro / visual sutil
        self.lbl_safety_status.config(text="✔ SALVO!", fg=self.COLOR_SUCCESS)

    def prev_dialogue(self):
        self.save_current_dialogue()
        if self.current_diag_idx > 0:
            self.current_diag_idx -= 1
            sel_id = str(self.current_diag_idx)
            self.tree_diags.selection_set(sel_id)
            self.tree_diags.see(sel_id)
            self.load_dialogue_to_editor(self.current_diag_idx)

    def next_dialogue(self):
        self.save_current_dialogue()
        if self.current_archive and self.current_diag_idx + 1 < len(self.current_archive.dialogues):
            self.current_diag_idx += 1
            sel_id = str(self.current_diag_idx)
            self.tree_diags.selection_set(sel_id)
            self.tree_diags.see(sel_id)
            self.load_dialogue_to_editor(self.current_diag_idx)

    def save_current_file(self):
        if not self.current_archive:
            return
        self.save_current_dialogue()
        try:
            self.current_archive.save(backup=True)
            messagebox.showinfo("Sucesso!", 
                                f"Arquivo '{self.current_archive.filename}' salvo com sucesso!\n"
                                f"Todos os ponteiros de 32-bit foram recalculados perfeitamente.\n"
                                f"Backup criado: '{self.current_archive.filename}.bak'")
        except Exception as e:
            messagebox.showerror("Erro ao salvar", f"Ocorreu um erro ao gravar o arquivo binário:\n{e}")

    def export_json_action(self):
        if not self.current_archive:
            return
        default_name = os.path.splitext(self.current_archive.filename)[0] + ".json"
        out_p = filedialog.asksaveasfilename(defaultextension=".json", initialfile=default_name, 
                                             filetypes=[("Arquivos JSON", "*.json")])
        if out_p:
            self.current_archive.export_json(out_p)
            messagebox.showinfo("Exportado", f"Diálogos exportados para:\n{out_p}")

    def import_json_action(self):
        if not self.current_archive:
            return
        in_p = filedialog.askopenfilename(filetypes=[("Arquivos JSON", "*.json")])
        if in_p:
            count = self.current_archive.import_json(in_p, self.target_lang)
            self.populate_dialogues_list()
            messagebox.showinfo("Importação Concluída", f"{count} falas foram importadas com sucesso!")

    def on_ref_lang_changed(self, event):
        self.ref_lang = self.combo_ref.current()
        self.populate_dialogues_list()
        if self.current_archive:
            self.load_dialogue_to_editor(self.current_diag_idx)

    def on_target_lang_changed(self, event):
        self.target_lang = self.combo_target.current()
        self.populate_dialogues_list()
        if self.current_archive:
            self.load_dialogue_to_editor(self.current_diag_idx)

    def recompile_rom_action(self):
        """Recompila a ROM (current.nds) usando ndstool preservando o cabeçalho de 64 MB."""
        ndstool = os.path.join(os.path.dirname(DEFAULT_ROOT), "ndstool.exe")
        target_nds = os.path.join(os.path.dirname(DEFAULT_ROOT), "current.nds")
        if not os.path.exists(ndstool):
            messagebox.showerror("Erro", f"ndstool.exe não encontrado em:\n{ndstool}")
            return

        try:
            if self.current_archive and self.current_archive.is_modified:
                self.save_current_file()

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
            res = subprocess.run(cmd, cwd=os.path.dirname(DEFAULT_ROOT), capture_output=True, text=True)
            if res.returncode != 0:
                messagebox.showerror("Erro na Recompilação", f"Erro no ndstool:\n{res.stderr}")
                return

            # Preserva cabeçalho de 64 MB (0x14 = 0x09)
            with open(target_nds, "r+b") as f:
                f.seek(0x14)
                f.write(bytes([0x09]))

            sz_mb = os.path.getsize(target_nds) / (1024 * 1024)
            messagebox.showinfo("ROM Recompilada!",
                                f"ROM recompilada com sucesso em:\n{target_nds}\n\n"
                                f"Tamanho: {sz_mb:.2f} MB\n"
                                f"Cabeçalho de 64 MB preservado (compatível com DeSmuME e Flashcards)!")
        except Exception as e:
            messagebox.showerror("Erro ao Recompilar", f"Falha na recompilação:\n{e}")

    def toggle_guides(self):
        self.ds_canvas.toggle_guides()

    def update_arm9_status_ui(self):
        arm9_path = os.path.join(DEFAULT_ROOT, "arm9.bin")
        if not os.path.exists(arm9_path):
            self.lbl_info_arm9.config(text="ARM9: Arquivo não encontrado", fg=self.COLOR_WARN)
            self.btn_patch_arm9.config(state="disabled")
            return
        try:
            with open(arm9_path, "rb") as f:
                f.seek(0x0e04)
                byte = f.read(1)
            if byte == b"\x01":
                self.lbl_info_arm9.config(text="ARM9 UTF-8 (EN): Ativo ✔ (Acentos OK)", fg=self.COLOR_SUCCESS)
                self.btn_patch_arm9.config(state="disabled", text="✔ Corrigido")
            elif byte == b"\x02":
                self.lbl_info_arm9.config(text="ARM9 UTF-8 (EN): Inativo ✖ (Causa ﾃｩ)", fg=self.COLOR_DANGER)
                self.btn_patch_arm9.config(state="normal", text="⚡ Corrigir ARM9")
            else:
                self.lbl_info_arm9.config(text="ARM9: Byte desconhecido", fg=self.COLOR_WARN)
        except Exception as e:
            self.lbl_info_arm9.config(text=f"Erro ARM9: {e}", fg=self.COLOR_DANGER)

    def patch_arm9_action(self):
        arm9_path = os.path.join(DEFAULT_ROOT, "arm9.bin")
        bak_path = arm9_path + ".bak"
        if not os.path.exists(arm9_path):
            messagebox.showerror("Erro", "Arquivo arm9.bin não encontrado na pasta raiz!")
            return
        try:
            if not os.path.exists(bak_path):
                import shutil
                shutil.copy2(arm9_path, bak_path)
            with open(arm9_path, "rb") as f:
                data = bytearray(f.read())
            if len(data) > 0x0e04 and data[0x0e04] == 0x02:
                data[0x0e04] = 0x01
                with open(arm9_path, "wb") as f:
                    f.write(data)
                messagebox.showinfo("ARM9 Corrigido!", 
                                    "Patch aplicado com sucesso no arm9.bin!\n"
                                    "Agora o jogo usará a fonte europeia (coraline_font.NFTR) e decodificação UTF-8 no idioma Inglês (EN).\n"
                                    "Acentos como é, á, ã, ç, etc. funcionarão perfeitamente!")
                self.update_arm9_status_ui()
            elif len(data) > 0x0e04 and data[0x0e04] == 0x01:
                messagebox.showinfo("Informação", "O ARM9 já está corrigido com suporte a UTF-8 no idioma Inglês!")
                self.update_arm9_status_ui()
        except Exception as e:
            messagebox.showerror("Erro ao aplicar patch", f"Não foi possível modificar arm9.bin:\n{e}")

# ==============================================================================
# INICIALIZAÇÃO DA APLICAÇÃO
# ==============================================================================
if __name__ == "__main__":
    app_root = tk.Tk()
    app = CoralineTextEditorApp(app_root)
    app_root.mainloop()
