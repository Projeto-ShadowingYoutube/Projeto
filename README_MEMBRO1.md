# Membro 1 — Reading Challenge

## Visão geral

O usuário lê um texto em inglês com tempo limitado e depois responde cinco perguntas de compreensão, sem poder voltar
ao texto. O texto vem da Wikipedia (padrão) ou do Project Gutenberg (via Gutendex). As perguntas são geradas pela LLM
(`app/services/llm.py`) e podem ser de **múltipla escolha** (corrigidas pelo servidor) ou **abertas** (corrigidas pela
LLM), conforme a modalidade escolhida.

## Como usar

_A preencher a partir do bloco R9 (tela)._ Nenhuma variável de ambiente nova: usa as `LLM_*` que já existem.

## Arquitetura

_A preencher bloco a bloco._ Fluxo previsto:
`paginas/reading.js` → `nucleo/api-reading.js` → `/api/reading/...` (`app/api/reading.py`) →
`app/services/reading_*.py` → Wikipedia/Gutendex, `llm.gerar_json` e banco (`app/models_reading.py`).

## API

_A preencher a partir do bloco R5._

## Banco de dados

| Rev-id | Tipo | Conteúdo |
|---|---|---|
| `0101` | esquema | `readingtext`, `readingchallenge`, `readingquestion`, `readingattempt` (bloco R1) |
| `0102` | dados | textos de reserva com perguntas prontas (bloco R3) |

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
| R2 | Normalização e tempo de leitura | Normalização dos textos; contagem de palavras e limite por ppm | — | ✅ Concluído (21/11), aguardando commit |
| R3 | Fontes: Wikipedia, Gutendex e reserva | Serviço MediaWiki; adaptador de domínio público; testes de obtenção e seleção | R1, R2 | Planejado |
| R4 | Perguntas geradas pela LLM | Serviço de LLM separado do HTTP; prompt de 5 perguntas; schema estruturado; modos MC e Open; fallback | R1 | Planejado |
| R5 | Criação do desafio (API) | `POST /api/reading/challenges`; validação Pydantic; falhas | R3, R4 | Planejado |
| R6 | Leitura com tempo validado no servidor | Bloqueio da leitura quando o tempo termina (servidor) | R5 | Planejado |
| R7 | Submissão e correção de múltipla escolha | Submissão e correção; pontuação; tempo, acertos e modalidade; persistência | R6 | Planejado |
| R8 | Correção das abertas pela LLM | Correção com saída estruturada; tratamento de falhas da LLM | R7 | Planejado |
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

## Testes

Em `tests/reading/`. Nunca chamam a rede nem a LLM (`monkeypatch` e `llm_falsa`). _Detalhes a cada bloco._

## Alterações na base

Nenhuma.

## Para o Membro 4

_A preencher no bloco R11 (dependências, URLs externas — Wikipedia e Gutendex —, migrações e resultados finais)._
