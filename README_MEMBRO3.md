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

1. Entre na sua conta e abra **`/writing`** (ex.: http://127.0.0.1:8000/writing). Não há botão na navbar (D13): a
   interface inicial que levará a cada desafio será criada pelo tech lead.
2. Leia o aviso de privacidade (o texto vai para um provedor externo de IA) e veja quantos desafios restam hoje
   (10 por dia; cada desafio criado gasta 1).
3. Escolha uma **categoria** (o tema é sorteado dentro dela) ou **Surpresa** (qualquer categoria).
4. Escreva no editor. O **contador** mostra as palavras (mesma regra do servidor) e o mínimo recomendado do tema; o
   **timer** mostra o tempo restante (fica vermelho no último minuto). O texto é **salvo sozinho** 3 s depois de
   você parar de digitar, a cada 30 s e ao sair da página ("Salvo às 14:32").
5. Pode sair e voltar: **Salvar e voltar**, outra página ou até recarregar (a URL guarda a redação:
   `/writing?redacao=7`). O texto e o tempo continuam de onde estavam; o tempo corre no servidor.
6. Clique em **Enviar redação** (a partir de 50 palavras; pede confirmação). Quando o tempo acaba, o envio é
   automático, com o último texto salvo.
7. Em **Redações recentes** você retoma um rascunho ou vê as enviadas.

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
| `POST /api/writing/attempts/{id}/submissao` | `{texto}` (máx. 10.000 caracteres) | redação **corrigida** (com `usou_ultimo_salvamento` e `feedback`) | 404 · 409 `redacao_ja_enviada` · 422 `redacao_curta` · 422 · 502/503/504 `llm_*` (texto salvo, redação em `erro_avaliacao`) |
| `POST /api/writing/attempts/{id}/avaliacao` ("avaliar de novo") | — | redação corrigida | 404 · 409 `redacao_ja_avaliada` · 409 `redacao_nao_enviada` · 409 `limite_de_avaliacoes` · 502/503/504 `llm_*` |

**Redação (resposta):** `id, estado, categoria, categoria_nome, enunciado, tempo_limite_segundos, palavras_minimas,
texto, palavras, iniciada_em, prazo, segundos_restantes, salva_em, enviada_em, usou_ultimo_salvamento,
avaliacoes_restantes, feedback` (`feedback`: `null` até ser avaliada; senão `notas, nota_geral, resumo, trechos,
modelo, versao_prompt, criado_em`). Na lista, cada item tem também `nota_geral` (`null` se não avaliada).

**Envio e correção (W6):** o envio grava o texto (commit) e **só então** chama a LLM. Sucesso → `WritingFeedback` e
estado `avaliada`. Falha da LLM → estado `erro_avaliacao` e a resposta é o erro da LLM (D17), com a mensagem "A sua
redação foi salva; tente avaliar de novo." O "avaliar de novo" aceita `enviada` ou `erro_avaliacao`, até 3 chamadas à
LLM por redação (D4), e não gasta cota. Sem LLM configurada, a tentativa não conta (D16). Lógica em
`app/services/writing_avaliacao.py`.
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
| 409 | `redacao_ja_avaliada` | "Avaliar de novo" numa redação já avaliada (inclusive o duplo clique, pelo `UNIQUE` do feedback) | — |
| 409 | `redacao_nao_enviada` | "Avaliar de novo" num rascunho | — |
| 409 | `limite_de_avaliacoes` | A redação já usou as 3 chamadas à LLM (D4) | — |

Os demais (`nao_encontrado`, `dados_invalidos`, `nao_autenticado`, `limite_de_desafios`) são os da base.

### Correção por IA (`app/services/writing_llm.py`, W5)

`avaliar(texto, enunciado, categoria, palavras_minimas, palavras)` → `ResultadoAvaliacao`
(`notas, nota_geral, resumo, trechos, modelo, versao_prompt, descartados`). Uma chamada `llm.gerar_json` por
correção; os erros da LLM sobem sem tratamento (quem chama decide, W6).

**Contrato JSON** (`AvaliacaoLLM` em `app/schemas_writing.py`; o JSON Schema vai junto das instruções):

| Campo | Regra |
|---|---|
| `categorias.{gramatica, vocabulario, coerencia, organizacao, atendimento_tarefa}` | as 5 chaves obrigatórias; cada uma `{nota: int 0–10, comentario: 1–600 caracteres}` |
| `resumo` | 1–800 caracteres, em português |
| `trechos[]` (até 15) | `categoria` (uma das 5), `citacao` (1–300, cópia exata), `gravidade` (1–3), `explicacao` (≤ 400, português), `sugestao` (≤ 300, inglês), `instrucao_reescrita` (≤ 300, português, sem dar a resposta) |

**Prompt:** `INSTRUCOES` (papel de corretor IELTS/TOEFL, critérios das 5 categorias, escala, regras dos trechos,
idiomas, segurança) + `montar_mensagem()` (tipo de tarefa, tema, mínimo, contagem de palavras do servidor e a redação
entre `<redacao>…</redacao>`, com qualquer delimitador digitado pelo usuário neutralizado). `VERSAO_PROMPT = 1`,
gravada com o feedback.

**Trechos** (`localizar_trechos`, função pura): citação procurada exatamente no texto (tolerando aspas e espaços nas
pontas); inexistente → descartada; repetida → próxima ocorrência; sobreposta → fica a mais grave (D14); no máximo 10;
saída ordenada pela posição. **Posições `inicio`/`fim` em caracteres Unicode (como no Python):** no JS, recortar com
`Array.from(texto)`, não com `texto.slice` (lá um emoji ocupa 2 posições).

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

| D11 | 21/11/2026 | O botão **Enviar** pede confirmação ("Depois de enviada, ela não pode mais ser editada"); o envio automático do fim do tempo não pergunta | Evita envio acidental; o envio é irreversível |
| D12 | 21/11/2026 | Autosave **3 s após parar de digitar** + **a cada 30 s** (se houver mudança) + **ao sair** (limpeza da página, troca de aba e `pagehide` com `keepalive`) | Perde no máximo alguns segundos de texto, sem uma requisição por tecla |
| D13 | 21/11/2026 | **Sem botão na navbar**: o acesso é pela URL `/writing`. (Primeiro foi decidido um botão "Writing Challenge"; revisto no mesmo dia, antes do commit, por instrução do tech lead) | O tech lead vai criar uma interface inicial que leva a cada um dos quatro desafios (o Shadowing é um deles); essa interface só precisa de um link para `/writing` |

| D14 | 21/11/2026 | Trechos sobrepostos: fica o de **maior gravidade** (empate: o que veio primeiro); **no máximo 10** trechos guardados | A tela não precisa desenhar destaques sobrepostos; o aluno vê primeiro o que é mais grave |
| D15 | 21/11/2026 | Nota geral = **média simples com 1 casa decimal** (ex.: 7,4) | Não perde informação; não há critério oficial para pesos por categoria |

| D16 | 21/11/2026 | Sem LLM configurada (sem chave), a tentativa de correção **não conta** no limite de 3; a redação fica em `erro_avaliacao` com 503 | Um servidor mal configurado não gasta as tentativas das pessoas |
| D17 | 21/11/2026 | Envio com falha da LLM responde **com o erro da LLM** (502/503/504); a tela sabe que a redação está salva pelo código `llm_*` | Padrão do guia e do projeto (o status HTTP diz a verdade) |

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
| W4 | Tela do editor | Interface do editor; contador de palavras JS; timer regressivo; autosave periódico | ✅ concluído |
| W5 | Serviço de avaliação | Contrato JSON; prompt das 5 categorias; serviço de avaliação; validação Pydantic; score por categoria | ✅ concluído |
| W6 | Avaliação na API | Persistência do feedback e da versão original; timeout e resposta inválida; testes de tamanhos e tipos | ✅ concluído (inclui teste real com o Gemini) |
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

#### W4 — Tela do editor
- **Status:** concluído (21/11/2026), com a lógica da tela validada por roteiro manual (sem E2E: o Chromium do
  Playwright não está instalado nesta máquina; o E2E fica para o W10).
- **Tarefas atendidas:** desenvolvimento da interface do editor de redação; contador de palavras em JavaScript;
  timer regressivo; autosave periódico do texto.
- **Arquivos:** `app/templates/paginas/writing.html`, `app/static/js/paginas/writing.js`,
  `app/static/js/nucleo/api-writing.js`, `app/static/css/writing.css`, `tests/writing/test_paginas.py` (novos);
  `app/api/writing.py` (router `paginas` com `GET /writing`); **encaixes** `app/main.py` (`writing.paginas`),
  `app/static/js/main.js`, `app/templates/base.html` (só o CSS). Antes e depois na seção "Encaixes na base".
- **Decisões do usuário:** D11 (confirmar o envio), D12 (autosave 3 s + 30 s + ao sair), D13 (sem botão na navbar:
  acesso pela URL `/writing`, por instrução do tech lead; o botão chegou a ser feito e foi removido antes do commit).
- **Decisões técnicas:** uma página com três telas (início, editor, fim) e a redação aberta na URL
  (`?redacao=`); timer a partir de `segundos_restantes` do servidor; conteúdo do servidor só por
  `textContent`/`value` (sem `innerHTML`); salvamento ao fechar a aba com `fetch(..., {keepalive: true})` no
  `api-writing.js` (o `enviarJSON` da base não tem essa opção); `spellcheck="false"` no editor (como nas provas, sem
  corretor do navegador); colar texto não é bloqueado (acessibilidade).
- **Testes:** `test_paginas.py`, 11 testes (login e HX-Redirect, as três telas, F5 com `?redacao=`, CSS no
  `base.html`, arquivos estáticos, import no `main.js`, paridade textual das expressões JS × Python e **paridade real**:
  o teste roda a `contarPalavras` do `writing.js` no Node.js e compara com o Python em 18 textos; pulado se não houver
  Node). Verificação extra, fora da suíte: `node --check` nos dois JS novos e 20/20 casos iguais (incluindo japonês e
  árabe). Suíte inteira: **352 coletados, 350 aprovados, 2 pulados, 0 falhas**; `ruff` limpo.
- **Mutações (5, todas detectadas):** (1) expressão do JS sem o hífen; (2) JS sem NFC; (3) encaixe do `main.py` sem
  `writing.paginas`; (4) encaixe do `main.js` sem o import; (5) encaixe do `base.html` sem o CSS (refeita depois da
  remoção do botão; a mutação original era "sem o botão").
- **Teste manual (usuário):** a página só apareceu completa depois de um Ctrl+Shift+R (o navegador usava o
  `main.js` antigo em cache; ver "Para o Membro 4"). Depois disso, **roteiro completo aprovado**: aviso de IA, cota,
  categorias, redações recentes, contador (5 palavras em `I don't agree, it's well-known.`), "Salvo às…", F5 volta ao
  editor com texto e timer, "Salvar e voltar" e retomar o rascunho, envio com confirmação, tema claro/escuro, e o
  **envio automático no fim do tempo** nos dois casos (≥ 50 palavras → "Redação enviada"; < 50 → "O tempo acabou",
  D10). Network com todas as chamadas em 200.
- **Problemas encontrados:** (1) o teste do `main.js` falhou de início porque o arquivo da base usa `\r\n` e o `$`
  da expressão não casava antes do `\r` (corrigido com `\r?`); (2) no script de mutação, o trecho do import aparecia
  também no comentário de exemplo do encaixe; a trava "exatamente uma vez" impediu a mutação sem alterar nada, e o
  trecho foi corrigido.
- **Próxima ação:** Etapa A do W5 (contrato JSON, prompt das 5 categorias e serviço de avaliação, sem rotas).

#### W5 — Serviço de avaliação (sem rotas)
- **Status:** concluído (21/11/2026).
- **Tarefas atendidas:** definição do contrato JSON da avaliação; criação de prompt para avaliação separada de
  gramática, vocabulário, coerência, organização e atendimento à tarefa; implementação do serviço de avaliação no
  backend; validação da saída da LLM através de Pydantic; criação de score por categoria. (Adianta parte do W8: a
  `instrucao_reescrita` de cada problema vem nesta mesma chamada.)
- **Arquivos:** `app/services/writing_llm.py`, `tests/writing/test_avaliacao_servico.py` (novos);
  `app/schemas_writing.py` (contrato `AvaliacaoLLM`). Nenhum arquivo da base; nenhum encaixe.
- **Decisões do usuário:** D14 (sobreposição: fica o mais grave; máximo 10) e D15 (média com 1 casa).
- **Decisões técnicas:** categorias como chaves fixas (faltar uma = inválida); limites de tamanho e de nota no
  contrato; contagem de palavras do servidor na mensagem; delimitadores + neutralização contra prompt injection
  (reduz o risco, não elimina; o contrato vale para qualquer resposta); citação exata (sem casamento aproximado);
  erros da LLM sobem para o W6 tratar; prompt em português.
- **Testes:** `test_avaliacao_servico.py`, 33 testes (caminho feliz com média e rastreabilidade; médias em 3
  cenários; sem trechos; mensagens enviadas; 4 grafias do delimitador; 6 respostas inválidas × 2 tentativas;
  inválida e depois válida; timeout e indisponível sobem; sem chave → não configurada; localização: inexistente,
  aspas, aspas legítimas, repetida, sobreposta por gravidade e por ordem, vizinhas, limite de 10, ordem, emoji,
  campos completos). Suíte inteira: **383 coletados, 381 aprovados, 2 pulados, 0 falhas**; `ruff` limpo;
  `test_base_protegida` verde (`llm.py` intocado).
- **Mutações (8, todas detectadas):** (1) não descartar citação inexistente; (2) média errada; (3) categoria
  opcional no contrato; (4) nota sem limite 0–10; (5) sobreposição sem preferir o mais grave; (6) repetida sempre na
  1ª ocorrência; (7) sem neutralizar o delimitador; (8) sem limite de 10 trechos.
- **Problemas encontrados:** a mutação 7 só derrubou 2 das 4 grafias do ataque (`</REDACAO>` e `< / redacao >`
  passavam), porque o teste contava o delimitador só em minúsculas e sem espaços. O código neutralizava as quatro;
  o teste é que não provava. Corrigido (o teste conta qualquer grafia), e as 4 passaram a falhar com a mutação.
- **Não executado:** correção com o Gemini de verdade (precisa da `LLM_CHAVE` do usuário no `.env`); prevista para o
  W6, quando a rota existir.
- **Próxima ação:** Etapa A do W6 (avaliação na API: persistência, erro_avaliacao, "avaliar de novo").

#### W6 — Avaliação na API
- **Status:** concluído (21/11/2026), nos testes automáticos e com o Gemini de verdade.
- **Teste real com o Gemini (21/11/2026):** script de medição (fora da suíte; chama `writing_llm.avaliar()` com a
  `LLM_CHAVE` do `.env`, sem gravar no banco) com 3 redações de um mesmo tema IELTS, com erros de propósito.
  - A chave só pôde ser criada numa conta Google pessoal (a institucional bloqueia a criação de projetos).
  - Modelos testados: `gemini-flash-latest` → 503 "high demand" nas 3; `gemini-2.5-flash` → 404 "no longer
    available to new users"; `gemini-3.8-flash` → 2 timeouts de 60 s e um 503; **`gemini-3.1-flash-lite` → as 3 com
    sucesso**. Em todas as falhas, o tratamento funcionou como planejado (`llm_indisponivel` ou `llm_tempo_esgotado`,
    mensagem em português para o usuário, detalhe do provedor só no log).
  - Resultado com `gemini-3.1-flash-lite`:

    | Redação | Palavras | Tempo | Nota geral | Atendimento à tarefa | Trechos aceitos / descartados |
    |---|---|---|---|---|---|
    | Curta | 57 | 23,7 s (1ª chamada) | 3,2 | 2 | 5 / 0 |
    | Média | 208 | 3,1 s | 5,4 | 5 | 7 / 0 |
    | Longa | 335 | 4,2 s | 4,6 | 6 | 6 / 1 |

  - Conferido: 3/3 respostas no contrato (nenhuma inválida); comentários e instruções em português e sugestões em
    inglês (D6); citações exatas (só 1 descartada em 18); "atendimento à tarefa" penaliza quem fica abaixo de 250
    palavras; instruções de reescrita orientam sem dar a resposta. A nota baixa de organização da longa está
    correta: a redação de teste tinha parágrafos depois da conclusão, e o modelo percebeu.
- **Tarefas atendidas:** persistência do feedback e da versão original; tratamento de timeout e resposta inválida
  da LLM; testes com diferentes tamanhos e tipos de redação.
- **Arquivos:** `app/services/writing_avaliacao.py` e `tests/writing/test_api_avaliacao.py` (novos);
  `app/api/writing.py` (envio corrige; `POST .../avaliacao`; `feedback` e `avaliacoes_restantes` na resposta;
  `nota_geral` na lista), `app/schemas_writing.py` (`TrechoAvaliado`, `FeedbackWriting`),
  `app/static/js/paginas/writing.js` (ajuste mínimo: erro `llm_*` no envio vai para "Redação enviada" com o aviso
  da falha; "Enviando e corrigindo…"), `tests/writing/conftest.py` (`RESPOSTA_LLM`, `llm_corrige`),
  `tests/writing/test_api_desafio.py` (envio agora com a LLM simulada). Nenhum arquivo da base; nenhum encaixe.
- **Desvio da Etapa A:** a lógica da avaliação foi para um arquivo novo (`writing_avaliacao.py`) em vez do
  `writing_desafios.py`, para evitar um import circular (`writing_desafios` → `writing_llm` → `schemas_writing` →
  `writing_desafios`). O comportamento combinado não mudou.
- **Decisões do usuário:** D16 (sem LLM configurada não conta) e D17 (envio responde com o erro da LLM).
- **Decisões técnicas:** commit do texto antes da LLM; contador gravado antes da chamada; captura de `llm.ErroLLM`
  e relançamento com mensagem própria (padrão do guia); `IntegrityError` do `UNIQUE` do feedback → 409 (duplo
  clique); erro inesperado durante a chamada vira o 500 genérico da base, com o texto já salvo.
- **Testes:** `test_api_avaliacao.py`, 18 testes (24 com os parametrizados): envio corrige e grava; redação nova
  com 3 avaliações; GET e lista com o resultado; timeout/indisponível/limite do provedor; resposta inválida 2×; sem
  chave (D16); texto e tentativa gravados antes da chamada (erro inesperado → 500); avaliar de novo sem gastar cota;
  enviada sem feedback; limite de 3; já avaliada; rascunho; duplo clique; isolamento; **tamanhos e tipos** (exatamente
  50 palavras, ~9.990 caracteres, acentos e emoji, HTML e especiais); D2 + correção do último autosave.
  `test_api_desafio.py`: os testes de envio usam a LLM simulada, e dois passaram a esperar `avaliada` em vez de
  `enviada` (todas as conferências anteriores mantidas). `node --check` no `writing.js`. Suíte inteira:
  **406 coletados, 404 aprovados, 2 pulados, 0 falhas**; `ruff` limpo.
- **Mutações (7, todas detectadas):** (1) tentativa não gravada antes da chamada; (2) falha não marca
  `erro_avaliacao`; (3) contar a tentativa sem LLM configurada; (4) sem o limite de 3; (5) sem tratar o
  `IntegrityError`; (6) sem a mensagem própria do timeout; (7) envio sem corrigir.
- **Problemas encontrados (todos nos meus testes):** (1) o texto de teste tinha 44 palavras, não as 51 do meu
  comentário (contei de cabeça), e o envio era recusado pelo mínimo de 50: agora a contagem é conferida no próprio
  teste com `contar_palavras`; (2) esperei que um erro inesperado "estourasse" no teste, mas o middleware da base o
  transforma num 500 genérico (comportamento correto): o teste passou a esperar o 500.
- **Próxima ação:** Etapa A do W7 (tela de resultado).

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
| `tests/writing/test_paginas.py` | Página `/writing` (login, telas, F5), encaixes (CSS no `base.html`, `main.js`) e paridade da contagem de palavras JS × Python (textual e executando o JS no Node.js, se instalado) |
| `tests/writing/test_avaliacao_servico.py` | Serviço de avaliação com `llm_falsa`: contrato, respostas inválidas, falhas da LLM, mensagens (inclusive prompt injection), nota geral e localização dos trechos |
| `tests/writing/test_api_avaliacao.py` | Envio que corrige, falhas da LLM (redação nunca se perde), "avaliar de novo" e seus limites, duplo clique, isolamento e tamanhos/tipos de redação no fluxo completo |
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
| 2 | W3, W4 | `app/main.py` (`_rotas_das_features`) | 2 (a 2ª linha ganhou `writing.paginas` no W4) |
| 3 | W4 | `app/static/js/main.js` | 1 |
| 4 | W4 | `app/templates/base.html` (CSS) | 1 |

Total até o W4: **5 linhas adicionadas em 4 arquivos**, nenhuma removida.

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

**2. `app/main.py`**, função `_rotas_das_features` (W3; W4 acrescentou `writing.paginas`): registra as rotas da API
`/api/writing` e a página `/writing`.

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
    rotas += [writing.router, writing.paginas]

    return rotas
```

**3. `app/static/js/main.js`** (W4): importa o JS da página (cada página se registra ao ser importada).

Antes:
```javascript
// Membro 2 (Speaking): import "./paginas/speaking.js";

// Membro 3 (Writing): import "./paginas/writing.js";

iniciarTema();
```
Depois:
```javascript
// Membro 2 (Speaking): import "./paginas/speaking.js";

// Membro 3 (Writing): import "./paginas/writing.js";
import "./paginas/writing.js";

iniciarTema();
```

**4. `app/templates/base.html`**, bloco de CSS (W4).

Antes:
```html
        {# Membro 2 (Speaking): CSS #}

        {# Membro 3 (Writing): CSS #}

        <script src="https://cdn.jsdelivr.net/npm/htmx.org@2.0.8/dist/htmx.min.js" ...></script>
```
Depois:
```html
        {# Membro 2 (Speaking): CSS #}

        {# Membro 3 (Writing): CSS #}
        <link rel="stylesheet" href="/static/css/writing.css">

        <script src="https://cdn.jsdelivr.net/npm/htmx.org@2.0.8/dist/htmx.min.js" ...></script>
```

**Encaixes não usados:** `app/templates/base.html` (botão na navbar), por decisão (D13: acesso pela URL `/writing`;
o bloco está idêntico ao da `Membro4`); `requirements.txt` (nenhuma dependência nova).

Para conferir a qualquer momento: `git --no-pager diff Membro4 -- app/models.py app/main.py app/static/js/main.js
app/templates/base.html requirements.txt`.

## Alterações na base

Nenhuma. (Esta seção é para mudanças **fora** dos pontos de encaixe, que exigem aprovação explícita; ver
`CLAUDE.md`, seção 3. Os encaixes estão na seção anterior.)

## Para o Membro 4

_(preenchido ao longo dos blocos; checklist da seção 10 do `CLAUDE.md`)_

- Dependências novas: nenhuma prevista (`difflib` é da biblioteca padrão).
- Variáveis de ambiente novas: nenhuma (usa as da LLM que já existem).
- **Tempo de uma correção real (para os timeouts do servidor e do proxy):** com `gemini-3.1-flash-lite`, **3 a 4 s**
  numa chamada "aquecida" e **~24 s** na primeira (ver W6). Com modelos sobrecarregados, a chamada chega ao limite de
  `LLM_TIMEOUT_SEGUNDOS` (60 s). O envio espera a correção (D7), então o proxy de produção precisa aceitar pelo menos
  **~65 s** em `POST /api/writing/attempts/{id}/submissao` e `.../avaliacao`.
- **Modelo do Gemini em produção (decisão do Membro 4):** o padrão da base (`gemini-flash-latest`) estava
  sobrecarregado no teste (503), o `gemini-2.5-flash` não está mais disponível para contas novas (404) e o
  `gemini-3.8-flash` deu timeouts; o **`gemini-3.1-flash-lite` funcionou bem**. Prefira um modelo com versão no nome
  (os `-latest` mudam sozinhos) e confirme-o na conta que vai pagar. O nome do modelo fica gravado em cada feedback
  (`WritingFeedback.modelo`).
- **Sobrecarga do provedor (503) no `llm.py` (base, não alterado):** de propósito, o `llm.py` não repete chamadas que
  falham por rede ou provedor. No teste, os 503 "high demand" eram temporários. Uma nova tentativa automática com
  espera, só para 503, evitaria parte desses erros (no Writing, o usuário já tem o "avaliar de novo", até 3 vezes).
  Fica como sugestão para avaliar no `llm.py`.
- **Acesso à página:** `/writing` (sem botão na navbar, D13). Para a interface inicial do tech lead, o link no padrão
  do app é `<button hx-get="/writing" hx-target="main" hx-push-url="true">` (ou um `<a href="/writing">` comum).
- **Cache dos arquivos estáticos (problema da base, não do Writing; para avaliar no B14–B16):** o `/static` é servido
  sem `Cache-Control` e sem versão na URL, então o navegador reaproveita cópias antigas por um tempo que ele mesmo
  decide. No teste manual do W4, o `main.js` antigo (sem o import do `writing.js`) continuou em uso depois da
  mudança, e a página do Writing apareceu sem conteúdo até um **Ctrl+Shift+R**. O mesmo vai acontecer com quem
  alterar qualquer JS/CSS existente (inclusive no merge das três branches) e com os usuários depois de cada deploy.
  Possíveis soluções (alteração na base, fora do escopo do Membro 3): versão na URL dos arquivos
  (`main.js?v=<commit>`) ou `Cache-Control: no-cache` no `/static` (revalida com o ETag que já é enviado).
- Migrações: `0301` (esquema) e `0302` (dados: temas iniciais). Na integração, juntar as cabeças das três faixas com
  `alembic merge` **antes** de rodar `python -m app.migrar` (com várias cabeças, `migrar.revisao_mais_recente()`,
  que usa `get_current_head()`, falha).
