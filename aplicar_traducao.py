"""
aplicar_traducao.py - Injeta os arquivos traduzidos na pasta descompactada da ROM (NDS)

Uso:
  python aplicar_traducao.py [caminho_da_pasta_descompactada]

Se nenhum caminho for passado, tentará encontrar automaticamente ../NDS_UNPACK ou a pasta local.
"""

import os
import sys
import shutil
import glob

def aplicar(target_root: str):
    repo_root = os.path.dirname(os.path.abspath(__file__))
    target_root = os.path.abspath(target_root)
    
    print("=" * 65)
    print("  CORALINE (NDS) - INJETOR DA TRADUÇÃO PT-BR")
    print("=" * 65)
    print(f"Pasta do Repositório : {repo_root}")
    print(f"Pasta de Destino     : {target_root}\n")
    
    if not os.path.exists(target_root):
        print(f"[-] Erro: Pasta de destino não existe: {target_root}")
        return False

    # 1. Copiar Textos (eve_*.bin)
    src_txt = os.path.join(repo_root, "data", "data", "txt")
    dst_txt = os.path.join(target_root, "data", "data", "txt")
    os.makedirs(dst_txt, exist_ok=True)
    
    txt_files = glob.glob(os.path.join(src_txt, "eve_*.bin"))
    print(f"[*] Injetando {len(txt_files)} arquivos de diálogo em data/data/txt/...")
    for f in txt_files:
        shutil.copy2(f, os.path.join(dst_txt, os.path.basename(f)))
    print("    -> Diálogos atualizados com sucesso!")

    # 2. Copiar Overlays (Itens e Minijogos)
    src_overlay = os.path.join(repo_root, "overlay")
    dst_overlay = os.path.join(target_root, "overlay")
    os.makedirs(dst_overlay, exist_ok=True)
    
    for ov in ["overlay_0000.bin", "overlay_0001.bin"]:
        ov_src = os.path.join(src_overlay, ov)
        if os.path.exists(ov_src):
            shutil.copy2(ov_src, os.path.join(dst_overlay, ov))
            print(f"    -> Injetado {ov} (nomes de itens e minijogos)")

    # 3. Copiar Texturas modificadas (.NCGR)
    src_ncgr = os.path.join(repo_root, "data", "data", "info", "touchthescreen.NCGR")
    dst_ncgr = os.path.join(target_root, "data", "data", "info", "touchthescreen.NCGR")
    if os.path.exists(src_ncgr):
        os.makedirs(os.path.dirname(dst_ncgr), exist_ok=True)
        shutil.copy2(src_ncgr, dst_ncgr)
        print("    -> Injetada textura touchthescreen.NCGR (tela de toque)")

    # 4. Patch ARM9 (Acentos UTF-8)
    target_arm9 = os.path.join(target_root, "arm9.bin")
    if os.path.exists(target_arm9):
        print("[*] Verificando patch de acentuação no arm9.bin...")
        from patch_arm9 import apply_arm9_patch
        apply_arm9_patch(target_arm9)
    else:
        print("[!] Aviso: arm9.bin não encontrado na pasta de destino para aplicar o patch UTF-8.")

    print("\n" + "=" * 65)
    print("  TRADUÇÃO INJETADA COM SUCESSO!")
    print("  Agora basta recompilar a ROM (current.nds) usando o dslazy ou ndstool.")
    print("=" * 65)
    return True

if __name__ == "__main__":
    if len(sys.argv) > 1:
        target = sys.argv[1]
    else:
        # Tenta achar ../NDS_UNPACK por padrão
        candidate = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "NDS_UNPACK"))
        if os.path.exists(candidate):
            target = candidate
        else:
            target = os.path.dirname(os.path.abspath(__file__))
            
    aplicar(target)
