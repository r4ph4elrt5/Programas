# API local opcional

A API permite integrar outro programa local ao mesmo fluxo de importação,
fila e confirmação do aplicativo. Ela não oferece uma API própria de Instagram,
Facebook, TikTok ou Kwai e não remove exigências de aprovação desses serviços.

## Instalar e iniciar

No PowerShell, dentro da pasta do projeto já preparada:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[api]"
.\.venv\Scripts\python.exe -m multipost --api
```

O servidor escuta somente `127.0.0.1:8765`. Execute a interface e a API
alternadamente, usando o mesmo diretório de dados: não inicie dois gerenciadores
da mesma fila. Não exponha essa porta por roteador, túnel, proxy ou servidor público.
A API não é um serviço hospedado e não permanece ativa quando o processo termina.

## Autorizar um cliente local

Na primeira inicialização da API, uma credencial é criada no arquivo
`%LOCALAPPDATA%\MultiPost\api-key`. O arquivo fica no diretório de dados escolhido
quando você usa `--data-dir` ou `MULTIPOST_DATA_DIR`.

O cliente deve ler a credencial localmente e enviar o cabeçalho
`Authorization: Bearer <credencial-local>` em todas as requisições.
O servidor não retorna o token pela API e não o imprime. Não envie esse arquivo
ao GitHub, ao chat ou a terceiros. No Windows, proteja o diretório de dados com
as permissões da sua conta; uma credencial é suficiente para controlar a fila.

Exemplo de consulta somente de leitura no PowerShell, sem imprimir a credencial:

```powershell
$dataDirectory = Join-Path $env:LOCALAPPDATA "MultiPost"
$apiCredential = (Get-Content -LiteralPath (Join-Path $dataDirectory "api-key") -Raw).Trim()
$requestHeaders = @{ Authorization = "Bearer $apiCredential" }
Invoke-RestMethod -Uri "http://127.0.0.1:8765/health" -Headers $requestHeaders
Remove-Variable apiCredential, requestHeaders
```

HTTP em loopback é usado somente na máquina local. Não substitua o endereço
por um host remoto. O servidor não habilita CORS para páginas externas.

## Rotas

Todas as rotas exigem autorização. Os corpos de requisição usam JSON.

| Método e rota | Uso e corpo |
| --- | --- |
| `GET /health` | Versão e capacidades declaradas. Não comprova autorização remota do YouTube. |
| `GET /videos` | Vídeos importados e metadados. |
| `POST /videos` | Importa um arquivo existente no computador do servidor: `{"path":"C:\\Videos\\meu-video.mp4"}`. |
| `GET /jobs` | Estado atual das tarefas. |
| `POST /jobs` | Cria tarefas depois de autorização explícita; campos abaixo. |
| `POST /jobs/{id}/cancel` | Solicita cancelamento local. |
| `POST /jobs/{id}/retry` | Autoriza retentativa quando o estado permite; resultados ambíguos são bloqueados. |
| `POST /jobs/{id}/confirm` | Confirmação declarada de publicação assistida: `{"url":"https://..."}` ou `{"url":""}`. |
| `POST /jobs/{id}/reconcile` | Consulta um envio YouTube conhecido; corpo `{"remote_id":null}` ou ID encontrado por você no YouTube Studio. |
| `POST /queue/pause` | Pausa/retoma a fila: `{"paused":true}` ou `{"paused":false}`. |
| `GET /draft` | Carrega o rascunho. |
| `PUT /draft` | Salva um objeto JSON de rascunho, limitado a 100 KB. |

## Criar tarefas

Uma chamada `POST /jobs` autoriza o processamento da publicação, inclusive o
envio real ao YouTube quando ele está selecionado e conectado. Peça a confirmação
do usuário do seu cliente antes de enviar esta chamada. `approved` deve ser
o booleano `true`; o servidor recusa sua ausência ou `false`.

Exemplo de corpo para um vídeo já importado:

```json
{
  "video_id": "ID_RETORNADO_PELA_IMPORTACAO",
  "title": "Meu vídeo",
  "caption": "Legenda geral #video",
  "platforms": ["youtube", "instagram", "facebook", "tiktok", "kwai"],
  "overrides": {"instagram": "Legenda para o Instagram"},
  "privacy": "private",
  "made_for_kids": false,
  "tags": ["video"],
  "category": "22",
  "scheduled_at": null,
  "approved": true
}
```

`made_for_kids` deve refletir sua decisão real sobre o conteúdo; não copie
automaticamente o valor do exemplo. `privacy` aceita `private`, `unlisted` ou
`public`. Para agendar, use `scheduled_at` em ISO 8601 com fuso, por exemplo
`2026-12-01T10:00:00-04:00`; confira o horário escolhido. A resposta contém
`job_ids` com uma tarefa por destino.

`tags` é uma lista opcional de até 50 textos; o conector também valida o limite
combinado de 500 caracteres do YouTube, incluindo separadores e aspas aplicáveis.
`category` é o identificador numérico da categoria YouTube como texto; o padrão
é `"22"` (Pessoas e blogs). Use uma categoria disponível para seu conteúdo e região.
Esses campos são metadados do YouTube e não alteram as legendas das outras redes.

Não envie tokens de redes sociais no corpo, nas legendas ou nos rascunhos.
O YouTube é conectado pela interface desktop antes de iniciar a API.

## Estados e recuperação

Um pacote assistido aguarda confirmação manual, sem publicação automática.
Um upload do YouTube pode continuar em processamento e precisa ser consultado
até que haja resultado conclusivo. Privado/não listado é distinto de público.

`retry` não deve ser usado em um upload com resultado remoto desconhecido.
Verifique o YouTube Studio e use reconciliação quando houver ID conhecido.
Tarefas que venceram mais de 60 segundos antes da retomada são marcadas para
revisão; a autorização de retentativa é uma ação explícita do usuário.

Respostas 401 indicam credencial local ausente/inválida. Respostas 400 indicam
uma operação ou estado inválido. Respostas 422 indicam campos inválidos.
Uma resposta 500 não confirma que uma operação remota deixou de acontecer:
consulte os estados antes de reenviar.
