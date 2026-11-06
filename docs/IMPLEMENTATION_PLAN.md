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
| B5 | ✅ Concluído (06/11), aguardando commit | `app/models.py` (`Deck.usuario_id`, `UNIQUE(usuario_id, nome)`, `Usuario.decks` ↔ `Deck.usuario`), `migrations/versions/0003_posse_dos_decks.py` (batch, nomes explícitos, trava para Decks sem dono), `app/services/decks.py` (`nome_unico`/`resumo_dos_decks` por usuário), `app/api/decks.py` (`usuario_atual` no router; dono conferido em `_deck`/`_card` → 404), `app/migrar.py` (`__main__` delega ao módulo canônico), `tests/conftest.py` (`app_de_teste`, `entrar_como`), `tests/test_api_decks.py` (só uma fixture; corpo dos 11 testes intacto), `tests/test_isolamento.py` (6 testes), `tests/test_migracoes.py` (legado sem Decks + recusa com Decks + teste do comando real), `tests/test_api_auth.py` (teste do B4 atualizado), README | SQLite: 89 passed, 1 skipped (inclui teste do CLI). **Postgres: 90 passed** (inclui up/down da 0003). Ruff limpo. Trava legada verificada nos dois bancos (versão fica em 0002, nada alterado). HTTP real com duas contas no Postgres de dev: anônimo 401; Bruno 404 em revisar/deletar/avaliar o que é da Ana; "Inglês" nas duas contas. | (1) `python -m app.migrar` mostrava traceback em vez da mensagem: o módulo era carregado duas vezes (`__main__` e `app.migrar`), com duas classes `BancoIncompativel`. Corrigido e coberto por teste (que falha sem a correção). (2) **A trava D3 disparou no banco de dev do usuário:** um Deck "te" com 1 Card, criado na validação do B4. Por decisão do usuário (06/11), ele foi **apagado**. O backup `dados/backup/postgres-antes-0003.dump` foi feito antes. | B6 — Etapa A |
| B6–B16 | Pendente | — | — | — | — |
