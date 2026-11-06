# 🗣️ Projeto Shadowing App

Plataforma interativa para prática de *Shadowing* em inglês, utilizando vídeos do YouTube e reconhecimento de voz em tempo real para sincronia e avaliação de pronúncia.

## ⚠️ Avisos importantes (leia antes de atualizar)

**Quem já tinha o projeto rodando:**
- **Novo passo obrigatório: `python -m app.migrar`** (Shadowing 2.0). O banco agora tem versão, controlada pelo
  Alembic, e o app **não sobe** se o banco estiver desatualizado. Depois de cada `git pull`, e antes de rodar o
  servidor, rode `python -m app.migrar` com a venv ativada. O comando faz backup do `estudos.db` sozinho. Seus decks
  e cards são preservados. Detalhes em [Banco de dados e migrações](#-banco-de-dados-e-migrações).
- **Faça backup dos seus dados antes do `git pull`.** O `estudos.db` (seus Decks e Cards) e o `ultimo_video.json`
  saíram do Git e agora ficam em `dados/`. O pull **apaga** esses arquivos da raiz. Antes de atualizar:
  ```bash
  mkdir -p dados && cp estudos.db ultimo_video.json dados/
  ```
- **O comando para rodar mudou:** `python -m uvicorn app.main:app --reload` (antes era `main:app`).
  Se o servidor antigo estiver aberto com `--reload`, ele quebra: pare e rode de novo com o comando novo.
- **Reinstale as dependências:** `pip install -r requirements.txt` (entrou o `vosk`; ferramentas de teste e
  lint foram para o `requirements-dev.txt`).
- **As URLs mudaram.** Páginas: `/pagina1` → `/`, `/legenda?link=` → `/estudo?link=`, `/revisao` → `/decks`,
  `/estudo_revisao?deck_id=` → `/decks/{id}/revisao`. A API virou REST (ex.: `POST /salvar_card` →
  `POST /api/decks/{id}/cards`, com JSON); a lista completa está em `/docs`. Links e favoritos antigos não funcionam.
- As pastas antigas `audio/`, `midia/` e `modelos/` na raiz não são mais usadas (podem ser apagadas ou
  movidas para `dados/`).

**Requisitos e limitações:**
- **FFmpeg é obrigatório**: sem ele não dá para baixar os vídeos nem gerar o áudio das frases.
- **Use Chrome ou Edge**: o reconhecimento de voz (transcrição) não funciona em outros navegadores.
- **O vídeo é baixado do YouTube** (yt-dlp) para tocar sem a interface do YouTube. Isso contraria os termos de
  uso do YouTube; use só para estudo. O primeiro carregamento de cada vídeo leva alguns segundos.
- **Primeiro uso do karaokê**: o modelo de fala do Vosk (~40 MB) é baixado para `dados/modelos/`.
- **Disco**: os vídeos ficam em `dados/midia/`; só os 5 usados mais recentemente são mantidos.
- **Avaliação da fala**: a nota de entonação está desligada (dava zero com microfones reais) e a pronúncia de
  cada som (fonema) ainda não é avaliada. Veja [Avaliação da fala](#-avaliação-da-fala).
- **Karaokê**: sem legenda automática do YouTube nem alinhamento possível, o tempo das palavras é uma
  estimativa e pode adiantar ou atrasar.
- **YouTube muda com frequência**: se legendas ou vídeos pararem de carregar, atualize as libs:
  `pip install -U "yt-dlp[default]" youtube-transcript-api`.
- **Python 3.11+ recomendado**: o yt-dlp já avisa que vai deixar de suportar o Python 3.10.

## 🚀 Como rodar o projeto localmente

**1. Clone o repositório e entre na pasta:**
```bash
git clone https://github.com/Projeto-ShadowingYoutube/Projeto.git
cd Projeto
```

**2. Crie e ative o ambiente virtual:**
```bash
python -m venv venv

# Linux / macOS / WSL
source venv/bin/activate

# Windows
venv\Scripts\activate
```

**3. Instale as dependências:**
```bash
pip install -r requirements.txt
```
Isso também instala o **Deno** dentro da venv. O yt-dlp precisa dele para baixar os vídeos do YouTube.
Se o áudio das frases parar de carregar, atualize as libs do YouTube: `pip install -U "yt-dlp[default]" youtube-transcript-api`.

**4. Instale o FFmpeg** (usado para juntar vídeo e áudio baixados e cortar o áudio das frases):
- Linux / WSL: `sudo apt update && sudo apt install -y ffmpeg`
- macOS: `brew install ffmpeg`
- Windows: `winget install ffmpeg`

**5. Crie ou atualize o banco de dados** (rode de novo depois de todo `git pull`):
```bash
python -m app.migrar
```
Na primeira vez, o comando cria `dados/estudos.db`. Nas outras, aplica só o que mudou (ou diz "Nada a fazer").

**6. Rode o servidor** (de dentro da pasta `Projeto`, com a venv ativada):
```bash
python -m uvicorn app.main:app --reload
```
> Erro `No module named 'app'`: você está fora da pasta `Projeto`. Erro `No module named 'numpy'` (ou outra
> biblioteca): a venv não está ativada, e o comando usou o Python do sistema. Com a venv ativa, o prompt começa com `(venv)`.
>
> Erro `BancoDesatualizado ... Rode: python -m app.migrar`: faça o passo 5.

Acesse **http://127.0.0.1:8000** no navegador (Chrome ou Edge, que suportam o reconhecimento de voz).
A documentação da API fica em **http://127.0.0.1:8000/docs**.

Tudo o que o app gera ao rodar fica em `dados/` (fora do Git): o banco `estudos.db` (e seus backups em `dados/backup/`), a cache de legendas,
os vídeos baixados (só os 5 usados mais recentemente) e o modelo de fala do Vosk (~40 MB, baixado no
primeiro uso do karaokê).

## 💾 Banco de dados e migrações

**Qual banco é usado.** É o valor de `DATABASE_URL`. A ordem de leitura é: variável de ambiente, depois o arquivo
`.env` na raiz do projeto, depois o padrão. O padrão é o SQLite em `dados/estudos.db`. Para usar outro banco, copie
`.env.example` para `.env` e ajuste. O `.env` fica fora do Git, porque pode ter senhas.

**O esquema é versionado (Alembic).** Cada mudança nas tabelas é um arquivo em `migrations/versions/`, numerado
(`0001_baseline.py`, `0002_...`). O banco guarda em que versão está (tabela `alembic_version`).

**O que `python -m app.migrar` faz:**
1. Lê em que versão o banco está.
2. Se houver algo a mudar e o banco for SQLite com dados, **faz um backup** em `backup/`, ao lado do arquivo do
   banco (para o padrão: `dados/backup/estudos-AAAAMMDD-HHMMSS-....db`).
3. **Banco antigo** (criado antes do Alembic, sem versão): confere se as tabelas são exatamente as do baseline e só
   **marca** o banco como versão `0001`, sem alterar nenhum dado. Se o esquema for diferente, para com erro e
   **não altera nada**.
4. Aplica as migrações que faltam.

Rodar o comando de novo não faz nada ("Nada a fazer") e não cria backup.

**Por que o app não migra sozinho ao subir:** migração mexe no banco e pode ser destrutiva. Fazer isso escondido
num `--reload`, ou em vários processos ao mesmo tempo em produção, é arriscado. Por isso o app só **confere** a
versão ao subir, e para com uma instrução clara se estiver desatualizado.

**Restaurar um backup (SQLite):** pare o servidor e copie o arquivo de `dados/backup/` por cima de `dados/estudos.db`.

**Para quem desenvolve: alterei um modelo (`app/models.py`), e agora?**
```bash
python -m alembic revision --autogenerate -m "descricao curta" --rev-id 0002   # gera migrations/versions/0002_....py
# REVISE o arquivo gerado (o autogenerate não detecta tudo, por exemplo renomeações)
python -m app.migrar                                                           # aplica no seu banco
pytest                                                                         # test_migracoes confere modelos x migrações
```
O teste `tests/test_migracoes.py` falha se um modelo mudar sem a migração correspondente. Não use
`alembic upgrade` direto: ele não faz backup. Use `python -m app.migrar`.

## 🎯 Avaliação da fala

Cada gravação recebe uma nota, no modelo das provas automáticas de "repita a frase" (PTE, Versant):

| Nota | Como é medida |
|---|---|
| **Palavras** (⅔) | A transcrição é casada com o texto da frase; as palavras que faltaram ficam sublinhadas na legenda |
| **Ritmo** (⅓) | O Vosk alinha a gravação ao texto; compara-se em que ponto da frase cada palavra começa (pausas e duração das palavras, sem contar a velocidade) |
| ~~Entonação~~ | Desligada por enquanto (`AVALIAR_ENTONACAO` em `app/services/avaliacao.py`): curva de altura da voz (F0) em semitons, com as palavras como âncora |

A velocidade aparece à parte, no timer. A pronúncia de cada som (fonema) ainda não é avaliada.

## 🗂️ Arquitetura

```
app/
├── main.py           # cria o FastAPI e registra as rotas
├── config.py         # caminhos, constantes e configuração por ambiente (DATABASE_URL / .env)
├── db.py, models.py  # conexão com o banco e modelos (Decks, Cards, cache do dicionário)
├── migrar.py         # python -m app.migrar: backup + migrações do Alembic
├── schemas.py        # formatos de entrada/saída da API
├── api/              # camada HTTP: rotas finas, que validam e chamam os serviços
│   ├── paginas.py      páginas HTML (navegação via HTMX)
│   ├── legendas.py     legendas + limite de tokens
│   ├── videos.py       vídeo, áudio de cada frase e tempo das palavras
│   ├── avaliacoes.py   avaliação da fala gravada
│   ├── decks.py        Decks, Cards e revisão espaçada (REST)
│   └── dicionario.py   popup de dicionário
├── services/         # regras de negócio, sem FastAPI (testáveis isoladamente)
│   ├── youtube.py      tudo o que fala com o YouTube (legendas, título, download, legenda automática)
│   ├── legendas.py     legendas da cache ou do YouTube
│   ├── cache_legendas.py
│   ├── frases.py       reagrupa os blocos do YouTube em frases e estima o tempo das palavras
│   ├── midia.py        download do vídeo em segundo plano e corte do áudio (FFmpeg)
│   ├── karaoke.py      escolhe a melhor fonte de tempo das palavras
│   ├── alinhamento.py  legenda automática / Vosk → tempo de cada palavra
│   ├── avaliacao.py    notas de palavras, ritmo e entonação da fala do usuário
│   ├── dicionario.py   spaCy + Wiktionary
│   └── decks.py        nomes únicos, dashboard e intervalo da revisão espaçada
├── templates/        # base.html, paginas/, partials/
└── static/
    ├── css/            um arquivo por assunto (base, inicio, player, painel, legenda, modais, decks)
    └── js/             ES modules
        ├── main.js       ponto de entrada
        ├── nucleo/       cliente da API, interface global, ciclo de vida das páginas, tema
        ├── componentes/  player, legenda (karaokê + dicionário), waveform, gravador, avaliação, escolha de Deck
        └── paginas/      estudo, decks, revisao
migrations/           # Alembic: env.py e versions/ (uma migração por mudança no esquema)
tests/                # um arquivo por módulo (pytest)
docs/                 # plano de implementação (IMPLEMENTATION_PLAN.md) e métricas do projeto
```

## 🧪 Desenvolvimento
```bash
pip install -r requirements-dev.txt
pytest          # testes + cobertura
ruff check .    # lint (regras em pyproject.toml)
```
