# Arquitetura

O pacote `src/multipost` separa a interface desktop, os serviços da aplicação,
a persistência, o processamento de mídia e os conectores externos.

- A interface CustomTkinter coleta as escolhas do usuário e mostra dados reais.
  Operações demoradas ficam fora da thread de desenho e retornam resultados
  por uma fila consultada pela thread principal.
- O serviço de aplicação coordena importação, rascunhos, tarefas independentes,
  transições de estado e recuperação após reinício.
- SQLite guarda vídeos, configurações e histórico localmente. Credenciais
  não são registros comuns do banco.
- O serviço de mídia usa `ffprobe` para análise e `ffmpeg` para miniaturas e
  arquivos derivados. Os comandos usam argumentos separados, sem shell para
  interpretar caminhos enviados pelo usuário.
- O registro de plataformas informa capacidades explícitas. Destinos assistidos
  exportam pacotes; não fazem requisições a endpoints privados de publicação.
- O cliente YouTube implementa OAuth desktop, upload retomável, consulta do
  processamento e integração com o cofre seguro de credenciais.

## Tarefa por destino

Um mesmo vídeo pode ter cinco tarefas. Cada uma conserva legenda, horário,
estado, progresso, erro e identificador remoto, quando existe. Uma falha não
transforma outras tarefas em falhas nem em sucessos. A confirmação de API,
o arquivo preparado e a confirmação declarada pelo usuário são estados distintos.

Uma falha de rede após início de envio pode ser ambígua: o servidor pode ter
aceitado o conteúdo. Nesse caso a recuperação prioriza reconciliação pelo
identificador já conhecido e conferência no serviço. Não se cria silenciosamente
outro upload. Reinício também não deve disparar publicações vencidas sem revisão.

## Agendamento

O agendador é local e depende de processo ativo. Datas são persistidas com fuso
para evitar comparações entre horários ambíguos. A fila controla a execução para
evitar que duas chamadas concorrentes iniciem a mesma tarefa.

## Segurança

O aplicativo não guarda senhas de redes sociais, não captura cookies e não
automatiza interfaces de terceiros para publicar. OAuth usa o navegador oficial
com callback loopback. Tokens são armazenados somente em backend seguro de
`keyring`; um backend indisponível não autoriza fallback para texto puro.

Os diretórios persistentes ficam fora do código e fora do diretório temporário
de um executável empacotado. Logs têm retenção limitada e não devem registrar
tokens, cabeçalhos de autorização nem URLs completas de sessões de upload.

## Distribuição e testes

`scripts/build.ps1` constrói um pacote PyInstaller `onedir` no Windows.
`multipost.spec` inclui os recursos do CustomTkinter e os imports dinâmicos
necessários aos clientes Google e ao backend de credenciais.

Testes de backend e integrações simuladas não exigem contas de redes sociais.
Testes de mídia exercitam os executáveis locais. Testes da interface precisam
de um desktop/display. Build em Linux valida apenas o pacote daquele sistema;
a distribuição Windows exige build e verificação no Windows.
