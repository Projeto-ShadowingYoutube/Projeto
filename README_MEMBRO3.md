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
   automático, com o último texto salvo. A correção leva alguns segundos ("Enviando e corrigindo…").
7. **Resultado:** nota geral, as 5 categorias (nota, barra e comentário), o resumo e a sua redação com os trechos
   problemáticos destacados por cor (legenda abaixo do texto). Clique num trecho (ou Tab + Enter) para ver a
   categoria, a gravidade, a explicação e o que fazer; a versão corrigida só aparece em **Ver sugestão** (D18).
8. Se a correção falhar, a redação continua salva: **Avaliar de novo** (até 3 vezes por redação, sem gastar a cota).
9. Em **Redações recentes** você retoma um rascunho ou reabre um resultado (com a nota geral ao lado).
10. **Rewrite Challenge:** no resultado, **Rewrite Challenge →** (aparece se a correção apontou trechos). Até 3 frases
    problemáticas, cada uma com o trecho destacado, o problema e o que fazer. Os campos já vêm com a frase: edite-as
    (o envio só libera quando todas foram alteradas) e clique em **Enviar reescritas**. A IA diz se cada uma melhorou,
    com nota e comentário, e a comparação mostra o que saiu (riscado) e o que entrou (destacado). As que não
    melhoraram voltam numa 2ª rodada (máximo de 2). O histórico fica guardado; nada é sobrescrito.

Para a correção por IA funcionar localmente, coloque a **sua** chave do Gemini em `LLM_CHAVE` no `.env` (crie em
https://aistudio.google.com/apikey; nunca no Git). Sem ela, o app sobe normalmente e a correção responde 503
(`llm_nao_configurada`). Os testes **não** precisam da chave.

## Arquitetura

Todos os arquivos da feature são novos e levam o nome dela (nenhum arquivo da base foi alterado fora dos encaixes):

| Camada | Arquivo | Responsabilidade |
|---|---|---|
| Modelos | `app/models_writing.py` | `WritingPrompt`, `WritingAttempt`, `WritingFeedback`, `WritingRewrite` e os estados |
| Schemas | `app/schemas_writing.py` | Entrada/saída da API e os contratos da LLM (`AvaliacaoLLM`, `AvaliacaoReescritasLLM`) |
| Rotas | `app/api/writing.py` | `/api/writing/...` (login no router, `_tentativa` → 404) e a página `/writing` |
| Serviços | `app/services/writing_temas.py` | Categorias e sorteio do tema |
| | `app/services/writing_texto.py` | Contagem de palavras (a mesma regra do JS) |
| | `app/services/writing_desafios.py` | Criar, autosave e envio, com o prazo no servidor |
| | `app/services/writing_llm.py` | Prompts, chamadas ao `llm.gerar_json` e localização dos trechos |
| | `app/services/writing_avaliacao.py` | Estados da correção, limite de tentativas e gravação do feedback |
| | `app/services/writing_rewrite.py` | Seleção de frases, rodadas, comparação (`difflib`) e histórico |
| Migrações | `migrations/versions/0301_writing_challenge.py` · `0302_writing_temas_iniciais.py` | Esquema · dados (24 temas) |
| Tela | `app/templates/paginas/writing.html` | As 5 telas: início, editor, fim, resultado, rewrite |
| | `app/static/js/paginas/writing.js` | Lógica da página (`registrarPagina("writing")`) |
| | `app/static/js/nucleo/api-writing.js` | Cliente da API (`requisitarJSON`/`enviarJSON` da base) |
| | `app/static/js/componentes/writing-destaques.js` | Funções puras dos destaques (testadas no Node.js) |
| | `app/static/css/writing.css` | Estilos (só variáveis de tema da base) |
| Testes | `tests/writing/` | Ver a seção "Testes" |

Fluxo: tela (`writing.js`) → `api-writing.js` → `app/api/writing.py` (login, dono, cota) → `services/writing_*.py`
→ banco (SQLModel) e LLM (`llm.gerar_json` da base, sem alteração; prompts em `writing_llm.py`).

Pontos de encaixe usados (só o bloco `Membro 3 (Writing)` de cada um): `app/models.py`, `app/main.py`,
`app/static/js/main.js` e `app/templates/base.html` (CSS). Antes e depois na seção "Encaixes na base".

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

**Rewrite Challenge (W8):**

| Rota | Entrada | Saída | Erros próprios |
|---|---|---|---|
| `GET /api/writing/attempts/{id}/rewrite` | — | desafio | 404 · 409 `redacao_nao_avaliada` · 409 `sem_problemas` |
| `POST /api/writing/attempts/{id}/rewrite` | `{reescritas: [{indice, texto (1–1.000)}]}` (uma por problema da rodada) | desafio atualizado | 404 · 409 `redacao_nao_avaliada` · 409 `sem_problemas` · 409 `rewrite_concluido` · 409 `rodada_ja_enviada` · 422 `reescritas_invalidas` · 422 · 502/503/504 `llm_*` (nada gravado) |

**Desafio (resposta):** `concluido, rodada_atual (null se concluído), rodadas_restantes, problemas[]` (`indice,
categoria, gravidade, citacao, frase, explicacao, instrucao`) e `historico[]` (`rodada, indice, categoria,
frase_original, instrucao, reescrita, avaliacao {melhorou, nota, comentario}, comparacao [{tipo: igual | removido |
adicionado, texto}], criado_em`). Lógica em `app/services/writing_rewrite.py`; o prompt da avaliação em
`writing_llm.py` (`VERSAO_PROMPT_REWRITE = 1`). Não gasta a cota diária.

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
| 409 | `redacao_nao_avaliada` | Rewrite antes da correção | — |
| 409 | `sem_problemas` | Rewrite numa redação cuja correção não apontou trechos | — |
| 409 | `rewrite_concluido` | Rewrite depois da 2ª rodada, ou com tudo já melhorado | — |
| 409 | `rodada_ja_enviada` | A mesma rodada enviada duas vezes (corrida; `UNIQUE` da tabela) | — |
| 422 | `reescritas_invalidas` | A rodada não traz exatamente uma reescrita para cada problema dela | — |

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

| D18 | 21/11/2026 | Na tela de resultado, a **sugestão** (versão corrigida) fica escondida atrás de **"Ver sugestão"**; primeiro a explicação e a instrução | Não entregar a resposta de cara; o Rewrite Challenge (W8/W9) pede para reescrever justamente esses trechos |
| D19 | 21/11/2026 | Layout do resultado: **redação à esquerda, notas à direita** no computador; no celular, empilhado (notas primeiro) | A redação destacada é o centro da tela; menos rolagem |

| D20 | 21/11/2026 | No Rewrite, a pessoa reescreve a **frase inteira** que contém o trecho apontado | Atende "selecionar frases problemáticas"; reescrever só o trecho seria trivial |
| D21 | 21/11/2026 | A **rodada 2** traz só os problemas que **não melhoraram** na rodada 1; tudo melhorado = fim | Treina o que ainda falta, sem repetir o que já foi resolvido |
| D22 | 21/11/2026 | A rodada é enviada **inteira** (uma reescrita por problema), avaliada numa **chamada só** à LLM | Controle de custo (D4) |
| D23 | 21/11/2026 | Falha da LLM no Rewrite: **nada é gravado e a rodada não é gasta**; a tela mantém os textos para reenviar | Gravar "pendente" exigiria uma migração nova (a avaliação é obrigatória na tabela) para um caso raro |

| D24 | 21/11/2026 | Na tela do Rewrite, o campo da rodada 1 já vem **preenchido com a frase original** | Editar é mais natural do que redigitar a frase inteira |
| D25 | 21/11/2026 | Na rodada 2, o campo vem com **a reescrita da rodada 1** | Continua de onde parou |
| D26 | 21/11/2026 | **Enviar reescritas** só libera quando todas as frases foram **alteradas** em relação ao texto com que o campo começou | Não gastar uma chamada à LLM com frases não mexidas |

| D27 | 21/11/2026 | A medição com a LLM real vira um **teste opcional** no repositório (`tests/writing/test_llm_real.py`, só com `LLM_REAL=1`) | O Membro 4 consegue medir os tempos no servidor de produção com o mesmo código. É o único lugar que contorna, de propósito e só com a variável, a fixture `llm_desligada` da base (por `monkeypatch`, sem alterar o `conftest.py`) |
| D28 | 21/11/2026 | Rodar a suíte no **PostgreSQL** → revisto: **fica para a integração do Membro 4** | É o banco de produção, mas o Docker não está instalado na máquina; instalar o Docker Desktop (WSL2, administrador) só para isso não compensa, já que o Membro 4 roda a suíte no Postgres na integração |
| D29 | 21/11/2026 | **E2E no navegador** (`tests/writing/test_e2e_writing.py`, só com `E2E=1`): autosave + recarregar, resultado com destaques, Rewrite | Única validação automática da tela; no padrão do E2E da base |
| D30 | 21/11/2026 | O Writing **não usa o modal de erro da base**: todo erro aparece na tela aberta (`[data-erro]` de cada tela, função `avisar`). Corrigidos os 6 usos de uma vez | O botão "início" do modal leva para a tela do Shadowing (fora do Writing). Mudar o modal seria alteração na base e afetaria as três features |

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
| W7 | Tela de resultado | Interface de resultado; destaque dos trechos problemáticos | ✅ concluído |
| W8 | Rewrite no backend | Seleção dos problemas; comando por problema; endpoint da reescrita; comparação; avaliação da 2ª versão; histórico | ✅ concluído |
| W9 | Tela do Rewrite | Interface do Rewrite Challenge | ✅ concluído |
| W10 | Integração e entrega | Testes unitários da avaliação (fechamento); testes de integração da sequência completa | ✅ concluído (Postgres fica para a integração do Membro 4) |
| W10.1 | Erros na própria tela | Correção: o modal de erro da base levava para fora do Writing | ✅ concluído |

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

#### W7 — Tela de resultado
- **Status:** concluído (21/11/2026): testes automáticos e roteiro manual do usuário aprovados (sem E2E).
- **Tarefas atendidas:** desenvolvimento da interface de resultado; destaque visual de trechos problemáticos.
- **Arquivos:** `app/static/js/componentes/writing-destaques.js` (novo: `partesDoTexto`, `formatarNota`, nomes das
  categorias e gravidades; módulo puro, sem imports); `app/templates/paginas/writing.html` (tela `resultado` e botão
  "Avaliar de novo"); `app/static/js/paginas/writing.js` (resultado, detalhe do trecho, "Avaliar de novo", nota nas
  recentes; sai o texto provisório do W6); `app/static/js/nucleo/api-writing.js` (`avaliar`);
  `app/static/css/writing.css` (duas colunas, barras, cores das categorias nos dois temas, detalhe);
  `tests/writing/test_paginas.py`. Nenhum arquivo da base; nenhum encaixe.
- **Decisões do usuário:** D18 (sugestão atrás de "Ver sugestão") e D19 (redação à esquerda, notas à direita).
- **Decisões técnicas:** destaques montados no front com `textContent` (sem `innerHTML`; destacar no servidor
  misturaria texto do usuário com HTML); recorte com `Array.from` (posições em caracteres Unicode, como no Python);
  a função ignora trechos fora dos limites ou sobrepostos (não confia cegamente nos dados); `white-space: pre-wrap`
  preserva as quebras de linha; `<mark>` focável com Enter/Espaço; cor sempre acompanhada de legenda e do nome da
  categoria; detalhe num painel (tooltip não funciona no celular); módulo puro separado para o Node importar o
  código real nos testes.
- **Testes:** `test_paginas.py` com 13 testes (+ tela `resultado`, + módulo servido, + `partesDoTexto` executada
  no Node.js importando o módulo real: emoji e acentos antes do trecho, sem trechos, começo e fim, fora dos limites
  e vazio, sobreposto, fora de ordem; sempre confere que a concatenação das partes é o texto original e que cada
  parte destacada é exatamente o trecho do servidor). `node --check` nos 3 JS. Suíte inteira: **408 coletados,
  406 aprovados, 2 pulados, 0 falhas**; `ruff` limpo.
- **Mutações (5, todas detectadas):** (1) `slice` em vez de `Array.from`; (2) não ignorar sobrepostos; (3) não
  ignorar fora dos limites; (4) perder o texto depois do último trecho; (5) template sem a tela de resultado.
- **Teste manual (usuário, com o Gemini real `gemini-3.1-flash-lite`):** os 7 passos aprovados: resultado completo
  (7 trechos nas posições exatas, cores por categoria, 5 cartões com contagem de trechos, "atendimento à tarefa" = 3
  para 116 palavras), detalhe do trecho por clique e por Tab + Enter, "Ver sugestão", F5, nota nas recentes, tema
  claro/escuro, celular, XSS (`<b>` e `<script>` aparecem como texto) e "Avaliar de novo" depois de uma falha forçada
  (modelo inexistente no `.env`).
- **Comportamento confirmado com o usuário:** o Tab só move o foco entre os trechos; o painel atualiza com Enter,
  Espaço ou clique (padrão de acessibilidade para `role="button"`: foco não dispara ação, e o painel `aria-live` não
  é lido a cada Tab).
- **Problemas encontrados:** (1) no primeiro rascunho do teste do Node, o script usava `require` num módulo ES e só
  funcionava porque o `node -e` expõe módulos internos como globais (frágil); reescrito com `import` explícito.
  (2) No teste manual, a redação e os cartões apareciam centralizados (herdavam o alinhamento da base): corrigido com
  `text-align: left` só na área do resultado (`writing.css`).
- **Observação (qualidade da LLM, não do código):** no teste manual, 2 dos 9 erros postos de propósito (`dont`,
  `goverment`) não viraram trechos, embora o comentário de Vocabulário cite o `goverment`. Todos os trechos
  devolvidos foram desenhados (as contagens batem). Melhorar a cobertura seria um ajuste de prompt
  (`VERSAO_PROMPT = 2`), não proposto agora.
- **Próxima ação:** Etapa A do W8 (Rewrite no backend).

#### W8 — Rewrite Challenge no backend
- **Status:** concluído (21/11/2026) nos testes automáticos (a tela e o teste com o Gemini real vêm no W9).
- **Tarefas atendidas:** algoritmo para selecionar frases problemáticas da redação; geração do comando de
  reescrita específico para cada problema (a `instrucao_reescrita` de cada trecho, gerada na correção do W5, exposta
  por problema); endpoint para submissão da versão reescrita; comparação entre frase original e reescrita;
  avaliação automática da segunda versão; persistência do histórico original → feedback → rewrite.
- **Arquivos:** `app/services/writing_rewrite.py` e `tests/writing/test_rewrite.py` (novos);
  `app/services/writing_llm.py` (prompt e `avaliar_reescritas`), `app/schemas_writing.py` (contrato
  `AvaliacaoReescritasLLM` e formatos da API), `app/api/writing.py` (`GET` e `POST .../rewrite`). Nenhum arquivo da
  base; nenhum encaixe; **nenhuma migração** (a tabela `writingrewrite` do W1 já tinha todas as colunas).
- **Decisões do usuário:** D20 (frase inteira), D21 (rodada 2 só com os não melhorados), D22 (rodada inteira numa
  chamada) e D23 (falha não grava nem gasta a rodada).
- **Decisões técnicas:** seleção pura e determinística (não precisa ser gravada; a linha guarda o índice e a cópia
  da frase); extração da frase por `. ! ?` seguidos de espaço ou quebra de linha (o "3.5" não corta; abreviações como
  "e.g." cortam: limitação documentada); comparação por `difflib` em pedaços (palavras, espaços e pontuação), com
  as garantias de reconstrução, calculada ao ler; índices devolvidos pela LLM conferidos (diferente →
  `llm_resposta_invalida`); delimitadores digitados nas frases neutralizados; `IntegrityError` do `UNIQUE` → 409.
- **Testes:** `test_rewrite.py`, 36 testes: frase (7 casos), seleção (prioridade + variedade + frase única;
  variedade trocando um erro grave repetido; determinismo; menos trechos), comparação (reconstrução em 5 casos; o que
  mudou), mensagem (prompt injection), API (desafio inicial; rodada 1 com uma linha por problema e a original
  intacta; rodada 2 e fim; tudo melhorado; problemas faltando, a mais, fora da rodada, repetidos; texto vazio e
  longo; antes da correção; sem trechos; índices errados da LLM; timeout sem gravar nem gastar a rodada; envio duplo;
  outra conta → 404; não gasta cota). O `test_protecao_api` cobre as 2 rotas novas. Suíte inteira: **446
  coletados, 444 aprovados, 2 pulados, 0 falhas**; `ruff` limpo.
- **Mutações (9, todas detectadas):** (1) seleção sem variar categorias; (2) repetir a frase; (3) comparação sem o
  texto removido; (4) rodada 2 com todos; (5) aceitar índices errados da LLM; (6) aceitar rodada incompleta; (7) sem
  limite de rodadas; (8) frase cortada no "3.5"; (9) sem neutralizar delimitadores.
- **Problemas encontrados:** a mutação 1 passou na primeira rodada: os dados do teste davam a mesma seleção com e sem
  a regra de variar as categorias (coincidência). Acrescentado um teste em que a regra muda o resultado. Também
  troquei, no teste do envio duplo, uma substituição manual de função por `monkeypatch` (padrão do projeto).
- **Teste manual (usuário, pelo `/docs`, com o Gemini real):** `GET .../rewrite` e `POST .../rewrite` numa redação
  avaliada funcionaram (problemas, avaliação, comparação e rodada 2).
- **Próxima ação:** Etapa A do W9 (tela do Rewrite).

#### W9 — Tela do Rewrite Challenge
- **Status:** implementado (21/11/2026); testes automáticos aprovados; **aguarda o teste manual do usuário**.
- **Tarefas atendidas:** interface do Rewrite Challenge.
- **Arquivos:** `app/static/js/componentes/writing-destaques.js` (+ `partesDaFrase`), `app/templates/paginas/writing.html`
  (tela `rewrite` e botão no resultado), `app/static/js/paginas/writing.js` (abrir, problemas, validação D26, envio,
  histórico com a comparação, conclusão; `&rewrite=1` na URL), `app/static/js/nucleo/api-writing.js` (`rewrite`,
  `enviarRewrite`), `app/static/css/writing.css` (cartões, `<del>`/`<ins>`, vereditos), `tests/writing/test_paginas.py`.
  Nenhum arquivo da base; nenhum encaixe.
- **Decisões do usuário:** D24 (campo com a frase original), D25 (rodada 2 com a reescrita anterior), D26 (enviar só
  frases alteradas).
- **Decisões técnicas:** a tela é sempre redesenhada a partir do servidor (sem estado escondido no navegador); a
  comparação vem pronta do servidor (sem lógica duplicada em JS); `<del>`/`<ins>` com `textContent`; em falha da LLM
  os textos ficam nos campos (D23); a sugestão (D18) não aparece no Rewrite; botão só aparece se houver trechos.
- **Testes:** `test_paginas.py` com 15 testes (+ tela `rewrite` e botão; + `partesDaFrase` executada no Node: meio,
  começo, fim, emoji/acentos, repetida, ausente, vazia, nula). `node --check` nos 3 JS. Suíte inteira: **447
  coletados, 445 aprovados, 2 pulados, 0 falhas**; `ruff` limpo.
- **Mutações (4, todas detectadas):** (1) perder o texto depois do trecho; (2) destacar deslocado; (3) tirar a
  proteção da citação vazia/nula; (4) template sem a tela do Rewrite.
- **Problemas encontrados:** (1) a mutação 3 passou na primeira rodada: para a citação **vazia** ela é equivalente
  (o pedaço vazio é descartado pelo filtro); a proteção importa para `null`/`undefined`, que o JS converteria no
  texto "null". Acrescentado o caso nulo, e a mutação passou a ser pega. (2) A frase de conclusão tinha uma montagem
  de texto confusa (três `replace` encadeados); reescrita como uma expressão direta antes dos testes.
- **Teste manual (usuário, Gemini real):** etapas 1 a 7 aprovadas (botão no resultado, problemas com o trecho
  destacado, bloqueio do envio, rodada 1 com veredito e comparação, F5, rodada 2 com a reescrita anterior,
  conclusão, tema claro/escuro). Na etapa 8 (falha forçada), o usuário clicou em **"início"** no modal de erro da base
  e saiu da página, perdendo as reescritas digitadas (que, pelo D23, não são gravadas).
- **Correção depois do teste manual:** no envio do Rewrite, o erro passou a aparecer **na própria tela** (acima do
  botão, em vermelho, com "As suas reescritas continuam aqui: tente enviar de novo"), e não mais no modal da base.
  O modal continua para os casos sem texto a perder (abrir o Rewrite, rodada já gravada). A mensagem some ao editar
  um campo ou reenviar. Base não alterada.
- **Etapa 8 refeita (usuário):** o erro aparece na própria tela, os textos ficam nos campos e a rodada não é gasta. ✅
- **Próxima ação:** Etapa A do W10 (integração e entrega).

#### W10 — Integração e entrega ao Membro 4
- **Status:** concluído (21/11/2026): SQLite, E2E e `LLM_REAL` aprovados. **Postgres não executado** (Docker não
  instalado; por decisão do usuário, fica para a integração do Membro 4).
- **Tarefas atendidas:** testes unitários do sistema de avaliação (fechamento, guiado pela cobertura); testes de
  integração da sequência completa de Writing.
- **Arquivos:** `tests/writing/test_fluxo_completo.py`, `tests/writing/test_e2e_writing.py` e
  `tests/writing/test_llm_real.py` (novos); `tests/writing/test_rewrite.py` (casos de frase sem pontuação e a premissa
  da comparação), `tests/writing/test_temas.py` (APIs descontinuadas trocadas), `app/services/writing_rewrite.py`
  (código morto removido); `README_MEMBRO3.md` (arquitetura final e "Para o Membro 4").
- **Decisões do usuário:** D27 (medição com a LLM real como teste opcional `LLM_REAL=1`), D28 (rodar no Postgres),
  D29 (E2E no navegador).
- **Fluxo completo (`test_fluxo_completo.py`, 2 testes):** criar (cota −1) → autosave → recarregar → enviar →
  correção → Rewrite rodada 1 → rodada 2 → concluído, conferindo no banco o texto original intacto, 1 feedback e 5
  reescritas (nada sobrescrito), modelo e versões; e o cenário falha da correção → avaliar de novo → Rewrite.
- **Cobertura dos arquivos do Writing:** **100%** em todos (`api/writing.py`, `models_writing.py`,
  `schemas_writing.py` e os 6 `services/writing_*.py`). As 2 linhas que faltavam no `writing_rewrite.py`: uma era
  alcançável e ganhou teste (frase sem pontuação, com espaços antes da quebra); a outra era **código morto** (juntar
  dois pedaços seguidos do mesmo tipo na comparação, o que o `difflib` nunca produz) e foi removida, com um teste que
  garante a premissa. Cobertura não prova qualidade: as mutações continuam sendo a prova.
- **Mutações do fluxo completo (5, todas detectadas):** rewrite gravando sempre na rodada 1; envio sem congelar o
  texto; criar sem gastar cota; correção sem gravar o modelo; avaliar de novo sem mudar para `avaliada`.
- **`LLM_REAL` (D27):** sem a variável, pulado (conferido). Com `LLM_REAL=1`, no terminal do assistente a chamada ao
  Google falhou na verificação do certificado SSL (`CERTIFICATE_VERIFY_FAILED`), o mesmo problema de rede do
  `git fetch` do início da sessão. A verificação SSL não foi desligada (seria inseguro). **No terminal do usuário:
  3 passed** (`gemini-3.1-flash-lite`): correção curta (57 palavras) **3,1 s**, nota 2,8, 5 trechos, 0 descartados;
  correção média (157 palavras) **3,7 s**, nota 4,6, 6 trechos, 0 descartados; Rewrite (2 frases) **1,1 s**, com
  o veredito esperado (`[True, False]`).
- **E2E (D29):** Chromium do Playwright instalado. Sem `E2E=1`, pulado (conferido). Com `E2E=1`, no terminal do
  assistente a página não terminava de carregar: requisições ao **servidor local** ficavam pendentes de forma não
  determinística (numa rodada os estáticos, na outra a do HTMX), enquanto os CDNs respondiam. O código do Writing
  não está envolvido (os mesmos arquivos e rotas passam no `TestClient`); a hipótese era a restrição de rede do
  terminal do assistente. **No terminal do usuário: 3 passed em ~20 s** (hipótese confirmada). Avisos de
  descontinuação vindos de bibliotecas da base (`starlette`, `websockets`, `uvicorn`), sem relação com o Writing.
- **Postgres (D28):** o Docker não está instalado nesta máquina (o comando `docker` não existe), então não foi possível
  subir o `shadowing_teste`. **Não executado; decisão do usuário: fica para a integração do Membro 4** (que tem o
  Docker), em vez de instalar o Docker Desktop agora. O teste da base que sobe e desce todas as migrações (agora com a
  `0301` e a `0302`) roda lá. Ver "Para o Membro 4".
- **Suíte inteira (SQLite):** **454 coletados, 450 aprovados, 4 pulados** (E2E e Postgres da base; E2E e `LLM_REAL`
  do Writing, todos opcionais), **0 falhas**; `ruff` limpo; `test_base_protegida` verde.

#### W10.1 — Erros na própria tela (correção)
- **Status:** concluído (21/11/2026): testes automáticos e teste manual do usuário aprovados.
- **Problema relatado:** com a cota esgotada, clicar numa categoria abria o modal de erro da base ("Você já fez os 10
  desafios de hoje…"), e o botão **"início"** dele levava para a tela do Shadowing. O "×" mantinha no Writing.
- **Causa:** o modal é global da base (`app/templates/base.html`, `#botaoErro` com `hx-get="/inicio"
  hx-push-url="/"`), feito para voltar à tela do Shadowing. O `writing.js` o usava (`mostrarErro`) em 6 lugares. A
  mensagem em si (429 `limite_de_desafios`) estava correta: a conta tinha usado os 10 desafios do dia nos testes.
- **Correção (D30):** cada uma das 5 telas ganhou um `<p class="writing-erro" data-erro role="alert" hidden>`;
  `avisar(mensagem)` escreve (com `textContent`) no da tela visível, e `limparAviso()` esconde todos (chamado por
  `mostrarTela()`, ao tentar de novo e ao editar uma reescrita). Quando o erro leva a outra tela, a troca vem
  **antes** do aviso. O par `mostrarErroDoRewrite`/`esconderErroDoRewrite` (W9) virou um caso dessas funções, e a
  classe `.writing-rw-erro` passou a se chamar `.writing-erro`.
- **Os 6 casos:** (1) criar desafio (ex.: 429) → aviso no início; (2) abrir redação inexistente (404) → início + aviso;
  (3) erro inesperado no envio → aviso no editor, texto editável; (4) erro inesperado no "avaliar de novo" → aviso na
  tela "Redação enviada"; (5) erro ao abrir o Rewrite → resultado + aviso; (6) rodada do Rewrite já gravada →
  recarrega o Rewrite + aviso.
- **Arquivos:** `app/templates/paginas/writing.html`, `app/static/js/paginas/writing.js`, `app/static/css/writing.css`,
  `tests/writing/test_paginas.py`. Nenhum arquivo da base; nenhum encaixe.
- **Testes:** `test_paginas.py` com 16 testes (+ cada tela tem exatamente um `[data-erro]`; + o `writing.js` não
  chama nem importa `mostrarErro`; o teste antigo do `data-rw-erro` foi substituído). `node --check` no `writing.js`.
  Suíte inteira: **456 coletados, 452 aprovados, 4 pulados, 0 falhas**; `ruff` limpo; `test_base_protegida` verde.
- **Mutações (3, todas detectadas, arquivos restaurados e conferidos por hash):** (1) criar desafio volta a chamar
  `mostrarErro`; (2) o import de `mostrarErro` volta; (3) a tela "fim" sem o espaço de erro.
- **Problemas encontrados:** (1) o primeiro teste "sem `mostrarErro`" procurava o nome em qualquer lugar e falhou por
  causa do comentário que explica a decisão; passou a procurar a chamada e o import. (2) O script de mutação falhou
  duas vezes ao ler a saída do pytest (codificação do Windows e a falta da linha de resumo com `-q`), sem afetar os
  arquivos (restaurados no `finally`); corrigido e refeito.
- **Teste manual (usuário): aprovado.** Roteiro: caso 1 com a cota esgotada (clicar numa categoria: aviso vermelho abaixo das
  categorias, sem modal); caso 2 abrindo `/writing?redacao=99999`; tema claro/escuro. Os casos 3 a 6 são difíceis de
  provocar à mão: cobertos pela revisão e pela trava do teste.

## Testes

```powershell
.\venv\Scripts\Activate.ps1
python -m pytest                    # suíte inteira (SQLite temporário)
python -m pytest tests/writing      # só os testes do Writing
python -m ruff check .

# Opcionais (desligados por padrão):
$env:E2E="1"; python -m pytest tests/writing/test_e2e_writing.py --no-cov       # navegador (Chromium + internet)
$env:LLM_REAL="1"; python -m pytest tests/writing/test_llm_real.py -s --no-cov  # Gemini de verdade (LLM_CHAVE)
```

Cobertura dos arquivos do Writing: **100%** (W10).

| Arquivo | O que cobre |
|---|---|
| `tests/writing/test_fluxo_completo.py` | Integração: a sequência inteira (criar → autosave → enviar → correção → Rewrite → histórico) e o caminho com falha da correção, conferindo no banco que nada foi sobrescrito |
| `tests/writing/test_e2e_writing.py` | **Opcional (`E2E=1`)**: no Chromium, autosave + recarregar; envio → resultado com os destaques e o detalhe; Rewrite com comparação e veredito, rodada 2 e F5 |
| `tests/writing/test_llm_real.py` | **Opcional (`LLM_REAL=1`)**: 2 correções e 1 avaliação de Rewrite com a LLM de verdade, com os tempos impressos |
| `tests/writing/conftest.py` | Fixtures `temas` (o `create_all` dos testes não roda a migração de dados) e `cota_nova` (automática: limitador de cota novo a cada teste), e `criar_tema()` |
| `tests/writing/test_paginas.py` | Página `/writing` (login, telas, F5), encaixes (CSS no `base.html`, `main.js`), paridade da contagem de palavras JS × Python, erros na própria tela (D30) e os destaques do resultado (`partesDoTexto` executada no Node.js; os testes com Node são pulados se ele não estiver instalado) |
| `tests/writing/test_avaliacao_servico.py` | Serviço de avaliação com `llm_falsa`: contrato, respostas inválidas, falhas da LLM, mensagens (inclusive prompt injection), nota geral e localização dos trechos |
| `tests/writing/test_api_avaliacao.py` | Envio que corrige, falhas da LLM (redação nunca se perde), "avaliar de novo" e seus limites, duplo clique, isolamento e tamanhos/tipos de redação no fluxo completo |
| `tests/writing/test_rewrite.py` | Rewrite: extração da frase, seleção dos problemas, comparação, mensagem para a LLM, rodadas, validações, falhas da LLM, envio duplo e isolamento |
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

Checklist da seção 10 do `CLAUDE.md`:

| Item | Situação |
|---|---|
| **Dependências novas** (Python e de sistema) | **Nenhuma.** O `difflib` é da biblioteca padrão. Nada baixa modelos. O **Node.js** é opcional e só para desenvolvimento: 3 testes de JS o usam e são pulados sem ele. O **Chromium do Playwright** (já previsto no `requirements-dev.txt` da base) só para o E2E opcional |
| **Variáveis de ambiente novas** | **Nenhuma.** Usa as da LLM que já existem (`LLM_CHAVE`, `LLM_MODELO`...). Sem `LLM_CHAVE`, o app sobe e o Writing funciona até o envio; a correção responde 503 `llm_nao_configurada`, com a redação salva |
| **URLs externas** | Só o provedor da LLM (Gemini: `https://generativelanguage.googleapis.com/v1beta/openai/`, o padrão da base) |
| **Migrações** | `0301` (esquema: 4 tabelas novas, nenhuma tabela da base alterada) e `0302` (**dados**: 24 temas). A `0301` tem `down_revision = "0006"`. Na integração, juntar as cabeças das três faixas com `alembic merge` **antes** de `python -m app.migrar` (com várias cabeças, `migrar.revisao_mais_recente()`, que usa `get_current_head()`, falha) |
| **Alterações na base** | **Nenhuma.** Só os 4 encaixes (5 linhas), listados com antes e depois em "Encaixes na base" |
| **CPU, memória e tempos** | Leve no servidor (sem processamento pesado). Tempo dominado pela LLM: ver abaixo |
| **Suíte final** | SQLite (depois do W10.1): **456 coletados, 452 aprovados, 4 pulados (opcionais), 0 falhas**; `ruff` limpo; cobertura do Writing 100%. **E2E (`E2E=1`): 3 passed.** **`LLM_REAL=1`: 3 passed** (correção 3,1 a 3,7 s; Rewrite 1,1 s). **Postgres: não executado** (Docker ausente na máquina do Membro 3; **rodar na integração**) |

Detalhes:

- **Postgres:** rode a suíte com `TEST_DATABASE_URL` no `shadowing_teste` (README da base). Inclui o teste que sobe e
  desce todas as migrações, agora com a `0301` (FKs e UNIQUEs nomeados) e a `0302` (o downgrade apaga só os 24 temas
  e recusa se houver redação usando algum). Os tipos usados são os mesmos da base (JSON, DateTime, AutoString), e o
  sorteio usa `func.random()`, que existe nos dois bancos.
- **Tempo de uma correção real (para os timeouts do servidor e do proxy):** com `gemini-3.1-flash-lite`, **3 a 4 s**
  numa chamada "aquecida" e **~24 s** na primeira (ver W6). Com modelos sobrecarregados, a chamada chega ao limite de
  `LLM_TIMEOUT_SEGUNDOS` (60 s). O envio espera a correção (D7), então o proxy de produção precisa aceitar pelo menos
  **~65 s** em `POST /api/writing/attempts/{id}/submissao`, `.../avaliacao` e `.../rewrite`. Para medir no servidor
  de produção: `LLM_REAL=1 python -m pytest tests/writing/test_llm_real.py -s --no-cov`.
- **Custo da LLM por redação:** 1 chamada na correção (até 3 com "avaliar de novo", D4) + até 2 no Rewrite (uma por
  rodada, D22). A cota diária (10 por feature) só conta a criação do desafio.
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
- **Merge sem conflito esperado:** os arquivos do Writing são todos novos (`*writing*`, `tests/writing/`), e os
  encaixes estão só nos blocos `Membro 3 (Writing)`. Conferir com
  `git --no-pager diff Membro4 --stat` (só arquivos novos + 4 arquivos de encaixe + `README_MEMBRO3.md`).
