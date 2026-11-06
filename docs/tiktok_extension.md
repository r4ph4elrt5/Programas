# TikTok com a extensão do MultiPost

A extensão é um painel auxiliar para Chrome ou Edge, conectado ao MultiPost que
está aberto no mesmo computador. Ela apresenta suas tarefas do TikTok, legenda,
caminho do vídeo e horário solicitado. Você pode copiar esses dados, abrir o
TikTok Studio e registrar depois que concluiu a publicação ou o agendamento.

A extensão não controla a página do TikTok: não injeta scripts, não seleciona
arquivos no site, não preenche os campos nem clica em Publicar/Agendar. Também
não lê cookies, senhas, tokens ou páginas da sua conta. O envio e a revisão no
Studio continuam sendo feitos por você.

## Por que o envio não é automatizado no navegador?

Os [termos oficiais do TikTok](https://www.tiktok.com/legal/page/row/terms-of-service/pt-BR)
proíbem “usar scripts automatizados para colher informações dos Serviços ou de
outra forma interagir com os Serviços”. Portanto, encontrar o botão na página
não demonstra autorização para automatizá-lo. O painel auxiliar não é uma
integração certificada pelo TikTok e não garante ausência de penalidades.

Para publicação automática, o caminho é uma integração oficial elegível e
autorizada. As [diretrizes de Direct Post](https://developers.tiktok.com/doc/content-sharing-guidelines/)
não aceitam presumir elegibilidade para ferramentas destinadas apenas às contas
do próprio desenvolvedor ou da equipe. Esta extensão não contorna essa exigência.

## 1. Atualizar o MultiPost no Windows

Feche o aplicativo. Se você instalou na pasta `MultiPost-Desktop`, abra o
PowerShell nessa pasta e execute:

```powershell
git status --short
git pull --ff-only
if ($LASTEXITCODE -ne 0) { throw "A atualização parou. Preserve os arquivos e confira a mensagem do Git." }
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
if ($LASTEXITCODE -ne 0) { throw "A instalação parou. Confira a mensagem acima." }
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1
```

Os comandos pressupõem que você está na branch `codex/multipost-desktop`.
Se `git status` indicar alterações suas, preserve-as antes de atualizar.
Não apague arquivos nem force a troca de branch para resolver um conflito.
O instalador prepara as dependências da ponte local; Python 3.12 e FFmpeg
continuam necessários.

## 2. Instalar a extensão

1. No Chrome, abra `chrome://extensions`; no Edge, `edge://extensions`.
2. Ative o **Modo do desenvolvedor**.
3. Escolha **Carregar sem compactação** e selecione a pasta `extension` dentro
   do repositório. Se recebeu um ZIP, extraia-o antes e escolha essa pasta.
4. Abra a extensão MultiPost pelo botão de extensões do navegador.

O painel pede acesso apenas à ponte local em `127.0.0.1:8765`, ao armazenamento
da própria extensão, ao painel lateral e à cópia para a área de transferência.
Não conceda acesso às páginas do TikTok: essa permissão não faz parte do projeto.

## 3. Conectar ao aplicativo

1. No MultiPost, vá a **Configurações → Extensão TikTok**.
2. Clique em **Ativar ponte**. Um código aparece apenas nessa seção.
3. Digite o código no painel da extensão e clique em conectar.

O código vale por cinco minutos. Se expirar, use **Novo código**. Não envie o
código ao chat, ao TikTok ou a terceiros. Ele é apenas para parear a extensão
local; não é uma senha da sua conta. Ao fechar o aplicativo ou desligar a ponte,
a extensão perde o acesso. Pode ser necessário parear novamente depois.

A ponte só escuta em `127.0.0.1:8765`. Não exponha essa porta à internet, não use
túneis e não abra uma segunda instância com o mesmo banco. Caso já tenha iniciado
`python -m multipost --api`, encerre essa API antes de ativar a ponte da interface.
O pareamento não utiliza o arquivo `api-key` da API genérica.

## 4. Preparar e concluir uma postagem

1. No MultiPost, importe o vídeo, escreva a legenda e selecione **TikTok**.
   Crie a tarefa. Aguarde o estado **Aguardando publicação manual**.
2. No painel da extensão, escolha essa tarefa. Copie a legenda e o caminho do
   vídeo e abra o **TikTok Studio**. Entre na sua conta pelo site oficial.
3. No Studio, clique em selecionar vídeo. Na janela do Windows, você pode colar
   o caminho copiado no campo **Nome**. Cole a legenda no campo de descrição e
   revise capa, audiência, direitos autorais e marcação de IA quando aplicável.
4. Aguarde upload e verificações. Publique ou configure o agendamento no próprio
   Studio e confira o resultado no site. Só então registre na extensão que você
   publicou ou agendou. Inclua o link quando disponível.

Não confirme apenas porque apareceu “Enviado”. Isso indica que o arquivo chegou
ao serviço, não que o vídeo foi publicado ou agendado. Um progresso de 100% e um
botão habilitado também não comprovam a conclusão. Os avisos e verificações do
Studio continuam valendo. Na tela enviada pelo usuário, o TikTok exigia ao menos
15 minutos de antecedência para aquele agendamento; siga o limite que o site
mostrar para sua conta, sem tentar desativar avisos ou forçar botões.

## Horários e histórico

O agendamento local do MultiPost é o horário em que o pacote assistido será
preparado. Ele não cria um agendamento remoto no TikTok.

Quando você declarar que agendou no Studio, o histórico mostrará **Agendamento
declarado pelo usuário**, com a data escolhida. Esse registro é separado de
**Publicação declarada pelo usuário** e de uma confirmação recebida por API.
O MultiPost não verificou a publicação futura só porque você registrou um
agendamento. Confira o fuso horário e os agendamentos no TikTok Studio.
Depois que você conferir a publicação no TikTok, pode registrar uma nova
confirmação manual de publicação para essa tarefa. A passagem do horário,
sozinha, não muda o registro para publicado.

## Análise opcional do HTML copiado

O painel pode analisar um trecho de HTML que você mesmo cole nele. A análise é
local, não abre a página da conta e não executa os scripts do conteúdo colado.
Ela ajuda a distinguir upload em andamento, arquivo enviado e verificações.

Alguns trechos do Studio incluem vários estados simultaneamente, com os estados
inativos marcados por `data-show="false"`. A análise considera apenas os estados
ativos. O resultado continua **sem confirmação de publicação**: não é prova de
que o TikTok publicou ou agendou o vídeo. Não cole cookies, tokens ou logs de
requisições no painel nem os compartilhe.

## Problemas comuns

- **Ponte não conecta:** mantenha o MultiPost aberto, ative a ponte e confira se
  outro processo está usando a porta 8765.
- **Código recusado:** gere outro em Configurações e digite no painel local.
- **Tarefa não aparece:** confira se o destino é TikTok e aguarde o preparo do
  pacote. Atualize a lista da extensão.
- **Arquivo movido:** localize-o novamente na biblioteca do aplicativo ou abra
  o pacote exportado. Não escolha um vídeo diferente sem revisar a tarefa.
- **Botão Agendar desabilitado:** confira as mensagens e verificações no Studio.
  A extensão não altera nem ignora esses bloqueios.
