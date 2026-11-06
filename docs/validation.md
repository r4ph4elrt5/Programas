# Relatório de validação

Ambiente: Linux, Python 3.12.14; desenvolvimento em 6 de novembro de 2026.

## Fluxos exercitados

- Vídeos reais gerados com FFmpeg, incluindo caminhos com espaços e caracteres acentuados.
- Inspeção ffprobe, miniatura, conversão vertical, preservação do original e cancelamento.
- Banco SQLite, persistência após reinício, backup consistente, fila e agendamento.
- Um vídeo gerando cinco tarefas; YouTube com respostas simuladas e quatro pacotes assistidos reais.
- Confirmação manual distinta de confirmação da API, URLs validadas e proteção contra duplicação.
- Falha de rede/resultado remoto incerto, falha de persistência após upload, recuperação de interrupções.
- Concorrência entre início, cancelamento, nova tentativa e reagendamento.
- Interface sob display virtual Xvfb: navegação nas nove telas, rascunhos, seleção de vídeo convertido,
  criação de tarefa e exportação assistida. Temas claro/escuro inspecionados em 1280×860 e 980×680.
- API FastAPI com autenticação, consentimento explícito e encerramento cancelável.
- API em processo real via HTTP local: importação de vídeo e quatro tarefas chegando a `WAITING_USER`;
  arquivos de vídeo e legenda conferidos. Requisição sem autenticação recusada com HTTP 401.

## Comandos

```bash
DISPLAY=:97 .venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/python -m compileall -q src tests
DISPLAY=:97 .venv/bin/python -m multipost --smoke-test
.venv/bin/python -m multipost --diagnostics --data-dir /tmp/multipost-final-diagnostics
.venv/bin/python -m PyInstaller --noconfirm multipost.spec
DISPLAY=:97 dist/MultiPost/MultiPost --smoke-test
dist/MultiPost/MultiPost --diagnostics --data-dir /tmp/multipost-final-packaged
```

O display `:97` foi criado apenas para os testes. No Windows, execute os comandos
equivalentes com `.venv\Scripts\python.exe`, sem `DISPLAY`.
Testes de API/display precisaram de execução fora do sandbox restrito a sockets;
isso não alterou as verificações de autenticação, TLS ou integridade das dependências.

Resultado da suíte: **79 testes passaram**, sem testes ignorados na execução com display.
Ruff, imports/compilação, diagnóstico, navegação e build PyInstaller Linux passaram.
Há um aviso de descontinuação de `httpx` no TestClient do Starlette; os testes não falharam.
As fontes do display virtual usaram fallback no Linux; o empacotamento Windows inclui os recursos CustomTkinter.

## Limitações verificáveis

- OAuth e upload YouTube foram testados com mocks, sem credenciais reais. Não comprovam acesso a um canal.
- Nenhuma publicação real, pública ou privada, foi feita durante o desenvolvimento.
- Instagram, Facebook, TikTok e Kwai são assistidos, sem postagem automática.
- Pacote PyInstaller gerado/testado aqui é Linux. Não é um executável Windows.
- Scripts PowerShell e build Windows foram preparados, mas não executados neste ambiente.
- A CI foi configurada; sua existência não significa que já executou ou produziu artefatos Windows.
- Publicação de conteúdo, classificação Shorts e ausência de penalidades dependem das plataformas,
  da conta e dos direitos sobre o vídeo e a música.

## Atualização 0.2 — extensão TikTok

Comandos adicionais executados:

```bash
DISPLAY=:98 .venv/bin/python -m pytest -q
.venv/bin/ruff check .
npm --prefix extension test
node --check extension/panel.mjs
node --check extension/background.mjs
```

Resultado atualizado: **94 testes Python passaram**, sem testes ignorados, e
**32 testes JavaScript passaram**. Ruff, compilação/imports e sintaxe dos módulos
JavaScript passaram. O aviso de descontinuação do TestClient continua sem causar falhas.

Os testes novos exercitam o servidor local da ponte, consumo único e expiração
do código, limite de tentativas, isolamento por extensão, rejeição de origens
web e de outras plataformas, revogação, encerramento sem fechar o aplicativo,
persistência de agendamento declarado e confirmação manual posterior de publicação.
Os testes gráficos cobrem os controles de pareamento e a ordem de encerramento.
O cliente JavaScript real da extensão também foi executado em Node contra a
ponte Python por HTTP local: pareamento, isolamento das tarefas, declaração de
agendamento, confirmação manual posterior e revogação passaram. Esse teste não
substitui a validação do painel no navegador.

Os testes JavaScript exercitam o cliente da ponte e o analisador de HTML offline,
incluindo estados ocultos, avisos, carregamento, botão desabilitado, HTML inerte
e proibição de inferir publicação a partir do upload. Não testam uma conta TikTok.

A instalação real da extensão neste Chromium foi impedida pela política
administrativa `ExtensionInstallBlocklist: ["*"]` existente na máquina.
Essa política não foi alterada ou contornada. A instalação e a interação da
extensão no Chrome/Edge Windows ainda precisam de validação no computador do usuário.
Não foi realizado nenhum upload nem agendamento real no TikTok.
