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

Cada pessoa tem uma conta (e-mail + senha), e **cada Deck pertence a uma conta**. Ninguém vê nem altera os Decks
de outra pessoa.

**A API inteira exige login** (desde o B13). Sem sessão, toda rota `/api/...` responde 401 (`nao_autenticado`). Ficam
abertos só: `/api/auth/*` (cadastro, login, logout, me), as páginas `/login` e `/cadastro`, os arquivos `/static` e a
documentação `/docs`. Isso inclui as rotas mais caras do servidor: vídeo (o `/status` **inicia download** no
YouTube), onda, áudio, karaokê (FFmpeg/Vosk), avaliação da fala e dicionário (Wiktionary). O teste
`tests/test_protecao_api.py` percorre **todas as rotas registradas** e exige o 401. Uma rota nova criada sem
proteção quebra o teste, a menos que seja incluída de propósito em `ROTAS_PUBLICAS`.

**Na interface:**
- **Todas as páginas exigem login**, menos `/login` e `/cadastro`. Quem abre uma página sem estar logado vai para
  `/login?proximo=<página>` e, depois de entrar, volta para ela.
- A navbar mostra o e-mail da conta e o botão **Sair**.
- Se a sessão vencer no meio do uso, a próxima ação leva ao login e depois de volta à mesma página. Isso vale
  também para os dois caminhos que não passam pelo `api.js`: a onda (agora via `requisitarJSON`) e o arquivo do
  vídeo (no erro do `<video>`, o player reconsulta o `/status`, que leva ao login se a sessão venceu).
- Como funciona (`app/api/paginas.py`): sem sessão, quem abre a URL direto recebe um redirecionamento 303. Na
  navegação pelo HTMX, o servidor responde com o header `HX-Redirect`. No front, um 401 da API (`requisitarJSON`
  em `static/js/nucleo/api.js`) também leva ao login.
- **A senha nunca vai na URL:** os formulários de login e cadastro são `method="post"`, e o botão só habilita quando
  o JS assume o envio. Sem isso, um envio antes de o JS carregar usaria GET, e a senha iria para o histórico e
  para os logs do servidor.
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

## 🗒️ Telas vazias (empty states)

Quando uma área não tem nada para mostrar, ela diz **por quê** e oferece **a próxima ação**. O componente é
`static/js/componentes/estado-vazio.js`.

| Onde | Mensagem | Ações |
|---|---|---|
| Dashboard de Decks, conta sem Decks | "Você ainda não tem Decks" e como os Cards nascem (marcador 🔖 no estudo) | **Estudar um vídeo** · **Criar Deck** |
| Dashboard, erro ao carregar | "Não foi possível carregar os seus Decks." | **Tentar de novo** |
| Revisão de um Deck sem Cards | "Este Deck ainda não tem Cards" | **Estudar um vídeo** · **Voltar aos Decks** |
| Revisão de um Deck em dia | "Tudo revisado! 🎉 Próxima revisão deste Deck: em 3 dias (10/11)" | **Voltar aos Decks** · **Estudar um vídeo** |
| Modal "Escolher Deck" (salvar Card), sem Decks | "Você ainda não tem Decks. Use “Criar Deck” abaixo." | (botão do próprio modal) |
| Modal "Escolher Deck", filtro sem resultado | "Nenhum Deck com “xyz”." | — |
| Estudo, legenda sem frases | Explica o motivo provável e sugere outro vídeo | (botão "início" do modal) |

A data da próxima revisão vem do resumo dos Decks: `GET /api/decks` traz `proxima_revisao`, a data mais próxima
entre os Cards já revisados, ou `null`. A página de revisão só consulta o resumo quando não há Cards para revisar.
O fim de uma revisão continua como no sistema de agosto (aviso "Você finalizou a revisão…" e volta ao dashboard).

## 📝 Legendas (manuais e automáticas, em qualquer variante de inglês)

O app estuda vídeos com legenda em **inglês**, em qualquer variante: `en`, `en-US`, `en-GB`, `en-CA`... (código
`en` ou começando com `en-`; ver `app/services/youtube.py`).

**Qual legenda é usada** (em ordem):
1. **Manual** (escrita por uma pessoa), em qualquer variante de inglês: `en` primeiro, depois as variantes em ordem
   alfabética. Uma manual `en-GB` vence uma automática `en`, porque é mais precisa.
2. Sem manual: **automática** (gerada pelo YouTube), na mesma ordem.
3. Nenhuma em inglês: erro 404 "O vídeo não possui nenhuma legenda em inglês disponível."

A ordem é fixa, então o mesmo vídeo sempre dá a mesma escolha. A resposta de `GET /api/legendas` informa
`legenda_manual` (true/false) e `idioma_legenda` (ex.: `"en-GB"`). O idioma também fica na cache. Caches antigas,
sem esse campo, são lidas como `"en"`, sem invalidar nada e sem gastar token.

**Vídeo sem legenda manual:** o estudo mostra a tela **"⚠️ Este vídeo não tem legenda manual"**. Ela explica que a
legenda automática pode ter palavras erradas ou faltando e que a divisão em frases e a pontuação são menos
precisas, e mostra o idioma e o título. Os botões são **Estudar mesmo assim** e **Escolher outro vídeo** (volta ao
início). O token já foi gasto quando a tela aparece, porque a legenda já veio do YouTube. Com legenda manual,
aparece o aviso de sempre (tipo, idioma e título).

**Karaokê** (tempo de cada palavra): usa a legenda automática do YouTube em `en-orig` (o reconhecimento de fala
original), senão `en`, senão qualquer outra variante `en-*` (ordem alfabética).

**Testes:** `tests/test_legendas_ingles.py` (escolha da legenda, karaokê, cache antiga) e o teste de navegador
`test_video_sem_legenda_manual_mostra_a_tela_de_aviso`.

## 🎟️ Tokens (limite de vídeos novos por conta)

Buscar as legendas de um vídeo no YouTube custa: muitas consultas seguidas fazem o YouTube bloquear o servidor.
Por isso, cada **conta** pode carregar um número limitado de vídeos **novos** por janela de tempo.

| | |
|---|---|
| **Limite** | 5 tokens a cada 5 minutos, por conta (`LIMITE_TOKENS` em `app/config.py`) |
| **Gasta 1 token** | Carregar um vídeo que não está na cache. Inclui vídeo **sem legenda**: a consulta ao YouTube aconteceu, e é ela que o limite protege. Devolver o token permitiria consultar o YouTube sem limite usando vídeos sem legenda. |
| **Não gasta** | Vídeo que está na cache (hoje, o último vídeo carregado no app), URL inválida, navegar entre frases, revisar Decks |
| **De quem é** | Da conta logada (chave `usuario:<id>`), e não do IP. Pessoas na mesma rede (casa, laboratório) não dividem tokens, e trocar de rede não dá tokens novos. |
| **Algoritmo** | Janela fixa (`FixedWindowRateLimiter`, biblioteca `limits`). No primeiro uso, começa uma janela de 5 minutos. Quando ela termina, os 5 tokens voltam todos juntos. O requisito chama isso de "Token Bucket": para quem usa, o comportamento é o de tokens que se renovam. |
| **Onde fica** | Em memória do processo: zera quando o servidor reinicia e exige um único processo (worker) em produção (pendência registrada no plano). |

**Na tela:**
- A navbar mostra os tokens restantes. Em zero, o contador fica vermelho. Ao passar o mouse aparece "Tokens renovam
  em 4:12", e ao fim da contagem o contador se atualiza sozinho.
- Ao carregar o vídeo que gasta o **último** token, o aviso da legenda avisa: "Este foi seu último token. Novos
  tokens em 4:12."
- **Sem tokens**, o estudo mostra a tela "Seus tokens acabaram", com contagem regressiva, botão **Ir para os Decks**
  (a revisão não gasta tokens) e **Voltar ao início**. O botão **Carregar o vídeo** só aparece quando a contagem
  termina. O limite é informado, **nunca contornado**: nada é tentado de novo sozinho.

**API** (ambas exigem login):
- `GET /api/tokens` → `{"tokens_restantes": 3, "limite": 5, "renova_em": 252}`. `renova_em` é o número de
  segundos até a janela recomeçar, ou `null` se nenhum token foi gasto.
- `GET /api/legendas?url=...` → além das legendas, traz `tokens_restantes` e `renova_em`. Sem tokens, responde
  **429** (formato abaixo) com o header **`Retry-After`** (segundos), o padrão HTTP para "tente de novo depois".

**Testes:** `tests/test_tokens.py` usa o limitador real, com contas independentes, 429 com o tempo, cache e vídeo
sem legenda. Os testes de navegador cobrem a tela "Seus tokens acabaram" e a renovação, numa janela curta.

## 🌊 Waveform (onda da frase)

A onda azul acima do microfone é o áudio original da frase. Ela é desenhada a partir de **peaks**: uma lista de
números de 0 a 1 (o volume de cada pedacinho da frase), calculada **uma vez** no servidor e guardada no banco.

```
1ª vez:  GET /api/videos/{id}/waveform?inicio&fim → vídeo + FFmpeg (8 kHz) → numpy: 400 peaks → grava no banco
depois:  GET /api/videos/{id}/waveform?inicio&fim → lê do banco ("cache": true), sem vídeo e sem FFmpeg
tela:    WaveSurfer.create({peaks, duration, ...}) → desenha; o progresso e o cursor acompanham o vídeo
```

| | Antes (até o B8) | Agora (B9) |
|---|---|---|
| O que o navegador baixa por frase | O WAV inteiro (~88 KB por segundo) | ~3 KB de JSON (400 números) |
| Quem calcula a onda | O navegador, a cada visita | O servidor, uma vez por frase |
| Onde fica | WAV em `dados/midia`, apagado junto com o vídeo | Tabela `waveform` no banco: sobrevive à limpeza dos vídeos |
| Segunda visita | Baixa e decodifica de novo | Vem pronta, sem FFmpeg |

**Como os peaks são calculados** (`app/services/waveform.py`): o áudio do trecho (mono, 8 kHz) é dividido em 400
blocos iguais, e cada peak é o maior volume do bloco, normalizado pelo maior volume do trecho (silêncio = só zeros).
400 é aproximadamente o máximo de barras que cabem no painel (barra de 2 px + espaço de 1 px).

**Banco: tabela `waveform`.** Colunas `video_id`, `inicio`, `fim` (2 casas), `versao`, `duracao`, `quantidade`,
`peaks` (JSON) e `data_criacao`. O índice único é `(video_id, inicio, fim, versao)`. A onda não pertence a um
usuário: a de um trecho é a mesma para todos.

**Compatibilidade do cache:**
- A **versão do algoritmo** (`WAVEFORM_VERSAO_ALGORITMO` em `app/config.py`) faz parte da chave. Mudou o cálculo
  (quantidade de peaks, taxa, fórmula)? **Aumente a versão**: as ondas antigas deixam de ser usadas e cada uma é
  recalculada na próxima visita, sem migração de dados.
- Ao ler, o servidor confere se `quantidade` bate com o tamanho de `peaks`. Um registro incompleto é recalculado.
- Duas requisições da mesma frase ao mesmo tempo: o índice único recusa a segunda gravação, e ela usa a da primeira.

**O que não mudou:** o visual da onda (cores, barras, altura), **clicar ou arrastar na onda leva o vídeo àquele
ponto**, o cursor vermelho e a cor de progresso acompanham o vídeo, e a mensagem aparece no lugar da onda se ela
não carregar. O karaokê, o gravador e a avaliação da fala não usam a onda e não foram alterados.

**Rota antiga:** `GET /api/videos/{id}/audio` (o WAV) continua existindo, mas ficou sem uso interno. É candidata a
remoção.

**Testes:** `tests/test_waveform.py` (cálculo, cache sem FFmpeg, versão, registro corrompido, concorrência e
erros) e o teste de navegador `test_onda_vem_pronta_do_servidor_e_clicar_nela_leva_o_video_ao_ponto`.

## ⚙️ Configurações de estudo

Cada conta tem as próprias preferências de estudo, salvas no banco. Por isso elas acompanham a pessoa em qualquer
navegador e sobrevivem a F5, logout e reinício do servidor.

| Preferência | Como muda | Faixa | Padrão |
|---|---|---|---|
| **Velocidade do vídeo** | Slider da barra do player (duplo clique volta para 1x), no estudo e na revisão | 0.25x a 1.5x | 1x |
| **Volume do vídeo** | Controle ao lado da velocidade: slider (duplo clique volta para 100%) e o alto-falante, que liga e desliga o mudo | 0% a 100% | 100% |

- **Na tela:** o estudo e a revisão já abrem na velocidade e no volume salvos (eles vêm no HTML da página,
  `data-velocidade` e `data-volume`). O vídeo, os controles e o timer do gravador começam neles. Ao mexer num
  controle, a mudança vale na hora e é salva cerca de meio segundo depois de parar (um arraste inteiro = um
  salvamento; mexer na velocidade e no volume em seguida = um salvamento com os dois). Sair da página logo depois
  também salva.
- **Volume:** o ícone acompanha o nível (sem som, baixo, alto). Clicar nele silencia; clicar de novo volta ao volume
  de antes. Os dois controles ficam travados até "Iniciar Estudos". O volume é só o do vídeo: ouvir a própria
  gravação não é afetado. Em janelas mais estreitas, velocidade e volume descem juntos para uma segunda linha da
  barra.
- **API:** `GET /api/configuracoes` → `{"velocidade": 1.0, "volume": 1.0}` (os padrões, se a pessoa nunca salvou
  nada). `PATCH /api/configuracoes` com `{"volume": 0.4}` (ou `velocidade`, ou os dois) altera **só os campos
  enviados** e devolve todas as configurações. Valor fora da faixa, `null` ou campo desconhecido → 422 (veja o formato dos erros abaixo).
- **Banco:** tabela `configuracaoestudo`, 1:1 com `usuario` (`usuario_id` é a chave primária, então há no máximo uma
  linha por usuário). A linha nasce no primeiro salvamento; até lá, valem os padrões
  (`app/services/configuracoes.py`). Preferência nova = uma coluna com valor padrão, sem migração de dados. Foi
  assim com o volume (migração `0006`): as linhas que já existiam ganharam volume 100% sozinhas.
- **Tolerância temporal** (o critério de "no ritmo" do gravador, 15%) continua fixa no código
  (`TOLERANCIA_RITMO` em `static/js/componentes/gravador.js`), por decisão do projeto.

## 🤖 LLM e desafios com IA (Reading, Writing, Speaking)

As três atividades novas (Reading, Writing e Speaking Challenge) usam um **serviço único de LLM**:
`app/services/llm.py`. Ele é **base compartilhada**: os Membros 1 a 3 usam, não alteram (ver `CLAUDE.md`).

**Configuração (`.env`).** Funciona com qualquer provedor que tenha a API no formato da OpenAI. Trocar de provedor é
só mudar o `.env`; o código das features não muda.

| Variável | Padrão | Para que serve |
|---|---|---|
| `LLM_CHAVE` | vazia | Chave do provedor. **Sem ela, o app sobe normalmente**; só as funções de IA respondem 503 |
| `LLM_BASE_URL` | Gemini (`https://generativelanguage.googleapis.com/v1beta/openai/`) | Endereço da API |
| `LLM_MODELO` | `gemini-flash-latest` | Nome do modelo (confira no painel do provedor) |
| `LLM_TIMEOUT_SEGUNDOS` | 60 | Espera máxima por uma resposta |
| `LLM_MODO_JSON` | true | Pede resposta em JSON ao provedor (`response_format`) |

Decisão da equipe (reunião de 07/11): **Gemini Flash gratuito no desenvolvimento** (cada membro cria a própria chave
em https://aistudio.google.com/apikey, nunca no Git) e **Gemini Flash pago no deploy**. A LLM roda só pela API do
servidor: o usuário final não instala nada.

**Como usar numa feature.** Os prompts ficam no serviço da feature; o `llm.py` não sabe nada de Reading, Writing ou
Speaking:
```python
from pydantic import BaseModel, Field
from app.services import llm

class Perguntas(BaseModel):
    perguntas: list[str] = Field(min_length=5, max_length=5)

resultado = llm.gerar_json(sistema="Crie 5 perguntas de compreensão...", usuario=texto, modelo=Perguntas)
resultado.perguntas   # já validado pelo Pydantic
```
- `gerar_json(sistema, usuario, modelo, temperatura=0.2, max_tokens=None)`: manda o schema do `modelo` junto das
  instruções, valida a resposta e devolve o objeto. Resposta fora do formato: **uma** nova tentativa, mostrando os
  erros ao modelo. Timeout e falha de rede não são repetidos.
- A chamada é **bloqueante** (segundos): use em rotas `def` (não `async def`) ou com `asyncio.to_thread`.
- `configurada()`: há chave? `modelo_em_uso()`: nome do modelo, para gravar junto do resultado.
- Falhas viram o erro padrão da API sozinhas (tabela abaixo). Para reagir antes (ex.: marcar a tentativa como
  "erro na avaliação"), capture `llm.ErroLLM`, grave o estado e relance com `raise`.

| Exceção | Status | `codigo` |
|---|---|---|
| `LLMNaoConfigurada` | 503 | `llm_nao_configurada` |
| `LLMIndisponivel` (rede, provedor fora, chave recusada, limite do provedor) | 502 | `llm_indisponivel` |
| `LLMTempoEsgotado` | 504 | `llm_tempo_esgotado` |
| `LLMRespostaInvalida` (2 respostas fora do formato) | 502 | `llm_resposta_invalida` |

Mensagem própria: `raise llm.LLMTempoEsgotado("A correção demorou. A sua redação foi salva; tente de novo.")`.

**Cota diária (decisão da equipe: 10 desafios por dia).** Cada conta pode iniciar 10 desafios por dia **em cada
feature** (`LIMITE_DESAFIOS_LLM` em `app/config.py`). A dependência vai **só na rota que cria o desafio**:
```python
from app.api.llm import exigir_cota

@router.post("/challenges", dependencies=[Depends(exigir_cota("reading"))])   # "reading", "writing" ou "speaking"
```
Acabou: 429 `limite_de_desafios`, com `desafios_restantes`, `limite`, `tentar_novamente_em` e o header `Retry-After`.
Mesmo algoritmo dos tokens de legenda: janela de 24 h a partir do primeiro desafio, em memória (zera ao reiniciar).
O desafio é contado ao ser criado, mesmo que a LLM falhe depois.

**Aviso de privacidade (decisão da equipe).** O texto (ou a transcrição da fala) vai para um provedor externo de IA.
Toda tela de desafio mostra o aviso **antes** do envio:
```javascript
import { criarAvisoIA } from "../componentes/aviso-ia.js";
const { aviso, configurada, cotas } = await api.situacaoLLM();   // GET /api/llm/situacao
raiz.querySelector(".area-do-aviso").append(criarAvisoIA(aviso));
```
`GET /api/llm/situacao` devolve também se a IA está configurada e as cotas de cada feature (`restantes`, `limite`,
`renova_em`), para a tela mostrar "7 de 10 desafios hoje".

**Testes: nunca chamam a LLM de verdade.** A fixture automática `llm_desligada` reprova qualquer teste que tente. Para
simular respostas, use a fixture `llm_falsa` (`tests/conftest.py`), que passa pela validação real:
```python
def test_gera_perguntas(llm_falsa, entrar_como):
    llm_falsa.responder({"perguntas": ["a", "b", "c", "d", "e"]})   # dict, objeto Pydantic ou texto cru
    llm_falsa.responder("isto não é JSON")                          # para testar a resposta inválida
    llm_falsa.falhar(llm.LLMTempoEsgotado())                       # para testar o timeout
    ...
    assert len(llm_falsa.chamadas) == 1                            # mensagens enviadas em cada chamada
```
Exemplos completos em `tests/test_llm.py`.

## ⚠️ Formato dos erros da API

**Toda** resposta de erro da API (status 4xx e 5xx) é um JSON com o mesmo formato:

```json
{
  "detail": "Deck não encontrado.",
  "codigo": "nao_encontrado"
}
```

| Campo | Tipo | Para que serve |
|---|---|---|
| `detail` | texto, sempre | Mensagem para a **pessoa**, em português. É o que a interface mostra. A redação pode mudar. |
| `codigo` | texto, sempre | Identificador para **programas** (o front, testes, integrações). Estável: use-o para decidir o que fazer. |
| extras | opcional | Campos a mais, no mesmo nível, só quando o erro precisa (veja abaixo). |

### Códigos

| Status | `codigo` | Quando acontece (exemplos) | Extras |
|---|---|---|---|
| 400 | `requisicao_invalida` | URL do YouTube inválida, intervalo de áudio inválido, gravação ilegível | — |
| 401 | `nao_autenticado` | Sem login ou sessão vencida; e-mail ou senha incorretos | — |
| 403 | `origem_nao_permitida` | POST/PATCH/DELETE vindo de outro site (proteção contra CSRF) | — |
| 403 | `acesso_negado` | Padrão para outros 403 (nenhuma rota usa hoje) | — |
| 404 | `nao_encontrado` | Deck/Card inexistente **ou de outra conta**; palavra não encontrada; rota que não existe | — |
| 405 | `metodo_nao_permitido` | Método HTTP errado para o endereço (ex.: `DELETE /api/decks`) | header `Allow` |
| 409 | `conflito` | E-mail já cadastrado; Card repetido no mesmo Deck | — |
| 413 | `conteudo_grande_demais` | Gravação maior que 10 MB | — |
| 422 | `dados_invalidos` | Corpo, parâmetro da URL ou formulário fora do formato esperado | `erros` |
| 429 | `limite_de_tokens` | Tokens de legenda acabaram (veja "Tokens") | `tokens_restantes`, `limite`, `tentar_novamente_em`; header `Retry-After` |
| 429 | `limite_atingido` | Padrão para outros 429 (nenhuma rota usa hoje) | — |
| 500 | `erro_interno` | Qualquer erro **inesperado** (bug). A resposta nunca traz detalhes internos | — |
| 500 | `erro_interno` | Erros conhecidos de processamento (ex.: FFmpeg falhou), com mensagem própria | — |
| 429 | `limite_de_desafios` | Cota diária de desafios com IA acabou (veja "LLM") | `desafios_restantes`, `limite`, `tentar_novamente_em`; header `Retry-After` |
| 502 | `servico_externo_indisponivel` | YouTube ou dicionário fora do ar / bloqueando | — |
| 502 | `llm_indisponivel` | Provedor de IA fora do ar, chave recusada ou limite do provedor | — |
| 502 | `llm_resposta_invalida` | A IA respondeu duas vezes fora do formato esperado | — |
| 503 | `llm_nao_configurada` | Servidor sem `LLM_CHAVE` | — |
| 503 | `servico_indisponivel` | Padrão para outros 503 (nenhuma rota usa hoje) | — |
| 504 | `llm_tempo_esgotado` | A IA não respondeu em `LLM_TIMEOUT_SEGUNDOS` | — |
| 504 | `tempo_esgotado` | Padrão para outros 504 (nenhuma rota usa hoje) | — |

### Exemplos

**422, dados inválidos.** O `detail` resume os problemas em uma frase. Em `erros`, vem um item por campo.
O status continua 422, o padrão do FastAPI para dados fora do formato (decisão D5 do plano).
```json
{
  "detail": "Dados inválidos: email: e-mail inválido; senha: mínimo de 8 caracteres.",
  "codigo": "dados_invalidos",
  "erros": [
    {"campo": "email", "mensagem": "e-mail inválido"},
    {"campo": "senha", "mensagem": "mínimo de 8 caracteres"}
  ]
}
```
`campo` é o nome do campo no corpo, na URL ou no formulário. É `"corpo"` quando o problema é o corpo inteiro (ex.:
não foi enviado).

**429, tokens esgotados** (com o header `Retry-After: 252`; `tentar_novamente_em` é o mesmo valor, em segundos):
```json
{"detail": "Seus tokens acabaram. Novos tokens em 4 min 12 s. Enquanto isso, você pode revisar seus Decks (a revisão não gasta tokens).",
 "codigo": "limite_de_tokens", "tokens_restantes": 0, "limite": 5, "tentar_novamente_em": 252}
```

**500, erro inesperado.** É sempre esta mesma resposta, de propósito:
```json
{"detail": "Erro interno. Tente novamente em instantes.", "codigo": "erro_interno"}
```
A exceção, a rota e a stack completa vão para o **log do servidor** (`ERROR: Erro inesperado em GET /api/...`),
em um único registro. Detalhes internos (caminhos, SQL, versões) numa resposta ajudariam um atacante.

### No front-end

`requisitarJSON` (`static/js/nucleo/api.js`) transforma qualquer erro numa exceção com:
- `erro.message`: o `detail`, pronto para mostrar;
- `erro.status`: o status HTTP;
- `erro.codigo`: o `codigo` (**use este para decidir o que fazer**, ex.: `if (erro.codigo === "limite_de_tokens")`);
- `erro.dados`: o corpo inteiro, com os extras (`erro.dados.tokens_restantes`, `erro.dados.erros`).

O 401 fora de `/api/auth/` não chega a virar exceção: leva direto ao login.

### Para quem cria rotas

```python
from fastapi import HTTPException
from app.erros import ErroDaApi

raise HTTPException(404, "Vídeo não encontrado.")      # codigo vem do status: "nao_encontrado"
raise ErroDaApi(429, "Seus tokens acabaram.", codigo="limite_de_tokens", tokens_restantes=0)  # codigo/extras próprios
```
- **Não monte `JSONResponse` de erro à mão.** Os handlers de `app/erros.py` padronizam tudo. A única exceção são
  os middlewares, que não passam pelos handlers e usam `resposta_de_erro(...)` do mesmo módulo.
- **Não capture `Exception` só para devolver 500.** Deixe o erro subir: o capturador registra no log e responde no
  formato padrão. Capture apenas erros **esperados** (ex.: `VideoIndisponivel` → 502) e dê a eles uma mensagem útil.
- Código novo? Acrescente em `CODIGOS` (`app/erros.py`), nesta tabela e num teste em `tests/test_erros.py`.

**Onde está:** `app/erros.py` (handlers e o capturador de erros inesperados) e `tests/test_erros.py` (um teste por
status, mais um teste que prova que o 500 não vaza detalhes e registra a stack).

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
├── erros.py          # formato único dos erros da API ({detail, codigo}) e captura de erros inesperados
├── schemas.py        # formatos de entrada/saída da API
├── api/              # camada HTTP: rotas finas, que validam e chamam os serviços
│   ├── paginas.py      páginas HTML (navegação via HTMX)
│   ├── auth.py         cadastro, login, logout, /me e as dependências usuario_atual / usuario_opcional
│   ├── configuracoes.py configurações de estudo do usuário (velocidade)
│   ├── legendas.py     legendas + limite de tokens por conta (429 com Retry-After)
│   ├── videos.py       vídeo, onda (waveform) e áudio de cada frase e tempo das palavras
│   ├── avaliacoes.py   avaliação da fala gravada
│   ├── decks.py        Decks, Cards e revisão espaçada (REST)
│   ├── dicionario.py   popup de dicionário
│   └── llm.py          desafios com IA: cota diária por conta (exigir_cota) e aviso de privacidade
├── services/         # regras de negócio, sem FastAPI (testáveis isoladamente)
│   ├── auth.py         hash de senha (Argon2id), contas e sessões
│   ├── configuracoes.py padrões e salvamento das configurações de estudo
│   ├── youtube.py      tudo o que fala com o YouTube (legendas em qualquer variante de inglês, título, download, legenda automática)
│   ├── legendas.py     legendas da cache ou do YouTube
│   ├── cache_legendas.py
│   ├── frases.py       reagrupa os blocos do YouTube em frases e estima o tempo das palavras
│   ├── midia.py        download do vídeo em segundo plano e corte do áudio (FFmpeg)
│   ├── waveform.py     peaks da onda de cada frase (numpy) e cache no banco
│   ├── karaoke.py      escolhe a melhor fonte de tempo das palavras
│   ├── alinhamento.py  legenda automática / Vosk → tempo de cada palavra
│   ├── avaliacao.py    notas de palavras, ritmo e entonação da fala do usuário
│   ├── dicionario.py   spaCy + Wiktionary
│   ├── decks.py        nomes únicos, dashboard e intervalo da revisão espaçada
│   └── llm.py          serviço ÚNICO de LLM (qualquer provedor no formato da OpenAI), usado pelos desafios
├── templates/        # base.html, paginas/, partials/
└── static/
    ├── css/            um arquivo por assunto (base, inicio, player, painel, legenda, modais, decks)
    └── js/             ES modules
        ├── main.js       ponto de entrada
        ├── nucleo/       cliente da API, interface global, ciclo de vida das páginas, tema, configurações
        ├── componentes/  player, legenda (karaokê + dicionário), waveform, gravador, avaliação, escolha de Deck, estado vazio, aviso de IA
        └── paginas/      auth (login e cadastro), estudo, decks, revisao
migrations/           # Alembic: env.py e versions/ (uma migração por mudança no esquema)
docker/postgres/      # init.sql: cria o banco de testes no container do Postgres
docker-compose.yml    # PostgreSQL local para desenvolvimento (docker compose up -d db)
.env.example          # modelo das variáveis de ambiente (copie para .env)
tests/                # um arquivo por módulo (pytest)
docs/                 # plano de implementação (IMPLEMENTATION_PLAN.md), guias dos membros (guias/) e métricas
CLAUDE.md             # regras de trabalho com o Claude Code (base protegida, processo por blocos)
README_MEMBRO{N}.md   # documentação de cada feature nova, mantida pelo próprio membro (na branch dele)
```

## 👥 Trabalho em equipe (Membros 1 a 4)

- **Membro 1:** Reading Challenge · **Membro 2:** Speaking Challenge · **Membro 3:** Writing Challenge ·
  **Membro 4:** base do Shadowing, `llm.py`, integração (merge) e Docker/deploy (B14–B16).
- Cada membro trabalha **na própria branch**, criada a partir da `Membro4`, e não altera a base (lista em
  `CLAUDE.md`, "Base protegida"). O teste `tests/test_base_protegida.py` falha se um arquivo central mudar.
- Cada um documenta a sua feature em `README_MEMBRO{N}.md` (não neste README) e segue o guia
  `docs/guias/MEMBRO{N}_*.md`. Para começar com o Claude Code: `docs/guias/PROMPT_INICIAL.md`.

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
