# Conectar um canal do YouTube

O MultiPost usa a YouTube Data API e OAuth 2.0 para aplicativo desktop. Você
autoriza sua conta no navegador do Google; sua senha nunca é solicitada dentro
do MultiPost. Um token permite operações no canal dentro das permissões concedidas.

## Preparar no Google Cloud

1. Acesse https://console.cloud.google.com/ com sua conta.
2. Crie ou selecione um projeto.
3. Em **APIs e serviços**, habilite **YouTube Data API v3**.
4. Configure o consentimento OAuth no Google Auth Platform: nome do aplicativo,
   contato e público. Se o app estiver em teste, adicione sua conta como usuário
   de teste. A interface do Google pode mudar; consulte a documentação oficial.
5. Crie um cliente OAuth do tipo **Aplicativo para computador / Desktop app**.
6. Baixe o JSON do cliente e guarde-o fora do repositório.

Não use uma chave de API comum no lugar de OAuth. Não use conta de serviço para
um canal pessoal. Não publique o JSON no GitHub e não cole tokens em chats.

## Autorizar pelo MultiPost

1. Abra **Contas** e escolha conectar YouTube.
2. Selecione o JSON baixado.
3. O aplicativo abre o navegador e um callback local temporário para receber
   a autorização. Autorize apenas na página oficial do Google.
4. Confira o canal identificado pelo aplicativo antes de criar uma publicação.

O token é guardado por `keyring` no cofre seguro do sistema. No Windows,
é usado o Windows Credential Manager. Se o cofre estiver indisponível, o
aplicativo deve recusar o armazenamento; não substitua por um backend em texto puro.

## Primeiro envio

Use um vídeo seu e curto, com privacidade **privada**, e confira título,
descrição e a declaração de conteúdo infantil. Autorize o envio pelo aplicativo.
Verifique o resultado no YouTube Studio e só então escolha a visibilidade que
deseja para publicações posteriores.

O desenvolvimento usa respostas simuladas nos testes. Sem seu projeto OAuth e
uma autorização real, não é possível comprovar publicação na sua conta. Não
considere o teste simulado como um envio real.

## Restrições importantes

- Projetos de API não auditados podem ter uploads limitados a privados. A
  mudança de visibilidade depende das políticas e auditorias do YouTube.
- Projetos têm quotas. Uma mensagem de quota não é resolvida com tentativas
  repetidas; espere a renovação ou siga o processo oficial para extensão.
- Consentimento OAuth em modo de teste pode ter tokens de duração limitada;
  reconecte quando necessário. A verificação do aplicativo e a auditoria da API
  são processos distintos.
- Vídeos podem ser rejeitados ou ter sua publicação restringida por direitos
  autorais, regras da comunidade e políticas de conteúdo.
- Verticalidade por si só não garante classificação como Short.
- Um vídeo com processamento pendente não é publicação pública confirmada.

## Desconectar e revogar

Desconecte em **Contas** para remover a credencial local. Verifique também o
acesso na sua [Conta Google](https://myaccount.google.com/permissions) e remova
o aplicativo se quiser garantir a revogação pelo provedor, inclusive quando
estiver sem rede durante a desconexão local. Uma publicação já enviada não é
apagada ao desconectar.

## Fontes oficiais

- https://developers.google.com/youtube/v3/guides/auth/installed-apps
- https://developers.google.com/youtube/v3/docs/videos/insert
- https://developers.google.com/youtube/v3/guides/using_resumable_upload_protocol
- https://developers.google.com/youtube/v3/docs/videos/list
- https://developers.google.com/youtube/v3/getting-started#quota
- https://support.google.com/youtube/answer/15424877
