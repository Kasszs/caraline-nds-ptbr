# 🗝️ Coraline (Nintendo DS) — Tradução em Português do Brasil (PT-BR)

> **Projeto de Tradução, Localização e Ferramentas de Engenharia Reversa para o jogo *Coraline* do Nintendo DS.**

---

## 🌟 Sobre o Projeto

Bem-vindo ao projeto de tradução e localização de **Coraline** para o **Nintendo DS** em Português do Brasil!

Este repositório reúne tudo o que é essencial para traduzir, revisar e jogar a história de Coraline na nossa língua:
- 📝 **Todos os textos de diálogos e salas** (`eve_*.bin`) traduzidos e revisados com fidelidade à obra e ao tom original.
- 🎒 **Menus, itens e minijogos** traduzidos diretamente nos arquivos de overlay da ROM.
- 🎨 **Texturas gráficas em português** (como a tela de toque *"Toque na tela"*).
- 🛠️ **Suíte de Ferramentas Exclusivas** desenvolvidas em Python (com interface visual) para editar textos, simular a tela do DS e injetar texturas sem depender de editores hexadecimais complexos.

---

## ☕ Como Funciona por Dentro (Explicado de Forma Bem Humana)

Se você já se perguntou como um jogo de videogame antigo guarda suas falas e como uma tradução é colocada dentro dele, aqui está o segredo dos bastidores:

### 1. Onde as falas ficam guardadas?
Dentro da ROM do Nintendo DS existe uma estrutura de pastas (assim como no seu computador). Na pasta `data/data/txt/`, existem cerca de 38 arquivos que começam com o nome `eve_` (abreviação de *event* ou evento).
- Cada cômodo da casa (o banheiro, a sala da Outra Mãe, o jardim, o poço) tem seu próprio arquivo (ex: `eve_living01.bin`, `eve_bathroom01.bin`).
- Dentro de cada arquivo, as falas de cada personagem ficam organizadas em blocos com 6 idiomas lado a lado (Japonês, Inglês, Francês, Alemão, Espanhol e Italiano).
- Nós usamos o slot do **Inglês (EN)** para colocar o nosso Português!

### 2. O mistério dos acentos sumidos (e o "Pulo do Gato" no ARM9)
No início, quando tentávamos escrever palavras normais da nossa língua como *você*, *não*, *coração* ou *botão*, o jogo enlouquecia na tela: apareciam letras japonesas embaralhadas como `ﾃｩ` ou o jogo simplesmente travava!

**Por que isso acontecia?**  
No Nintendo DS, o executável principal (`arm9.bin`) foi programado para achar que o inglês usava apenas caracteres básicos. Qualquer código diferente fazia ele tentar ler como texto em japonês.

**Como resolvemos:**  
Descobrimos que modificando um único bytezinho no endereço de memória `0x0E04` do `arm9.bin` (trocando o valor `0x02` por `0x01`), o jogo "acorda" e ativa a leitura em **UTF-8**, puxando a fonte europeia oficial (`coraline_font.NFTR`) que já estava adormecida dentro do jogo. Com isso, **todos os nossos acentos (á, é, í, ó, ú, ã, õ, ç) passaram a funcionar com perfeição pixel a pixel!**

### 3. A telinha do Nintendo DS e o perigo do texto vazar
A tela do Nintendo DS tem apenas **256 pixels de largura por 192 de altura**. A caixa de diálogo do Coraline foi desenhada para comportar frases de no máximo **140 pixels de largura** e até **3 linhas** por vez.
- Se uma frase em português ficar comprida demais, a última palavra sai da tela ou é cortada.
- Para evitar isso sem ter que abrir o jogo mil vezes no emulador, criamos o **CoralineTextEditor**: ele desenha na tela do seu computador uma réplica exata da telinha do DS, com a mesma fonte do jogo, e avisa na hora se a frase coube ou se estourou a margem!

### 4. Itens e Minijogos (Os arquivos de Overlay)
Para economizar a pouca memória RAM do portátil (apenas 4 megabytes!), o jogo não carrega tudo de uma vez. Ele usa pequenos módulos chamados *overlays*:
- `overlay_0000.bin`: Guarda a tabela de nomes de todos os itens do inventário (chave de botão, pedra furada, etc.).
- `overlay_0001.bin`: Guarda os títulos e instruções dos minijogos.
Nossa ferramenta edita e atualiza esses textos sem alterar os ponteiros de memória!

### 5. As Imagens e Texturas (Formato Nitro 2D)
Nem tudo é texto puro: avisos como *"Touch the Screen"* ou botões são imagens. No DS, elas usam o formato NITRO (`.NCGR` para pixels, `.NCLR` para a paleta de cores de 16 ou 256 cores, e `.NSCR` para a grade da tela).
- Nossa ferramenta `CoralineTextureTool.py` converte esses arquivos em imagens PNG transparentes que qualquer um pode editar no Photoshop ou Paint.NET, e depois injeta de volta na ROM sem perder qualidade.

---

## 🗂️ Estrutura Deste Repositório

Fizemos uma curadoria minuciosa em relação aos arquivos brutos da ROM para manter apenas o que realmente pertence e importa para a tradução:

```text
caraline-nds-ptbr/
│
├── 📜 CoralineTextEditor.py       # Editor visual completo de diálogos com simulador de tela DS
├── 🎨 CoralineTextureTool.py      # Extrator e injetor de texturas 2D (NCGR/NCLR para PNG)
├── ⚡ patch_arm9.py               # Script para aplicar o patch de acentuação UTF-8 no executável
├── 🚀 aplicar_traducao.py         # Script para injetar toda a tradução numa pasta da ROM
├── ⚙️ Iniciar_Editor_Coraline.bat # Atalho de 2 cliques para iniciar o editor no Windows
├── 📋 requirements.txt            # Dependências Python (Pillow)
│
├── 📂 data/data/
│   ├── 🔤 coraline_font.NFTR      # Fonte oficial do jogo (usada pelo simulador para cálculo de pixels)
│   ├── 🔤 coraline_font2.NFTR     # Fonte estendida original
│   ├── 💬 txt/                    # Os 38 arquivos eve_*.bin traduzidos em PT-BR
│   │   └── auditoria_caixa_pixels.txt # Relatório de verificação de limites das caixas
│   ├── 📚 txt_backup_original/    # Arquivos originais em inglês para comparação e referência
│   ├── 🗂️ txt_json_dumps/         # Dumps em JSON organizados de todos os diálogos
│   └── 🖼️ info/
│       └── touchthescreen.NCGR    # Textura modificada em formato do Nintendo DS
│
├── 📂 overlay/
│   ├── overlay_0000.bin           # Nomes de itens do inventário em PT-BR
│   └── overlay_0001.bin           # Nomes e textos dos minijogos em PT-BR
│
├── 📂 texturas_exportadas/
│   ├── touchthescreen.png         # Textura traduzida em PNG ("Toque na tela")
│   └── touchthescreen.meta.json   # Metadados de paleta e dimensões para reinjeção
│
└── 🌐 docs/
    └── index.html                 # Página web oficial do projeto
```

---

## 🚀 Como Usar e Testar

### Pré-requisitos
- **Python 3.8+** instalado.
- Instale as bibliotecas necessárias:
  ```bash
  pip install -r requirements.txt
  ```

### 1. Abrir o Editor de Textos
Basta dar dois cliques no arquivo `Iniciar_Editor_Coraline.bat` ou executar:
```bash
python CoralineTextEditor.py
```
- Você verá a lista de arquivos `eve_*.bin` à esquerda.
- O diálogo original em inglês e a tradução em português ao lado.
- A tela simulada do Nintendo DS renderizando exatamente com a fonte do jogo!

### 2. Aplicar a Tradução em uma ROM
Se você tem uma pasta descompactada da ROM (feita com o dslazy ou ndstool):
```bash
python aplicar_traducao.py C:\caminho\para\NDS_UNPACK
```
O script cuidará de:
1. Copiar todos os 38 arquivos `eve_*.bin` para a pasta correta.
2. Atualizar os overlays com itens e minijogos.
3. Injetar as texturas traduzidas.
4. Aplicar automaticamente o patch UTF-8 no `arm9.bin`.

Depois, basta recompilar a ROM usando o **dslazy** ou **ndstool** e jogar no seu emulador favorito (DeSmuME, MelonDS) ou em um flashcard no Nintendo DS real!

---

## 👥 Contribuição e Créditos

- **Engenharia Reversa & Ferramentas:** Ferramentas customizadas desenvolvidas especialmente para a arquitetura de arquivos do Coraline NDS.
- **Tradução & Revisão:** Comunidade brasileira de ROMhacking e fãs de Coraline.

Sinta-se à vontade para abrir uma *Issue* ou enviar um *Pull Request* com correções de diálogos, melhorias nas texturas ou sugestões!
