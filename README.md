# Coraline (Nintendo DS) - Traducao em Portugues do Brasil (PT-BR)

[![Status: Em Desenvolvimento](https://img.shields.io/badge/Status-Em_Desenvolvimento-yellow.svg)](https://github.com/Kasszs/caraline-nds-ptbr)
[![Versao](https://img.shields.io/badge/Versao-0.8.0--beta-orange.svg)](https://github.com/Kasszs/caraline-nds-ptbr)
[![Progresso Geral](https://img.shields.io/badge/Progresso-85%25-blue.svg)](https://github.com/Kasszs/caraline-nds-ptbr)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)

Suite de traducao, localizacao e ferramentas de engenharia reversa para a versao de Nintendo DS do jogo Coraline.

> [!IMPORTANT]
> **Status do Projeto: Em Desenvolvimento Ativo (WIP)**  
> Este projeto encontra-se em estagio beta de desenvolvimento. O enredo principal, as rotinas do executavel e as ferramentas de suporte estao operacionais, mas a traducao das texturas secundarias e o playtesting integral in-game permanecem em andamento.

---

## Status do Projeto e Roadmap

| Componente | Progresso | Detalhes |
| :--- | :---: | :--- |
| **Roteiro e Dialogos** | 100% | Todos os 38 arquivos `eve_*.bin` traduzidos e auditados |
| **Patch ARM9 (UTF-8)** | 100% | Offset `0x0E04 = 0x01` para suporte a acentos da lingua portuguesa |
| **Menus e Sistema** | 100% | Telas de salvamento, menu de pausa e 54 personagens mapeados |
| **Overlays Binarios** | 100% | Nomes de itens (`overlay_0000.bin`) e minijogos (`overlay_0001.bin`) |
| **Ferramentas de Edicao** | 100% | `CoralineTextEditor` e `CoralineTextureTool` com interface grafica |
| **Texturas Graficas (NITRO 2D)** | 35% | Telas principais adaptadas; graficos contextuais pendentes |
| **Revisao In-Game (Playtesting)** | 50% | Validacao parcial em emuladores e console real |
| **Patch Distribuivel (XDelta)** | Pendente | Programado para a conclusao da etapa de revisao |

### Checklist de Implementacao

- [x] Engenharia reversa dos formatos de texto e analise de limites da caixa de dialogo (140 px, 3 linhas)
- [x] Traducao completa dos 38 arquivos de evento (`eve_*.bin`)
- [x] Implementacao da ativacao de decodificacao UTF-8 no executavel `arm9.bin`
- [x] Localizacao das strings do executavel (SALVAR, SAIR, ITENS, ROUPAS e 54 tags de personagens)
- [x] Correcao de posicionamento horizontal do botao SALVAR (X=128 px) para evitar sobreposicao
- [x] Traducao da tabela de itens em `overlay_0000.bin` e minijogos em `overlay_0001.bin`
- [x] Desenvolvimento do `CoralineTextEditor.py` com simulador de tela baseado na fonte real (`.NFTR`)
- [x] Desenvolvimento do `CoralineTextureTool.py` com suporte a formatos NITRO 2D e controle de zoom
- [x] Rotina automatizada de recompilacao da ROM via `ndstool` com preservacao de cabecalho (64 MB)
- [ ] Conclusao da adaptacao grafica das texturas restantes no diretorio `texturas_exportadas/`
- [ ] Playtesting integral de ponta a ponta para validacao de contexto, formatacao e estabilidade
- [ ] Geracao de patch no formato XDelta para aplicacao direta na ROM americana limpa

---

## Recursos das Ferramentas

### 1. CoralineTextEditor.py
- **Simulador Real NDS (256x192)**: Renderiza o texto caractere por caractere utilizando os glifos extraidos da fonte bitmap proprietaria (`coraline_font.NFTR`, 15x16 px, 3 bpp com antialiasing e sombra).
- **Medicao Geometrica em Pixels**: Alerta em tempo real sobre excesso de largura e quebras de linha que ultrapassem a area util da caixa de dialogo.
- **Referencia Canonica**: Exibicao paralela com o texto em ingles extraido da versao oficial americana limpa (`txt_backup_original`).
- **Edicao do Executavel ARM9**: Gerenciamento direto das 54 entradas mestre do executavel (menus, telas de salvamento e nomes de personagens), incluindo exportacao e importacao em lote via JSON.
- **Gerenciamento de Overlays**: Edicao dos arquivos `overlay_0000.bin` e `overlay_0001.bin`.
- **Patch Integrado**: Aplicacao do byte UTF-8 no executavel com verificacao de estado.
- **Recompilacao Integrada**: Execucao do `ndstool` com preservacao de cabecalho (offset `0x14 = 0x09`), assegurando compatibilidade com emuladores e flashcards.

### 2. CoralineTextureTool.py
- **Formatos Suportados**: `.NCGR`, `.NCBR` (graficos em tiles), `.NCLR` (paletas de cores de 16 e 256 cores) e `.NSCR` (telas e tilemaps).
- **Fluxo de Trabalho**: Exportacao das texturas para `texturas_exportadas/` e reinjecao automatizada a partir de arquivos PNG editados com geracao de backup.
- **Interface com Zoom**: Visualizacao de 1x a 4x com fundo xadrez para transparencia.
- **Modo CLI**: Execucao por linha de comando para automacoes e scripts externos.

---

## Estrutura do Repositorio

```text
caraline-nds-ptbr/
├── CoralineTextEditor.py       # Aplicacao principal de edicao de textos
├── CoralineTextureTool.py      # Aplicacao de gerenciamento e conversao de texturas
├── Iniciar_Editor_Coraline.bat # Atalho de inicializacao do editor de textos
├── Iniciar_Editor_Texturas.bat # Atalho de inicializacao do editor de texturas
├── patch_arm9.py               # Script para aplicacao da correcao UTF-8 no executavel
├── aplicar_traducao.py         # Script para injecao dos arquivos traduzidos na ROM
├── requirements.txt            # Dependencias do ambiente Python
├── data/
│   └── data/
│       ├── coraline_font.NFTR      # Arquivo de fonte principal do jogo
│       ├── coraline_font2.NFTR     # Arquivo de fonte secundaria
│       ├── txt/                    # Arquivos eve_*.bin traduzidos
│       │   └── auditoria_caixa_pixels.txt
│       ├── txt_backup_original/    # Arquivos originais em ingles para comparacao
│       ├── txt_json_dumps/         # Estrutura dos textos e strings do ARM9 em JSON
│       └── info/
│           └── touchthescreen.NCGR # Textura compilada no formato do console
├── overlay/
│   ├── overlay_0000.bin           # Nomes de itens traduzidos
│   └── overlay_0001.bin           # Textos de minijogos traduzidos
├── texturas_exportadas/
│   ├── touchthescreen.png         # Textura traduzida em formato PNG
│   └── touchthescreen.meta.json   # Metadados de paleta e dimensoes
└── docs/
    └── index.html                 # Pagina informativa e documentacao web
```

---

## Instrucoes de Execucao

### Pre-requisitos
- Python versao 3.8 ou superior.
- Instalacao das dependencias necessarias:
  ```bash
  pip install -r requirements.txt
  ```

### Utilizacao dos Editores
No ambiente Windows, utilize os atalhos:
- `Iniciar_Editor_Coraline.bat` para o editor de textos.
- `Iniciar_Editor_Texturas.bat` para o editor de texturas.

Via terminal:
```bash
python CoralineTextEditor.py
python CoralineTextureTool.py
```

### Insercao da Traducao na ROM
Para injetar as modificacoes em uma pasta contendo os arquivos extraidos da ROM original (via dslazy ou ndstool):
```bash
python aplicar_traducao.py [caminho_da_pasta_descompactada]
```
O script atualizara os arquivos de dialogo, modulos de overlay, texturas e as strings do executavel `arm9.bin`. Apos a conclusao, a ROM pode ser reconstruida.
