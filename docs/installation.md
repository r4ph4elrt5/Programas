# Instalação no Windows 10 e 11

## Pré-requisitos

- Python 3.12 com o launcher `py` e suporte a Tkinter.
- FFmpeg e ffprobe acessíveis pelo PATH.
- Internet para instalar dependências e autorizar os serviços oficiais.
- Espaço em disco para o vídeo original, suas versões derivadas e exportações.

Baixe o Python no site oficial e marque a opção de disponibilizá-lo no PATH.
Para FFmpeg, consulte as distribuições para Windows indicadas em
https://ffmpeg.org/download.html. Se você utiliza o Windows Package Manager,
pode optar por instalar com `winget install --id Gyan.FFmpeg --exact`.
Essa instalação é uma ação sua; o MultiPost não baixa nem executa instaladores
de ferramentas do sistema silenciosamente.

Feche e reabra o PowerShell após instalar. Confira:

```powershell
py -3.12 --version
ffmpeg -version
ffprobe -version
```

## Preparar o projeto

Baixe ou clone este repositório. Abra o PowerShell dentro da pasta `Programas`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

O script usa Python 3.12, cria o ambiente virtual `.venv`, instala as dependências
declaradas pelo projeto e executa o diagnóstico. Ele não solicita senhas de redes
sociais nem cria contas ou projetos externos. Se já existir `.venv`, ela é
reutilizada somente se usar Python 3.12; outra versão exige uma decisão sua sobre
renomear ou substituir a pasta.

Abra o aplicativo:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1
```

Não é necessário ativar o ambiente virtual manualmente.

## Instalação manual equivalente

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m multipost --diagnostics
.\.venv\Scripts\python.exe -m multipost
```

## Pastas e privacidade

No Windows, o aplicativo usa `%LOCALAPPDATA%\MultiPost` para banco de dados,
configuração, cache, exportações e logs. Os vídeos originais permanecem nos
locais escolhidos por você. Não mova nem exclua os originais enquanto houver
tarefas pendentes que os referenciem.

As legendas, nomes de arquivos e links salvos podem conter informações pessoais.
Mantenha as permissões da pasta restritas à sua conta. Tokens do YouTube ficam
no Windows Credential Manager por meio de `keyring`. Não há fallback para
armazenamento de tokens em texto puro.

## Atualizar e fazer backup

Feche o aplicativo e copie `%LOCALAPPDATA%\MultiPost` para um local protegido.
Guarde os vídeos originais separadamente. Depois atualize o código e execute
`setup.ps1` novamente. As credenciais do cofre do Windows não são copiadas com o
banco; pode ser necessário conectar novamente o canal.

## Outros sistemas

O código pode ser desenvolvido em Linux com Python 3.12, Tkinter, FFmpeg e
um cofre seguro compatível com `keyring`. O diretório persistente segue
`$XDG_DATA_HOME/MultiPost` ou o padrão do usuário. Linux sem desktop pode
executar os testes de backend; a interface exige um display. Um executável
Windows deve ser construído e validado no Windows.
