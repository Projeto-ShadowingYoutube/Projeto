# Membro 3 — Writing Challenge + Rewrite Challenge

> Documentação da feature do Membro 3 (branch `Membro3`, criada a partir da `Membro4` no commit `49636dd`).
> Regras do trabalho: `CLAUDE.md`. Guia da feature: `docs/guias/MEMBRO3_WRITING.md`. Nada desta feature vai no
> `README.md`.

## Visão geral

O **Writing Challenge** treina a escrita em inglês no formato das provas TOEFL e IELTS: a pessoa escolhe uma categoria
(ou "Surpresa"), recebe um tema sorteado e escreve uma redação com contador de palavras, timer regressivo e
salvamento automático. Ao enviar, uma IA corrige o texto em cinco categorias (gramática, vocabulário, coerência,
organização e atendimento à tarefa), com nota, comentário e os trechos problemáticos destacados no próprio texto.

O **Rewrite Challenge** vem depois da correção: o sistema escolhe até 3 trechos problemáticos, dá uma instrução de
reescrita para cada um, compara a versão original com a reescrita (palavra a palavra) e a IA avalia se melhorou. O
histórico original → feedback → reescritas fica guardado, e o texto original nunca é sobrescrito.

## Como usar

_(preenchido a partir do W4, quando a tela existir)_

Para a correção por IA funcionar localmente, coloque a **sua** chave do Gemini em `LLM_CHAVE` no `.env` (crie em
https://aistudio.google.com/apikey; nunca no Git). Sem ela, o app sobe normalmente e a correção responde 503
(`llm_nao_configurada`). Os testes **não** precisam da chave.

## Arquitetura

_(atualizada a cada bloco)_

Arquivos previstos (todos novos, com o nome da feature):

| Camada | Arquivos |
|---|---|
| Modelos | `app/models_writing.py` |
| Schemas (entrada/saída e contrato da LLM) | `app/schemas_writing.py` |
| Rotas (`/api/writing/...` e página `/writing`) | `app/api/writing.py` |
| Regras de negócio | `app/services/writing_temas.py`, `writing_texto.py`, `writing_desafios.py`, `writing_llm.py`, `writing_rewrite.py` |
| Migrações | `migrations/versions/0301_*.py` (esquema), `0302_*.py` (temas iniciais) |
| Tela | `app/templates/paginas/writing.html`, `app/static/js/paginas/writing.js`, `app/static/js/nucleo/api-writing.js`, `app/static/css/writing.css` |
| Testes | `tests/writing/` |

Pontos de encaixe usados (só o bloco `Membro 3 (Writing)` de cada um): `app/models.py`, `app/main.py`,
`app/static/js/main.js`, `app/templates/base.html` (CSS e botão da navbar).

Fluxo: tela (`writing.js`) → `api-writing.js` (`requisitarJSON`/`enviarJSON`) → `app/api/writing.py` (login, dono,
cota) → `services/writing_*.py` → banco (SQLModel) e LLM (`llm.gerar_json`, prompts em `writing_llm.py`).

## API

Todas as rotas exigem login (`APIRouter(prefix="/api/writing", dependencies=[Depends(usuario_atual)])`; sem sessão →
401, coberto pelo `tests/test_protecao_api.py` da base). Redação de outra conta responde **404**, igual a uma
inexistente (dependência `_tentativa` em `app/api/writing.py`).

| Rota | Entrada | Saída | Erros próprios |
|---|---|---|---|
| `GET /api/writing/categorias` | — | lista de `{slug, nome, prova, tempo_limite_segundos, palavras_minimas}` | — |
| `POST /api/writing/challenges` | `{categoria?}` (sem corpo ou `null` = "Surpresa") | **201** + redação | 422 · 429 `limite_de_desafios` (base) · 503 `sem_temas` |
| `GET /api/writing/attempts` | — | as 50 redações mais recentes da conta (`id, estado, categoria, categoria_nome, palavras, iniciada_em, enviada_em`) | — |
| `GET /api/writing/attempts/{id}` | — | redação | 404 |
| `PATCH /api/writing/attempts/{id}` (autosave) | `{texto}` (máx. 10.000 caracteres) | `{palavras, salva_em, segundos_restantes}` | 404 · 409 `redacao_ja_enviada` · 409 `prazo_encerrado` · 422 |
| `POST /api/writing/attempts/{id}/submissao` | `{texto}` (máx. 10.000 caracteres) | redação (com `usou_ultimo_salvamento`) | 404 · 409 `redacao_ja_enviada` · 422 `redacao_curta` · 422 |

**Redação (resposta):** `id, estado, categoria, categoria_nome, enunciado, tempo_limite_segundos, palavras_minimas,
texto, palavras, iniciada_em, prazo, segundos_restantes, salva_em, enviada_em, usou_ultimo_salvamento`.
`segundos_restantes` vem do relógio do servidor (o timer da tela parte dele). Datas no horário de Brasília, sem fuso.

**Entradas com `extra="forbid"`:** campos além dos documentados (ex.: `estado`) → 422. Estado, prazo e palavras nunca
vêm do cliente.

**Regras de tempo (D2):** até 30 s depois do prazo, tudo funciona. Depois: autosave → 409 `prazo_encerrado` (não
grava); envio → ignora o texto recebido e envia o último autosave (`usou_ultimo_salvamento: true`).

### Códigos de erro próprios (`codigo`)

Criados com `ErroDaApi(..., codigo=...)`, sem alterar `app/erros.py`. Testados em `tests/writing/test_api_desafio.py`.

| Status | `codigo` | Quando | Extras |
|---|---|---|---|
| 409 | `redacao_ja_enviada` | Autosave ou novo envio de uma redação que já saiu do rascunho | — |
| 409 | `prazo_encerrado` | Autosave depois do prazo + 30 s | — |
| 422 | `redacao_curta` | Envio com menos de 50 palavras (inclusive o último autosave, depois do prazo: D10) | `palavras`, `minimo` |
| 503 | `sem_temas` | Nenhum tema ativo na categoria (ou em nenhuma, na "Surpresa") | — |

Os demais (`nao_encontrado`, `dados_invalidos`, `nao_autenticado`, `limite_de_desafios`) são os da base.

## Banco de dados

Faixa de migrações do Membro 3: `0301`, `0302`, … A primeira tem `down_revision = "0006"`.

```
usuario ──1:N──► writingattempt ──N:1──► writingprompt   (tema: compartilhado, sem dono)
                      │
                      └──1:1──► writingfeedback ──1:N──► writingrewrite
```

| Tabela | Campos | Restrições |
|---|---|---|
| `writingprompt` | `categoria` (índice), `enunciado`, `tempo_limite_segundos`, `palavras_minimas`, `ativo` | — |
| `writingattempt` | `usuario_id`, `prompt_id`, `texto`, `estado`, `palavras`, `iniciada_em`, `prazo`, `salva_em`, `enviada_em`, `avaliacoes_tentadas` | `fk_writingattempt_usuario_id_usuario`, `fk_writingattempt_prompt_id_writingprompt`; índices em `usuario_id` e `prompt_id` |
| `writingfeedback` | `attempt_id`, `notas` (JSON), `nota_geral`, `resumo`, `trechos` (JSON), `modelo`, `versao_prompt`, `criado_em` | `fk_writingfeedback_attempt_id_writingattempt`; **`uq_writingfeedback_attempt`** (um feedback por tentativa) |
| `writingrewrite` | `feedback_id`, `rodada`, `indice_trecho`, `trecho_original`, `instrucao`, `reescrita`, `avaliacao` (JSON), `modelo`, `versao_prompt`, `criado_em` | `fk_writingrewrite_feedback_id_writingfeedback`; **`uq_writingrewrite_rodada_trecho`** (`feedback_id`, `rodada`, `indice_trecho`); índice em `feedback_id` |

- **Estados da tentativa** (`app/models_writing.py`): `rascunho` → `enviada` → `avaliada` ou `erro_avaliacao`.
  Validados no código (sem `CHECK` no banco, como no resto do projeto).
- **`prazo`** é gravado ao criar (início + tempo do tema): mudar o tema depois não afeta tentativas abertas (D2).
- **O diff da reescrita não é gravado**: é calculado ao ler (`difflib`), a partir de dois textos que nunca mudam.

| Migração | Tipo | O que faz |
|---|---|---|
| `0301_writing_challenge.py` | esquema | Cria as 4 tabelas (só tabelas novas). FKs nomeadas à mão (o autogenerate as gera sem nome) |
| `0302_writing_temas_iniciais.py` | dados | 24 temas originais (4 por categoria), dados congelados na própria migração. Downgrade apaga só esses temas e **recusa** (sem alterar nada) se algum estiver em uso por uma redação |

### Categorias (`app/services/writing_temas.py`)

| Slug | Nome na tela | Inspiração | Tempo | Mín. palavras |
|---|---|---|---|---|
| `ielts_opiniao` | Opinião | IELTS Writing Task 2 | 40 min | 250 |
| `ielts_discussao` | Discussão de dois lados | IELTS Writing Task 2 | 40 min | 250 |
| `ielts_problema_solucao` | Problema e solução | IELTS Writing Task 2 | 40 min | 250 |
| `ielts_vantagens` | Vantagens e desvantagens | IELTS Writing Task 2 | 40 min | 250 |
| `toefl_discussao_academica` | Discussão acadêmica | TOEFL (Academic Discussion) | 10 min | 100 |
| `toefl_independente` | Preferência pessoal | TOEFL (Independent Writing) | 30 min | 300 |

- **Sorteio:** `sortear_tema(session, categoria=None)`: tema ativo ao acaso (`func.random()` no banco); `None` =
  "Surpresa" (qualquer categoria). Sem tema ativo → `None`; categoria desconhecida → `ValueError`.
- **Contagem de palavras** (`app/services/writing_texto.py`, `contar_palavras`): sequência de letras ou números, com
  apóstrofo ou hífen só no meio; texto normalizado (NFC). Python `[^\W_]+(?:['’\-][^\W_]+)*`, JS (W4)
  `/[\p{L}\p{N}]+(?:['’-][\p{L}\p{N}]+)*/gu`. Ex.: `I don't agree.` = 3, `well-known` = 1, `word — word` = 2.

## Decisões

| ID | Data | Decisão | Motivo |
|---|---|---|---|
| D1 | 21/11/2026 | Notas de **0 a 10 (inteiro) por categoria**; a nota geral é a **média calculada pelo servidor** | Mais legível na tela; a média não depende de a LLM fazer contas certo |
| D2 | 21/11/2026 | No fim do timer, o front envia sozinho. Após o **prazo + 30 s de tolerância**, o servidor recusa o autosave e **envia o último texto salvo**, ignorando o que chegar | Ninguém perde a redação, e ninguém ganha tempo burlando o timer da tela |
| D3 | 21/11/2026 | **Mínimo de 50 palavras** para enviar; **máximo de 10.000 caracteres**. O mínimo do tema (ex.: 250) não bloqueia, só pesa no "atendimento à tarefa" | Evita gastar LLM com textos de teste; protege banco e custo |
| D4 | 21/11/2026 | "Avaliar de novo" após falha: **até 3 vezes por tentativa**. Rewrite: **até 3 problemas**, avaliados **numa chamada só**, **até 2 rodadas por redação** | A cota diária só conta a criação; sem limites, uma redação geraria chamadas sem fim |
| D5 | 21/11/2026 | A pessoa escolhe a **categoria** ou "**Surpresa**" (categoria aleatória); o tema dentro dela é sempre sorteado | Controle para treinar uma prova sem perder o sorteio |
| D6 | 21/11/2026 | Comentários e explicações **em português**; citações e sugestões de reescrita **em inglês** | Mais didático para quem está aprendendo |
| D7 | 21/11/2026 | Avaliação **síncrona**: a submissão grava o texto, chama a LLM e devolve o resultado | Padrão do projeto (rotas `def`); fila assíncrona seria mais código e risco sem ganho real |
| D8 | 21/11/2026 | **Um commit por bloco** (W0 = este plano, depois W1 … W10), feito pelo usuário, só com a suíte inteira e o `ruff` verdes, verificados antes de cada commit | Histórico organizado; cada commit deixa a branch funcionando |

| D9 | 21/11/2026 | A cota usa o padrão do `CLAUDE.md`: `Depends(exigir_cota("writing"))` na rota `POST /challenges`. Uma requisição inválida (422) ou sem tema (503) **também gasta 1 desafio** | A dependência roda antes da validação do corpo (confirmado num experimento). Seguir o padrão mantém as três features iguais para o Membro 4; a tela só envia categorias vindas de `GET /categorias`, e com 24 temas não falta tema |
| D10 | 21/11/2026 | Tempo acabou e o último autosave tem menos de 50 palavras → **422 `redacao_curta`**; a redação fica como rascunho vencido e a tela oferece outro desafio | Não gastar uma correção com texto curto demais (coerente com o D3) |

Todas as decisões respeitam a base protegida: os limites viram constantes nos serviços `writing_*.py` (nada em
`app/config.py`), nenhuma variável de ambiente ou dependência nova, `llm.py` usado sem alteração e a cota só na rota
que cria o desafio.

## Plano e progresso

### Mapa de dependências

```
W1 Modelos + migração 0301 (esquema)
 └─► W2 Temas (categorias, migração 0302 de dados, sorteio, contagem de palavras)
      └─► W3 API do desafio (criar com cota, ler, autosave, submissão com prazo no servidor)
           ├─► W4 Tela do editor (contador, timer, autosave, aviso de IA)
           └─► W5 Contrato JSON + prompt + serviço de avaliação (puro, sem rotas)
                └─► W6 Avaliação na API (persistência, erro_avaliacao, "avaliar de novo")
                     ├─► W7 Tela de resultado + destaque dos trechos      ◄── W4
                     └─► W8 Rewrite no backend (seleção, comandos, diff, avaliação, histórico)
                          └─► W9 Tela do Rewrite                           ◄── W7
                               └─► W10 Integração ponta a ponta + entrega ao Membro 4
```

### Blocos

| ID | Bloco | Tarefas atendidas | Status |
|---|---|---|---|
| W0 | Plano (este README) | — | ✅ concluído |
| W1 | Modelos e migração do esquema (0301) | Modelagem WritingPrompt/Attempt/Feedback (+ WritingRewrite); migration das tabelas | ✅ concluído |
| W2 | Temas e regras puras (0302) | Categorias TOEFL/IELTS; seleção aleatória; regra de contagem de palavras | ✅ concluído |
| W3 | API do desafio | Endpoint de criação; endpoint de submissão; autosave (servidor); timer no servidor | ✅ concluído |
| W4 | Tela do editor | Interface do editor; contador de palavras JS; timer regressivo; autosave periódico | pendente |
| W5 | Serviço de avaliação | Contrato JSON; prompt das 5 categorias; serviço de avaliação; validação Pydantic; score por categoria | pendente |
| W6 | Avaliação na API | Persistência do feedback e da versão original; timeout e resposta inválida; testes de tamanhos e tipos | pendente |
| W7 | Tela de resultado | Interface de resultado; destaque dos trechos problemáticos | pendente |
| W8 | Rewrite no backend | Seleção dos problemas; comando por problema; endpoint da reescrita; comparação; avaliação da 2ª versão; histórico | pendente |
| W9 | Tela do Rewrite | Interface do Rewrite Challenge | pendente |
| W10 | Integração e entrega | Testes unitários da avaliação (fechamento); testes de integração da sequência completa | pendente |

### Cronograma (2 dias)

| Quando | Blocos | Marco |
|---|---|---|
| Dia 1, manhã | W1, W2, W3 | Backend do desafio pronto e testado |
| Dia 1, tarde | W4, W5 | Editor usável; serviço de avaliação testado com a LLM falsa |
| Dia 2, manhã | W6, W7 | **MVP:** escrever → enviar → ver a correção com destaques |
| Dia 2, tarde | W8, W9, W10 | Rewrite completo, integração e entrega ao Membro 4 |

Essencial (MVP): W1–W7. Completa o escopo: W8–W10. Adiável sem perder tarefas: teste E2E no navegador e acabamento
visual. Se o prazo apertar, a proposta é um 3º dia curto para o W10, sem cortar tarefas nem testes.

### Estratégia de testes

- Regras puras (W2, W5, W8): testes unitários sem banco nem HTTP.
- LLM: sempre `llm_falsa` (resposta válida, JSON inválido, citação inexistente/repetida, timeout, provedor fora, 503).
- API: duas contas (`entrar_como`), outro usuário → 404; estados (409); prazo; cota (429); limites (422).
- Persistência: `engine_teste` confere que o texto original continua intacto.
- Migrações: `test_migracoes` (SQLite) e upgrade/downgrade no Postgres.
- Regressão a cada bloco: suíte inteira (referência: 266 aprovados, 2 pulados), `ruff`, `test_base_protegida`,
  `git diff --stat` (só arquivos novos + encaixes).
- Mutação a cada bloco: quebrar de propósito uma regra importante, ver um teste falhar e restaurar.

### Registro por bloco

#### W0 — Plano
- **Status:** concluído (21/11/2026).
- **Arquivos:** `README_MEMBRO3.md` (criado).
- **Linha de base (FASE 0):** branch `Membro3`, commit `49636dd`, banco local na 0006; `pytest` (SQLite): 268
  coletados, **266 aprovados, 2 pulados** (E2E sem `E2E=1`; Postgres sem `TEST_DATABASE_URL`), 0 falhas; `ruff`:
  limpo. Aviso preexistente da base: `StarletteDeprecationWarning` (httpx no TestClient), não reprova nada.
- **Próxima ação:** Etapa A do W1.

#### W1 — Modelos e migração do esquema (0301)
- **Status:** concluído (21/11/2026).
- **Tarefas atendidas:** modelagem das entidades WritingPrompt, WritingAttempt e WritingFeedback (+ WritingRewrite,
  para o histórico do Rewrite); migration das novas tabelas.
- **Arquivos:** `app/models_writing.py` (novo), `migrations/versions/0301_writing_challenge.py` (novo, gerado pelo
  autogenerate e revisado à mão), `tests/writing/__init__.py` e `tests/writing/test_modelos.py` (novos);
  **encaixe** `app/models.py` (1 linha: `import app.models_writing  # noqa: E402, F401`).
- **Decisões técnicas:** quatro tabelas ligadas por FK (o banco garante "um feedback por tentativa" e "nenhuma
  reescrita duplicada"); notas e trechos em JSON (lidos sempre junto com o feedback); `prazo` gravado na criação;
  diff não gravado (derivável); estado validado no código. `tests/writing/` é um pacote (`__init__.py`) para não
  colidir com testes da base de mesmo nome (o pytest usa o modo de import padrão).
- **Testes:** `tests/writing/test_modelos.py`, 8 testes (padrões da tentativa, tema ativo, JSON lido do banco, UNIQUE do
  feedback, UNIQUE da reescrita, linhas novas por rodada/trecho, encaixe no metadata, 0301 sobe/desce com FKs
  nomeadas e sem tocar nas tabelas da base). Suíte inteira: **276 coletados, 274 aprovados, 2 pulados, 0 falhas**;
  `ruff` limpo; `test_base_protegida` verde.
- **Mutações (todas detectadas, arquivos restaurados e conferidos por hash):** (1) sem o UNIQUE do feedback →
  `test_banco_recusa_segundo_feedback...` falha; (2) FK do dono sem nome na 0301 → `test_migracao_0301...` falha;
  (3) 0301 sem a coluna `avaliacoes_tentadas` → `test_migracoes_produzem_o_mesmo_esquema_dos_modelos` falha.
- **Banco local:** `python -m app.migrar` → backup `dados/backup/estudos-20261121-111858-318461.db`, banco na 0301.
- **Problemas encontrados:** o autogenerate gerou as FKs sem nome (esperado; corrigido na revisão). Nenhum na base.
- **Próxima ação:** Etapa A do W2 (temas, migração 0302, sorteio, contagem de palavras).

#### W2 — Temas e regras puras (0302)
- **Status:** concluído (21/11/2026).
- **Tarefas atendidas:** definição de categorias de prompts inspiradas em TOEFL/IELTS; implementação da seleção
  aleatória de tema; regra da contagem de palavras do servidor (a do JS vem no W4).
- **Arquivos (todos novos):** `app/services/writing_temas.py`, `app/services/writing_texto.py`,
  `migrations/versions/0302_writing_temas_iniciais.py`, `tests/writing/conftest.py` (fixture `temas`),
  `tests/writing/test_temas.py`, `tests/writing/test_texto.py`. Nenhum encaixe neste bloco.
- **Decisões do usuário:** nomes "Opinião" e "Discussão de dois lados" (em vez de "Opinião (concordar ou discordar)"
  e "Discutir os dois lados").
- **Decisões técnicas:** temas congelados dentro da 0302 (sem importar o serviço), com teste que confere que a
  migração e `CATEGORIAS` não divergem; sorteio no banco (`func.random()`); contagem com regra explícita, não
  `split()`; downgrade da 0302 recusa se houver tema em uso (padrão `BancoIncompativel` da 0003).
- **Testes:** 27 novos (`test_temas.py`: categorias, sorteio por categoria, "Surpresa", inativo nunca sorteado,
  sem temas → `None`, categoria desconhecida, 0302 bate com o serviço, insere 24 temas 4 por categoria, desce
  apagando só os seus, recusa descer com tema em uso; `test_texto.py`: 16 casos de contagem + texto longo).
  Suíte inteira: **303 coletados, 301 aprovados, 2 pulados, 0 falhas**; `ruff` limpo; `test_base_protegida` verde.
- **Mutações (todas detectadas):** (a) sorteio sem filtro `ativo`; (b) contagem com `split()`; (c) sem NFC;
  (d) downgrade da 0302 sem a trava; (e) tempo na 0302 divergente do serviço.
- **Problemas encontrados:** (1) dois erros nos meus testes na primeira execução (`DetachedInstanceError` na
  fixture e `dict()` sobre o resultado da consulta), corrigidos; (2) a primeira rodada de mutações, feita com
  `Get-Content`/`Set-Content` do PowerShell 5.1, corrompeu os acentos dos arquivos mutados e derrubou testes não
  relacionados: refeita com um script Python em UTF-8 (arquivos restaurados e conferidos byte a byte); (3) a
  mutação "sem NFC" revelou um caso de teste fraco (`café` conta 1 mesmo sem NFC, porque o acento combinado no
  fim é ignorado): trocado por `naïve` (acento no meio), que prova a necessidade do NFC.
- **Banco local:** `python -m app.migrar` → backup `dados/backup/estudos-20261121-114802-147301.db`, banco na 0302
  com 24 temas.
- **Próxima ação:** Etapa A do W3 (API do desafio: criar com cota, ler, autosave, submissão com prazo no servidor).

#### W3 — API do desafio
- **Status:** concluído (21/11/2026).
- **Tarefas atendidas:** endpoint para criação de um Writing Challenge; endpoint de submissão da redação; lado
  servidor do autosave periódico e do timer regressivo (prazo conferido no servidor).
- **Arquivos:** `app/api/writing.py`, `app/schemas_writing.py`, `app/services/writing_desafios.py`,
  `tests/writing/test_api_desafio.py` (novos); `tests/writing/conftest.py` (fixture automática `cota_nova`);
  **encaixe** `app/main.py` (2 linhas: `from app.api import writing` + `rotas += [writing.router]`).
- **Decisões do usuário:** D9 (opção A: cota pelo padrão `Depends`) e D10 (recusar com 422).
- **Decisões técnicas:** o serviço não conhece HTTP (exceções próprias, traduzidas para `ErroDaApi` na rota); o
  "agora" entra como parâmetro (testes simulam o tempo movendo o `prazo` no banco); `segundos_restantes` vem do
  servidor; entradas com `extra="forbid"`; limite de 10.000 caracteres no schema; sem estado "expirada" (o prazo
  gravado já diz isso); limitador de cota novo a cada teste (o da base é global ao processo).
- **Testes:** `test_api_desafio.py`, 38 testes (categorias; criar com prazo gravado, "Surpresa" de 3 formas, corpo
  inválido, sem temas, 11º desafio → 429, cota por conta; ler, listar só as próprias em ordem, 404; autosave com
  acentos/emoji, limite exato e acima, campo extra, dentro e fora da tolerância, depois do envio; envio, mínimo de
  palavras (49 × 50), vazio/pontuação, acima do limite, segundo envio, tolerância, D2, D10; isolamento com 404 em
  GET/PATCH/POST e nada alterado). O `test_protecao_api` da base passou a cobrir as 6 rotas novas (conferido na
  coleta). Suíte inteira: **341 coletados, 339 aprovados, 2 pulados, 0 falhas**; `ruff` limpo.
- **Mutações (7, todas detectadas):** (1) sem filtro de dono; (2) autosave sem conferir o prazo; (3) autosave depois
  do envio; (4) envio depois do prazo usando o texto recebido; (5) envio sem o mínimo de palavras; (6) router sem
  login (pego pelo `test_protecao_api`); (7) criar sem gastar cota.
- **Problemas encontrados:** a mutação 4 passou no teste principal do D2 e só foi pega por um teste secundário: o
  `enviar()` tinha uma proteção redundante (só gravava o texto quando não usava o autosave) que mascarava a
  mutação, e o teste não conferia a contagem de palavras, que ficava errada. Corrigido nos dois lados: o código
  grava sempre o texto final, e o teste confere `palavras`. Depois disso, o teste principal pega a mutação.
- **Próxima ação:** Etapa A do W4 (tela do editor).

## Testes

```powershell
.\venv\Scripts\Activate.ps1
python -m pytest              # suíte inteira (SQLite temporário)
python -m pytest tests/writing   # só os testes do Writing
python -m ruff check .
```

| Arquivo | O que cobre |
|---|---|
| `tests/writing/conftest.py` | Fixtures `temas` (o `create_all` dos testes não roda a migração de dados) e `cota_nova` (automática: limitador de cota novo a cada teste), e `criar_tema()` |
| `tests/writing/test_api_desafio.py` | API do desafio: criar (cota, sorteio, prazo), ler, listar, autosave, envio, regras de tempo (D2, D10), limites e isolamento entre contas |
| `tests/writing/test_modelos.py` | Modelos (padrões, JSON, UNIQUEs) e a migração 0301 (sobe/desce, FKs nomeadas) |
| `tests/writing/test_temas.py` | Categorias, sorteio do tema e a migração de dados 0302 (conteúdo, downgrade e trava) |
| `tests/writing/test_texto.py` | Contagem de palavras (apóstrofo, hífen, números, pontuação, acentos, NFC, vazio) |

## Encaixes na base (linhas alteradas)

Os únicos trechos de arquivos da base alterados por esta feature. São os **pontos de encaixe** que o `CLAUDE.md`
(seção 4) reserva para cada membro: só o bloco logo abaixo do comentário `Membro 3 (Writing)`, sem mexer nos blocos
dos Membros 1 e 2 nem nas linhas em branco entre eles (assim o merge das três branches não tem conflito). Atualizada a
cada bloco que usa um encaixe.

| # | Bloco | Arquivo | Linhas adicionadas |
|---|---|---|---|
| 1 | W1 | `app/models.py` (fim do arquivo) | 1 |
| 2 | W3 | `app/main.py` (`_rotas_das_features`) | 2 |

**1. `app/models.py`** (W1): registra os modelos do Writing no `SQLModel.metadata` (Alembic e testes).

Antes:
```python
# Membro 2 (Speaking)

# Membro 3 (Writing)
```
Depois:
```python
# Membro 2 (Speaking)

# Membro 3 (Writing)
import app.models_writing  # noqa: E402, F401
```

**2. `app/main.py`**, função `_rotas_das_features` (W3): registra as rotas da API `/api/writing`.

Antes:
```python
    # Membro 2 (Speaking)

    # Membro 3 (Writing)

    return rotas
```
Depois:
```python
    # Membro 2 (Speaking)

    # Membro 3 (Writing)
    from app.api import writing
    rotas += [writing.router]

    return rotas
```

**Encaixes previstos e ainda não usados:** `app/static/js/main.js` (W4: `import "./paginas/writing.js";`),
`app/templates/base.html` (W4: CSS e botão da navbar) e, no `app/main.py`, `writing.paginas` acrescentado à mesma
lista (W4). O `requirements.txt` não deve ser usado (nenhuma dependência nova).

Para conferir a qualquer momento: `git --no-pager diff Membro4 -- app/models.py app/main.py app/static/js/main.js
app/templates/base.html requirements.txt`.

## Alterações na base

Nenhuma. (Esta seção é para mudanças **fora** dos pontos de encaixe, que exigem aprovação explícita; ver
`CLAUDE.md`, seção 3. Os encaixes estão na seção anterior.)

## Para o Membro 4

_(preenchido ao longo dos blocos; checklist da seção 10 do `CLAUDE.md`)_

- Dependências novas: nenhuma prevista (`difflib` é da biblioteca padrão).
- Variáveis de ambiente novas: nenhuma (usa as da LLM que já existem).
- Migrações: `0301` (esquema) e `0302` (dados: temas iniciais). Na integração, juntar as cabeças das três faixas com
  `alembic merge` **antes** de rodar `python -m app.migrar` (com várias cabeças, `migrar.revisao_mais_recente()`,
  que usa `get_current_head()`, falha).
