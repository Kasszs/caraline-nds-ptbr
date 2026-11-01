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
    print("  CORALINE (NDS) - INJETOR DA TRADUCAO PT-BR")
    print("=" * 65)
    print(f"Pasta do Repositorio : {repo_root}")
    print(f"Pasta de Destino     : {target_root}\n")
    
    if not os.path.exists(target_root):
        print(f"[-] Erro: Pasta de destino nao existe: {target_root}")
        return False

    # 1. Copiar Textos (eve_*.bin)
    src_txt = os.path.join(repo_root, "data", "data", "txt")
    dst_txt = os.path.join(target_root, "data", "data", "txt")
    os.makedirs(dst_txt, exist_ok=True)
    
    txt_files = glob.glob(os.path.join(src_txt, "eve_*.bin"))
    print(f"[*] Injetando {len(txt_files)} arquivos de dialogo em data/data/txt/...")
    for f in txt_files:
        shutil.copy2(f, os.path.join(dst_txt, os.path.basename(f)))
    print("    -> Dialogos atualizados com sucesso.")

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
        print("    -> Injetada textura touchthescreen.NCGR")

    # 4. Patch ARM9 (Menus e Acentos UTF-8)
    target_arm9 = os.path.join(target_root, "arm9.bin")
    if os.path.exists(target_arm9):
        print("[*] Atualizando menus e ativando patch UTF-8 no arm9.bin...")
        arm9_json = os.path.join(repo_root, "data", "data", "txt_json_dumps", "arm9_system_ptbr.json")
        try:
            sys.path.insert(0, repo_root)
            from CoralineTextEditor import Arm9Archive
            arm9 = Arm9Archive(target_arm9)
            if os.path.exists(arm9_json):
                arm9.import_json(arm9_json)
            arm9.save_file()
            print("    -> arm9.bin atualizado com menus traduzidos e suporte a UTF-8.")
        except Exception as e:
            print(f"[!] Falha ao aplicar rotina do Arm9Archive ({e}), tentando patch direto...")
            from patch_arm9 import apply_arm9_patch
            apply_arm9_patch(target_arm9)
    else:
        print("[!] Aviso: arm9.bin nao encontrado na pasta de destino.")

    print("\n" + "=" * 65)
    print("  INJECAO CONCLUIDA COM SUCESSO")
    print("  Recompile a ROM utilizando ndstool ou dslazy.")
    print("=" * 65)
    return True

if __name__ == "__main__":
    if len(sys.argv) > 1:
        target = sys.argv[1]
    else:
        candidate = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "NDS_UNPACK"))
        if os.path.exists(candidate):
            target = candidate
        else:
            target = os.path.dirname(os.path.abspath(__file__))
            
    aplicar(target)
