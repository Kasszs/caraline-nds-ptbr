# Coraline (Nintendo DS) - Traducao em Portugues do Brasil (PT-BR)

Projeto de traducao, localizacao e desenvolvimento de ferramentas para a versao de Nintendo DS do jogo Coraline.

---

## Visao Geral

Este repositorio contem os dados, arquivos traduzidos e ferramentas necessarias para a localizacao de Coraline (Nintendo DS) em Portugues do Brasil:

- Arquivos de dialogos e eventos (arquivos eve_*.bin) traduzidos.
- Nomes de itens e minijogos adaptados nos modulos de overlay.
- Texturas graficas adaptadas para o idioma portugues.
- Ferramentas desenvolvidas em Python para edicao de textos, simulacao de renderizacao na resolucao nativa do console e conversao de texturas.

---

## Funcionamento Tecnico do Jogo e da Traducao

### 1. Estrutura dos Arquivos de Dialogo (eve_*.bin)
A ROM do jogo organiza os textos dos eventos em 38 arquivos com prefixo `eve_` localizados no diretorio `data/data/txt/`.
Cada arquivo corresponde a uma area ou evento especifico (como `eve_living01.bin` ou `eve_bathroom01.bin`).
Internamente, os dialogos estao organizados em blocos contendo seis faixas de idioma: Japones, Ingles, Frances, Alemao, Espanhol e Italiano. Este projeto utiliza a faixa correspondente ao idioma ingles para a insercao dos textos traduzidos em portugues.

### 2. Decodificacao de Caracteres e Modificacao no Executavel ARM9
Originalmente, a rotina de decodificacao de texto associada ao idioma ingles no executavel principal (`arm9.bin`) nao suportava caracteres acentuados. A insercao de caracteres da codificacao UTF-8 resultava em falhas de renderizacao ou no encerramento inesperado do jogo.

A alteracao do byte localizado no offset `0x0E04` do valor `0x02` para `0x01` modifica a rotina de tratamento de texto. Com essa alteracao, o executavel passa a utilizar o decodificador UTF-8 compativel com a fonte europeia (`coraline_font.NFTR`), permitindo a exibicao correta de todos os caracteres acentuados da lingua portuguesa (a, e, i, o, u, c e respectivas variacoes).

### 3. Restricoes de Resolucao e Limites da Caixa de Texto
A resolucao de tela do Nintendo DS e de 256 por 192 pixels. No jogo, a area util da caixa de dialogo comporta textos com largura maxima de 140 pixels e ate tres linhas por exibicao.
Textos que excedem esses limites sao truncados ou exibidos de forma incorreta. A ferramenta `CoralineTextEditor` utiliza as metricas da fonte original para simular a caixa de dialogo em tempo real, indicando se a largura das linhas esta em conformidade com os limites do jogo.

### 4. Modulos de Overlay (overlay_*.bin)
Para otimizar o uso da memoria RAM do console, partes do codigo e tabelas de texto sao carregadas dinamicamente em modulos de overlay:
- `overlay_0000.bin`: Armazena a tabela de identificadores e nomes dos itens do inventario.
- `overlay_0001.bin`: Armazena os textos e titulos relativos aos minijogos.

### 5. Graficos e Texturas (Formato NITRO 2D)
Elementos visuais de interface utilizam os formatos padrao da arquitetura NITRO da Nintendo:
- `.NCGR`: Dados graficos dos blocos de pixels.
- `.NCLR`: Tabelas de paleta de cores.
- `.NSCR`: Mapas de posicionamento de tiles na tela.

A ferramenta `CoralineTextureTool.py` converte esses arquivos para o formato PNG preservando as informacoes de paleta, permitindo a edicao grafica externa e a posterior reinjecao no formato original da ROM.

---

## Estrutura do Repositorio

```text
caraline-nds-ptbr/
├── CoralineTextEditor.py       # Editor de dialogos com simulador de tela
├── CoralineTextureTool.py      # Utilitario de extracao e reinjecao de texturas
├── patch_arm9.py               # Script para aplicacao da correcao UTF-8 no executavel
├── aplicar_traducao.py         # Script para insercao dos arquivos na pasta da ROM
├── Iniciar_Editor_Coraline.bat # Script de inicializacao no Windows
├── requirements.txt            # Dependencias do ambiente Python
├── data/
│   └── data/
│       ├── coraline_font.NFTR      # Arquivo de fonte principal do jogo
│       ├── coraline_font2.NFTR     # Arquivo de fonte secundaria
│       ├── txt/                    # Arquivos eve_*.bin traduzidos
│       ├── txt_backup_original/    # Arquivos eve_*.bin originais para comparacao
│       ├── txt_json_dumps/         # Estrutura dos textos exportada em formato JSON
│       └── info/
│           └── touchthescreen.NCGR # Textura modificada no formato do console
├── overlay/
│   ├── overlay_0000.bin           # Nomes de itens traduzidos
│   └── overlay_0001.bin           # Textos de minijogos traduzidos
├── texturas_exportadas/
│   ├── touchthescreen.png         # Textura traduzida em formato PNG
│   └── touchthescreen.meta.json   # Metadados de paleta e dimensoes
└── docs/
    └── index.html                 # Pagina informativa do projeto
```

---

## Instrucoes de Uso

### Requisitos
- Python versao 3.8 ou superior.
- Instalacao das dependencias:
  ```bash
  pip install -r requirements.txt
  ```

### Edicao de Textos
Para iniciar o editor grafico de textos:
```bash
python CoralineTextEditor.py
```

### Aplicacao da Traducao na ROM
Para inserir os arquivos modificados em uma pasta contendo os arquivos extraidos da ROM (via dslazy ou ndstool):
```bash
python aplicar_traducao.py [caminho_da_pasta_descompactada]
```
O script executa as seguintes etapas:
1. Copia dos arquivos `eve_*.bin` para `data/data/txt/`.
2. Atualizacao dos arquivos `overlay_0000.bin` e `overlay_0001.bin`.
3. Insercao das texturas modificadas.
4. Verificacao e aplicacao da correcao de acentuacao UTF-8 no arquivo `arm9.bin`.

Apos a execucao, a ROM pode ser reconstruida utilizando o software correspondente.
