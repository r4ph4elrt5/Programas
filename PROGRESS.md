# MultiPost Desktop — estado da implementação

## Implementado

- Aplicativo desktop em português com nove seções, temas claro/escuro e rascunho persistente.
- Importação de múltiplos vídeos, metadados, hash, miniaturas e localização de arquivo movido.
- Conversão FFmpeg H.264/AAC vertical com margens ou corte central, progresso e cancelamento.
- Legenda geral e personalização por destino; privacidade, público infantil, tags e categoria YouTube.
- Cinco tarefas independentes por vídeo, SQLite/SQLAlchemy, auditoria, tentativas, pausa e histórico.
- Agendamento local persistente, reagendamento e revisão de horários perdidos.
- Exportação assistida real para Instagram, Facebook, TikTok e Kwai; cópia de legenda e confirmação declarada.
- Conector YouTube com OAuth desktop, cofre nativo, upload retomável e consulta do processamento.
- Bloqueio de reenvio em resultados ambíguos, reconciliação e exclusão de instâncias concorrentes.
- API local opcional autenticada para importação, fila, rascunhos e confirmação.
- Extensão Chrome/Edge com ponte local pareada e restrita às tarefas assistidas TikTok.
- Registro distinto de agendamento declarado pelo usuário, sem confirmação automática de publicação.
- Análise offline de HTML colado, distinguindo upload, verificações e botão habilitado.
- Scripts Windows, configuração PyInstaller, CI Windows e documentação em português.

## Dependências externas restantes

- Configurar projeto Google Cloud, cliente OAuth desktop e autorizar o canal para validar envio real.
- Publicações assistidas devem ser concluídas pelo usuário nos serviços oficiais.
- Acesso automático a outras plataformas exige elegibilidade e aprovação específicas; não implementado nesta versão.
- Executável Windows e scripts PowerShell precisam de validação no Windows. O ambiente atual é Linux.
- Agendamento exige computador ligado e processo ativo; nenhuma execução com computador desligado.

## Verificação

Consulte [o relatório de validação](docs/validation.md) para comandos, resultados e limitações.
Não foram realizadas publicações reais. Nenhum token acompanha o projeto.

## Próxima ação externa

No Windows, instalar Python 3.12 e FFmpeg, executar `scripts/setup.ps1` e `scripts/run.ps1`.
Em Contas conectadas, importar o cliente OAuth Google e autorizar. Revisar um upload privado antes de autorizar um envio real.
Para o TikTok, seguir [o guia da extensão](docs/tiktok_extension.md). O upload e
o clique final no Studio continuam manuais, conforme os termos oficiais consultados.
