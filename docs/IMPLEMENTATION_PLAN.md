# Shadowing 2.0 — Plano de implementação

Documento vivo: plano, decisões, critérios de aceitação e progresso de cada bloco.
**Ao começar uma sessão nova:** leia este arquivo, confira `git status` / `git log` e rode `pytest` antes de continuar.

- Branch de trabalho: `Membro4`
- Escopo autorizado: requisitos de setembro, outubro e novembro. O sistema de agosto (decks, cards, revisão
  espaçada) é a base funcional e não deve ser reescrito.
- Regra de trabalho: um bloco por vez. Cada bloco segue: explicar → aprovar → implementar → validar → relatório.
  Um commit por bloco validado, e só com autorização.

---

## Baseline (Fase 0 — 06/11/2026)

| Item | Estado |
|---|---|
| Git | `Membro4` em `3dac9b8`, working tree limpo |
| Testes | `pytest`: **55 passed**, cobertura 79% |
| Lint | `ruff check .`: sem avisos |
| Banco real | `dados/estudos.db`: 0 decks, 0 cards, 1 entrada de dicionário |
| Ambiente | Python 3.14.4 (venv), Docker 29.9, FFmpeg instalado |

---

## Decisões registradas

| # | Data | Decisão | Motivo |
|---|---|---|---|
| D1 | 06/11 | Seguir na branch `Membro4` | Decisão do usuário |
| D2 | 06/11 | Tolerância temporal (`TOLERANCIA_RITMO = 0.15` em `gravador.js`) **fica como constante**. O requisito Out-2 não será implementado. | Decisão do usuário |
| D3 | 06/11 | O banco local vazio é a realidade: **não há dados legados para migrar**. A migração é só do esquema. | Decisão do usuário. Se aparecerem decks sem dono, a migração falha com uma mensagem clara (não inventa dono). |
| D4 | 06/11 | **PostgreSQL antes dos usuários** | O SQLite não altera restrições (UNIQUE de `deck.nome`, FK nova). O isolamento deve ser testado no banco de destino. Com o banco vazio, a troca cedo é barata. |
| D5 | 06/11 | Erros: **422** continua para erro de validação de schema; **400** para regra de negócio. Todas as respostas de erro usam o mesmo corpo. | Padrão do FastAPI; os testes atuais usam 422 |
| D6 | 06/11 | Sessão no servidor: token aleatório no cookie (HttpOnly, SameSite=Lax, Secure em produção) e só o hash do token no banco | Permite logout de verdade (revogar a sessão) |
| D7 | 06/11 | Login obrigatório em decks e cards (B5) e legendas (B11). As rotas de conteúdo (vídeo, áudio, waveform, palavras, avaliação, dicionário) só são protegidas no **B13**, depois das features. | Proteger tudo cedo misturaria auth com o desenvolvimento de waveform e legendas (fetch cru, `<video src>`, fixtures de teste) |
| D8 | 06/11 | Testes automáticos continuam em SQLite temporário. Nos blocos de banco, a suíte também roda no Postgres (`TEST_DATABASE_URL`). | Ciclo rápido sem depender de Docker |
| D9 | 06/11 | `Card` não recebe `user_id`: o dono é deduzido pelo caminho Card → Deck → User | Uma única fonte da verdade |
| D10 | 06/11 | Plataforma de deploy: a decidir no B16 | O usuário não tem preferência |
| D11 | 06/11 | Sem `DATABASE_URL`, o padrão continua sendo o SQLite. O Postgres é o ambiente recomendado, ativado pelo `.env`. | Decisão do usuário: quem não tem Docker continua rodando sem configurar nada |
| D13 | 06/11 | Todas as páginas exigem login (inclusive o início e o estudo), menos `/login` e `/cadastro` | Proposto no B6 e aprovado: o app é por conta |
| D14 | 06/11 | CSRF por verificação de `Origin` (middleware) + `SameSite=Lax`, sem token CSRF | Recomendação OWASP; não exige mudar cada formulário/fetch |
| D16 | 07/11 | Corrigir o bug do download de vídeo apagado como bloco separado (B9.1) | Decisão do usuário (opção A): afeta a revisão de agosto |
| D17 | 07/11 | Controle de volume ao lado da velocidade, salvo na conta (B9.2) | Pedido do usuário, fora do escopo original; salvar na conta escolhido pelo usuário |
| D15 | 06/11 | Configurações de estudo em tabela própria 1:1 (`usuario_id` como PK), linha criada sob demanda, padrões no código; velocidade entregue no HTML da página e salva por `PATCH` com atraso | Separa identidade de preferências; o vídeo já abre na velocidade certa; evita um salvamento por passo do slider |
| D12 | 06/11 | No Postgres não há backup automático no `migrar`: `pg_dump` manual em dev, snapshot do provedor em produção (revisar no B14/B16) | O backup automático exigiria `pg_dump` instalado ou acesso ao container, o que não é portátil |

---

## Mapa de dependências

```
B1 Config/.env ─► B2 Alembic ─► B3 PostgreSQL (dev)
                                   │
                                   ▼
                    B4 User + sessão + cadastro/login (API)
                      │            │              │
                      ▼            ▼              ▼
            B5 Posse/isolamento  B6 Telas auth  B8 Configurações de estudo
                      │
B7 Erros padronizados ─► B11 Tokens por usuário + feedback 429
B9 Waveform (peaks + cache)     B10 Legendas automáticas + aviso
B12 Empty states ─► B13 Proteção das rotas de conteúdo
                      │
                      ▼
B14 Dockerfile + compose + /health ─► B15 Testes integrados em Postgres ─► B16 Deploy
```

---

## Blocos

| ID | Bloco | Requisitos | Arquivos previstos | Depende de | Critérios de aceitação |
|---|---|---|---|---|---|
| B0 | Documento do plano | Documentação | `docs/IMPLEMENTATION_PLAN.md` | — | O arquivo existe e está atualizado |
| B1 | Configuração por ambiente | Nov-4 (antecipado) | `app/config.py`, `app/db.py`, `.env.example`, `.gitignore` | — | `DATABASE_URL` e `SECRET` vêm do ambiente ou de `.env`. Sem `.env`, o app usa o SQLite atual. 55 testes passam. |
| B2 | Alembic com o esquema atual como baseline | Set-9/10 (prep.) | `alembic.ini`, `migrations/`, `app/main.py`, README | B1 | A migração inicial é idêntica ao esquema atual. Há backup antes de qualquer `upgrade`. |
| B3 | PostgreSQL no desenvolvimento | Set-9, Nov-3 (parcial) | `docker-compose.yml` (só o `db`), `requirements.txt`, `tests/conftest.py` | B2 | `upgrade head` funciona no Postgres. A suíte passa em SQLite e em Postgres. O SQLite original fica intacto. |
| B4 | User, hash Argon2, sessão, cadastro/login/logout, `current_user` | Set-1,3,4,5,6,7 | `models.py`, `services/auth.py`, `api/auth.py`, `schemas.py`, migração, testes | B3 | E-mail único. Hash Argon2. Cookie HttpOnly. Logout revoga a sessão. `GET /api/me`. Credencial errada → 401. |
| B5 | Posse dos decks e isolamento | Set-2,8,10 | `models.py`, `services/decks.py`, `api/decks.py`, migração, `conftest.py`, `test_isolamento.py` | B4 | Rotas de deck/card exigem login. Recurso de outro usuário → 404. Nome único por usuário. Asserções de agosto inalteradas. |
| B6 | Telas de login/cadastro e proteção das páginas | Set-3,4,7 (front) | `templates/paginas/login.html`, `cadastro.html`, `base.html`, `api/paginas.py`, `api.js`, CSS | B4 | Sem sessão → tela de login. Um 401 redireciona ao login. A navbar mostra o usuário e o botão Sair. Verificação de `Origin` (CSRF). |
| B7 | Padronização de erros | Out-10 | `app/erros.py`, `main.py`, `api/*.py`, `api.js`, testes | — | O corpo `{"detail", "codigo"}` vale para todos os códigos. 5xx sem stack exposta. |
| B8 | Configurações individuais de estudo (velocidade) | Out-1,3 (Out-2: ver D2) | `models.py`, `api/configuracoes.py`, `player.js`, `estudo.js`, `revisao.js`, migração, testes | B4, B6 | A velocidade persiste por usuário, sobrevive a F5, logout e restart, e cada usuário tem a sua |
| B9 | Waveform: peaks JSON + metadados + cache | Out-4,5,6 | `models.py`, `services/waveform.py`, `api/videos.py`, `waveform.js`, `estudo.js`, migração, testes | B3 | Peaks calculados uma vez, guardados com `versao_algoritmo`. Cache hit sem FFmpeg. Clique, arraste e cursor preservados. |
| B10 | Legendas automáticas em inglês + tela de aviso | Out-7,8 | `services/youtube.py`, `services/legendas.py`, `estudo.html`, `estudo.js`, testes | B7 | Variantes `en-*` aceitas. Tela de aviso para legenda não manual. Vídeos com legenda manual sem mudança. |
| B11 | Tokens por usuário + feedback quando acabam | Out-9, Nov-9 (parcial) | `api/legendas.py`, `interface.js`, `estudo.js`, testes | B4, B7 | Limite por conta. O 429 traz `Retry-After` e o tempo restante. O front mostra uma mensagem específica. Cache hit não gasta token. |
| B12 | Empty states | Out-11 | `decks.js`, `escolha-deck.js`, `revisao.js`, `estudo.js`, CSS | B6 | Cada área vazia tem mensagem e ação. Checklist de regressão integrado (Out-12). |
| B13 | Proteção das rotas de conteúdo | D7 | `api/videos.py`, `api/avaliacoes.py`, `api/dicionario.py`, `waveform.js`, `player.js`, testes | B4..B12 | Sem sessão → 401. Front trata o 401 nesses caminhos. Testes atualizados. |
| B14 | Dockerfile, compose completo, `/health` | Nov-1,3,4,5 | `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `api/health.py`, README | B3 | `docker compose up` do zero funciona. `/health` responde 200 ou 503. Nenhum secret versionado. |
| B15 | Testes integrados em Postgres | Nov-8,9 | `tests/test_isolamento.py`, `tests/test_tokens.py`, instruções | B5, B11, B14 | A suíte passa no Postgres do compose. Isolamento em todas as rotas. Tokens independentes por conta. |
| B16 | Deploy, testes em produção e correções | Nov-2,6,7,10 | Configuração da plataforma, README | B14, B15, D10 | O app roda em produção com Postgres. O roteiro de testes de produção é executado e registrado. |

Out-12 (integração ao fluxo existente) é validado dentro de cada bloco de outubro e no checklist final do B12.

---

## Cronograma (7 dias)

| Dia | Blocos | Prioridade |
|---|---|---|
| 1 | B0, B1, B2, B3 | Essencial |
| 2 | B4 | Essencial |
| 3 | B5, B6 | Essencial (fecha o MVP de setembro) |
| 4 | B7, B8, B11 | Importante |
| 5 | B9, B10 | Importante |
| 6 | B12, B13, B14, B15 | B14/B15 essenciais; B12/B13 importantes |
| 7 | B16 + folga + documentação | Pode ser adiado |

Ordem de corte, se faltar prazo: B12 → B10 (tela de aviso) → B9. Todo corte é registrado aqui.

---

## Estratégia de testes

- Em cada bloco: testes novos, a suíte completa (regressão), `ruff check .` e revisão do diff.
- Agosto: as asserções de `tests/test_api_decks.py` não mudam. A partir do B5, só a fixture passa a entregar um usuário logado.
- Auth: dois usuários (A/B) em todas as rotas protegidas; sessão ausente, expirada ou revogada; senha errada.
- Persistência: o mesmo banco reaberto por um engine novo (equivale a um restart) e um restart manual.
- Frontend: sem testes JS no projeto; cada bloco traz um roteiro manual.
- Produção: só se declara "testado em produção" depois do roteiro executado no ambiente real.

## Estratégia de migração

1. Antes de todo `upgrade`: cópia de `dados/estudos.db` para `dados/backup/`. O SQLite original nunca é apagado.
2. O Alembic é a única fonte de mudanças de esquema. O primeiro migration é o baseline; um banco existente recebe `alembic stamp`.
3. Mudanças de esquema e de dados ficam em migrations separados. Não há dados legados (D3).
4. Depois de cada `upgrade`: `alembic check` e testes contra o banco migrado.

---

## Pendências fora do escopo (registradas, não implementadas)

- A cache de legendas guarda **um único vídeo** para todos os usuários (`dados/ultimo_video.json`). Com várias
  contas, um vídeo tira o outro da cache e o usuário gasta token de novo.
- O limitador de tokens, os downloads em andamento e os resultados do karaokê ficam **em memória do processo**:
  zeram a cada restart e exigem um único worker em produção.
- Não há limite de tentativas de login (força bruta). O Argon2 encarece cada tentativa, mas não há bloqueio. (B4)
- O cadastro revela, com o 409, que um e-mail já tem conta. Evitar isso exigiria confirmação por e-mail. (B4)
- **B16 (atenção):** a verificação de `Origin` (`app/seguranca.py`) compara com o header `Host`. Atrás de um proxy
  reverso que reescreva o `Host`, todo POST legítimo receberia 403. No deploy, preservar o `Host` no proxy ou
  configurar o host público.
- ~~**BUG pré-existente (achado no B9): vídeo apagado pela limpeza nunca é baixado de novo.**~~ **Corrigido no B9.1.**
  `midia._limpar_antigos` mantém só os 5 vídeos mais recentes. Mas `midia.iniciar_download` só refaz o download se
  a tarefa anterior **falhou**, e uma tarefa concluída com sucesso continua no registro em memória `_downloads`.
  Voltar a um vídeo apagado faz o `/status` responder "não pronto, sem falha" para sempre, e o player fica em
  "Baixando o vídeo... 0%" até reiniciar o servidor. **Afeta a revisão de agosto** (cards de vídeos antigos).
  Reproduzido isolado em 07/11. Veio da reorganização do projeto (`3dac9b8`), antes deste trabalho. Correção
  sugerida (pequena): refazer também quando a tarefa terminou mas o arquivo não existe mais.
- Tabela `waveform` cresce sem limite (~3 KB por frase; ~3 MB a cada mil frases). Sem limpeza por enquanto. (B9)
- Rota `GET /api/videos/{id}/audio` sem uso interno desde o B9: candidata a remoção. (B9)
- `docs/metricas.txt` está desatualizado (cita `cache.py`/`database.py`).
- 🔎 Risco: o YouTube pode bloquear o yt-dlp a partir de IPs de datacenter (afeta o B16).

---

## Progresso

| ID | Status | Arquivos modificados | Testes | Problemas | Próxima ação |
|---|---|---|---|---|---|
| B0 | ✅ Concluído (06/11) | `docs/IMPLEMENTATION_PLAN.md` | — | — | — |
| B1 | ✅ Concluído e commitado (`3e15e30`) | `app/config.py` (classe `Configuracoes`, `DATABASE_URL`), `app/db.py` (engine pela URL, `opcoes_de_conexao`), `.env.example`, `.gitignore` (`.env`), `requirements.txt` (`pydantic-settings` explícito), `tests/test_config.py` | 60 passed (55 + 5 novos); ruff limpo; boot real com uvicorn (`/`, `/api/decks`, `/api/tokens` → 200); troca de banco via variável e via `.env` verificada | Nenhum. Decisão: só `DATABASE_URL` por enquanto (a sessão do B4 não precisa de chave secreta, ver D6) | B2 — Etapa A |
| B2 | ✅ Concluído e commitado (`7f073bb`) | `alembic.ini`, `migrations/env.py`, `migrations/script.py.mako`, `migrations/versions/0001_baseline.py`, `app/migrar.py` (novo), `app/db.py` (sem `create_all`), `app/main.py` (startup só verifica a versão), `tests/conftest.py`, `tests/test_migracoes.py` (7 testes), `requirements.txt` (`alembic==1.20.1`), README (seção "Banco de dados e migrações") | 67 passed; ruff limpo; fluxo completo numa **cópia** do `estudos.db` real (recusa → migrar com backup + stamp → idempotente → boot 200); o banco real continua recusado até o usuário rodar `python -m app.migrar` | (1) O backup ia para `dados/backup` mesmo migrando outro arquivo: corrigido, agora vai para `backup/` ao lado do banco. (2) Faltava `path_separator` no `alembic.ini` (no Windows, `C:` era quebrado em `:`): corrigido. | B3 — Etapa A |
| B3 | ✅ Concluído e commitado (`494a8c3`) | `docker-compose.yml` (serviço `db`, postgres:17, porta só em 127.0.0.1, volume, healthcheck), `docker/postgres/init.sql` (banco `shadowing_teste`), `requirements.txt` (`psycopg[binary]==3.3.8`), `.env.example`, `tests/conftest.py` (`TEST_DATABASE_URL` + trava `*_teste` + fixture `url_banco_externo_teste`), `tests/test_migracoes.py` (+1 teste up/down no Postgres), `app/migrar.py` (mensagem de backup do Postgres), README (seção Postgres, backup/restauração, testes). **Nenhuma regra de `app/` mudou.** | SQLite: 67 passed, 1 skipped. **Postgres: 68 passed.** Ruff limpo. App no Postgres: migrar (idempotente) → criar deck/card → restart do app e do container → dados preservados. `pg_dump`/`pg_restore` testados (bash e PowerShell). Trava contra banco não-teste testada. | (1) `localhost` no Windows tenta IPv6 `::1` primeiro, e cada conexão travava (8 s com timeout, indefinido sem): as URLs passaram a usar `127.0.0.1`. (2) O `>` do PowerShell 5.1 corrompe o dump binário: a documentação usa `pg_dump -f` dentro do container + `docker compose cp`. | B4 — Etapa A |
| B4 | ✅ Concluído e commitado (`3ff287e`) | `app/models.py` (`Usuario`, `Sessao`), `app/services/auth.py` (novo: Argon2id, cadastro, autenticação com tempo constante, rehash, sessões com SHA-256), `app/api/auth.py` (novo: cadastro/login/logout/me + `usuario_atual` + `APIKeyCookie`), `app/schemas.py` (`NovoUsuario`, `Credenciais`, `UsuarioPublico`), `app/config.py` (`AMBIENTE`, `COOKIE_SESSAO`, `DURACAO_SESSAO_DIAS`), `app/main.py`, `migrations/versions/0002_usuarios_e_sessoes.py`, `tests/conftest.py` (fixture `engine_teste`), `tests/test_api_auth.py` (13 testes), `tests/test_config.py` (+1), `requirements.txt` (`argon2-cffi==25.1.0`), `.env.example`, README (seção "Contas e login", backup no Git Bash) | SQLite: 81 passed, 1 skipped. **Postgres: 82 passed.** Ruff limpo. HTTP real com uvicorn no Postgres de dev: cadastro → me → logout → me 401 → login errado (genérico) → login com e-mail em maiúsculas → me. Hash `$argon2id$v=19$m=65536,t=3,p=4` conferido no banco. | O comando de backup do README falhava no **Git Bash** (converte `/tmp/...` em caminho do Windows), e por isso a migração 0002 do banco de dev rodou **sem backup**. Sem impacto: o banco estava sem dados e a 0002 só cria tabelas. README corrigido (`MSYS_NO_PATHCONV=1`) e backup pós-migração feito e restaurado com sucesso. | B5 — Etapa A |
| B5 | ✅ Concluído e commitado (`12a0b93`) | `app/models.py` (`Deck.usuario_id`, `UNIQUE(usuario_id, nome)`, `Usuario.decks` ↔ `Deck.usuario`), `migrations/versions/0003_posse_dos_decks.py` (batch, nomes explícitos, trava para Decks sem dono), `app/services/decks.py` (`nome_unico`/`resumo_dos_decks` por usuário), `app/api/decks.py` (`usuario_atual` no router; dono conferido em `_deck`/`_card` → 404), `app/migrar.py` (`__main__` delega ao módulo canônico), `tests/conftest.py` (`app_de_teste`, `entrar_como`), `tests/test_api_decks.py` (só uma fixture; corpo dos 11 testes intacto), `tests/test_isolamento.py` (6 testes), `tests/test_migracoes.py` (legado sem Decks + recusa com Decks + teste do comando real), `tests/test_api_auth.py` (teste do B4 atualizado), README | SQLite: 89 passed, 1 skipped (inclui teste do CLI). **Postgres: 90 passed** (inclui up/down da 0003). Ruff limpo. Trava legada verificada nos dois bancos (versão fica em 0002, nada alterado). HTTP real com duas contas no Postgres de dev: anônimo 401; Bruno 404 em revisar/deletar/avaliar o que é da Ana; "Inglês" nas duas contas. | (1) `python -m app.migrar` mostrava traceback em vez da mensagem: o módulo era carregado duas vezes (`__main__` e `app.migrar`), com duas classes `BancoIncompativel`. Corrigido e coberto por teste (que falha sem a correção). (2) **A trava D3 disparou no banco de dev do usuário:** um Deck "te" com 1 Card, criado na validação do B4. Por decisão do usuário (06/11), ele foi **apagado**. O backup `dados/backup/postgres-antes-0003.dump` foi feito antes. | B6 — Etapa A |
| B6 | ✅ Concluído e commitado (`1dcd139`) | `app/api/paginas.py` (todas as páginas exigem login; 303 ou `HX-Redirect` para `/login?proximo=`; `caminho_seguro` contra open redirect; `Cache-Control: no-store`), `app/api/auth.py` (`usuario_opcional`), `app/seguranca.py` (novo: verificação de `Origin` em POST/PUT/PATCH/DELETE → 403), `app/main.py`, `templates/base.html` (navbar com e-mail + Sair; sem botões quando deslogado), `templates/paginas/login.html` e `cadastro.html` (novos), `static/js/paginas/auth.js` (novo), `static/js/nucleo/api.js` (401 → login; `api.auth`), `static/js/main.js` (Sair), `static/js/nucleo/interface.js`, `static/css/auth.css` (novo), `tests/test_paginas.py` (21), `tests/test_csrf.py` (7), `tests/test_e2e_navegador.py` (4, opt-in `E2E=1`), `requirements-dev.txt` (`playwright==1.64.1`), README | SQLite e Postgres: suíte completa (ver relatório). **Navegador real (Chromium):** 4 testes E2E passaram em 5 execuções seguidas: cadastro → /decks → criar Deck → revisar (Fácil) → excluir Card → Sair → voltar → login errado/certo; isolamento entre contas; sessão vencida → login; CSRF real (logout forçado de outra origem). **Mutação:** sem o middleware, só os 7 testes de CSRF falham. Capturas de tela conferidas (escuro e claro). | (1) Um teste de CSRF com `text/plain` não provava nada (o FastAPI já recusa corpo não-JSON): trocado pelo vetor real (logout forçado, sem corpo). (2) **Corrida com `autofocus`:** em conteúdo inserido pelo HTMX, o Chrome aplica o autofocus no quadro seguinte e roubava o foco da senha (o texto ia para o e-mail). Corrigido com foco síncrono via JS. | B7 — Etapa A |
| B7 | ✅ Concluído e commitado (`42208ea`) | `app/erros.py` (novo: `CODIGOS`, `ErroDaApi`, `resposta_de_erro`, handlers de `HTTPException` e 422, middleware `capturar_erros_inesperados`), `app/main.py` (registro; capturador como middleware mais externo), `app/api/legendas.py` (429 via `ErroDaApi`, `codigo=limite_de_tokens`), `app/seguranca.py` (403 via `resposta_de_erro`, `codigo=origem_nao_permitida`), `static/js/nucleo/api.js` (`erro.codigo`), `tests/test_erros.py` (14 testes), 3 testes com o corpo exato atualizados (`codigo` acrescentado), README (seção "Formato dos erros da API") | Ver relatório. 500 conferido num uvicorn real: resposta genérica e **um único** registro de log com a stack. | (1) Com o handler de `Exception`, o Starlette relançava o erro e o uvicorn registrava a stack de novo: trocado por um middleware capturador. (2) A ordem dos middlewares estava invertida no primeiro rascunho (no Starlette, o último adicionado é o mais externo): corrigida e coberta por teste (erro dentro do middleware de CSRF também vira 500 padrão). (3) **Teste de navegador intermitente** (1 falha em ~10): era a mesma corrida de foco do B6, que a correção anterior só tinha tornado mais rara. O HTMX inicia a página após o "settle" (~20 ms), e o `focus()` do auth.js podia tirar o foco de quem já digitava. Corrigido no app (o foco só acontece se nenhum campo do formulário está focado). Investigando, achei uma **falha de segurança**: um envio antes de o JS assumir faria GET com a **senha na URL**. Corrigido com `method="post"` e o botão desabilitado até o JS estar pronto, com teste. O E2E espera o formulário ficar pronto antes de digitar. Resultado: 20 rodadas sob carga sem falha. Uma mutação removendo só a proteção do foco não reproduziu a falha em 8 rodadas, porque a corrida é rara; a causa foi estabelecida pela análise e pela captura de tela da falha. | B8 — Etapa A |
| B8 | ✅ Concluído e commitado (`6baf17d`) | `app/models.py` (`ConfiguracaoEstudo`, 1:1), `migrations/versions/0004_configuracoes_de_estudo.py`, `app/config.py` (faixa de velocidade), `app/schemas.py` (`AlteracaoConfiguracoes` com `extra="forbid"` e recusa de `null`; `ConfiguracoesDeEstudo`), `app/services/configuracoes.py` e `app/api/configuracoes.py` (novos: GET/PATCH), `app/main.py`, `app/api/paginas.py` (velocidade no HTML de estudo/revisão), `templates/paginas/estudo.html` e `revisao.html` (`data-velocidade`), `static/js/componentes/player.js` (**só acréscimos**: velocidade inicial em `criar`, `aoMudarVelocidade`), `static/js/componentes/gravador.js` (`atualizarTempoEsperado`), `static/js/nucleo/configuracoes.js` (novo: salvamento com atraso de 500 ms), `nucleo/api.js`, `paginas/estudo.js` e `revisao.js`, `app/erros.py` (tradução de `extra_forbidden`), `tests/test_api_configuracoes.py` (14), `tests/test_e2e_navegador.py` (+1), README | Ver relatório. **E2E de velocidade:** slider muda vídeo, rótulo e timer na hora; um arraste = 1 salvamento; recarregar mantém 0.75x (vídeo, slider, rótulo, timer); duplo clique volta a 1x e salva; sair da página logo depois ainda salva. 6 rodadas sob carga sem falha. **Mutações:** ignorar a velocidade salva → falha; não recalcular o timer → falha. Postgres de dev migrado para 0004 (com `pg_dump` antes). | (1) `PATCH {"velocidade": null}` daria 500: "opcional" passou a significar "pode não vir", não "pode ser null" (422, com teste). (2) A mensagem de campo desconhecido vinha em inglês: traduzida no `erros.py`. (3) A 1ª frase/Card é preparada antes de o player existir: o timer do gravador mostraria o tempo em 1x. Corrigido com `Gravador.atualizarTempoEsperado()`, que também atualiza o timer quando o slider muda com o gravador parado, seguindo o comportamento documentado no próprio gravador. | B11 — Etapa A (ou B9, conforme o usuário) |
| B11 | ✅ Concluído e commitado (`cc325cf`) | `app/api/legendas.py` (login no router; chave `usuario:<id>`; `situacao_dos_tokens`, `tempo_legivel`; 429 com `limite`, `tentar_novamente_em` e `Retry-After`; `GET /api/tokens` com `limite` e `renova_em`), `app/schemas.py` (`Tokens`; `Legendas.renova_em`), `app/config.py`, `templates/paginas/estudo.html` (modal "Seus tokens acabaram" e aviso de último token), `static/css/modais.css`, `static/js/nucleo/interface.js` (`formatarTempo`, `contagemRegressiva`, dica e atualização automática do contador), `static/js/main.js`, `static/js/paginas/estudo.js`, `tests/test_tokens.py` (12, limitador real), `tests/test_api_legendas.py` (fixture logada; fake com `reset_time`; corpo dos testes intacto), `tests/test_erros.py` (429 ampliado), `tests/test_e2e_navegador.py` (YouTube simulado no servidor de teste; +2 testes: **primeiro E2E da página de estudo**, que também cobre a velocidade salva do B8, e renovação dos tokens), README (seção "🎟️ Tokens") | Ver relatório. **Mutação:** com a chave igual para todos (como o IP de uma rede compartilhada), o teste de contas independentes falha. E2E: 7 testes, 5 rodadas sob carga sem falha. | (1) A mensagem proposta ("vídeos já carregados continuam disponíveis") era falsa, porque a cache guarda só o último vídeo do app: trocada por "revise seus Decks", que é verdade. (2) A primeira tentativa de mutação não foi aplicada (erro no `sed`); refeita corretamente. | B9 — Etapa A |
| B9 | ✅ Concluído e commitado (`263711c`) | `app/models.py` (`Waveform`, peaks em coluna JSON, índice único com a versão), `migrations/versions/0005_waveform.py`, `app/config.py` (`WAVEFORM_*`), `app/services/waveform.py` (novo: `calcular_peaks` com numpy, cache no banco, validação de integridade, concorrência), `app/api/videos.py` (`GET /waveform`; `/audio` mantido, sem uso interno), `app/schemas.py` (`WaveformDoTrecho`), `static/js/componentes/waveform.js` (**só a obtenção dos dados mudou**; clique, arraste, cursor e falha intactos), `nucleo/api.js` (`urlWaveform`), `paginas/estudo.js` (pré-carrega a onda), `tests/test_waveform.py` (12), `tests/test_e2e_navegador.py` (+1; estado de downloads isolado por teste), README (seção "🌊 Waveform") | Ver relatório. **Antes/depois no navegador, mesmo roteiro:** clique a 60% → vídeo em 1,5 s e cursor em 60% nos dois; captura visualmente igual; **sem** pedido ao WAV depois. Protótipo confirmou que o WaveSurfer 8 desenha e pinta o progresso só com peaks. Karaokê, legenda, gravador, player e avaliação **não foram tocados** (`git status`). Postgres de dev migrado para 0005 (com `pg_dump` antes). | **Bug pré-existente encontrado** (não corrigido, fora do escopo, aguardando decisão): ver Pendências, "Vídeo apagado pela limpeza nunca é baixado de novo". | Decisão sobre o bug → B10 — Etapa A |
| B9.1 | ✅ Concluído e commitado (`a1d0b9b`) | `app/services/midia.py` (`iniciar_download` também refaz o download quando a tarefa terminou mas o arquivo foi apagado pela limpeza), `tests/test_api_videos.py` (+2: regressão do bug e "download em andamento não é duplicado") | O teste de regressão **falhava antes da correção** e passa depois. A mesma reprodução isolada que mostrou o bug agora baixa de novo. | Bug pré-existente (de `3dac9b8`), corrigido por decisão do usuário (opção A). | — |
| B9.2 | ✅ Concluído e commitado (`e2d6fa0`) | **Pedido do usuário (fora do escopo original, autorizado em 07/11):** controle de volume ao lado da velocidade, salvo na conta. `app/config.py` (`VOLUME_PADRAO`), `app/models.py` (`ConfiguracaoEstudo.volume`), `migrations/versions/0006_volume_nas_configuracoes.py` (coluna com `server_default` 1.0), `app/schemas.py`, `app/services/configuracoes.py`, `app/api/paginas.py` (`data-volume`), `templates/partials/player.html` (grupo velocidade + volume), `templates/paginas/estudo.html` e `revisao.html`, `static/css/player.css` (mesmo estilo do slider de velocidade), `static/js/componentes/player.js` (**só acréscimos**: volume, mudo, `aoMudarVolume`), `static/js/nucleo/configuracoes.js` (velocidade e volume no mesmo PATCH com atraso), `paginas/estudo.js` e `revisao.js`, `tests/test_api_configuracoes.py` (+6; 11 comparações do B8 ganharam `"volume"`), `tests/test_e2e_navegador.py` (+1; 2 comparações do B8 ajustadas), README | E2E: posição ao lado da velocidade, travado até "Iniciar Estudos", slider muda vídeo/rótulo/ícone na hora, mudo e volta, duplo clique em 100%, velocidade + volume num salvamento só, recarregar mantém os dois. Capturas nos temas escuro e claro. Postgres de dev migrado para 0006 (com `pg_dump` antes): configurações existentes preservadas, volume 100%. | Em 1280 px de largura, a barra passa a ter duas linhas (transporte em cima, velocidade + volume embaixo). **Ajuste pedido pelo usuário (07/11): visual do volume idêntico ao da velocidade** (decidido manter ícones de fonte): barra 150 px, ícone 15 px sem caixa de botão, largura fixa (sem o slider "pular" ao trocar de ícone), sem ficar apagado quando travado, contorno de foco só pelo teclado. Medido antes e depois; o teste E2E compara as medidas dos dois controles. **Ajuste final (07/11), aprovado pelo usuário:** na barra fica só o alto-falante; o slider e o percentual aparecem numa caixa acima ao passar o mouse ou focar pelo teclado, para a barra do estudo caber numa linha em 1280 px (sobravam ~60 px). O E2E verifica a linha única **no estudo** (a barra mais larga) e espera as fontes de ícones carregarem antes de comparar medidas. | B10 — Etapa A |
| B10 | ✅ Concluído (07/11), aguardando commit | `app/services/youtube.py` (`eh_ingles`, `codigos_em_ingles`; `baixar_legendas` escolhe manual em qualquer `en-*` antes da automática e devolve o idioma; karaokê aceita `en-*`), `app/services/legendas.py` e `cache_legendas.py` (`idioma_legenda`, cache antiga lida como `"en"`), `app/api/legendas.py`, `app/schemas.py`, `templates/paginas/estudo.html` (tela "Este vídeo não tem legenda manual"), `static/js/paginas/estudo.js` (`mostrarAvisoDaLegenda`), `static/css/modais.css`, `tests/test_legendas_ingles.py` (22), `tests/test_e2e_navegador.py` (+1), falsos de `test_api_legendas.py`/`test_tokens.py`/E2E adaptados (lista percorrível e 3 valores; asserções intactas), README (seção "📝 Legendas") | Ver relatório. Captura da tela de aviso conferida. | O código "en-US" quebrava no hífen na tela de aviso: corrigido com `nowrap`. | B12 — Etapa A |
| B12–B16 | Pendente | — | — | — | — |
