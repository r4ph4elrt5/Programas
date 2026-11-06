# Guia de uso

## Importar e preparar

Na biblioteca, escolha um ou vários vídeos. O MultiPost consulta os metadados
com ffprobe e gera miniaturas. Duração, tamanho e resolução vêm do arquivo real.
Um arquivo ausente ou inválido precisa ser corrigido antes de continuar.

Abra a prévia no reprodutor padrão do computador para verificar áudio,
orientação e conteúdo. Quando precisar ajustar o formato, gere uma versão
derivada: ajuste com margens preserva o quadro; preenchimento por corte central
pode remover conteúdo das bordas. Confira o resultado antes de usar. O original
não deve ser sobrescrito.

## Criar uma publicação

1. Em **Nova publicação**, selecione o vídeo.
2. Preencha título e legenda geral.
3. Marque os destinos desejados.
4. Use as abas dos destinos para personalizar as legendas. Uma legenda
   personalizada substitui a geral naquele destino; restaure a legenda geral
   quando quiser remover essa personalização.
5. Para YouTube, selecione a privacidade e declare se o conteúdo é destinado
   a crianças. Essa declaração é obrigatória e deve refletir o conteúdo.
6. Revise os dados e crie as tarefas.

Uma publicação para cinco plataformas cria cinco tarefas independentes.
O sucesso em um destino não implica sucesso nos outros.

## Concluir publicações assistidas

Instagram pessoal, Facebook pessoal, TikTok e Kwai usam este fluxo:

1. Aguarde a preparação do pacote.
2. Abra a pasta exportada e confira o vídeo.
3. Copie a legenda pelo aplicativo.
4. Abra o destino oficial e faça a publicação manualmente.
5. Quando o site não permitir envio, transfira o pacote para o celular e use
   o aplicativo oficial da plataforma.
6. Volte ao MultiPost e confirme que concluiu, informando o link se disponível.

Essa confirmação é uma declaração sua. O aplicativo não consulta esses serviços
para verificar uma publicação feita manualmente e não apresenta essa declaração
como confirmação de API. Abrir o site, copiar a legenda ou exportar um pacote
jamais é considerado publicação concluída.

## Publicar no YouTube

Conecte o canal em **Contas** usando o [guia OAuth](youtube_setup.md).
O envio acontece depois que você cria uma tarefa autorizada. Aguarde o upload
e o processamento. Um vídeo enviado com privacidade privada ou não listado
é identificado como tal; isso não equivale a um vídeo público.

Uploads por projetos sem auditoria podem ficar restritos a privados pelo
YouTube. A classificação como Short depende das regras vigentes do YouTube,
inclusive duração, proporção e eventuais restrições sobre músicas/direitos.

## Agendar

Informe a data e hora na tela de edição, observando o formato exibido. O horário
é convertido e armazenado com fuso. Confira a data na fila antes de sair.

O aplicativo precisa permanecer aberto e o computador acordado. Para redes
assistidas, o horário prepara o pacote: você ainda precisa publicar no destino.
Após uma interrupção, revise tarefas vencidas antes de autorizá-las novamente.
O agendamento local não é um serviço na nuvem e não liga o computador.

## Falhas, cancelamentos e duplicação

Use o botão de cancelar da tarefa quando quiser interromper. Um cancelamento
local durante o envio não garante que o servidor tenha descartado o vídeo.
Se o resultado remoto for desconhecido, confira o YouTube Studio e consulte
o status antes de criar qualquer novo envio. O aplicativo não reenvia
automaticamente um resultado ambíguo.

Erros de autenticação exigem reconexão. Limites de quota devem ser respeitados;
não crie chaves ou contas alternativas para contorná-los. O histórico mantém
o resultado de cada destino, incluindo erros e confirmações manuais.

## Configurações e diagnóstico

Escolha o tema claro ou escuro em **Configurações**. Em **Diagnóstico**, confira
as ferramentas de mídia, versão do aplicativo e caminhos locais. Não compartilhe
arquivos OAuth, tokens, backups do cofre ou relatórios sem revisar seus dados.
Desconectar o YouTube remove a credencial local; veja o guia OAuth sobre revogação.
