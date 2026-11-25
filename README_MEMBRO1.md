# Membro 1 — Reading Challenge

## Visão geral

O usuário lê um texto em inglês com tempo limitado e depois responde cinco perguntas de compreensão, sem poder voltar
ao texto. O texto vem da Wikipedia (padrão) ou do Project Gutenberg (via Gutendex). As perguntas são geradas pela LLM
(`app/services/llm.py`) e podem ser de **múltipla escolha** (corrigidas pelo servidor) ou **abertas** (corrigidas pela
LLM), conforme a modalidade escolhida.

## Como usar

1. Entre na conta e clique em **📖 Reading** na barra do topo (ou abra `/reading`).
2. Leia o aviso de IA e veja quantos desafios restam hoje (10 por dia).
3. Escolha o tipo de pergunta (múltipla escolha ou aberta), o texto (Wikipedia ou livro do Project Gutenberg) e a
   velocidade (150, 200 ou 250 palavras por minuto) e clique em **COMEÇAR**.
4. Leia o texto antes de o tempo acabar. Clique em **TERMINEI DE LER** quando quiser; no zero, a leitura acaba sozinha
   e o texto some.
5. Responda às 5 perguntas, sem voltar ao texto: marque uma alternativa ou escreva a resposta (até 1000
   caracteres). Pode deixar alguma em branco (conta como erro; o envio pede confirmação). Na resposta aberta, as
   respostas vão para a IA corrigir (o aviso aparece antes do envio).
6. Veja o resultado: nota de 0 a 10, ✓ / ½ / ✗ por pergunta, a resposta correta (ou esperada), a justificativa, o
   comentário da correção, os tempos e o texto de volta ("Ver o texto"). Se a IA falhar ao corrigir, as respostas
   ficam guardadas e o botão **TENTAR CORRIGIR DE NOVO** aparece.
7. **HISTÓRICO** (na tela de início e no resultado): os 50 desafios mais recentes; **Ver** abre o resultado,
   **Continuar** retoma um desafio não terminado.

Um F5 no meio do desafio volta ao mesmo ponto (a URL guarda `?desafio=ID`), com as respostas ainda não enviadas. Sem `LLM_CHAVE`, os desafios usam os
textos de reserva, com perguntas prontas.

Nenhuma variável de ambiente nova: usa as `LLM_*` que já existem.

## Arquitetura

- `app/services/reading_textos.py`: funções puras (limpeza, seleção do trecho, tempo de leitura).
- `app/services/reading_fontes.py`: Wikipedia, Gutendex, artigos salvos e reserva → `ReadingText`.
- `app/services/reading_llm.py` + `app/schemas_reading.py`: as 5 perguntas (LLM ou reserva).
- `app/services/reading_desafios.py`: criação do desafio e o tempo da leitura.
- `app/services/reading_correcao.py` e `reading_avaliacao.py`: respostas, correção da múltipla escolha e das abertas.
- `app/api/reading.py`: rotas da API (`router`) e a página `/reading` (`paginas`).
- Tela: `templates/paginas/reading.html`, `static/js/paginas/reading.js`, `static/js/nucleo/api-reading.js`,
  `static/css/reading.css`.

Fluxo de um desafio:
```
tela (reading.js → api-reading.js)
  POST /api/reading/challenges ─ cota ─► reading_desafios.criar_desafio
        ├─ reading_fontes.obter_texto ── Wikipedia (Good articles) / Gutendex ──► artigo salvo ──► reserva (0102)
        ├─ reading_llm.perguntas_para_o_desafio ── llm.gerar_json (5 perguntas) ──► falhou: texto de reserva
        └─ ReadingChallenge + 5 ReadingQuestion (1 commit; relógio depois da geração)
  GET /texto (só no prazo) · POST /encerrar-leitura (perguntas sem resposta)
  POST /respostas ─► reading_correcao (MC no servidor) | reading_avaliacao (aberta: llm.gerar_json, crédito parcial)
  GET /resultado · POST /avaliar (nova correção) · GET /challenges (histórico)
```
Rotas finas em `app/api/reading.py`; regras sem FastAPI em `app/services/reading_*.py`; banco em
`app/models_reading.py` (migrações 0101 e 0102).

## API

Todas exigem login (401 sem sessão). Erros no formato padrão `{detail, codigo}`.

| Rota | Entrada | Saída | Erros |
|---|---|---|---|
| `GET /api/reading/challenges` | — | 200: histórico, os 50 mais recentes da conta (mais novo primeiro): `[{id, iniciado_em, titulo, modalidade, estado, usou_reserva, nota, acertos}]` (`nota`/`acertos` `null` sem correção) | — |
| `POST /api/reading/challenges` (gasta 1 da cota) | `{"modalidade": "multipla_escolha" \| "aberta", "fonte"?: "wikipedia" \| "gutenberg", "ppm"?: 150 \| 200 \| 250}` (padrões `wikipedia` e 200; campo extra → 422) | 201: `id, estado, modalidade, ppm, limite_segundos, iniciado_em, leitura_encerrada_em, usou_reserva, texto{titulo, conteudo, palavras, fonte, url, credito}`. **Sem as perguntas** | 422 `dados_invalidos`; 429 `limite_de_desafios`; 502 `texto_indisponivel`; 502/503/504 `llm_*` (LLM falhou e não há reserva) |
| `GET /api/reading/challenges/{id}` | — | 200: o resumo (sem texto e sem perguntas), com `segundos_restantes` | 404 `nao_encontrado` (inexistente ou de outra conta) |
| `GET /api/reading/challenges/{id}/texto` | — | 200: `titulo, conteudo, palavras, fonte, url, credito, segundos_restantes`; só em `lendo` e até o prazo + 5 s | 409 `leitura_encerrada`; 404 |
| `POST /api/reading/challenges/{id}/encerrar-leitura` (idempotente) | — | 200: o resumo (`estado: "respondendo"`) + `perguntas[{ordem, tipo, enunciado, alternativas}]`, **sem** resposta correta e sem justificativa | 404 |
| `POST /api/reading/challenges/{id}/respostas` | `{"respostas": [5 textos]}` (na ordem; `""` = não respondida; até 1000 caracteres; campo extra → 422) | 201: o resultado (abaixo) | 422 `dados_invalidos`; 422 `resposta_invalida` (+ `ordem`: na MC, fora das alternativas); 409 `leitura_em_andamento`; 409 `ja_respondido`; 409 `tempo_invalido`; 404 |
| `GET /api/reading/challenges/{id}/resultado` | — | 200: o resultado | 409 `sem_resultado`; 404 |
| `POST /api/reading/challenges/{id}/avaliar` | — | 200: o resultado já corrigido (nova correção da aberta pela LLM) | 409 `avaliacao_indisponivel`; 502/503/504 `llm_*`; 404 |

Na aberta, `POST /respostas` grava as respostas e **depois** chama a LLM: se ela falhar, sai o erro padrão da LLM
(502/503/504), as respostas continuam gravadas e o desafio fica em `erro_avaliacao` (o `GET /resultado` mostra).

**Resultado:** `id, estado, modalidade, usou_reserva, acertos, nota (0–10), tempo_leitura_segundos,
tempo_resposta_segundos, enviado_em, avaliado_em, texto{...}, perguntas[{ordem, tipo, enunciado, alternativas,
resposta, correta, pontuacao, resposta_correta, justificativa, comentario}]`. `pontuacao`: 1, 0,5 (só na aberta) ou
0; `correta` = pontuação 1; `acertos` = quantas valem 1; `nota` = soma das pontuações × 2. Enquanto a aberta não foi
corrigida: `correta`, `pontuacao`, `acertos`, `nota` e `avaliado_em` são `null`.

Todas as respostas com o resumo trazem `segundos_restantes`, calculado no servidor (0 fora da leitura).

**Códigos próprios:**
- `texto_indisponivel` (502): a fonte falhou, não há artigo salvo e não há reserva no banco; ou o texto de reserva
  sorteado tem perguntas prontas fora do formato (R13; fica um erro no log com o id do texto).
- `leitura_encerrada` (409): o texto foi pedido depois do prazo de leitura (+ tolerância) ou depois de encerrar.
- `leitura_em_andamento` (409): respostas enviadas com o desafio ainda em `lendo`.
- `ja_respondido` (409): o desafio já tem uma tentativa.
- `tempo_invalido` (409): na submissão, os horários gravados não fecham (a leitura não terminou entre o início e o
  prazo + 5 s). Só acontece com bug ou banco alterado à mão; nada é gravado (R12).
- `resposta_invalida` (422, com `ordem`): na múltipla escolha, a resposta não é uma das alternativas.
- `sem_resultado` (409): resultado pedido antes do envio das respostas.
- `avaliacao_indisponivel` (409): nova correção pedida fora de `erro_avaliacao` (ou de `avaliando` há mais de 5 min).

**Estados do desafio:** `lendo` → `respondendo` (R6) → `corrigido` (múltipla escolha, R7). Aberta: `respondendo` →
`avaliando` (respostas gravadas) → `corrigido`, ou `erro_avaliacao` se a LLM falhar → (`/avaliar`) `avaliando` →
`corrigido` (R8).

## Banco de dados

| Rev-id | Tipo | Conteúdo |
|---|---|---|
| `0101` | esquema | `readingtext`, `readingchallenge`, `readingquestion`, `readingattempt` (bloco R1) |
| `0102` | dados | 5 trechos de artigos da Wikipedia (Honey bee, Coffee, Volcano, Moon, Penguin), CC BY-SA 4.0, cada um com 5 perguntas prontas (bloco R3; justificativas traduzidas para o português no R4, DR16) |

## Decisões

| ID | Data | Decisão | Motivo |
|---|---|---|---|
| DR1 | 21/11/2026 | Fonte padrão: Wikipedia com filtros; Gutendex como 2ª fonte (mesma interface); textos de reserva no banco como fallback (Q7) | Variedade infinita + cumpre a tarefa de domínio público; a reserva evita ficar sem texto |
| DR2 | 21/11/2026 | O usuário escolhe a modalidade: 5 de múltipla escolha **ou** 5 abertas (Q8) | A lista de tarefas pede os dois modos e registra a "modalidade escolhida" |
| DR3 | 21/11/2026 | Fallback das perguntas: se a LLM não gerar 5 perguntas válidas, o desafio usa um texto de reserva com perguntas prontas | O usuário faz o desafio mesmo com a IA fora; o desafio conta na cota |
| DR4 | 21/11/2026 | Velocidade de leitura: o usuário escolhe 150, 200 ou 250 palavras/min (padrão 200) | Tempo limite = palavras ÷ ppm × 60, adaptado ao nível |
| DR5 | 21/11/2026 | Tamanho do texto: 250 a 600 palavras, cortando no fim de um parágrafo | Leitura de 1 a 4 min; limita o custo da LLM |
| DR6 | 21/11/2026 | Sem limite de tempo para responder (o tempo gasto é registrado) | A lista só pede o bloqueio da leitura |
| DR7 | 21/11/2026 | Código (nomes, comentários, mensagens) em português; os testes de cada bloco ficam prontos antes do próximo | Pedido do usuário; segue o padrão do repositório |
| DR8 | 21/11/2026 | Sem prazo fixo: os blocos seguem a ordem das dependências | Decisão do usuário |
| DR9 | 21/11/2026 | Seleção do trecho (opções C + B): só parágrafos inteiros, nunca corte no meio. Prioriza a introdução; se não couber em 250–600 palavras, procura um bloco contínuo de outra seção; se nada couber, descarta o artigo (a fonte tenta outro, até 3 vezes, e depois usa a reserva) | O texto fica íntegro (com começo e fim naturais) sem perder artigos longos |
| DR10 | 21/11/2026 | Tempo limite arredondado para cima em múltiplos de 5 s (ex.: 90,3 s → 95 s) | Timer mais legível; decisão do usuário |
| DR11 | 21/11/2026 | Só o título do artigo/livro aparece (`ReadingText.titulo`); os títulos de seção e capítulo servem para separar as seções e são descartados (opção B) | Mais simples; não muda o esquema nem o R2 |
| DR12 | 21/11/2026 | Reserva em duas camadas: (1) a fonte falhou → artigo da mesma fonte já salvo no banco (a LLM gera as perguntas); (2) nenhum salvo, ou a LLM falhou → um dos 5 artigos fixos da Wikipedia da 0102, com perguntas prontas. Sempre com crédito e licença (`reading_fontes.credito`) | A reserva também é Wikipedia e cresce com o uso; a CC BY-SA exige crédito |
| DR13 | 21/11/2026 | Gutenberg: descarta o que vem antes do primeiro capítulo com texto (prefácio, sumário) e dá prioridade ao capítulo 1 | O começo do livro costuma ser prefácio ou sumário |
| DR14 | 21/11/2026 | Falha de rede ou timeout da fonte não é repetida: vai direto ao artigo salvo ou à reserva (só artigos ruins geram nova tentativa, até 3) | Cada nova tentativa esperaria o timeout de novo (mesma regra do `llm.py`) |
| DR15 | 21/11/2026 | Rodar os testes com `python -m pytest`; o problema do `pytest` puro (preexistente) fica anotado para o Membro 4, sem alterar o `pyproject.toml` | O `pyproject.toml` é base protegida; a correção é de uma linha e vale para as três features |
| DR16 | 21/11/2026 | Enunciados e alternativas em inglês; justificativa em português, citando entre aspas o trecho do texto em inglês. As justificativas da reserva foram traduzidas **editando a própria 0102** (decisão do usuário), e não numa migração nova | Treino de leitura em inglês, explicação na língua de quem aprende. A 0102 ainda não saiu desta branch; um banco que já a aplicou continua com as justificativas antigas (ver registro do R4) |
| DR17 | 21/11/2026 | Qualquer falha da LLM, inclusive LLM não configurada (sem `LLM_CHAVE`), leva a um texto de reserva com as perguntas prontas (`usou_reserva=True`, aviso no log). Sem reserva, o `ErroLLM` sobe (502/503/504) | O app funciona para quem ainda não criou a chave; a tela pode avisar "perguntas prontas" |
| DR18 | 21/11/2026 | Perguntas de nível intermediário (B1–B2). Nível escolhido pelo usuário fica para depois, se houver tempo | Os textos são autênticos (Wikipedia/Gutenberg) |
| DR19 | 21/11/2026 | Desafios simultâneos são permitidos: um desafio novo não cancela o anterior, que expira pelo tempo (R6) | Bloquear exigiria a regra e a tela de "abandonar desafio" |
| DR20 | 21/11/2026 | `fonte` opcional no corpo (padrão `wikipedia`); a tela do R9 mostra o seletor | Simples para o cliente; a Wikipedia é a fonte padrão (DR1) |
| DR21 | 21/11/2026 | `GET /challenges/{id}` já no R5, só com o resumo (sem texto e sem perguntas); o texto durante a leitura fica para o R6 | Testa o isolamento desde já; as regras de tempo são do R6 |
| DR22 | 22/11/2026 | Tolerância de 5 s depois do prazo para entregar o texto | Cobre a latência entre o timer zerar na tela e a requisição chegar |
| DR23 | 22/11/2026 | Encerrar a leitura antes do tempo é permitido (botão "Terminei de ler"); o tempo real fica gravado | Tempo de leitura real entra no resultado (R7) |
| DR24 | 22/11/2026 | Prazo vencido sem encerrar (aba fechada): as perguntas continuam disponíveis e a leitura conta como o limite | Coerente com a DR6 (sem limite para responder) |
| DR25 | 22/11/2026 | Resposta em branco (`""`) é aceita como "não respondida" e conta como erro | A pessoa pode enviar sem responder todas |
| DR26 | 22/11/2026 | O resultado traz o texto de novo (título, conteúdo e crédito) | A leitura acabou; serve para conferir as justificativas |
| DR27 | 22/11/2026 | Nota de 0 a 10: cada acerto vale 2 | Escala prevista no modelo (`nota`) |
| DR28 | 22/11/2026 | Respostas com o desafio em `lendo` → 409 `leitura_em_andamento` (sem encerrar automaticamente) | A tela sempre encerra antes; encerrar sozinho esconderia um erro do front |
| DR29 | 22/11/2026 | **Crédito parcial** na aberta (decisão do usuário): a LLM dá 1, 0,5 ou 0 por pergunta, com comentário em português. Nota = soma × 2 (0 a 10); `acertos` conta só as que valem 1. Julga o sentido, não a gramática | Mais justo com respostas incompletas; a escala da nota continua a mesma da múltipla escolha |
| DR30 | 22/11/2026 | A correção recebe o texto inteiro, além da resposta esperada | Aceita respostas certas escritas de outro jeito (≈ 600 tokens a mais) |
| DR31 | 22/11/2026 | Nova correção (`/avaliar`) em `erro_avaliacao`, ou em `avaliando` há mais de 5 minutos (servidor caiu no meio da chamada) | Ninguém fica com o desafio travado |
| DR32 | 22/11/2026 | Falha da LLM ao corrigir: grava `erro_avaliacao` e relança o `ErroLLM` (502/503/504) | Convenção documentada no `llm.py`; o front já trata `erro.codigo` |
| DR33 | 22/11/2026 | Chromium instalado (`python -m playwright install chromium`, fora do repositório) e E2E do Reading já no R9 (`E2E=1`) | O comportamento da tela (timer, F5, encerrar) só é testável num navegador |
| DR34 | 22/11/2026 | F5 retoma o desafio: a URL guarda `?desafio=ID` | Sem isso, o F5 perderia o desafio já pago com a cota |
| DR35 | 22/11/2026 | Copiar/selecionar o texto não é bloqueado | Atrapalha a acessibilidade e não impede a burla; o servidor garante prazo e tempo registrado |
| DR36 | 22/11/2026 | Botão "📖 Reading" na navbar | Exemplo do CLAUDE.md, estilo dos outros botões |
| DR37 | 22/11/2026 | Wikipedia: sorteio entre os **"Good articles"** (`generator=search`, `incategory:Good_articles`, `gsrsort=random`), e não entre todos os artigos | Medição real: 1 de 6 artigos aleatórios aproveitáveis × 7 de 8 Good articles; continua uma chamada por tentativa |
| DR38 | 22/11/2026 | Temas de história militar são aceitos; o filtro `eh_inadequado` continua barrando só termos fortes | Conteúdo enciclopédico comum; filtrar "war"/"battle" descartaria muitos artigos bons |
| — | 23/11/2026 | **Não feita:** sem `LLM_CHAVE`, ir direto à reserva sem buscar o artigo (sugestão opcional; o usuário seguiu para o R10) | Hoje, sem chave, o artigo é buscado e gravado, mas o desafio usa a reserva (DR17) |
| DR39 | 23/11/2026 | Envio com perguntas em branco pede `confirm()` ("Há N perguntas sem resposta. Enviar mesmo assim?") | Mesmo padrão da base (deletar deck) |
| DR40 | 23/11/2026 | Rascunho das respostas no `sessionStorage` (chave `reading-rascunho-<id>`), apagado no envio | O F5 nas perguntas não perde o que foi escrito; é só conveniência (fica no navegador) |
| DR41 | 23/11/2026 | Histórico: os 50 mais recentes, sem paginação | Simples; consulta pelo índice de `usuario_id` |
| DR42 | 23/11/2026 | Desafios não terminados aparecem no histórico com "Continuar" | Retoma a leitura ou as respostas pelo mesmo `?desafio=ID` |
| DR43 | 24/11/2026 | Conferência explícita do tempo na submissão (guia, seção 7): o servidor recalcula com os horários gravados que a leitura terminou entre o início e o prazo + 5 s; senão, 409 `tempo_invalido`. Responder continua sem limite (DR6) | O guia pede a conferência na submissão; a DR6 foi mantida |
| DR45 | 24/11/2026 | Gutenberg (R12b): Gutendex só na 1ª página e sem `mime_type`; `.txt` do espelho oficial `gutenberg.pglaf.org/cache/epub/{id}/pg{id}.txt`; no máximo 150 KB e 25 s por livro, cortando na última linha em branco; obras de consulta e coletâneas filtradas pelo título | Medição real: a consulta filtrada passava de 20 s e o `gutenberg.org` respondia 503; o espelho entrega ≈ 27 KB/s e o trecho sai dos primeiros KB |
| DR44 | 24/11/2026 | Migração 0101: **sem mudanças** (decisão do usuário). Conferida com o próprio autogenerate (`alembic check` num banco migrado até a 0102: "No new upgrade operations detected"), sem teste automático novo | A 0101 escrita à mão produz exatamente o esquema dos modelos; reescrever com `--autogenerate` perderia os nomes das FKs |

## Plano e progresso

**Linha de base** (21/11/2026, branch `Membro1`, HEAD `49636dd`, antes de qualquer mudança): `pytest` 266 aprovados,
2 pulados (E2E e Postgres, desligados por padrão), 0 falhas; `ruff check .` limpo. Para rodar, foi instalado o
`requirements-dev.txt` na venv (a venv não tinha pytest/ruff).

**Tarefas de agosto (UI de Decks: listagem, modal "Salvar Card", estados salvo/não salvo, guia fonético,
responsividade):** já entregues na base (`paginas/decks.js`, `componentes/escolha-deck.js`, `paginas/estudo.js`,
blocos B1–B13 do `docs/IMPLEMENTATION_PLAN.md`). Não há trabalho nesta branch; alterá-las seria mudar a base.

| ID | Bloco | Tarefas atendidas | Depende de | Status |
|---|---|---|---|---|
| R1 | Modelos e migração do esquema | Modelagem das 4 entidades; migrations Alembic | — | ✅ Concluído (21/11) |
| R2 | Normalização e tempo de leitura | Normalização dos textos; contagem de palavras e limite por ppm | — | ✅ Concluído (21/11) |
| R3 | Fontes: Wikipedia, Gutendex e reserva | Serviço MediaWiki; adaptador de domínio público; testes de obtenção e seleção | R1, R2 | ✅ Concluído (21/11) |
| R3b | Artigos da Wikipedia com tamanho suficiente | Serviço MediaWiki (qualidade do sorteio) | R3 | ✅ Concluído (22/11) |
| R4 | Perguntas geradas pela LLM | Serviço de LLM separado do HTTP; prompt de 5 perguntas; schema estruturado; modos MC e Open; fallback | R1 | ✅ Concluído (21/11) |
| R5 | Criação do desafio (API) | `POST /api/reading/challenges`; validação Pydantic; falhas | R3, R4 | ✅ Concluído (21/11) |
| R6 | Leitura com tempo validado no servidor | Bloqueio da leitura quando o tempo termina (servidor) | R5 | ✅ Concluído (22/11) |
| R7 | Submissão e correção de múltipla escolha | Submissão e correção; pontuação; tempo, acertos e modalidade; persistência | R6 | ✅ Concluído (22/11) |
| R8 | Correção das abertas pela LLM | Correção com saída estruturada; tratamento de falhas da LLM | R7 | ✅ Concluído (22/11) |
| R9 | Tela: início e leitura com timer | Página de leitura com timer; bloqueio automático (tela) | R6 | ✅ Concluído (22/11) |
| R10 | Tela: questões, resultado e histórico | Página das cinco questões | R7, R8, R9 | ✅ Concluído (23/11) |
| R11 | Integração, E2E e entrega | Testes de serviços, integração e E2E; Postgres; "Para o Membro 4" | todos | ✅ Concluído (24/11) |
| R12 | Acertos finais conforme o guia | Fixtures em `tests/reading/conftest.py`; conferência do tempo na submissão; verificação real do Gutenberg | R11 | ✅ Concluído (24/11) |
| R12b | Fonte Gutenberg funcionando | Adaptador de domínio público (uso real) | R12 | ✅ Concluído (24/11) |
| R13 | Casos de borda | Testes e duas correções (download só `text/plain`; reserva corrompida → 502) | R12b | ✅ Concluído (24/11), aguardando commit |

MVP: R1–R7 e R9. Escopo completo: R8 e R10. Fechamento: R11.

### R1 — Modelos e migração do esquema (✅ 21/11/2026)

- **Arquivos:** `app/models_reading.py` (novo: `ReadingText`, `ReadingChallenge`, `ReadingQuestion`,
  `ReadingAttempt`), `migrations/versions/0101_reading.py` (novo), `tests/reading/test_reading_modelos.py` (novo);
  ponto de encaixe: 1 linha em `app/models.py` (`import app.models_reading`).
- **Decisões:** valores de `fonte`/`modalidade`/`estado`/`tipo` como texto (validados nos schemas e serviços, sem Enum
  no banco); perguntas de reserva como JSON no próprio `ReadingText`; `ReadingAttempt` com UNIQUE em `desafio_id`
  (uma tentativa por desafio, garantida pelo banco); sem `Relationship` com `Usuario` (exigiria alterar a base).
- **Migração:** o autogenerate gerou as FKs sem nome e um índice redundante em `readingattempt.desafio_id`; a migração
  foi reescrita com todas as FKs e UNIQUEs nomeadas, e o índice redundante saiu do modelo (o UNIQUE já indexa).
  Aplicada no banco de desenvolvimento com `python -m app.migrar` (backup em `dados/backup/`).
- **Testes:** 10 novos (gravação e leitura com JSON, valores padrão, os três UNIQUEs, cinco perguntas por desafio,
  nomes das FKs e UNIQUEs após a migração, downgrade para a 0006 e upgrade de volta, encaixe em `app/models.py`).
  Suíte: **276 aprovados, 2 pulados, 0 falhas** (SQLite); `ruff` limpo. Postgres e E2E não executados neste bloco.
- **Mutações (todas detectadas, arquivos restaurados e conferidos com `cmp`):** sem UNIQUE da tentativa; FK sem nome
  na migração; sem import no encaixe; downgrade sem remover `readingtext`; UNIQUE da pergunta sem `ordem`.
- **Problemas encontrados:** (1) a mutação "sem import no encaixe" passou na 1ª versão do teste, porque o próprio
  arquivo de teste importava `app.models_reading` e mascarava a falta; o teste passou a rodar num processo novo.
  (2) A mutação "UNIQUE sem ordem" só era pega pelo `test_migracoes`; foi acrescentado o teste de cinco perguntas em
  ordens diferentes.
- **Atenção na integração (Membro 4):** as migrações 0101, 0201 e 0301 partem da 0006 → várias cabeças; o
  `app/migrar.py` usa `get_current_head()` e exige o `alembic merge` antes.
- **Próxima ação:** R2 (normalização dos textos e tempo de leitura).

### R2 — Normalização e tempo de leitura (✅ 21/11/2026)

- **Arquivos:** `app/services/reading_textos.py` (novo), `tests/reading/test_reading_textos.py` (novo). Nenhum
  arquivo da base, nenhum ponto de encaixe.
- **Funções (puras):** `normalizar` (HTML, entidades, referências `[n]`, espaços), `limpar_wikipedia` e
  `limpar_gutenberg` (texto bruto → seções com parágrafos; listas, títulos, cabeçalho/rodapé do Gutenberg e seções
  finais da Wikipedia saem), `eh_inadequado` (listas, desambiguação, temas sensíveis por início de palavra),
  `selecionar_trecho` (DR9), `contar_palavras`, `limite_leitura_segundos` (DR10).
- **Constantes:** `VELOCIDADES_PPM = (150, 200, 250)`, `PPM_PADRAO = 200`, `PALAVRAS_MIN = 250`,
  `PALAVRAS_MAX = 600`, `ARREDONDAMENTO_SEGUNDOS = 5`, `SECOES_FINAIS`, lista de termos sensíveis.
- **Decisões:** tempo calculado só com inteiros (divisão com teto), sem erro de float nos limites exatos; o filtro de
  conteúdo é uma lista de termos (simples e previsível, não infalível; ajustável numa constante).
- **Testes:** 44 novos. Suíte: **320 aprovados, 2 pulados, 0 falhas** (SQLite); `ruff` limpo. Postgres e E2E não
  executados (o bloco não usa banco).
- **Mutações (9, todas detectadas; arquivo restaurado e conferido com `cmp`):** sem remover `[n]`; parágrafo que
  passa do máximo incluído (corte); bloco atravessando seções; sem prioridade da introdução; sem arredondar para 5 s;
  fórmula invertida; filtro sensível sem início de palavra; linhas de lista aceitas; sem parar nas seções finais.
- **Problemas encontrados:** (1) um teste meu esperava o bloco 200+200 = 400, mas 200+300 = 500 também é contínuo e
  maior; o código estava certo, a expectativa foi corrigida. (2) A mutação do filtro sensível passou na 1ª versão:
  os exemplos ("therapist", "grapevine") não dependiam do `\b` inicial; trocados por "grapes"/"drapes"/"popcorn".
- **Próxima ação:** R3 (fontes: Wikipedia, Gutendex e textos de reserva).

### R3 — Fontes: Wikipedia, Gutendex e reserva (✅ 21/11/2026)

- **Arquivos:** `app/services/reading_fontes.py` (novo), `migrations/versions/0102_textos_reserva.py` (novo, só dados),
  `tests/reading/test_reading_fontes.py` (novo). Ajustes em arquivos da própria feature: `app/services/reading_textos.py`
  (DR13), `app/models_reading.py` (comentários e `JSON(none_as_null=True)`), testes do R1 e do R2. Nenhum arquivo da
  base, nenhum ponto de encaixe, nenhuma dependência nova (`requests` já existe).
- **Como funciona:** `obter_texto(session, "wikipedia" | "gutenberg")` → até 3 artigos (curtos, longos sem bloco
  válido ou inadequados são pulados; falha de rede não é repetida, DR14) → grava o `ReadingText` (ou reaproveita o
  mesmo artigo; corrida no UNIQUE tratada relendo a linha) → se nada der certo, `texto_salvo` (mesma fonte, sem
  reserva) → `texto_de_reserva` → `TextoIndisponivel` (a rota do R5 vira 502). `credito(texto)` monta o crédito e a
  licença para a tela.
- **Wikipedia:** uma chamada por tentativa (`generator=random`, `prop=extracts|info`, `explaintext`, `inprop=url`).
  **Gutenberg:** Gutendex (`languages=en`, `copyright=false`, `mime_type=text/plain`, página 1–20 sorteada) → livro
  sorteado → `.txt` baixado com `stream`, no máximo 3 MB. Timeouts: 10 s (APIs) e 20 s (livro). User-Agent do projeto.
- **Textos de reserva (0102):** os 5 trechos foram baixados uma única vez (21/11/2026) e passaram pelas regras do R2;
  as perguntas foram escritas para o projeto (4 alternativas, resposta correta, justificativa com citação do texto) e
  servem às duas modalidades (na aberta, sem as alternativas). Ficam com `fonte="wikipedia"` (o crédito depende da
  fonte); o que os identifica é `perguntas_reserva` preenchido. Downgrade: apaga os não usados e transforma os já
  usados em textos comuns (preserva o histórico). Se um desses artigos já tiver sido gravado antes da 0102, ele não é
  duplicado (fica sem perguntas prontas).
- **Bug encontrado e corrigido (vinha do R1):** a coluna JSON gravava o `None` do Python como o texto JSON `'null'`, e
  não como `NULL` do SQL; o filtro "é reserva?" (`IS NULL`) não funcionaria. Correção: `JSON(none_as_null=True)` no
  modelo (não muda o DDL nem a 0101) e `sa.null()` no downgrade da 0102; novo teste no R1.
- **Testes:** 31 novos (28 de fontes e reserva, 2 do Gutenberg no R2, 1 de NULL no R1). Suíte: **351 aprovados, 2
  pulados, 0 falhas** (SQLite); `ruff` limpo. Nenhum teste acessa a rede (sessão HTTP falsa). Postgres e E2E não
  executados.
- **Mutações (15, todas detectadas; arquivos restaurados e conferidos com `cmp`):** sem limite de tentativas; rede
  fora levanta erro; rede fora repete; reserva antes do salvo; salvo incluindo a reserva; salvo de outra fonte; sem
  timeout; sem limite de bytes; inadequados aceitos; `.zip` aceito; corrida sem reler; sem consulta antes do INSERT;
  status 4xx aceito; Gutenberg sem prioridade do capítulo 1; JSON `None` como `'null'`.
- **Problemas encontrados:** (1) a mutação "status 4xx aceito" passou na 1ª versão: a resposta 429 do teste não tinha
  JSON e falhava pelo motivo errado; agora o corpo é válido. (2) A mutação "sem consulta antes do INSERT" passou: o
  resultado continua certo por causa do tratamento da corrida; novo teste confere que reaproveitar não faz rollback.
  (3) O banco de desenvolvimento apareceu já na 0102 (backup das 19:56 criado pelo `migrar`, não rodado por mim).
- **Próxima ação:** R4 (perguntas geradas pela LLM, modos múltipla escolha e aberta, fallback para a reserva).

### R4 — Perguntas geradas pela LLM (✅ 21/11/2026)

- **Arquivos:** `app/schemas_reading.py` (novo), `app/services/reading_llm.py` (novo), `tests/reading/test_reading_llm.py`
  (novo), `tests/reading/test_reading_modelos.py` (sem `session.query`); `migrations/versions/0102_textos_reserva.py` (justificativas em português, DR16; o resto idêntico). Nenhum
  arquivo da base: o `llm.py` só é usado. Nada é gravado no banco neste bloco (as `ReadingQuestion` são gravadas no R5).
- **Schemas:** um por modalidade (`PerguntasMultiplaEscolha`, `PerguntasAbertas`), com exatamente 5 perguntas de
  enunciados diferentes. Pergunta: `enunciado`, `tipo`, `alternativas`, `resposta_correta`, `justificativa`, com
  limites de tamanho. Múltipla escolha: 4 alternativas diferentes (ignorando maiúsculas e espaços) e a resposta entre
  elas (guardada com a grafia exata da alternativa, para a correção do R7 comparar strings). Aberta: `alternativas`
  sempre vazia. O mesmo schema vai para a LLM (JSON Schema) e valida as perguntas da reserva.
- **Como funciona:** `perguntas_para_o_desafio(session, texto, modalidade)` → (1) texto de reserva: perguntas prontas,
  sem LLM; (2) senão `gerar_perguntas` → `llm.gerar_json` (prompt base + regras da modalidade; título e trecho na
  mensagem do usuário, entre `<texto>` e `</texto>`, com as marcas retiradas do conteúdo); (3) `ErroLLM` → texto de
  reserva sorteado (DR17); (4) sem reserva → relança. As alternativas são embaralhadas no servidor. Devolve
  `PerguntasDoDesafio(texto, perguntas, usou_reserva, modelo_llm)`; `modelo_llm` é `None` nas perguntas prontas.
- **Prompt:** nível B1–B2 (DR18); respondível só pelo trecho; tipos variados (ideia principal, detalhe, vocabulário no
  contexto, inferência); justificativa em português citando o texto; ignorar instruções dentro do texto. Temperatura e
  `max_tokens`: os padrões do `llm.py` (0,2 e sem limite).
- **Testes:** 36 novos (schemas, prompt, embaralhamento, nova tentativa, reserva por resposta inválida, timeout,
  provedor fora e LLM não configurada, reserva sem chamar a LLM, modalidade aberta, as 5 reservas reais da 0102 nas
  duas modalidades). Suíte: **387 aprovados, 2 pulados, 0 falhas** (SQLite); `ruff` limpo. Postgres e E2E não
  executados.
- **Mutações (16, todas detectadas no fim; arquivos restaurados e conferidos com `cmp`):** aceitar 4 perguntas;
  sem checar a resposta entre as alternativas; alternativas repetidas; aberta com alternativas; enunciados repetidos;
  sem normalizar a grafia da resposta; sem embaralhar; sem cair na reserva; chamar a LLM para texto de reserva; manter
  o texto original na reserva; `usou_reserva=False`; prompt da modalidade errada; marcas `<texto>` não retiradas;
  schema errado na aberta; resposta esperada errada na aberta da reserva; 0102 com as justificativas antigas.
- **Problemas encontrados:** (1) a mutação "sem checar a resposta entre as alternativas" passou na 1ª versão: a linha
  seguinte (`index`) também falha, mas com uma mensagem genérica, e essa mensagem volta para a LLM na 2ª tentativa;
  novo teste confere a mensagem. (2) O gerador da 0102 (scratchpad) tinha o downgrade antigo, sem `sa.null()`;
  corrigido antes de gerar de novo, e o diff da 0102 mostra só o docstring e as justificativas. (3) **O banco de
  desenvolvimento (`dados/estudos.db`) já estava na 0102 e continua com as justificativas em inglês**: o Alembic não
  roda de novo uma migração aplicada. Nenhum desafio usa a reserva ainda. **Resolvido:** o usuário rodou o downgrade
  para a 0101 e o `migrar` (backup `estudos-20261121-215758-730617.db`); os 5 textos têm as justificativas em português.
  (4) 8 `DeprecationWarning` do SQLModel nos testes do R1 (`session.query`, estilo antigo do SQLAlchemy): trocados por
  `session.exec(select(...))` em `test_reading_modelos.py`, mesmo comportamento. Resta 1 warning, preexistente da base
  (`StarletteDeprecationWarning` do `TestClient`, importado pelo `tests/conftest.py`).
- **Próxima ação:** R5 (rota `POST /api/reading/challenges`: cota, texto, perguntas, gravação e isolamento).

### R5 — Criação do desafio (API) (✅ 21/11/2026)

- **Arquivos:** `app/api/reading.py` (novo), `app/services/reading_desafios.py` (novo), `app/schemas_reading.py`
  (`NovoDesafio`, `TextoDoDesafio`, `ResumoDesafio`, `DesafioCriado`), `tests/reading/test_reading_api.py` (novo).
  **Ponto de encaixe:** 2 linhas no bloco "Membro 1 (Reading)" de `app/main.py` (`from app.api import reading` +
  `rotas += [reading.router]`; o router da página entra no R9). Nenhum outro arquivo da base.
- **Como funciona:** `POST /api/reading/challenges` → `usuario_atual` (401) → `exigir_cota("reading")` (429) →
  `NovoDesafio` (422) → `reading_desafios.criar_desafio`: `obter_texto` (R3) → `perguntas_para_o_desafio` (R4) →
  `limite_leitura_segundos` com o texto **usado** (o de reserva, se a LLM falhou) → `ReadingChallenge` +
  5 `ReadingQuestion` (ordem 1–5) num único commit (`flush` para obter o id, depois `commit`). `iniciado_em` é marcado
  depois da geração (a espera não conta como leitura). `TextoIndisponivel` → 502 `texto_indisponivel`; `ErroLLM`
  sobe para o handler da base. A resposta traz o texto e o crédito, nunca as perguntas.
- **Isolamento:** `_desafio()` (padrão `_deck`): de outra conta ou inexistente → 404 com a mesma resposta.
- **Testes:** 20 novos (integração FastAPI + serviços + banco, com fonte falsa em `rf.FONTES` e `llm_falsa`): criação
  e gravação, resposta sem as perguntas, padrões e escolhas, 6 corpos inválidos, 401, cota (10 + 429, por conta), 502
  sem texto, reserva quando a LLM falha (limite com o texto de reserva), 504 sem reserva sem gravar nada, desafios
  simultâneos, relógio depois da geração, falha ao gravar sem desafio pela metade, ppm inválido antes da busca, resumo,
  isolamento. O `test_protecao_api` passou a cobrir as 2 rotas novas sozinho. Suíte: **409 aprovados, 2 pulados,
  0 falhas** (SQLite); `ruff` limpo. Postgres e E2E não executados.
- **Mutações (15, todas detectadas; arquivos restaurados e conferidos com `cmp`):** sem cota; `_desafio` sem checar o
  dono; dono errado com 403; `TextoIndisponivel` sem tratamento; sem crédito; perguntas na resposta; campo extra
  aceito; ppm livre; `iniciado_em` antes da LLM; commit antes das perguntas; limite com o texto original; ordem a
  partir de 0; ppm sem checagem antes da busca; `usou_reserva` fixo; router não registrado.
- **Problemas encontrados:** (1) um teste esperava 300 palavras, mas o texto de exemplo tinha 299 (erro no teste;
  o código estava certo). (2) O script de mutação quebrou ao ler uma linha de erro do pytest e deixou
  `app/api/reading.py` mutado; restaurado na hora (conferido com `cmp`), e o script passou a restaurar com
  `try/finally`. (3) **Achado na base:** uma requisição com corpo inválido (422) **gasta 1 da cota**: o FastAPI roda a
  dependência `exigir_cota` antes de validar o corpo. Conferido com um teste temporário (restaram 9 de 10). Vale para
  as três features; registrado em "Para o Membro 4".
- **Próxima ação:** R6 (leitura com o tempo validado no servidor: texto só enquanto o tempo não acaba, encerrar a
  leitura e liberar as perguntas sem as respostas).

### R6 — Leitura com o tempo validado no servidor (✅ 22/11/2026)

- **Arquivos:** `app/services/reading_desafios.py` (funções de tempo, `encerrar_leitura`, `perguntas_do_desafio`),
  `app/api/reading.py` (rotas `/texto` e `/encerrar-leitura`; resumo com `segundos_restantes`), `app/schemas_reading.py`
  (`TextoParaLer`, `PerguntaParaResponder`, `LeituraEncerrada`; `segundos_restantes` no `ResumoDesafio`),
  `tests/reading/test_reading_leitura.py` (novo). Nenhum arquivo da base, nenhuma migração (os campos existem desde o R1).
- **Como funciona:** prazo = `iniciado_em + limite_segundos`. O bloqueio é calculado a cada requisição (sem tarefa
  agendada): `leitura_disponivel` = estado `lendo` e agora ≤ prazo + 5 s. `encerrar_leitura` faz um **UPDATE
  condicional** (`WHERE estado = 'lendo'`) que grava `estado="respondendo"` e `leitura_encerrada_em = min(agora,
  prazo)`: com duas requisições ao mesmo tempo, só a primeira grava; chamar de novo não muda nada (idempotente).
  As perguntas saem na ordem 1–5, só com `ordem, tipo, enunciado, alternativas`. `segundos_restantes` arredonda para
  cima e é 0 fora da leitura; o timer da tela (R9) usa esse número, e não o relógio do navegador.
- **Testes:** 25 novos, com relógio falso (`rd.agora`), sem `sleep`: texto dentro do prazo; limite exato, limite + 5 s,
  + 6 s e 1 h; texto depois de encerrar; encerrar antes (horário real) e depois do prazo (fim do prazo); perguntas sem
  resposta e sem justificativa (MC e aberta); idempotência; duas sessões simultâneas; resumo; isolamento nas duas rotas
  (e o desafio da Ana continua em `lendo`); funções puras (arredondamento, estado); ordem com perguntas gravadas fora de
  ordem. O `test_protecao_api` cobre as 2 rotas novas. Suíte: **436 aprovados, 2 pulados, 0 falhas** (SQLite); `ruff`
  limpo. Postgres e E2E não executados.
- **Mutações (15; 14 detectadas e 1 equivalente; arquivos restaurados e conferidos com `cmp`):** sem tolerância;
  tolerância infinita; texto depois de encerrar; sem o `min`; encerrar sobrescrevendo o horário; perguntas sem ordenar;
  restantes sem arredondar para cima; restantes ignorando o estado; perguntas com `resposta_correta`; com justificativa;
  texto sem checar o prazo; `/texto` e `/encerrar-leitura` sem checar o dono; resumo com o limite no lugar do restante.
  **Equivalente:** tirar o `session.refresh` do `encerrar_leitura` não muda nada, porque o `commit()` já expira os
  objetos da sessão (`expire_on_commit`, padrão do `get_session`); o `refresh` ficou para deixar a releitura explícita.
- **Problemas encontrados:** a mutação "sem tolerância" passou na 1ª versão: o teste lia `rd.TOLERANCIA_SEGUNDOS` e se
  ajustava à constante mutada. Agora usa os valores fixos da decisão DR22 (140 s e 141 s).
- **Próxima ação:** R7 (submissão e correção da múltipla escolha: pontuação, tempos, acertos, modalidade, persistência).

### R7 — Submissão e correção da múltipla escolha (✅ 22/11/2026)

- **Arquivos:** `app/services/reading_correcao.py` (novo), `app/api/reading.py` (rotas `/respostas` e `/resultado`),
  `app/schemas_reading.py` (`RespostasEnviadas`, `PerguntaCorrigida`, `ResultadoDesafio`),
  `tests/reading/test_reading_respostas.py` (novo). Nenhum arquivo da base, nenhuma migração (`ReadingAttempt` é do R1).
- **Como funciona:** `enviar_respostas(session, desafio, respostas)`: em `lendo` → `LeituraEmAndamento` (409); já
  respondido (estado ≠ `respondendo` ou tentativa existente) → `JaRespondido` (409) **antes** de corrigir. Múltipla
  escolha: `corrigir_multipla_escolha` (função pura) exige cada resposta entre as alternativas ou `""`
  (`RespostaInvalida` → 422 com a `ordem`) e compara com a grafia exata; `acertos`, `nota = acertos × 2`,
  `avaliado_em`, estado `corrigido`. Aberta: grava as respostas e o estado vai para `avaliando` (R8). Tempos: leitura =
  `leitura_encerrada_em − iniciado_em`, resposta = envio − fim da leitura. A tentativa e o estado vão num único commit;
  a corrida entre dois envios é decidida pelo UNIQUE (`IntegrityError` → rollback → `JaRespondido`). O resultado
  (POST e GET iguais) traz por pergunta a resposta da pessoa, se acertou, a resposta correta e a justificativa, e o
  texto com o crédito (DR26).
- **Testes:** 30 novos, com relógio falso: nota 10 e resultado completo; 4 combinações de acertos (com respostas em
  branco); gravação no banco; prazo vencido (leitura = limite); GET igual ao POST; 409 `sem_resultado`; 6 corpos
  inválidos; `resposta_invalida` sem gravar nada; 409 em `lendo`; segundo envio recusado sem alterar o primeiro e sem
  refazer a correção; corrida entre duas sessões; aberta gravada em `avaliando` sem chamar a LLM; isolamento nas duas
  rotas; funções puras (grafia exata, uma resposta por pergunta, nota). O `test_protecao_api` cobre as 2 rotas novas.
  Suíte: **468 aprovados, 2 pulados, 0 falhas** (SQLite); `ruff` limpo. Postgres e E2E não executados.
- **Mutações (18; 17 detectadas e 1 equivalente; arquivos restaurados e conferidos com `cmp`):** nota em escala
  errada; sempre acerta; branco como certa; resposta fora das alternativas; envio em `lendo`; segundo envio sem
  checagem prévia; corrida sem tratar o `IntegrityError`; tempos trocados; estado não atualizado; aberta corrigida
  como MC; sem `avaliado_em`; 4 respostas; sem limite de tamanho; campo extra; resultado sem checar o dono; resultado
  sem o texto; resultado sem justificativa. **Equivalente:** comparar ignorando maiúsculas, porque a resposta já tem de
  ser uma das alternativas (grafia exata) e o R4 garante alternativas diferentes mesmo ignorando maiúsculas.
- **Problemas encontrados:** (1) duas mutações passaram na 1ª rodada: "resultado sem o texto" (o teste conferia
  título e crédito, não o conteúdo) e "segundo envio sem checagem prévia" (o UNIQUE ainda recusava, mas depois de
  corrigir de novo; no R8 seria uma chamada à LLM gasta à toa). Os dois testes foram reforçados. (2) A rodada inteira
  de mutações passou do tempo limite do terminal e terminou em segundo plano; os arquivos foram conferidos com `cmp`
  depois.
- **Próxima ação:** R8 (correção das abertas pela LLM, com as respostas gravadas antes da chamada e o estado
  `erro_avaliacao` com nova tentativa).

### R8 — Correção das abertas pela LLM (✅ 22/11/2026)

- **Arquivos:** `app/services/reading_avaliacao.py` (novo: prompt, `avaliar_abertas`, `reavaliar`,
  `mensagem_da_correcao`), `app/schemas_reading.py` (`CorrecaoAberta`, `CorrecoesAbertas`; `pontuacao` na
  `PerguntaCorrigida`), `app/api/reading.py` (o envio da aberta chama a correção; rota `/avaliar`; `pontuacao` no
  resultado, derivada do acerto na múltipla escolha), `tests/reading/test_reading_avaliacao.py` (novo),
  `tests/reading/test_reading_respostas.py` (os 2 testes da aberta "sem correção" do R7 saíram: o comportamento mudou
  de propósito e está coberto no R8). Nenhum arquivo da base, nenhuma migração.
- **Como funciona:** o R7 grava as respostas (estado `avaliando`); em seguida `avaliar_abertas` chama
  `llm.gerar_json(sistema=PROMPT_CORRECAO, modelo=CorrecoesAbertas)`. A mensagem leva o texto (DR30) e, por pergunta,
  o enunciado, a resposta esperada e a resposta da pessoa entre `<resposta_do_aluno>` (marcas retiradas do conteúdo).
  O schema exige 5 correções com as ordens 1–5, pontuação 0, 0,5 ou 1 (booleano recusado) e comentário. O servidor
  força 0 nas respostas em branco e calcula `acertos` e `nota` (DR29); com tudo em branco, nem chama a LLM. Sucesso →
  `avaliacao`, `modelo_llm`, `avaliado_em`, estado `corrigido`. `ErroLLM` → `erro_avaliacao` (commit) e relança (DR32).
  `reavaliar`: em `erro_avaliacao`, um UPDATE condicional reserva o desafio (`erro_avaliacao` → `avaliando`) antes da
  chamada; em `avaliando` há mais de 5 minutos, segue direto (DR31); outros casos → `AvaliacaoIndisponivel` (409).
- **Testes:** 31 novos: crédito parcial (nota 7 com 1+0,5+0+1+1), gravação, GET igual; prompt (texto, perguntas,
  respostas esperadas, delimitação, injeção); branco vale 0 mesmo com a LLM dizendo 1; tudo em branco sem LLM; texto
  livre; nova tentativa do `llm.py`; múltipla escolha sem LLM; 5 respostas inválidas da LLM (respostas preservadas e
  `erro_avaliacao`); timeout, provedor fora e LLM não configurada; `/avaliar` depois de falha (falha de novo e depois
  corrige); 4 casos de `/avaliar` indisponível; múltipla escolha forçada a `erro_avaliacao`; desafio preso há 5 min;
  dois cliques (a 2ª é recusada enquanto a 1ª espera a LLM); isolamento; schema. Suíte: **498 aprovados, 2 pulados,
  0 falhas** (SQLite); `ruff` limpo. Postgres e E2E não executados.
- **Mutações (23, todas detectadas no fim; arquivos restaurados e conferidos):** branco aceito; LLM chamada com tudo
  em branco; sem `erro_avaliacao`; erro engolido; nota sem o parcial; acertos contando o parcial; sem `modelo_llm`;
  estado não vira `corrigido`; UPDATE sem condição; `/avaliar` aceitando a múltipla escolha; preso sem esperar; preso
  nunca liberado; prompt sem o texto, sem a resposta esperada, sem retirar as marcas, sem a regra de injeção; schema
  aceitando booleano, ordens repetidas, sem ordenar, comentário vazio; envio da aberta sem corrigir; `/avaliar` sem
  checar o dono; pontuação da múltipla escolha ignorada.
- **Problemas encontrados:** (1) a mutação "`/avaliar` aceitando a múltipla escolha" passou na 1ª rodada: hoje a
  múltipla escolha nunca chega a `erro_avaliacao`, e o UPDATE condicional já recusava. A checagem é uma defesa extra;
  novo teste força esse estado. (2) Risco aceito: dois `/avaliar` simultâneos num desafio **preso** há mais de 5 min
  podem chamar a LLM duas vezes (sem coluna para marcar a reserva, a condição "preso" continua verdadeira). Só acontece
  depois de uma queda do servidor no meio da chamada; o resultado fica correto (a última correção vale).
- **Próxima ação:** R9 (tela de início e leitura com timer, aviso de IA e cota; pontos de encaixe no `base.html` e no
  `main.js`).

### R9 — Tela: início e leitura com timer (✅ 22/11/2026)

- **Arquivos novos:** `app/templates/paginas/reading.html`, `app/static/js/paginas/reading.js`,
  `app/static/js/nucleo/api-reading.js`, `app/static/css/reading.css`, `tests/reading/test_reading_pagina.py`,
  `tests/reading/test_reading_e2e.py`. **Alterados:** `app/api/reading.py` (router `paginas` com `GET /reading`, via
  `pagina_protegida`). **Pontos de encaixe** (uma linha no bloco do Membro 1 em cada): `app/main.py`
  (`rotas += [reading.router, reading.paginas]`), `app/templates/base.html` (`<link>` do `reading.css` e o botão
  📖 Reading), `app/static/js/main.js` (`import "./paginas/reading.js";`). Nenhum outro arquivo da base.
- **Como funciona:** início → `api.situacaoLLM()` → `criarAvisoIA` (antes de qualquer envio), cota do reading (zerada:
  botão desativado e quando renova; sem IA configurada: avisa das perguntas prontas) → COMEÇAR → `POST /challenges`
  (aviso de carregamento; erro em português na tela, com a cota atualizada) → `?desafio=ID` na URL (`replaceState`) →
  leitura: parágrafos e crédito por `textContent`, link do original só se a URL começa com `https://`,
  `contagemRegressiva(segundos_restantes)` (tempo do servidor) → no zero ou em TERMINEI DE LER → o texto sai da tela →
  `POST /encerrar-leitura` → etapa das perguntas (por enquanto um aviso "Leitura encerrada"; a tela é o R10). F5:
  `GET /challenges/ID` → em `lendo` com tempo, `GET /texto`; prazo vencido ou `respondendo`, vai às perguntas;
  inexistente ou de outra conta, volta ao início com "Desafio não encontrado.". A limpeza cancela o timer e os
  listeners (`AbortController`); respostas que chegam depois de sair da página são ignoradas.
- **Testes:** 11 da página (Python: login, miolo HTMX, padrões marcados, aviso antes do botão, `?desafio` mantido no
  F5, estáticos, `main.js`, **nenhum `innerHTML`/`outerHTML`/`insertAdjacentHTML`/`document.write`/`eval` nos JS do
  Reading**, e as rotas do `api-reading.js` existem na API) + 6 E2E no Chromium (`E2E=1`): início → leitura → F5 →
  terminei; encerramento sozinho no zero; voltar depois do prazo vai às perguntas; cota esgotada desativa o botão;
  erro da API em português; texto com HTML aparece como texto, sem executar nada e sem link `javascript:`. Os E2E
  também reprovam qualquer erro de JavaScript na página. Suíte: **509 aprovados, 3 pulados, 0 falhas** (SQLite; o 3º
  pulado é o E2E do Reading sem `E2E=1`); com `E2E=1`: Reading **6/6** e **E2E da base 13/13** (o `base.html` e o
  `main.js` mudaram); `ruff` limpo. Postgres não executado.
- **Mutações (13, todas detectadas pelo navegador; arquivos restaurados e conferidos):** no zero não encerra; título e
  parágrafos com `innerHTML`; link sem checar `https`; desafio fora da URL; F5 ignorando `?desafio`; F5 com o tempo
  cheio; encerrar sem tirar o texto; cota zerada sem desativar; sem aviso de IA; erro da criação sem aparecer; voltar
  depois do prazo mostrando o início; `main.js` sem importar a página.
- **Problemas encontrados:** (1) o teste de `innerHTML` pegou a palavra num comentário do próprio JS; o comentário foi
  reescrito (o teste continua estrito). (2) O 1º teste de XSS no navegador usava um artigo falso da fonte, mas com a
  LLM sem chave a criação troca o texto pela reserva (DR17, comportamento certo); o texto malicioso passou a ser a
  única reserva do banco. (3) Uma contagem errada no teste das rotas do cliente (esperava 7, são 6). (4) Os E2E
  mostram 2 avisos de depreciação do `uvicorn`/`websockets` (bibliotecas; também aparecem nos E2E da base).
  (5) No teste manual, o COMEÇAR "não fazia nada": era o navegador usando um `main.js` antigo do cache (sem o JS, o
  formulário só recarregava a página). Confirmado num Chromium limpo contra uma cópia do app (201, texto na tela) e
  resolvido com Ctrl+Shift+R. Causa na base (estáticos sem `Cache-Control`), anotada em "Para o Membro 4". O mesmo
  teste mostrou que o sorteio da Wikipedia quase sempre traz artigos curtos demais (todos descartados → reserva):
  bloco R3b.
- **Próxima ação:** R10 (perguntas, resultado e histórico: múltipla escolha e aberta, nova correção depois de falha,
  `criarEstadoVazio`, sem `innerHTML`).

### R3b — Artigos da Wikipedia com tamanho suficiente (✅ 22/11/2026)

- **Motivo:** no teste manual do R9, os 3 artigos sorteados foram descartados por serem curtos e o desafio caiu na
  reserva. Medição real com o sorteio antigo (`generator=random`): 1 de 6 aproveitáveis; entre os Good articles: 7 de
  8 (as chamadas seguidas da medição levaram a um 429 da Wikipedia; a medição parou aí).
- **Arquivos:** `app/services/reading_fontes.py` (`CATEGORIA_WIKIPEDIA` e os parâmetros de `buscar_wikipedia`),
  `tests/reading/test_reading_fontes.py`. Nenhum arquivo da base. Limpeza, seleção, crédito e gravação não mudaram (a
  resposta tem o mesmo formato, `query.pages[0]`).
- **Como funciona:** `GET api.php?action=query&generator=search&gsrsearch=incategory:Good_articles&gsrsort=random&
  gsrlimit=1&gsrnamespace=0&prop=extracts|info&explaintext=1&exlimit=1&inprop=url` → o mesmo caminho do R3. 429 (limite
  de uso) → `FonteIndisponivel` → artigo salvo → reserva, sem repetir.
- **Testes:** 2 novos (parâmetros do sorteio; 429 com `Retry-After` não é repetido e usa um artigo salvo); o teste do
  R3 que conferia `generator=random` foi ajustado. Suíte: **511 aprovados, 3 pulados, 0 falhas**; E2E do Reading 6/6;
  `ruff` limpo. **Verificação real** (uma chamada, banco temporário): "Yam fortress", 488 palavras, sem reserva.
- **Mutações (5, todas detectadas; arquivo restaurado):** volta ao `generator=random`; categoria errada; sem
  `gsrsort=random`; sem `gsrnamespace`; 429 repetindo a busca.
- **Depois do commit:** no teste manual, os desafios continuaram na reserva. Causa: sem `LLM_CHAVE` no `.env`, as
  perguntas do artigo novo não podem ser geradas e o desafio troca o texto pela reserva (DR17, comportamento
  planejado). Os artigos novos da Wikipedia estavam sendo buscados e gravados (o R3b funcionou). Resolvido pelo
  usuário configurando a chave do Gemini.
- **Próxima ação:** R10.

### R10 — Tela: perguntas, resultado e histórico (✅ 23/11/2026)

- **Arquivos:** `app/services/reading_desafios.py` (`historico`, `LIMITE_HISTORICO`), `app/schemas_reading.py`
  (`ItemHistorico`), `app/api/reading.py` (`GET /api/reading/challenges`), `app/static/js/nucleo/api-reading.js`
  (`historico`), `app/templates/paginas/reading.html` (etapas perguntas, resultado e histórico; botão HISTÓRICO),
  `app/static/js/paginas/reading.js` (sai o marcador "Leitura encerrada" do R9; entram perguntas, rascunho,
  resultado, nova correção e histórico), `app/static/css/reading.css`, `tests/reading/test_reading_historico.py`
  (novo), `tests/reading/test_reading_e2e.py` (3 testes do R9 ajustados ao fim do marcador; 6 novos). Nenhum arquivo
  da base; nenhuma migração.
- **Como funciona:** encerrar → perguntas (MC: rádios, sem marcar = em branco; aberta: `textarea` com
  `maxlength=1000` e contador, mais o aviso de IA antes do envio) → cada mudança vai para o rascunho → ENVIAR (com
  em branco: `confirm`) → `POST /respostas` → resultado. `ja_respondido` ou erro `llm_*` → `GET /resultado` (com a
  mensagem; em `erro_avaliacao`, botão TENTAR CORRIGIR DE NOVO → `POST /avaliar`; em `avaliando`, ATUALIZAR).
  Resultado: nota, acertos, ✓/½/✗ (`pontuacao`), resposta dada ou "Sem resposta", correta/esperada, justificativa,
  comentário, tempos, modalidade, "Perguntas prontas" e `<details>` com o texto e o crédito. Histórico: tabela (data,
  texto, tipo, nota ou estado) com Ver/Continuar; vazio → `criarEstadoVazio` com "Começar um desafio". F5 no
  resultado reabre o resultado. Tudo por `textContent`.
- **Testes:** 7 da API do histórico (vazio, ordem e campos, só da conta, limite, padrão 50, empate na data pelo id,
  401) + 6 E2E novos (MC até o resultado com 3 certas, 1 errada e 1 em branco; cancelar o `confirm`; rascunho no F5;
  aberta com a LLM simulada: crédito parcial e **comentário da LLM com HTML aparece como texto**; falha da IA e nova
  correção; histórico vazio, lista, Continuar e Ver). Suíte: **519 aprovados, 3 pulados, 0 falhas**; E2E do Reading
  **12/12**; E2E da base **13/13**; `ruff` limpo. Postgres não executado.
- **Mutações (19; 18 detectadas e 1 equivalente; arquivos restaurados):** histórico sem filtrar a conta, na ordem
  inversa, sem desempate, sem limite, sem os não respondidos (INNER JOIN); envio sem `confirm`; MC mandando sempre a
  1ª alternativa; rascunho não salvo / não lido; comentário da LLM como HTML; sem aviso de IA nas abertas; falha da IA
  sem ir ao resultado; sem botão de nova correção; parcial como errado; branco sem "Sem resposta"; histórico abrindo o
  resultado em vez de continuar; histórico vazio sem estado vazio; F5 no resultado voltando ao início.
  **Equivalente:** `guardarNaUrl` dentro do `mostrarResultado`: em todos os caminhos a URL já tem o `?desafio` (a
  criação e o "Ver" do histórico já o gravam); a chamada ficou como redundância defensiva.
- **Próxima ação:** R11 (integração: Postgres, E2E completo, "Para o Membro 4" com dependências, URLs, migrações e
  resultados finais).
- **Depois do relatório:** no teste manual, as perguntas não apareceram. Causa: o navegador usou o `reading.js` do R9
  (cache) com o template novo, e o JS antigo procurava um elemento que não existe mais (erro de JavaScript).
  Confirmado abrindo o desafio real do usuário (numa cópia do banco) num Chromium limpo: 5 perguntas e 20
  alternativas na tela. Resolvido com Ctrl+Shift+R; a causa na base (estáticos sem `Cache-Control`) já estava anotada.

### R11 — Integração, Postgres e entrega (✅ 24/11/2026)

- **Decisões do usuário:** Postgres pelo caminho do README da base (`POSTGRES_*` no `.env` do usuário e
  `docker compose up -d db`, volume permanente; a suíte no Postgres foi rodada **pelo usuário**, para a senha não
  passar pelos meus comandos); medição de 3 criações reais com a chave do usuário.
- **O que foi feito:** suíte no PostgreSQL 17; suítes finais no SQLite e E2E (Reading + base); auditoria do diff da
  base desde `49636dd` (só os 6 pontos de encaixe); tabela "Tarefas × blocos"; "Arquitetura" e "Para o Membro 4"
  finais (dependências, variáveis, URLs, migrações, recursos, resultados, pendências). Nenhum código mudou neste bloco.
- **Resultados:** SQLite 519 aprovados, 3 pulados; **PostgreSQL 520 aprovados, 2 pulados** (o teste exclusivo do
  Postgres passou); E2E 25/25; `ruff` limpo; `test_base_protegida` 10/10. Nenhuma diferença de comportamento entre
  SQLite e Postgres (JSON com `NULL`, `func.random()`, `rowcount` do UPDATE condicional, datas e ordenação).
- **Medição:** Wikipedia 0,9–2,0 s; Gemini sobrecarregado (1 × 503, 2 × timeout de 60 s), os 3 desafios caíram na
  reserva corretamente; memória 85 MB. A espera de ≈ 60 s com a LLM travada ficou registrada como pendência.
- **Ambiente:** o container `projeto-db-1` (Postgres) continua no ar; parar com `docker compose stop db` (os dados
  ficam no volume).
- **Ajuste pedido pelo usuário (aviso de demora):** por causa da espera de até ≈ 60 s com a LLM lenta, a tela avisa
  "Pode demorar até 1 minuto…" e mostra um sinal de carregamento (anel girando, nas cores do tema, mais lento com
  `prefers-reduced-motion`; `role="status"` para leitores de tela) na preparação do desafio e na correção das abertas;
  o botão de nova correção mostra "CORRIGINDO… (pode demorar até 1 minuto)". Arquivos: `reading.html`, `reading.js`,
  `reading.css`, `test_reading_pagina.py` (+1) e `test_reading_e2e.py` (+2: preparação e correção lentas). Suíte:
  **520 aprovados, 3 pulados** (SQLite); E2E do Reading **14/14**; `ruff` limpo. Mutações (3, todas detectadas;
  arquivos restaurados): CSS sem a regra do `[hidden]` (carregamento sempre visível), sem o sinal, correção sem o
  aviso.

### R12 — Acertos finais conforme o guia (✅ 24/11/2026)

- **Motivo:** releitura do `docs/guias/MEMBRO1_READING.md` e do `docs/guias/PROMPT_INICIAL.md` a pedido do usuário.
- **Fixtures (guia, seção 8):** novo `tests/reading/conftest.py` com `Relogio`/`relogio` (usa o `INICIO` do arquivo
  de teste, se houver), `cota_nova`, `fonte_fora`, `texto_reserva` e `ambiente` (as três juntas). Saíram as cópias de
  `test_reading_leitura.py`, `_respostas.py`, `_avaliacao.py`, `_historico.py` e a `cota_nova` de `_api.py`
  (`pytestmark = pytest.mark.usefixtures(...)`). Conferido: **os mesmos 246 testes, um a um**, antes e depois (IDs
  coletados do commit anterior e do atual). Problema no caminho: o corte automático levou junto a `correcoes()` do
  `test_reading_avaliacao.py` (não era cópia); o `ruff` acusou e ela foi devolvida.
- **Tempo na submissão (DR43):** `reading_correcao.leitura_dentro_do_prazo` e `TempoInvalido` → 409
  `tempo_invalido` no `POST /respostas`. Testes: +9 (5 casos de horário gravado: prazo, prazo + 5 s, + 6 s, antes do
  início, sem fim; 3 fluxos normais: 10 s, 135 s e 1000 s, sempre ≤ limite; função pura).
- **Migração (DR44):** sem mudanças; `alembic check` sem diferenças.
- **Gutenberg de verdade (24/11/2026):** **não funciona hoje.** 3 × `obter_texto("gutenberg")` → `ReadTimeout` no
  Gutendex → reserva da Wikipedia. Medição direta: `languages=en&copyright=false` (página 1) responde em 0,5 s, mas
  com `mime_type=text/plain` ou `page=3` passa de 20 s (e de 60 s); e o download do `.txt` no `gutenberg.org` responde
  **503** (página HTML) em 3 endereços diferentes. As duas causas são externas; o app não quebra (cai na reserva),
  mas quem escolhe "Livro" recebe um texto da Wikipedia. **Não corrigido:** depende de decisão (ver "Pendências").
- **Testes:** suíte **529 aprovados, 3 pulados** (SQLite); E2E do Reading 14/14; `ruff` limpo. Postgres não
  executado neste bloco. **Mutações (5, todas detectadas; arquivos restaurados):** submissão sem conferir o tempo; sem
  a tolerância; sem conferir o início; 409 sem o código próprio; relógio do `conftest` ignorando o `INICIO` do
  arquivo.

### R12b — Fonte Gutenberg funcionando (✅ 24/11/2026)

- **Motivo:** no R12, a fonte Gutenberg não funcionava de verdade (Gutendex lento com filtros; `gutenberg.org` com
  503). Opção A aprovada pelo usuário.
- **Medições (24/11/2026):** espelhos oficiais `gutenberg.pglaf.org` e `aleph.pglaf.org`: 200, ≈ 27 KB/s (iguais);
  `mirrors.xmission.com`: 404 no caminho `cache/epub`. Com o código intermediário (3 MB por livro), o download levou
  13–38 s e um livro de 3,1 MB levou **150 s** (o `TIMEOUT_LIVRO` vale por leitura, não para o total). Nos livros
  medidos, o trecho começava nos primeiros 4 KB do arquivo. Uma das buscas trouxe um dicionário.
- **O que mudou (`app/services/reading_fontes.py`):** consulta ao Gutendex `languages=en&copyright=false` (1ª página,
  os 32 mais baixados; o formato `.txt` é conferido no código); download de
  `URL_TEXTO_GUTENBERG = https://gutenberg.pglaf.org/cache/epub/{id}/pg{id}.txt` (o crédito continua apontando para a
  página do livro no `gutenberg.org`); `LIMITE_BYTES_LIVRO = 150 KB` e `TEMPO_MAX_LIVRO = 25 s` para o download
  inteiro; se o arquivo foi cortado, descarta o que vem depois da última linha em branco (sem parágrafo pela metade);
  `_NAO_E_LEITURA` filtra pelo título dicionários, enciclopédias, thesaurus, glossários, índices e "(complete) works
  of". Sai a constante `PAGINAS_GUTENDEX`.
- **Verificação real (código final):** 3 de 3 desafios com livro de verdade a partir do capítulo 1, sem reserva:
  "Alice's Adventures in Wonderland" (4,4 s), "The Enchanted April" (7,1 s), "Twenty years after" (3,3 s). Antes, numa
  rodada intermediária: "Dorian Gray", "The Blue Castle", "Cranford" (4–7 s) e o dicionário, que motivou o filtro.
- **Testes:** +13 em `test_reading_fontes.py` (parâmetros do Gutendex e URL do espelho; livro sem `.txt` pulado;
  espelho com 503; corte na última linha em branco; livro abaixo do limite inteiro; download lento demais; 8 títulos
  do filtro). Suíte: **542 aprovados, 3 pulados** (SQLite); E2E do Reading 14/14; `ruff` limpo. Postgres não
  executado neste bloco. **Mutações (7, todas detectadas; arquivo restaurado):** volta ao `mime_type` e à página
  sorteada; download pela URL do Gutendex; sem o corte na linha em branco; sem o tempo máximo; sem o filtro de obras de
  consulta; filtro pegando "index" dentro de palavra; livro só com `.zip` aceito.
- **Limitações:** menos variedade (32 livros, menos os filtrados); peças de teatro (ex.: "Romeo and Juliet") passam no
  filtro e podem render trechos com nomes de personagens; o espelho é um serviço externo e pode mudar.
- **Teste manual NÃO realizado (24/11/2026):** o usuário não conseguiu testar pela tela (1) o desafio com um **livro**
  do Gutenberg e (2) a **correção das respostas abertas**, porque o Gemini respondeu **503** ("high demand"). Sem a
  LLM, o desafio com livro troca o texto pela reserva da Wikipedia (DR17) e a correção da aberta fica em
  `erro_avaliacao` (DR32), como previsto. O que **foi** verificado: a busca real dos livros (`obter_texto`, 3 de 3,
  sem a LLM) e, com a LLM simulada, a correção das abertas (`test_reading_avaliacao.py` e os E2E). **Falta:** repetir
  os dois testes manuais quando o Gemini voltar a responder.

### R13 — Casos de borda (✅ 24/11/2026)

- **Como foram achados:** cobertura de ramos (`--cov-branch`) só no Reading (tudo 100%, menos 1 ramo de
  `reading_textos.py`) e revisão do código atrás de situações que nenhum teste exercita.
- **Correções (com teste):**
  1. **Espelho do Gutenberg devolvendo 200 com uma página HTML** (manutenção, bloqueio): o HTML seria tratado como
     livro e poderia virar o trecho. Agora `_baixar_texto` exige `content-type: text/plain` antes de ler o corpo;
     senão, `FonteIndisponivel` (→ artigo salvo → reserva). Verificado de verdade: o espelho real passa.
  2. **Texto de reserva com perguntas prontas fora do formato** (banco alterado à mão, migração de dados com erro):
     antes, 500 genérico pela rota. Agora `reading_llm.ReservaInvalida` (com um erro no log) → 502
     `texto_indisponivel`, sem gravar o desafio; vale quando a reserva é o próprio texto (fonte fora) e quando ela
     substitui o artigo (LLM fora).
- **Só testes (o comportamento já era o certo):** F5 durante "Preparando…" (E2E: o desafio é criado mesmo assim e
  aparece no histórico com "Continuar"); resposta de múltipla escolha só com espaços conta como em branco;
  `encerrar-leitura` num desafio corrigido não muda nada; comentário da LLM com mais de 400 caracteres é recusado (e
  a nova tentativa do `llm.py` acontece); HTML em enunciados, alternativas e justificativas aparece como texto nas
  perguntas e no resultado (E2E), e a resposta com `<b>` é comparada como texto (nota 10); linha de livro que não é
  título nem frase completa é descartada (o ramo que faltava).
- **Documentados, sem teste** (limitação do navegador ou coberto pela base): aba em segundo plano por muito tempo (o
  timer usa `Date.now()` e se ajusta ao voltar; o servidor limita o tempo gravado); duas abas no mesmo desafio (a
  outra continua mostrando o texto até o timer dela acabar; o servidor garante o tempo gravado); sessão que vence no
  meio do desafio (a base leva ao login com `proximo=/reading?desafio=ID` e volta); emoji nas respostas abertas (o
  `maxlength` do navegador conta 2 por emoji e o Python 1: o navegador é mais restritivo, nada passa do limite do
  servidor).
- **Testes:** +14 (Python: 3 de `content-type`, 6 de reserva corrompida, 2 de respostas, 1 de comentário longo, 1 de
  linha descartada; E2E: +2). Suíte: **556 aprovados, 3 pulados** (SQLite); E2E **29/29** (16 do Reading + 13 da
  base); `ruff` limpo; cobertura de linhas e ramos **100%** em todos os arquivos do Reading. Postgres não executado
  neste bloco. **Mutações (4, todas detectadas; arquivos restaurados):** download sem exigir `text/plain`; reserva
  corrompida sem tratamento; rota sem mapear `ReservaInvalida`; enunciado da pergunta montado como HTML.

## Testes

Em `tests/reading/`. Nunca chamam a rede nem a LLM (`monkeypatch` e `llm_falsa`).

| Arquivo | Cobre |
|---|---|
| `test_reading_modelos.py` | R1: modelos, JSON, UNIQUEs, migração 0101 (nomes das FKs/UNIQUEs, downgrade) |
| `test_reading_textos.py` | R2: limpeza (Wikipedia e Gutenberg), seleção do trecho, contagem e tempo de leitura |
| `test_reading_fontes.py` | R3: fontes com HTTP falso, artigos salvos, reserva, crédito, migração 0102 |
| `test_reading_llm.py` | R4: schemas das perguntas, prompt, embaralhamento, reserva quando a LLM falha, reservas reais da 0102 |
| `test_reading_api.py` | R5: criação do desafio pela API (cota, validação, erros, reserva, transação, relógio), resumo e isolamento |
| `test_reading_leitura.py` | R6: texto só dentro do prazo, encerrar a leitura (idempotente, concorrente), perguntas sem resposta, isolamento |
| `test_reading_respostas.py` | R7: envio das respostas, correção e nota da múltipla escolha, tempos, erros, corrida, isolamento; R12: conferência do tempo na submissão |
| `test_reading_avaliacao.py` | R8: correção das abertas pela LLM (crédito parcial), prompt, falhas, `erro_avaliacao`, `/avaliar`, concorrência |
| `test_reading_pagina.py` | R9: página `/reading`, pontos de encaixe, estáticos, JS sem `innerHTML`, rotas do cliente |
| `conftest.py` | Fixtures do Reading (R12): relógio falso, cota nova, fonte fora do ar, texto de reserva, `ambiente` |
| `test_reading_historico.py` | R10: API do histórico (ordem, isolamento, limite, campos) |
| `test_reading_e2e.py` | R9 e R10 (`E2E=1`, Chromium): início, leitura, timer, F5, encerrar, cota, erros, XSS, perguntas, rascunho, resultado, nova correção, histórico |

**Como rodar:** com a venv ativa, **`python -m pytest`** (suíte inteira) ou `python -m pytest tests/reading -v`.
Navegador (opcional): `python -m playwright install chromium` uma vez e `E2E=1 python -m pytest tests/reading/test_reading_e2e.py`.
O `pytest` puro falha com `ModuleNotFoundError: No module named 'app'` (problema preexistente da base; ver "Para o
Membro 4"). Decisão DR15.

## Tarefas da lista oficial × blocos

Nenhuma tarefa foi excluída. As de agosto (UI dos decks) já estavam entregues na base.

| Mês | Tarefa | Bloco | Onde é testada |
|---|---|---|---|
| Set | Modelagem (texto, desafio, perguntas, tentativa) | R1 | `test_reading_modelos.py` |
| Set | Migrations Alembic | R1, R3 (0101, 0102) | `test_reading_modelos.py`, `test_migracoes.py`, `test_reading_fontes.py` |
| Set | Serviço MediaWiki | R3, R3b | `test_reading_fontes.py` |
| Set | Adaptador de domínio público (Gutenberg) | R3, R12b (uso real) | `test_reading_fontes.py` e verificação real (R12b) |
| Set | Normalização dos textos | R2 | `test_reading_textos.py` |
| Set | Contagem de palavras e limite por ppm | R2 | `test_reading_textos.py` |
| Set | Endpoint `POST /reading/challenges` | R5 | `test_reading_api.py` |
| Set | Validação Pydantic | R4, R5, R7, R8 | todos os de API e `test_reading_llm.py` |
| Set | Testes de obtenção, limpeza e seleção | R2, R3 | `test_reading_textos.py`, `test_reading_fontes.py` |
| Out | Serviço de LLM separado do HTTP | R4 | `test_reading_llm.py` |
| Out | Prompt para exatamente 5 perguntas | R4 | `test_reading_llm.py` |
| Out | Schema estruturado (enunciado, tipo, alternativas, resposta correta, justificativa) | R4 | `test_reading_llm.py` |
| Out | Modo Multiple Choice | R4, R7, R10 | `test_reading_respostas.py`, E2E |
| Out | Modo Open Answer | R4, R8, R10 | `test_reading_avaliacao.py`, E2E |
| Out | Página de leitura com timer em JS | R9 | E2E |
| Out | Bloqueio automático quando o tempo termina | R6 (servidor), R9 (tela) | `test_reading_leitura.py`, E2E |
| Out | Página das cinco questões | R10 | E2E |
| Out | Endpoint de submissão e correção | R7 | `test_reading_respostas.py` |
| Out | Persistência dos resultados no PostgreSQL | R7, R11 | suíte inteira no Postgres (R11) |
| Nov | Correção das abertas pela LLM com saída estruturada | R8 | `test_reading_avaliacao.py` |
| Nov | Pontuação | R7, R8 (crédito parcial) | `test_reading_respostas.py`, `test_reading_avaliacao.py` |
| Nov | Registro de tempo, acertos e modalidade | R7 | `test_reading_respostas.py` |
| Nov | Falhas de API externa e LLM com HTTPException e respostas padrão | R3, R5, R8 | `test_reading_api.py`, `test_reading_avaliacao.py` |
| Nov | Fallback quando não há 5 perguntas válidas | R4 | `test_reading_llm.py`, `test_reading_api.py` |
| Nov | Testes unitários | R1–R8 | `tests/reading/` |
| Nov | Testes de integração FastAPI + banco + geração | R5–R8, R10 | `test_reading_api.py` e seguintes |
| Nov | Testes end-to-end texto → leitura → perguntas → resultado | R9, R10 | `test_reading_e2e.py` (`E2E=1`) |
| — | Histórico (estado vazio) | R10 | `test_reading_historico.py`, E2E |

## Alterações na base

Nenhuma. Desde o início da branch (`49636dd`), os arquivos da base mudaram só nos pontos de encaixe do Membro 1
(6 linhas, conferidas com `git diff 49636dd..HEAD`): `app/main.py` (2), `app/models.py` (1),
`app/static/js/main.js` (1) e `app/templates/base.html` (2: CSS e botão). `requirements.txt` sem mudança.
`tests/test_base_protegida.py`: 10/10.

## Para o Membro 4

**Dependências.** Nenhuma nova (Python ou de sistema); `requirements.txt` sem mudança. Sem modelos baixados. O E2E
usa o Chromium do Playwright (`python -m playwright install chromium`, ≈ 150 MB em `~/.cache/ms-playwright`), como os
E2E da base.

**Variáveis de ambiente.** Nenhuma nova. Usa as `LLM_*` da base. **Funciona sem elas**: sem `LLM_CHAVE`, todo desafio
usa os textos de reserva (perguntas prontas, DR17), e as abertas ficam em `erro_avaliacao` (503) até a chave existir.

**URLs externas** (o servidor de produção precisa alcançá-las):
- `https://en.wikipedia.org/w/api.php` (textos; User-Agent do projeto; limite de uso anônimo: 429 vira reserva);
- `https://gutendex.com/books/` (lista dos livros) e `https://gutenberg.pglaf.org/` (download do `.txt`, espelho
  oficial do Project Gutenberg; o `www.gutenberg.org` só aparece no crédito, como link para pessoas);
- o provedor da LLM (`LLM_BASE_URL`; hoje o Gemini).

**Migrações.** `0101` (esquema: `readingtext`, `readingchallenge`, `readingquestion`, `readingattempt`, com todas as
FKs e UNIQUEs nomeadas) e `0102` (**dados**: 5 textos de reserva da Wikipedia, CC BY-SA 4.0, com perguntas prontas).
`0101` sai da `0006`: na integração, `alembic merge` com as cabeças do Speaking (`0201…`) e do Writing (`0301…`).

**Uso de recursos e tempos** (medidos em 24/11/2026, banco temporário, Gemini `gemini-flash-latest`):
- busca do texto na Wikipedia: 0,9–2,0 s; memória máxima do processo: 85 MB (sem modelos);
- a criação do desafio leva o tempo da Wikipedia **mais** o da LLM. Na medição, o Gemini estava sobrecarregado: 1
  resposta 503 (4,8 s) e 2 timeouts (60 s); nos 3 casos o desafio caiu na reserva, como previsto. Não houve geração
  bem-sucedida para medir. **Risco de experiência:** com a LLM travada, a pessoa espera ≈ 60 s
  (`LLM_TIMEOUT_SEGUNDOS`, da base) antes de cair na reserva. Ver "Pendências".
- a correção das abertas faz 1 chamada à LLM por desafio (texto + 5 respostas).

**Resultados depois do R13 (24/11/2026):** SQLite **556 aprovados, 3 pulados**; E2E **29/29**; cobertura 100%
(linhas e ramos) no Reading; `ruff` limpo. O Postgres foi rodado por último no R11 (520 aprovados): vale rodar de novo
antes do merge.

**Resultados finais (R11, 24/11/2026):** SQLite **520 aprovados, 3 pulados** (depois do aviso de demora);
PostgreSQL 17 (Docker, `shadowing_teste`) **520 aprovados, 2 pulados** (rodado antes do aviso de demora, que só mudou
a tela e acrescentou um teste da página); E2E (`E2E=1`) **27/27** (14 do Reading + 13 da base); `ruff` limpo. Os pulados são os
E2E sem `E2E=1` e, no SQLite, o teste exclusivo do Postgres.

**Pendências e achados** (não corrigidos nesta branch; dependem da base ou de decisão do grupo):

**Problema preexistente da base (não corrigido nesta branch):** `pytest` puro, na raiz, falha ao carregar o
`tests/conftest.py` com `ModuleNotFoundError: No module named 'app'`. Reproduzido numa cópia limpa do commit
`49636dd` (antes do Reading). Causa: o `pytest` só acrescenta a pasta do `conftest.py` (`tests/`) ao `sys.path`, não
a raiz; `python -m pytest` funciona porque acrescenta o diretório atual. Correção sugerida (uma linha no
`pyproject.toml`, que é base):
```diff
 [tool.pytest.ini_options]
 testpaths = ["tests"]
 addopts = "-q --cov=app --cov-report=term-missing"
+pythonpath = ["."]
```

**Achado na base (R5, não corrigido nesta branch):** `exigir_cota` é dependência da rota, e o FastAPI resolve as
dependências antes de validar o corpo: uma requisição com corpo inválido (422) gasta 1 desafio da cota. Vale para
Reading, Writing e Speaking. Pela interface (corpo montado pelo JS) isso não acontece na prática. Se o Membro 4 quiser
corrigir: chamar a função devolvida por `exigir_cota(...)` dentro da rota, depois da validação, ou validar o corpo
numa dependência anterior à cota.

**Achado na base (R9, não corrigido nesta branch): cache dos arquivos estáticos.** O `/static` é servido sem
`Cache-Control`; o navegador pode guardar um `main.js` antigo (heurística pelo `Last-Modified`) e não carregar o JS
novo de uma feature. Sintoma visto no Reading: o botão COMEÇAR "não fazia nada" (sem o JS, o formulário fazia o envio
padrão do HTML e só recarregava a página); resolveu com Ctrl+Shift+R. Vale para as três features e para o deploy.
Correções possíveis (base): versão na URL dos estáticos no `base.html` (ex.: `main.js?v=<commit>`) ou
`Cache-Control: no-cache` no `/static` (o navegador revalida pelo ETag, sem baixar de novo se não mudou).

**Warning preexistente da base:** `StarletteDeprecationWarning` (o `TestClient` do FastAPI usa `httpx`; a Starlette
pede `httpx2`). Inofensivo com as versões fixas do `requirements.txt`; vira problema só ao atualizar a Starlette.

**Espera longa quando a LLM trava (R11):** a geração das perguntas espera até `LLM_TIMEOUT_SEGUNDOS` (60 s) antes de
cair na reserva. Opções: um timeout menor no `.env` (afeta as três features; redações do Writing precisam de mais
tempo) ou um parâmetro de timeout por chamada no `llm.gerar_json` (alteração no `llm.py`). No Reading, a tela já
avisa que pode levar até 1 minuto e mostra um sinal de carregamento.

**Fonte Gutenberg (R12 → R12b, resolvido):** no R12 a fonte não funcionava (Gutendex lento com filtros,
`gutenberg.org` com 503). No R12b: 1ª página do Gutendex sem `mime_type` e o `.txt` do espelho oficial
`gutenberg.pglaf.org`, com 150 KB / 25 s por livro. Verificado de verdade: 3 de 3 desafios com livro, 3–7 s.

**Testes manuais pendentes (24/11/2026):** o desafio com livro do Gutenberg e a correção das respostas abertas
não foram testados pela tela com a LLM real: o Gemini respondia 503 (sobrecarga). Os testes automáticos (LLM
simulada) e a busca real dos livros passaram; falta repetir os dois testes manuais com a LLM no ar (ver o registro
do R12b).

**Melhoria não feita (decisão do usuário, 23/11):** sem `LLM_CHAVE`, o Reading ainda busca e grava o artigo da
Wikipedia antes de usar a reserva (chamadas e espera sem proveito).
