# MultiPost Desktop

Um vídeo, cinco destinos: YouTube Shorts, Instagram Reels, Facebook Reels,
TikTok e Kwai. Aplicativo desktop em português, com Python 3.12,
CustomTkinter, FFmpeg e banco SQLite local.

O MultiPost prepara cada publicação e acompanha seu resultado individual.
A publicação automática usa somente uma integração oficial autorizada.

| Destino | Fluxo desta versão |
| --- | --- |
| YouTube | OAuth oficial e upload retomável pela YouTube Data API; exige configuração do Google Cloud e autorização do canal. |
| Instagram | Pacote assistido para a conta pessoal: vídeo, legenda e instruções para concluir no aplicativo/site oficial. |
| Facebook | Pacote assistido para o perfil pessoal. A API de Páginas não autoriza publicar no perfil pessoal. |
| TikTok | Pacote assistido. Publicação direta exige acesso e aprovação adequados para a Content Posting API. |
| Kwai | Pacote assistido. Não se presume acesso a uma API de publicação para contas brasileiras. |

Preparar um pacote não publica o vídeo. Uma confirmação feita por você é
identificada separadamente de uma confirmação recebida da API. O aplicativo
não promete que um conteúdo será aprovado, classificado como Short ou livre de
penalidades: conteúdo, conta e permissões continuam sujeitos às regras do destino.

## Abrir no Windows

1. Instale [Python 3.12](https://www.python.org/downloads/) e
   [FFmpeg](https://ffmpeg.org/download.html), com `ffmpeg` e `ffprobe` no PATH.
2. Abra o PowerShell na pasta deste repositório e execute:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1
   ```

   `Bypass` vale somente para esse processo do PowerShell; não altera a política
   permanente do computador. Inspecione os scripts antes de executá-los.

Veja o [guia de instalação](docs/installation.md) para detalhes e solução de problemas.

## Primeiro uso

Importe um vídeo, confira os metadados, escreva a legenda e escolha os cinco
destinos. Revise as opções de privacidade e a declaração sobre conteúdo infantil
para o YouTube. Crie as tarefas somente quando quiser iniciar o fluxo.
Nos quatro destinos assistidos, abra a pasta exportada, copie a legenda e conclua
a publicação no serviço oficial. Depois registre a confirmação e, se disponível,
o link.

Para o YouTube, siga a [configuração OAuth](docs/youtube_setup.md) antes de enviar.
Credenciais e permissões reais não acompanham o projeto. Testes simulados não
comprovam acesso à sua conta ou publicação real.

## Desenvolvimento e validação

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m multipost --diagnostics
```

Os testes não publicam em redes sociais. As integrações externas são exercitadas
com respostas simuladas; testes de mídia usam FFmpeg local. Consulte o relatório
de validação entregue com o desenvolvimento para os resultados efetivamente executados.

## Dados e agendamentos

No Windows, os arquivos persistentes ficam em `%LOCALAPPDATA%\MultiPost`.
Tokens OAuth ficam no cofre de credenciais do sistema, nunca no Git ou nos logs.
Faça backup do diretório de dados com o aplicativo fechado e proteja o backup.
O cofre de credenciais não faz parte desse backup; uma nova máquina pode exigir reconexão.

O agendamento exige o aplicativo aberto e o computador ligado. Tarefas vencidas
encontradas após uma interrupção precisam de revisão; um envio com resultado
remoto desconhecido não é reenviado automaticamente.

## Documentação

- [Instalação](docs/installation.md)
- [Guia de uso](docs/user_guide.md)
- [Conectar YouTube](docs/youtube_setup.md)
- [Arquitetura](docs/architecture.md)
- [Problemas comuns](docs/troubleshooting.md)
- [Regras e fontes das plataformas](docs/platforms.md)
- [API local opcional](docs/api.md)
- [Extensão auxiliar do TikTok](docs/tiktok_extension.md)

## Executável Windows

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build.ps1
```

O build deve ser feito no Windows. A saída é `dist\MultiPost\MultiPost.exe`
com os arquivos ao redor; distribua a pasta inteira. FFmpeg e ffprobe precisam
estar instalados no computador de destino. A existência do script não comprova
que um executável foi gerado ou testado no Windows.

Licença [MIT](LICENSE).
