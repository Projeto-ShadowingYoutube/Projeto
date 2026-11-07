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
   banco (para o padrão: `dados/backup/estudos-AAAAMMDD-HHMMSS-....db`). **No PostgreSQL não há backup
   automático:** faça o `pg_dump` antes (veja abaixo).
3. **Banco antigo** (criado antes do Alembic, sem versão): confere se as tabelas são exatamente as do baseline e só
   **marca** o banco como versão `0001`, sem alterar nenhum dado. Se o esquema for diferente, para com erro e
   **não altera nada**.
4. Aplica as migrações que faltam.

Rodar o comando de novo não faz nada ("Nada a fazer") e não cria backup.

**Por que o app não migra sozinho ao subir:** migração mexe no banco e pode ser destrutiva. Fazer isso escondido
num `--reload`, ou em vários processos ao mesmo tempo em produção, é arriscado. Por isso o app só **confere** a
versão ao subir, e para com uma instrução clara se estiver desatualizado.

**Restaurar um backup (SQLite):** pare o servidor e copie o arquivo de `dados/backup/` por cima de `dados/estudos.db`.

### Usando PostgreSQL no desenvolvimento (recomendado)

O PostgreSQL é o banco de produção. O `docker-compose.yml` sobe um Postgres local, acessível só pela sua máquina
(`127.0.0.1`), com dois bancos: `shadowing` (seus dados) e `shadowing_teste` (só para o pytest). Requer o
[Docker Desktop](https://www.docker.com/products/docker-desktop/) aberto.

```bash
# 1. Configuração: copie o modelo e troque a senha (POSTGRES_PASSWORD) por uma sua
copy .env.example .env          # Linux/macOS: cp .env.example .env
#    No .env, descomente a linha DATABASE_URL e coloque nela a MESMA senha.

# 2. Suba o banco (fica rodando em segundo plano; os dados ficam num volume do Docker)
docker compose up -d db
docker compose ps               # espere o STATUS ficar "(healthy)"

# 3. Crie as tabelas e rode o app normalmente
python -m app.migrar
python -m uvicorn app.main:app --reload
```

- **Use `127.0.0.1` na `DATABASE_URL`, e não `localhost`.** No Windows, `localhost` tenta antes o IPv6 (`::1`), onde
  o container não escuta, e cada conexão demora segundos ou trava.
- **Voltar ao SQLite:** apague ou comente a linha `DATABASE_URL` no `.env`.
- **Parar o banco:** `docker compose stop db`. Os dados continuam no volume. `docker compose down` também preserva os
  dados. **Só `docker compose down -v` apaga os dados.**
- **Porta 5432 ocupada:** mude `POSTGRES_PORT` no `.env` e a porta na `DATABASE_URL`.
- **O banco de testes só é criado na primeira vez que o volume é iniciado.** Se o seu volume é anterior a este
  passo, crie-o à mão: `docker compose exec db createdb -U shadowing shadowing_teste`.

**Backup e restauração do PostgreSQL.** Faça o backup **antes** de rodar `python -m app.migrar` quando houver
migração nova. O arquivo é gerado dentro do container e depois copiado, porque o `>` do PowerShell corrompe
arquivos binários. Funciona em cmd, PowerShell e bash (Linux/macOS).

> **Git Bash no Windows:** ele converte sozinho os caminhos `/tmp/...` em caminhos do Windows, e o `pg_dump` falha
> com `could not open output file "C:/Users/..."`. Use `MSYS_NO_PATHCONV=1` antes de cada comando abaixo
> (ex.: `MSYS_NO_PATHCONV=1 docker compose exec db pg_dump ...`).
```bash
# Backup → dados/backup/postgres.dump
docker compose exec db pg_dump -U shadowing -d shadowing -Fc -f /tmp/backup.dump
docker compose cp db:/tmp/backup.dump dados/backup/postgres.dump

# Restauração (substitui o conteúdo atual do banco "shadowing"; pare o servidor antes)
docker compose cp dados/backup/postgres.dump db:/tmp/restaurar.dump
docker compose exec db pg_restore -U shadowing -d shadowing --clean --if-exists --no-owner /tmp/restaurar.dump
```

**Rodar os testes no PostgreSQL.** Sem configurar nada, o `pytest` usa SQLite temporário. Para rodar a mesma suíte
no Postgres, defina `TEST_DATABASE_URL` **só no terminal** (de propósito, ela não é lida do `.env`), apontando
para o banco `shadowing_teste`:
```bash
# cmd:         set TEST_DATABASE_URL=postgresql+psycopg://shadowing:SUA_SENHA@127.0.0.1:5432/shadowing_teste
# PowerShell:  $env:TEST_DATABASE_URL="postgresql+psycopg://shadowing:SUA_SENHA@127.0.0.1:5432/shadowing_teste"
# bash:        export TEST_DATABASE_URL=postgresql+psycopg://shadowing:SUA_SENHA@127.0.0.1:5432/shadowing_teste
pytest
```
Os testes apagam e recriam as tabelas. Por segurança, eles **se recusam a rodar** se o nome do banco não terminar
em `_teste`. Sem `TEST_DATABASE_URL`, o teste exclusivo do Postgres aparece como "skipped".

**Para quem desenvolve: alterei um modelo (`app/models.py`), e agora?**
```bash
python -m alembic revision --autogenerate -m "descricao curta" --rev-id 0002   # gera migrations/versions/0002_....py
# REVISE o arquivo gerado (o autogenerate não detecta tudo, por exemplo renomeações)
python -m app.migrar                                                           # aplica no seu banco
pytest                                                                         # test_migracoes confere modelos x migrações
```
O teste `tests/test_migracoes.py` falha se um modelo mudar sem a migração correspondente. Não use
`alembic upgrade` direto: ele não faz backup. Use `python -m app.migrar`.

## 🔐 Contas e login

Cada pessoa tem uma conta (e-mail + senha), e **cada Deck pertence a uma conta**. As rotas de Decks e Cards exigem
login, e ninguém vê nem altera os Decks de outra pessoa.

**Na interface:**
- **Todas as páginas exigem login**, menos `/login` e `/cadastro`. Quem abre uma página sem estar logado vai para
  `/login?proximo=<página>` e, depois de entrar, volta para ela.
- A navbar mostra o e-mail da conta e o botão **Sair**.
- Se a sessão vencer no meio do uso, a próxima ação leva ao login e depois de volta à mesma página.
- Como funciona (`app/api/paginas.py`): sem sessão, quem abre a URL direto recebe um redirecionamento 303. Na
  navegação pelo HTMX, o servidor responde com o header `HX-Redirect`. No front, um 401 da API (`requisitarJSON`
  em `static/js/nucleo/api.js`) também leva ao login.
- **Open redirect:** o `proximo` só aceita caminhos deste site. `?proximo=https://outro-site` vira `/`.
- As páginas saem com `Cache-Control: no-store`: depois de **Sair**, o botão "voltar" do navegador não mostra cópias
  antigas.

| Rota | O que faz |
|---|---|
| `POST /api/auth/cadastro` | Cria a conta (`{email, senha}`; senha de 8 a 128 caracteres) e já entra nela |
| `POST /api/auth/login` | Entra. Erro sempre como "E-mail ou senha incorretos" (não revela quais e-mails têm conta) |
| `POST /api/auth/logout` | Sai: a sessão é apagada no servidor, e o cookie antigo deixa de funcionar |
| `GET /api/auth/me` | Quem está logado (401 sem sessão) |

**Como funciona:**
- **Senha:** guardada só como hash **Argon2id** (`app/services/auth.py`), nunca em texto.
- **Sessão:** ao entrar, o servidor gera um token aleatório de 256 bits. Ele vai num cookie `sessao` com
  `HttpOnly` (o JavaScript não o lê) e `SameSite=Lax` (não é enviado em POSTs vindos de outros sites). No banco
  (tabela `sessao`) fica só o SHA-256 do token. A sessão vale 14 dias (`DURACAO_SESSAO_DIAS` em `app/config.py`).
- **CSRF** (um site malicioso usando a sessão de quem o visita). São duas barreiras. (1) O cookie é `SameSite=Lax`.
  (2) Em `POST`/`PUT`/`PATCH`/`DELETE`, o middleware `app/seguranca.py` recusa com 403 quando o navegador informa
  uma origem (`Origin`) diferente do próprio app. Clientes sem `Origin` (curl, scripts, testes) passam. A segunda
  barreira importa porque o `SameSite` trata outra **porta** do mesmo host como o mesmo "site".
- **Produção:** defina `AMBIENTE=producao` (no `.env` ou nas variáveis do servidor). Assim o cookie ganha `Secure` e
  só trafega por HTTPS.
- **Para proteger uma rota:** `usuario: Usuario = Depends(usuario_atual)` (de `app/api/auth.py`). Sem sessão válida,
  a resposta é 401. Em `app/api/decks.py`, a dependência fica no router inteiro, então rotas novas já nascem
  protegidas.

**Isolamento entre contas (Decks e Cards):**
- **Posse:** Usuário → Decks → Cards. O Deck tem `usuario_id`. O Card não tem: o dono dele é o dono do Deck.
- **Onde é conferido:** só no backend, nas dependências `_deck` e `_card` de `app/api/decks.py`, que todas as rotas
  usam. Esconder botões na tela não protege nada.
- **Recurso de outra conta responde 404**, igual a um que não existe. Responder 403 confirmaria que aquele ID existe
  (falha conhecida como IDOR).
- **Nome do Deck:** único dentro de cada conta (garantido também pelo banco: `UNIQUE (usuario_id, nome)`). Duas
  contas podem ter um Deck "Inglês".
- **Testes:** `tests/test_isolamento.py` (duas contas tentando acessar os dados uma da outra).

**Decks criados antes das contas (sem dono):** a migração `0003` não escolhe um dono por você. Se o banco tiver
Decks antigos, `python -m app.migrar` para com `ERRO: Existem N Deck(s) ... sem dono` **sem alterar nada**. Decida
o que fazer com eles (associar a um usuário ou apagar) e rode o comando de novo. Faça backup antes.

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
├── db.py, models.py  # conexão com o banco e modelos (Usuários, Sessões, Decks, Cards, cache do dicionário)
├── migrar.py         # python -m app.migrar: backup + migrações do Alembic
├── seguranca.py      # CSRF: recusa POST/PATCH/DELETE vindos de outros sites (verificação de Origin)
├── schemas.py        # formatos de entrada/saída da API
├── api/              # camada HTTP: rotas finas, que validam e chamam os serviços
│   ├── paginas.py      páginas HTML (navegação via HTMX)
│   ├── auth.py         cadastro, login, logout, /me e as dependências usuario_atual / usuario_opcional
│   ├── legendas.py     legendas + limite de tokens
│   ├── videos.py       vídeo, áudio de cada frase e tempo das palavras
│   ├── avaliacoes.py   avaliação da fala gravada
│   ├── decks.py        Decks, Cards e revisão espaçada (REST)
│   └── dicionario.py   popup de dicionário
├── services/         # regras de negócio, sem FastAPI (testáveis isoladamente)
│   ├── auth.py         hash de senha (Argon2id), contas e sessões
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
        └── paginas/      auth (login e cadastro), estudo, decks, revisao
migrations/           # Alembic: env.py e versions/ (uma migração por mudança no esquema)
docker/postgres/      # init.sql: cria o banco de testes no container do Postgres
docker-compose.yml    # PostgreSQL local para desenvolvimento (docker compose up -d db)
.env.example          # modelo das variáveis de ambiente (copie para .env)
tests/                # um arquivo por módulo (pytest)
docs/                 # plano de implementação (IMPLEMENTATION_PLAN.md) e métricas do projeto
```

## 🧪 Desenvolvimento
```bash
pip install -r requirements-dev.txt
pytest          # testes + cobertura
ruff check .    # lint (regras em pyproject.toml)
```

**Testes de navegador (opcionais).** `tests/test_e2e_navegador.py` abre o app num Chromium de verdade (Playwright):
cadastro, login, criar Deck, revisar, excluir Card, sair, isolamento entre contas, sessão vencida e CSRF. Eles usam
um banco temporário e um vídeo falso gerado pelo FFmpeg, então não precisam de rede nem gastam tokens. São mais
lentos, por isso ficam desligados no `pytest` comum:
```bash
python -m playwright install chromium     # uma vez (~150 MB)
# cmd: set E2E=1 | PowerShell: $env:E2E="1" | bash: export E2E=1
pytest tests/test_e2e_navegador.py
```
