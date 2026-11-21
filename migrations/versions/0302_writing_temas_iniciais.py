"""Writing Challenge (Membro 3, W2): temas iniciais (migração de DADOS; o esquema está na 0301).

Revisão: 0302
Anterior: 0301
Criada em: 2026-11-21

24 temas originais, 4 por categoria, no estilo das provas TOEFL e IELTS (escritos para o projeto, não copiados de
provas reais). Os dados ficam escritos AQUI, sem importar app/services/writing_temas.py: uma migração precisa dar
sempre o mesmo resultado, mesmo que o serviço mude depois. tests/writing/test_temas.py confere que categoria, tempo e
mínimo de palavras daqui batem com writing_temas.CATEGORIAS.

Downgrade: apaga só estes 24 temas (pelo enunciado exato). Se alguma tentativa já usar um deles, para sem alterar
nada: apagar o tema quebraria a tentativa e o histórico da pessoa (mesmo padrão da 0003).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.migrar import BancoIncompativel

revision: str = "0302"
down_revision: str | None = "0301"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# categoria: (tempo_limite_segundos, palavras_minimas) — cópia congelada de writing_temas.CATEGORIAS em 21/11/2026.
FORMATOS = {
    "ielts_opiniao": (2400, 250),
    "ielts_discussao": (2400, 250),
    "ielts_problema_solucao": (2400, 250),
    "ielts_vantagens": (2400, 250),
    "toefl_discussao_academica": (600, 100),
    "toefl_independente": (1800, 300),
}

TEMAS = {
    "ielts_opiniao": [
        "Some people believe that university education should be free for everyone and paid for by the "
        "government. To what extent do you agree or disagree?",
        "Many people think that children under the age of twelve should not be allowed to own a smartphone. "
        "To what extent do you agree or disagree?",
        "Some argue that working from home most days of the week makes employees more productive than working in "
        "an office. To what extent do you agree or disagree?",
        "It is often said that learning a foreign language at school is a waste of time now that translation apps "
        "are so accurate. To what extent do you agree or disagree?",
    ],
    "ielts_discussao": [
        "Some people think that cities should invest in public transport, while others believe that building more "
        "roads is the better solution to traffic. Discuss both views and give your own opinion.",
        "Some believe that famous athletes earn far too much money, while others think their salaries are fair "
        "given their talent and short careers. Discuss both views and give your own opinion.",
        "Some people prefer to spend their free time outdoors, while others think staying at home is more relaxing "
        "and rewarding. Discuss both views and give your own opinion.",
        "Some argue that schools should focus on academic subjects, while others believe that practical skills, "
        "such as cooking and managing money, are equally important. Discuss both views and give your own opinion.",
    ],
    "ielts_problema_solucao": [
        "In many cities, young people find it increasingly difficult to afford housing. What are the causes of this "
        "problem, and what measures could be taken to solve it?",
        "Large amounts of food are thrown away every day by supermarkets, restaurants and households. Why does this "
        "happen, and what can be done to reduce food waste?",
        "Many people today feel lonely, even though they are constantly connected online. What are the reasons for "
        "this, and how can the problem be addressed?",
        "In some countries, fewer and fewer young people are choosing to become teachers. What problems does this "
        "cause, and what solutions can you suggest?",
    ],
    "ielts_vantagens": [
        "More and more people are choosing to shop online instead of in physical stores. Do the advantages of this "
        "trend outweigh the disadvantages?",
        "Some students take a gap year to travel or work before starting university. What are the advantages and "
        "disadvantages of doing this?",
        "Many companies now use artificial intelligence to screen job applications. Do the advantages of this "
        "practice outweigh the disadvantages?",
        "In many countries, people are living and working until a much older age. What are the advantages and "
        "disadvantages of this development?",
    ],
    "toefl_discussao_academica": [
        "Your professor is teaching a class on urban planning and asks: “Should cities ban private cars from their "
        "historic centers?” Lucas argues that a ban would reduce pollution and make the streets safer for "
        "pedestrians. Maya disagrees, saying it would hurt local businesses and make life harder for elderly "
        "residents. In your post, express and support your own opinion and contribute to the discussion.",
        "Your professor is teaching a class on education and asks: “Should universities replace traditional exams "
        "with long-term projects?” Daniel believes that projects measure real skills better than memorization. "
        "Priya thinks exams are fairer because every student is assessed under the same conditions. In your post, "
        "express and support your own opinion and contribute to the discussion.",
        "Your professor is teaching a class on economics and asks: “Should governments tax sugary drinks to improve "
        "public health?” Sofia supports the tax, arguing that it changes consumer habits. Kenji opposes it, saying "
        "it unfairly affects low-income families. In your post, express and support your own opinion and "
        "contribute to the discussion.",
        "Your professor is teaching a class on media studies and asks: “Is social media doing more harm than good "
        "to democracy?” Emma argues that it spreads misinformation too quickly. Omar believes it gives a voice to "
        "people who were ignored by traditional media. In your post, express and support your own opinion and "
        "contribute to the discussion.",
    ],
    "toefl_independente": [
        "Do you agree or disagree with the following statement? It is better to have a few close friends than many "
        "acquaintances. Use specific reasons and examples to support your answer.",
        "Some people prefer to plan every detail of a trip in advance, while others prefer to be spontaneous. Which "
        "do you prefer, and why? Use specific reasons and examples to support your answer.",
        "Do you agree or disagree with the following statement? Young people today have more opportunities to "
        "succeed than their parents did. Use specific reasons and examples to support your answer.",
        "Would you rather work for a large, well-known company or for a small start-up? Use specific reasons and "
        "examples to support your answer.",
    ],
}

_temas = sa.table(
    "writingprompt",
    sa.column("categoria", sa.String),
    sa.column("enunciado", sa.String),
    sa.column("tempo_limite_segundos", sa.Integer),
    sa.column("palavras_minimas", sa.Integer),
    sa.column("ativo", sa.Boolean),
)


def _enunciados() -> list[str]:
    return [enunciado for lista in TEMAS.values() for enunciado in lista]


def upgrade() -> None:
    op.bulk_insert(_temas, [
        {
            "categoria": categoria, "enunciado": enunciado, "tempo_limite_segundos": FORMATOS[categoria][0],
            "palavras_minimas": FORMATOS[categoria][1], "ativo": True,
        }
        for categoria, enunciados in TEMAS.items() for enunciado in enunciados
    ])


def downgrade() -> None:
    conexao = op.get_bind()
    em_uso = conexao.execute(
        sa.text(
            "SELECT COUNT(*) FROM writingattempt JOIN writingprompt ON writingprompt.id = writingattempt.prompt_id "
            "WHERE writingprompt.enunciado IN :enunciados"
        ).bindparams(sa.bindparam("enunciados", expanding=True)),
        {"enunciados": _enunciados()},
    ).scalar()
    if em_uso:
        raise BancoIncompativel(
            f"Existem {em_uso} redação(ões) usando os temas iniciais do Writing. Esta migração não apaga temas em "
            "uso: apague essas redações antes (faça backup) ou não desça desta versão."
        )
    op.execute(_temas.delete().where(_temas.c.enunciado.in_(_enunciados())))
