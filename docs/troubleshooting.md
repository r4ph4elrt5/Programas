# Problemas comuns

## “Python 3.12 não encontrado”

Instale Python 3.12 pelo site oficial com o launcher `py`. Feche e reabra o
PowerShell e execute `py -3.12 --version`. Se já houver `.venv` de outra versão,
renomeie-a primeiro, preservando qualquer arquivo seu, e execute o setup novamente.

## “ffmpeg/ffprobe não encontrado”

Instale FFmpeg por uma distribuição indicada em https://ffmpeg.org/download.html
e acrescente a pasta `bin` ao PATH do usuário. Reabra o PowerShell e confira
`ffprobe -version` e `ffmpeg -version`. Sem ffprobe a importação não consegue
identificar o vídeo; sem ffmpeg não é possível converter ou gerar miniaturas.

## O PowerShell bloqueou um script

Inspecione o script e use o comando documentado com
`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1`.
A opção afeta somente esse processo. Em computador administrado por uma
organização, siga a política local e solicite ajuda ao administrador.

## Vídeo ausente, inválido ou incompatível

Confira se o arquivo ainda está no local importado e se abre em um reprodutor.
Não escolha uma pasta em vez de arquivo. Arquivos parciais, corrompidos ou
protegidos não devem ser publicados. Gere uma versão derivada compatível quando
necessário e revise o resultado, especialmente se houver corte central.

## OAuth recusado ou canal incorreto

Confira se o JSON é de **aplicativo desktop**, se a YouTube Data API está
habilitada e se sua conta foi adicionada aos usuários de teste. Reconecte no
navegador com a conta/canal desejados. Não cole sua senha Google no aplicativo.

## Cofre seguro indisponível

No Windows, use sua sessão normal de usuário com Windows Credential Manager
disponível. Em Linux, um desktop/cofre compatível com `keyring` pode ser
necessário. Não instale um backend que salve tokens sem criptografia para
contornar o erro. Os outros fluxos assistidos continuam utilizáveis.

## Upload privado quando queria público

Confira a escolha de privacidade. O YouTube também pode impor privacidade a
projetos de API não auditados. Siga o processo oficial de auditoria; alterar
tokens ou repetir o upload não remove essa limitação.

## Quota excedida, timeout ou resultado desconhecido

Respeite a quota do serviço. Para um resultado de envio desconhecido, abra
YouTube Studio antes de tentar novamente. Se houver ID remoto conhecido,
consulte o processamento pelo aplicativo. Não crie uma segunda tarefa apenas
para repetir um envio que pode ter sido aceito.

## Agendamento não executou

O aplicativo e o computador precisam estar ativos. Suspensão, desligamento,
fechamento da janela ou perda de acesso ao arquivo impedem a execução. Ao
retornar, revise os itens vencidos. Em destinos assistidos, o horário prepara
o pacote, mas você precisa concluir a publicação manualmente.

## Exportação não significa publicação

O pacote contém vídeo e legenda para uso no serviço oficial. Só marque a
confirmação manual depois de finalizar lá. Quando a interface web não oferecer
upload, transfira o arquivo ao celular e use o aplicativo oficial.

## Sem espaço, banco bloqueado ou erro de permissões

Confira o espaço livre e as permissões do diretório de dados. Use uma única
instância do aplicativo. Feche-o antes de copiar/restaurar o banco. Preserve um
backup antes de mexer em arquivos de dados; não apague o banco para resolver
um erro sem entender o que será perdido.

## Relatar um problema

Informe a ação, a mensagem, a versão e o diagnóstico. Nunca envie arquivo OAuth,
tokens, cabeçalhos de autenticação ou o conteúdo do cofre. Revise também nomes
de vídeos e legendas que possam conter dados pessoais antes de compartilhar logs.
