# Membro 1 — Reading Challenge

## Visão geral

O usuário lê um texto em inglês com tempo limitado e depois responde cinco perguntas de compreensão, sem poder voltar
ao texto. O texto vem da Wikipedia (padrão) ou do Project Gutenberg (via Gutendex). As perguntas são geradas pela LLM
(`app/services/llm.py`) e podem ser de **múltipla escolha** (corrigidas pelo servidor) ou **abertas** (corrigidas pela
LLM), conforme a modalidade escolhida.

## Como usar

_A preencher a partir do bloco R9 (tela)._ Nenhuma variável de ambiente nova: usa as `LLM_*` que já existem.

## Arquitetura

- `app/services/reading_textos.py`: funções puras (limpeza, seleção do trecho, tempo de leitura).
- `app/services/reading_fontes.py`: Wikipedia, Gutendex, artigos salvos e reserva → `ReadingText`.
- `app/services/reading_llm.py` + `app/schemas_reading.py`: as 5 perguntas (LLM ou reserva).

Fluxo previsto:
`paginas/reading.js` → `nucleo/api-reading.js` → `/api/reading/...` (`app/api/reading.py`) →
`app/services/reading_*.py` → Wikipedia/Gutendex, `llm.gerar_json` e banco (`app/models_reading.py`).

## API

Todas exigem login (401 sem sessão). Erros no formato padrão `{detail, codigo}`.

| Rota | Entrada | Saída | Erros |
|---|---|---|---|
| `POST /api/reading/challenges` (gasta 1 da cota) | `{"modalidade": "multipla_escolha" \| "aberta", "fonte"?: "wikipedia" \| "gutenberg", "ppm"?: 150 \| 200 \| 250}` (padrões `wikipedia` e 200; campo extra → 422) | 201: `id, estado, modalidade, ppm, limite_segundos, iniciado_em, leitura_encerrada_em, usou_reserva, texto{titulo, conteudo, palavras, fonte, url, credito}`. **Sem as perguntas** | 422 `dados_invalidos`; 429 `limite_de_desafios`; 502 `texto_indisponivel`; 502/503/504 `llm_*` (LLM falhou e não há reserva) |
| `GET /api/reading/challenges/{id}` | — | 200: o resumo (sem texto e sem perguntas), com `segundos_restantes` | 404 `nao_encontrado` (inexistente ou de outra conta) |
| `GET /api/reading/challenges/{id}/texto` | — | 200: `titulo, conteudo, palavras, fonte, url, credito, segundos_restantes`; só em `lendo` e até o prazo + 5 s | 409 `leitura_encerrada`; 404 |
| `POST /api/reading/challenges/{id}/encerrar-leitura` (idempotente) | — | 200: o resumo (`estado: "respondendo"`) + `perguntas[{ordem, tipo, enunciado, alternativas}]`, **sem** resposta correta e sem justificativa | 404 |
| `POST /api/reading/challenges/{id}/respostas` | `{"respostas": [5 textos]}` (na ordem; `""` = não respondida; até 1000 caracteres; campo extra → 422) | 201: o resultado (abaixo) | 422 `dados_invalidos`; 422 `resposta_invalida` (+ `ordem`: na MC, fora das alternativas); 409 `leitura_em_andamento`; 409 `ja_respondido`; 404 |
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
- `texto_indisponivel` (502): a fonte falhou, não há artigo salvo e não há reserva no banco.
- `leitura_encerrada` (409): o texto foi pedido depois do prazo de leitura (+ tolerância) ou depois de encerrar.
- `leitura_em_andamento` (409): respostas enviadas com o desafio ainda em `lendo`.
- `ja_respondido` (409): o desafio já tem uma tentativa.
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
| R4 | Perguntas geradas pela LLM | Serviço de LLM separado do HTTP; prompt de 5 perguntas; schema estruturado; modos MC e Open; fallback | R1 | ✅ Concluído (21/11) |
| R5 | Criação do desafio (API) | `POST /api/reading/challenges`; validação Pydantic; falhas | R3, R4 | ✅ Concluído (21/11) |
| R6 | Leitura com tempo validado no servidor | Bloqueio da leitura quando o tempo termina (servidor) | R5 | ✅ Concluído (22/11) |
| R7 | Submissão e correção de múltipla escolha | Submissão e correção; pontuação; tempo, acertos e modalidade; persistência | R6 | ✅ Concluído (22/11) |
| R8 | Correção das abertas pela LLM | Correção com saída estruturada; tratamento de falhas da LLM | R7 | ✅ Concluído (22/11), aguardando commit |
| R9 | Tela: início e leitura com timer | Página de leitura com timer; bloqueio automático (tela) | R6 | Planejado |
| R10 | Tela: questões, resultado e histórico | Página das cinco questões | R7, R8, R9 | Planejado |
| R11 | Integração, E2E e entrega | Testes de serviços, integração e E2E; Postgres; "Para o Membro 4" | todos | Planejado |

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
| `test_reading_respostas.py` | R7: envio das respostas, correção e nota da múltipla escolha, tempos, erros, corrida, isolamento |
| `test_reading_avaliacao.py` | R8: correção das abertas pela LLM (crédito parcial), prompt, falhas, `erro_avaliacao`, `/avaliar`, concorrência |

**Como rodar:** com a venv ativa, **`python -m pytest`** (suíte inteira) ou `python -m pytest tests/reading -v`.
O `pytest` puro falha com `ModuleNotFoundError: No module named 'app'` (problema preexistente da base; ver "Para o
Membro 4"). Decisão DR15.

## Alterações na base

Nenhuma.

## Para o Membro 4

_A preencher no bloco R11 (dependências, URLs externas — Wikipedia e Gutendex —, migrações e resultados finais)._

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

**Warning preexistente da base:** `StarletteDeprecationWarning` (o `TestClient` do FastAPI usa `httpx`; a Starlette
pede `httpx2`). Inofensivo com as versões fixas do `requirements.txt`; vira problema só ao atualizar a Starlette.
