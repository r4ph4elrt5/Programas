# Integrações e regras das plataformas

O MultiPost prepara um mesmo vídeo para cinco destinos. A preparação local não é
confirmação de publicação. Não existe garantia de ausência de penalidades: o
conteúdo, os direitos autorais, as regras da conta e as decisões de cada rede
continuam sob responsabilidade do titular e da plataforma.

| Destino | Integração desta versão | Requisito externo |
| --- | --- | --- |
| YouTube | OAuth desktop, upload retomável e consulta de processamento | Projeto Google Cloud, API habilitada, credenciais OAuth desktop e canal autorizado |
| Instagram | Pacote assistido e confirmação do usuário | Conta pessoal publica no site/app oficial; API requer conta profissional e permissões |
| Facebook | Pacote assistido e confirmação do usuário | Perfil pessoal publica no site/app oficial; API de Página é uma integração distinta |
| TikTok | Pacote assistido e confirmação do usuário | Content Posting API depende de aprovação e elegibilidade do caso de uso |
| Kwai | Pacote assistido e confirmação do usuário | Nenhuma API de publicação elegível foi comprovada para esta conta |

## YouTube

O programa usa apenas `youtube.upload` e `youtube.readonly`, abre o consentimento
no navegador oficial e recebe a autorização em loopback local. Tokens ficam no
cofre nativo do sistema (Windows Credential Manager no Windows), sem fallback
para arquivos em texto. Um ambiente sem cofre seguro pode usar todos os fluxos
assistidos, mas não mantém autenticação YouTube.

O upload usa a YouTube Data API `videos.insert`, em partes de 8 MiB. O programa
registra o ID retornado como `PROCESSING` e consulta `videos.list`; apenas uma
resposta com processamento concluído, upload processado e privacidade pública
recebe `PUBLISHED`. Conteúdo privado ou não listado processado recebe
`UPLOADED_PRIVATE`. Verifique a privacidade no YouTube Studio. Não confunda envio
com publicação pública. Falhas ambíguas exigem conferência do Studio antes de um
novo upload para evitar duplicatas.

Erros explícitos 429 e 5xx permitem até três esperas exponenciais reutilizando
a mesma sessão retomável. Falhas de conexão ambíguas não iniciam um novo upload.

O usuário deve declarar se o conteúdo é destinado a crianças. O padrão de
privacidade é privado. Agendamento remoto exige vídeo privado e data futura com
fuso explícito; o agendamento local depende de o aplicativo continuar aberto.
Nenhuma rotina pressupõe que um vídeo vertical será classificado como Short.
O YouTube determina a classificação e pode impor restrições de conta, quota,
verificação, auditoria e direitos autorais. Confira o console e a documentação
vigente antes de usar em produção.

Fontes oficiais (consulta realizada em 06/11/2026):

- [Upload oficial e parâmetros](https://developers.google.com/youtube/v3/docs/videos/insert)
- [Status e metadados](https://developers.google.com/youtube/v3/docs/videos)
- [OAuth para aplicativos desktop](https://developers.google.com/identity/protocols/oauth2/native-app)
- [Uploads retomáveis](https://developers.google.com/youtube/v3/guides/using_resumable_upload_protocol)
- [Regras para Shorts](https://support.google.com/youtube/answer/15424877)

## TikTok e demais redes assistidas

As diretrizes oficiais do TikTok dizem que ferramentas utilitárias para enviar
apenas às contas próprias/da equipe não são um caso aceito para Direct Post.
Clientes sem auditoria têm restrições adicionais. Por isso o aplicativo não
anuncia publicação automática TikTok nem tenta contornar essa regra.

- [Diretrizes oficiais TikTok](https://developers.tiktok.com/doc/content-sharing-guidelines/)
- [Publicação Instagram](https://developers.facebook.com/docs/instagram-platform/content-publishing/)
- [API de Reels para Páginas Facebook](https://developers.facebook.com/docs/video-api/guides/reels-publishing/)
- [Destino oficial Kwai](https://www.kwai.com/)

As páginas do YouTube `videos.insert` e das diretrizes TikTok foram obtidas e
examinadas durante o desenvolvimento. Os demais links servem como referência;
não foi validada uma autorização real de conta em nenhuma rede. Os conectores
assistidos abrem apenas destinos oficiais e exportam arquivos locais. Não
automatizam login, cliques, cookies, CAPTCHA ou publicação em endpoints privados.
