"""
patch_arm9.py - Patch de Suporte a UTF-8 (Acentos PT-BR) no ARM9 de Coraline (NDS)

Como funciona:
O jogo original armazena os diálogos em vários idiomas. No slot de idioma inglês (EN),
o executável ARM9 originalmente roteava a decodificação de texto para uma tabela restrita.
Quando caracteres acentuados (como á, é, ã, ç) eram inseridos, o jogo renderizava glifos
quebrados como "ﾃｩ" ou travava.

Ao modificar o byte no endereço 0x0E04 de 0x02 para 0x01:
- O ARM9 passa a usar o decodificador europeu em UTF-8 com a fonte oficial coraline_font.NFTR.
- Todos os acentos da língua portuguesa funcionam nativamente!
"""

import sys
import os
import shutil

def apply_arm9_patch(arm9_path: str) -> bool:
    if not os.path.exists(arm9_path):
        print(f"[-] Erro: Arquivo '{arm9_path}' não encontrado!")
        return False
        
    with open(arm9_path, "rb") as f:
        data = bytearray(f.read())
        
    if len(data) <= 0x0e04:
        print("[-] Erro: O arquivo arm9.bin é menor do que o esperado.")
        return False
        
    current_byte = data[0x0e04]
    if current_byte == 0x01:
        print("[*] Informação: O arm9.bin já possui o patch UTF-8 ativo (0x01)!")
        return True
        
    if current_byte == 0x02:
        bak_path = arm9_path + ".bak"
        if not os.path.exists(bak_path):
            shutil.copy2(arm9_path, bak_path)
            print(f"[+] Backup criado em: {bak_path}")
            
        data[0x0e04] = 0x01
        with open(arm9_path, "wb") as f:
            f.write(data)
            
        print("[+] Sucesso: Patch aplicado com sucesso no offset 0x0E04 (0x02 -> 0x01)!")
        print("[+] O jogo agora renderizará acentos PT-BR (ã, é, ç, etc.) perfeitamente.")
        return True
    else:
        print(f"[!] Aviso: Byte desconhecido no offset 0x0E04: 0x{current_byte:02X}. Nenhuma alteração feita.")
        return False

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "arm9.bin")
    apply_arm9_patch(target)
