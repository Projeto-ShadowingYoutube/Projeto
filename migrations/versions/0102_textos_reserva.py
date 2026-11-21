"""Reading Challenge (Membro 1, bloco R3): textos de reserva (migração de DADOS, sem mudança de esquema).

Revisão: 0102
Anterior: 0101
Criada em: 2026-11-21

Cinco trechos de artigos da Wikipedia em inglês, já limpos e selecionados pelas regras do R2, cada um com cinco
perguntas prontas (enunciado, 4 alternativas, resposta correta e justificativa). São usados quando a busca de textos
falha e não há artigo salvo, ou quando a LLM não consegue gerar as perguntas (decisões DR3 e DR12).

Crédito e licença: os textos são da Wikipedia (https://en.wikipedia.org), licença CC BY-SA 4.0
(https://creativecommons.org/licenses/by-sa/4.0/). Cada linha guarda o título e a URL do artigo; o trecho é uma
seleção de parágrafos do artigo, sem outras alterações. As perguntas foram escritas para este projeto.
Conteúdo copiado em 21/11/2026.

Os dados ficam aqui dentro (e não importados do app) para a migração continuar igual mesmo se o código mudar.
Downgrade: apaga os textos de reserva que nenhum desafio usa; os que já foram usados viram textos comuns (sem
perguntas prontas), para não quebrar o histórico.
"""
from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0102"
down_revision: str | None = "0101"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FONTE = "wikipedia"

readingtext = sa.table(
    "readingtext",
    sa.column("id", sa.Integer),
    sa.column("fonte", sa.String),
    sa.column("id_origem", sa.String),
    sa.column("titulo", sa.String),
    sa.column("url", sa.String),
    sa.column("conteudo", sa.String),
    sa.column("palavras", sa.Integer),
    sa.column("perguntas_reserva", sa.JSON),
    sa.column("data_criacao", sa.DateTime),
)
readingchallenge = sa.table("readingchallenge", sa.column("texto_id", sa.Integer))

TEXTOS_RESERVA = [{'id_origem': '58261',
  'titulo': 'Honey bee',
  'url': 'https://en.wikipedia.org/wiki/Honey_bee',
  'conteudo': 'A honey bee (also spelled honeybee) is a eusocial flying insect from the genus Apis of the largest '
              'bee family, Apidae. Honey bees are known for their creation of perennial nests within cavities '
              '(i.e. beehives) containing hexagonal cells made of secreted wax, their large colony sizes, and '
              'their routine regurgitation of digested carbohydrates as surplus food storage in the form of honey, '
              'the lattermost of which distinguishes their hives as a prized foraging target of many mellivorous '
              'animals including honey badgers, bears and human hunter-gatherers.\n'
              '\n'
              'Although honey bees represent only a small fraction of the roughly 20,000 known species of bees, '
              'they are the bee clade most familiar to humans and are also the most valuable beneficial insects to '
              'agriculture and horticulture. The best-known honey bee species is the western honey bee (Apis '
              'mellifera), which was domesticated and farmed (i.e. beekeeping) for honey production and crop '
              'pollination. The only other domesticated species is the eastern honey bee (Apis cerana), which are '
              'raised in South, Southeast and East Asia.\n'
              '\n'
              'Only members of the genus Apis are true honey bees, but some other bee species also produce and '
              'store honey and have been kept by humans for that purpose, including the stingless bees belonging '
              'to the genus Melipona and the Indian stingless or dammar bee Tetragonula iridipennis. In addition '
              'to harvesting honey, modern humans also use beeswax in making candles, soap, lip balms and various '
              'cosmetics, as a lubricant and in mould-making using the lost wax process. Other honey bee '
              'secretions such as royal jelly and bee venom are used pharmaceutically, especially in alternative '
              'medicine.',
  'palavras': 266,
  'perguntas_reserva': [{'enunciado': 'What material do honey bees use to build the hexagonal cells of their '
                                      'nests?',
                         'alternativas': ['Secreted wax', 'Mud and saliva', 'Chewed wood fibers', 'Dry leaves'],
                         'resposta_correta': 'Secreted wax',
                         'justificativa': 'The text says their nests contain "hexagonal cells made of secreted '
                                          'wax".'},
                        {'enunciado': 'Roughly how many species of bees are known?',
                         'alternativas': ['About 2,000', 'About 200', 'About 20,000', 'About 200,000'],
                         'resposta_correta': 'About 20,000',
                         'justificativa': 'Honey bees are "only a small fraction of the roughly 20,000 known '
                                          'species of bees".'},
                        {'enunciado': 'Which honey bee species is the best known?',
                         'alternativas': ['The eastern honey bee (Apis cerana)',
                                          'The western honey bee (Apis mellifera)',
                                          'The dammar bee (Tetragonula iridipennis)',
                                          'The stingless bees of the genus Melipona'],
                         'resposta_correta': 'The western honey bee (Apis mellifera)',
                         'justificativa': '"The best-known honey bee species is the western honey bee (Apis '
                                          'mellifera)."'},
                        {'enunciado': 'Where is the eastern honey bee raised?',
                         'alternativas': ['In Western Europe',
                                          'In North America',
                                          'In southern Africa',
                                          'In South, Southeast and East Asia'],
                         'resposta_correta': 'In South, Southeast and East Asia',
                         'justificativa': 'The eastern honey bee is raised "in South, Southeast and East Asia".'},
                        {'enunciado': 'Besides honey and wax, which honey bee secretions are used '
                                      'pharmaceutically?',
                         'alternativas': ['Nectar and pollen',
                                          'Royal jelly and bee venom',
                                          'Propolis and resin',
                                          'Honeydew and sap'],
                         'resposta_correta': 'Royal jelly and bee venom',
                         'justificativa': '"Other honey bee secretions such as royal jelly and bee venom are used '
                                          'pharmaceutically."'}]},
 {'id_origem': '604727',
  'titulo': 'Coffee',
  'url': 'https://en.wikipedia.org/wiki/Coffee',
  'conteudo': 'Coffee is a beverage brewed from roasted, ground coffee beans. Dark-colored and bitter, coffee has '
              'a stimulating effect on humans due to its caffeine content; however decaffeinated coffee is also '
              'commercially available. There are also various coffee substitutes.\n'
              '\n'
              "Coffee production begins when the seeds from coffee cherries, the Coffea plant's fruits, are "
              'separated to produce unroasted green coffee beans. The "beans" are roasted and then ground into '
              'fine particles. Coffee is brewed from the ground roasted beans, which are typically steeped in hot '
              'water before being filtered out. It is usually served hot, although chilled or iced coffee is '
              'common. Coffee can be prepared and presented in a variety of ways, e.g., espresso, French press, '
              'caffè latte, or already-brewed canned coffee. Sugar, sugar substitutes, milk, and cream are often '
              'added and change the flavor.\n'
              '\n'
              'Though coffee has become a global commodity, it has a history tied to food traditions around the '
              "Red Sea. The earliest reports of coffee drinking pertain to the plant's use among the Sufis of "
              'Yemen in southern Arabia in the middle of the 15th century. Up to the end of the 17th century, most '
              "of the world's coffee was imported from Yemen. As it gained in popularity, coffee started to be "
              'cultivated in Java in the 17th century and the Americas from the 18th century.\n'
              '\n'
              'The two most commonly grown coffee bean types are C. arabica and C. robusta. Coffee plants are '
              'cultivated in over 70 countries, primarily in the equatorial regions of the Americas, Southeast '
              'Asia, the Indian subcontinent, and Africa. Green, unroasted coffee is traded as an agricultural '
              'commodity. The global coffee industry was worth US$495.50 billion in 2023. In 2023, Brazil was the '
              "leading grower of coffee beans, producing 31% of the world's total, followed by Vietnam. While "
              'coffee sales reach billions of dollars annually worldwide, coffee farmers disproportionately live '
              'in poverty. Critics of the coffee industry have pointed to its negative impact on the environment, '
              'including clearing of land for coffee growing and water use.',
  'palavras': 336,
  'perguntas_reserva': [{'enunciado': 'Why does coffee have a stimulating effect on humans?',
                         'alternativas': ['Because of its caffeine content',
                                          'Because of the sugar added to it',
                                          'Because it is served hot',
                                          'Because of the roasting process'],
                         'resposta_correta': 'Because of its caffeine content',
                         'justificativa': 'Coffee "has a stimulating effect on humans due to its caffeine '
                                          'content".'},
                        {'enunciado': 'Where do the earliest reports of coffee drinking come from?',
                         'alternativas': ['Brazil', 'Java', 'Vietnam', 'Yemen, in southern Arabia'],
                         'resposta_correta': 'Yemen, in southern Arabia',
                         'justificativa': 'The earliest reports "pertain to the plant\'s use among the Sufis of '
                                          'Yemen in southern Arabia".'},
                        {'enunciado': "Until when was most of the world's coffee imported from Yemen?",
                         'alternativas': ['Until the middle of the 15th century',
                                          'Until the end of the 17th century',
                                          'Until the end of the 18th century',
                                          'Until 2023'],
                         'resposta_correta': 'Until the end of the 17th century',
                         'justificativa': '"Up to the end of the 17th century, most of the world\'s coffee was '
                                          'imported from Yemen."'},
                        {'enunciado': 'Which country was the leading grower of coffee beans in 2023?',
                         'alternativas': ['Vietnam', 'Yemen', 'Brazil', 'India'],
                         'resposta_correta': 'Brazil',
                         'justificativa': '"In 2023, Brazil was the leading grower of coffee beans, producing 31% '
                                          'of the world\'s total."'},
                        {'enunciado': 'What have critics of the coffee industry pointed to?',
                         'alternativas': ['Its negative impact on the environment',
                                          'The high price of coffee in shops',
                                          'The lack of coffee substitutes',
                                          'The bitter taste of the beans'],
                         'resposta_correta': 'Its negative impact on the environment',
                         'justificativa': 'Critics "have pointed to its negative impact on the environment".'}]},
 {'id_origem': '32571',
  'titulo': 'Volcano',
  'url': 'https://en.wikipedia.org/wiki/Volcano',
  'conteudo': 'A volcano is a vent or fissure in the crust of a planetary-mass object that allows hot lava, '
              'volcanic ash, and gases to escape from a magma chamber below the surface. On Earth, volcanoes are '
              "most often found where tectonic plates are diverging or converging, and because most of Earth's "
              'plate boundaries are underwater, most volcanoes are found underwater. For example, a mid-ocean '
              'ridge, such as the Mid-Atlantic Ridge, has volcanoes caused by divergent tectonic plates whereas '
              'the Pacific Ring of Fire has volcanoes caused by convergent tectonic plates. Volcanoes resulting '
              'from divergent tectonic activity are usually nonexplosive whereas those resulting from convergent '
              'tectonic activity cause violent eruptions. Volcanoes can also form where there is stretching and '
              "thinning of the crust's plates, such as in the East African Rift, the Wells Gray-Clearwater "
              'volcanic field, and the Rio Grande rift in North America. Volcanism away from plate boundaries most '
              'likely arises from upwelling diapirs from the core–mantle boundary called mantle plumes, 3,000 '
              'kilometres (1,900 mi) deep within Earth. This results in hotspot volcanism or intraplate volcanism, '
              'in which the plume may cause thinning of the crust and result in a volcanic island chain due to the '
              'continuous movement of the tectonic plate, of which the Hawaiian hotspot is an example. Volcanoes '
              'are usually not created at transform tectonic boundaries where two tectonic plates slide past one '
              'another.\n'
              '\n'
              'Volcanoes, based on their frequency of eruption or volcanism, are referred to as either active, '
              'dormant, or extinct. Active volcanoes have a history of volcanism and are likely to erupt again, '
              'while extinct ones are not capable of eruption at all as they have no magma source. "Dormant" '
              'volcanoes have not erupted in a long time – generally accepted as since the start of the Holocene, '
              'about 12,000 years ago – but may erupt again. However, dormant volcanoes are technically considered '
              'to be seismically "active". These categories are not entirely uniform; they may overlap for certain '
              'examples. Large eruptions can affect atmospheric temperature as ash and droplets of sulfuric acid '
              "obscure the Sun and cool Earth's troposphere. Historically, large volcanic eruptions have been "
              'followed by volcanic winters which have caused catastrophic famines.\n'
              '\n'
              'Other planets besides Earth have volcanoes. For example, volcanoes are very numerous on Venus. Mars '
              'has significant volcanoes. In 2009, a paper was published suggesting a new definition for the word '
              "'volcano' that includes processes such as cryovolcanism. It suggested that a volcano be defined as "
              "'an opening on a planet or moon's surface from which magma, as defined for that body, and/or "
              "magmatic gas is erupted.'",
  'palavras': 428,
  'perguntas_reserva': [{'enunciado': 'Where are most volcanoes on Earth found?',
                         'alternativas': ['In deserts',
                                          'Underwater',
                                          'In polar regions',
                                          'In the middle of continents'],
                         'resposta_correta': 'Underwater',
                         'justificativa': 'Because most plate boundaries are underwater, "most volcanoes are found '
                                          'underwater".'},
                        {'enunciado': 'What kind of eruptions do volcanoes caused by convergent tectonic plates '
                                      'usually have?',
                         'alternativas': ['Nonexplosive eruptions',
                                          'No eruptions at all',
                                          'Violent eruptions',
                                          'Only small gas eruptions'],
                         'resposta_correta': 'Violent eruptions',
                         'justificativa': 'Volcanoes from convergent tectonic activity "cause violent eruptions".'},
                        {'enunciado': 'What is the Hawaiian hotspot an example of?',
                         'alternativas': ['Hotspot (intraplate) volcanism',
                                          'A mid-ocean ridge',
                                          'A transform tectonic boundary',
                                          'An extinct volcano'],
                         'resposta_correta': 'Hotspot (intraplate) volcanism',
                         'justificativa': 'The text describes hotspot or intraplate volcanism, "of which the '
                                          'Hawaiian hotspot is an example".'},
                        {'enunciado': 'Why are extinct volcanoes not capable of eruption?',
                         'alternativas': ['They are covered by ice',
                                          'They are underwater',
                                          'They have not erupted for 12,000 years',
                                          'They have no magma source'],
                         'resposta_correta': 'They have no magma source',
                         'justificativa': 'Extinct volcanoes "are not capable of eruption at all as they have no '
                                          'magma source".'},
                        {'enunciado': 'On which planet are volcanoes described as very numerous?',
                         'alternativas': ['Mars', 'Venus', 'Jupiter', 'Mercury'],
                         'resposta_correta': 'Venus',
                         'justificativa': '"Volcanoes are very numerous on Venus." Mars is only said to have '
                                          'significant volcanoes.'}]},
 {'id_origem': '19331',
  'titulo': 'Moon',
  'url': 'https://en.wikipedia.org/wiki/Moon',
  'conteudo': 'The Moon is the only natural satellite of Earth. It orbits Earth in an elliptical path, at a '
              'distance that varies over the year, averaging around 378,000 kilometers (235,000 mi). It completes '
              'an orbit (lunar month) in relation to Earth and the Sun (synodically) every 29.5 days. The Moon and '
              'Earth are bound by gravitational attraction, which is stronger on the sides facing each other. The '
              "resulting tidal forces are the main driver of Earth's tides, and have pulled the Moon to always "
              "face Earth with the same near side. This tidal locking effectively synchronizes the Moon's rotation "
              'period (lunar day) to its orbital period (lunar month).\n'
              '\n'
              'In geophysical terms, the Moon is a planetary-mass object or satellite planet. Its mass is 1.2% '
              "that of the Earth, and its diameter is 3,474 km (2,159 mi), roughly one-quarter of Earth's (about "
              'as wide as the contiguous United States). Within the Solar System, it is larger and more massive '
              'than any known dwarf planet, and the fifth-largest and fifth–most massive moon, as well as the '
              'largest and most massive in relation to its parent planet. Its surface gravity is about one-sixth '
              "of Earth's, about half that of Mars, and the second-highest among all moons in the Solar System "
              "after Jupiter's moon Io. The body of the Moon is differentiated and terrestrial, with only a "
              'minuscule hydrosphere, atmosphere, and magnetic field. The lunar surface is covered in regolith '
              'dust, which mainly consists of the fine material ejected from the lunar crust by impact events. The '
              'lunar crust is marked by impact craters; some younger ones feature bright ray-like streaks. The '
              'Moon was volcanically active until 1.2 billion years ago, surfacing lava mostly on the thinner near '
              'side of the Moon, filling ancient craters, which through cooling formed the today prominently '
              "visible dark plains of basalt called maria ('seas'). The Moon is thought to have been formed out of "
              'material from Earth that was ejected by a giant impact of a Mars-sized body. Studies based on '
              'isotopic dating crystallization of the lunar magma ocean suggested that the Moon formed 4.35 '
              'billion years ago, late in the history of the Solar System.\n'
              '\n'
              'From a distance, the day and night phases of the lunar day are visible as the lunar phases, and '
              "when the Moon passes through Earth's shadow a lunar eclipse is observable. The Moon's apparent size "
              "in Earth's sky is about the same as that of the Sun, which causes it to cover the Sun completely "
              "during a total solar eclipse. The Moon is the brightest celestial object in Earth's night sky "
              'because of its large apparent size, while the reflectance (albedo) of its surface is comparable to '
              'that of asphalt. About 59% of the surface of the Moon is visible from Earth owing to the different '
              "angles at which the Moon can appear in Earth's sky (libration), making parts of the far side of the "
              'Moon visible.',
  'palavras': 493,
  'perguntas_reserva': [{'enunciado': 'How often does the Moon complete an orbit in relation to Earth and the Sun?',
                         'alternativas': ['Every 29.5 days', 'Every 24 hours', 'Every 7 days', 'Every 365 days'],
                         'resposta_correta': 'Every 29.5 days',
                         'justificativa': 'It completes an orbit (lunar month) "every 29.5 days".'},
                        {'enunciado': "What is the main driver of Earth's tides?",
                         'alternativas': ['The wind over the oceans',
                                          'The heat of the Sun',
                                          'The tidal forces between the Moon and Earth',
                                          "The Moon's magnetic field"],
                         'resposta_correta': 'The tidal forces between the Moon and Earth',
                         'justificativa': 'The gravitational attraction creates tidal forces, which "are the main '
                                          'driver of Earth\'s tides".'},
                        {'enunciado': "How strong is the Moon's surface gravity compared with Earth's?",
                         'alternativas': ["About half of Earth's",
                                          "About one-sixth of Earth's",
                                          "About the same as Earth's",
                                          "About one-quarter of Earth's"],
                         'resposta_correta': "About one-sixth of Earth's",
                         'justificativa': '"Its surface gravity is about one-sixth of Earth\'s."'},
                        {'enunciado': 'What are the dark plains called maria made of?',
                         'alternativas': ['Ice', 'Regolith dust', 'Asphalt', 'Basalt'],
                         'resposta_correta': 'Basalt',
                         'justificativa': 'Lava formed "the today prominently visible dark plains of basalt called '
                                          'maria".'},
                        {'enunciado': "How much of the Moon's surface is visible from Earth?",
                         'alternativas': ['About 59%', 'Exactly 50%', 'All of it', 'About 1.2%'],
                         'resposta_correta': 'About 59%',
                         'justificativa': '"About 59% of the surface of the Moon is visible from Earth", because '
                                          'of libration.'}]},
 {'id_origem': '23878',
  'titulo': 'Penguin',
  'url': 'https://en.wikipedia.org/wiki/Penguin',
  'conteudo': 'Penguins either waddle on their feet or slide on their bellies across the snow while using their '
              'feet to propel and steer themselves, a movement called "tobogganing", which conserves energy while '
              'moving quickly. They also jump with both feet together if they want to move more quickly or cross '
              'steep or rocky terrain.\n'
              '\n'
              'Penguins have an average sense of hearing for birds; this is used by parents and chicks to locate '
              'one another in crowded colonies. Their eyes are adapted for underwater vision and are their primary '
              'means of locating prey and avoiding predators; in air it has been suggested that they are '
              'nearsighted, although research has not supported this hypothesis.\n'
              '\n'
              'Penguins have a thick layer of insulating feathers that keeps them warm in water (heat loss in '
              'water is much greater than in air). The emperor penguin has a maximum feather density of about nine '
              'feathers per square centimeter which is actually much lower than other birds that live in Antarctic '
              'environments. However, they have been identified as having at least four different types of '
              'feather: in addition to the traditional feather, the emperor has afterfeathers, plumules, and '
              'filoplumes. The afterfeathers are downy plumes that attach directly to the main feathers and were '
              "once thought to account for the bird's ability to conserve heat when under water; the plumules are "
              'small down feathers that attach directly to the skin, and are much more dense in penguins than '
              'other birds; lastly the filoplumes are small (less than 1 cm long) naked shafts that end in a splay '
              'of fibers— filoplumes were thought to give flying birds a sense of where their plumage was and '
              'whether or not it needed preening, so their presence in penguins may seem inconsistent, but '
              'penguins also preen extensively.\n'
              '\n'
              'The emperor penguin has the largest body mass of all penguins, which further reduces relative '
              'surface area and heat loss. They also are able to control blood flow to their extremities, reducing '
              'the amount of blood that gets cold, but still keeping the extremities from freezing. In the extreme '
              'cold of the Antarctic winter, the females are at sea fishing for food, leaving the males to brave '
              'the weather by themselves. They often huddle together to keep warm and rotate positions to make '
              'sure that each penguin gets a turn in the centre of the heat pack.\n'
              '\n'
              'Calculations of the heat loss and retention ability of marine endotherms suggest that most extant '
              'penguins are too small to survive in such cold environments. In 2007, Thomas and Fordyce wrote '
              'about the "heterothermic loophole" that penguins utilize in order to survive in Antarctica. All '
              'extant penguins, even those that live in warmer climates, have a counter-current heat exchanger '
              'called the humeral plexus. The flippers of penguins have at least three branches of the axillary '
              'artery, which allows cold blood to be heated by blood that has already been warmed and limits heat '
              'loss from the flippers. This system allows penguins to efficiently use their body heat and explains '
              'why such small animals can survive in the extreme cold.\n'
              '\n'
              'They can drink salt water because their supraorbital gland filters excess salt from the '
              'bloodstream. The salt is excreted in a concentrated fluid from the nasal passages.\n'
              '\n'
              'Around one in 50,000 penguins (of most species) are born with brown rather than black plumage. '
              'These are called isabelline penguins. Isabellinism is different from albinism. Isabelline penguins '
              'tend to live shorter lives than normal penguins, as they are not well-camouflaged against the deep '
              'and are often passed over as mates.',
  'palavras': 588,
  'perguntas_reserva': [{'enunciado': 'What is the movement called "tobogganing"?',
                         'alternativas': ['Sliding on their bellies across the snow',
                                          'Jumping with both feet together',
                                          'Swimming under the ice',
                                          'Huddling together to keep warm'],
                         'resposta_correta': 'Sliding on their bellies across the snow',
                         'justificativa': 'Penguins "slide on their bellies across the snow", a movement called '
                                          '"tobogganing".'},
                        {'enunciado': 'What do penguins mainly use to locate prey and avoid predators?',
                         'alternativas': ['Their hearing', 'Their sense of smell', 'Their eyes', 'Their feathers'],
                         'resposta_correta': 'Their eyes',
                         'justificativa': 'Their eyes "are their primary means of locating prey and avoiding '
                                          'predators".'},
                        {'enunciado': 'What do male emperor penguins do during the Antarctic winter while the '
                                      'females are at sea?',
                         'alternativas': ['They fish for food near the coast',
                                          'They huddle together and rotate positions to keep warm',
                                          'They migrate to warmer climates',
                                          'They build nests of stones'],
                         'resposta_correta': 'They huddle together and rotate positions to keep warm',
                         'justificativa': 'The males "often huddle together to keep warm and rotate positions".'},
                        {'enunciado': 'Why can penguins drink salt water?',
                         'alternativas': ['Their feathers absorb the salt',
                                          'Their flippers remove the salt',
                                          'They only drink it in summer',
                                          'A gland filters excess salt from their bloodstream'],
                         'resposta_correta': 'A gland filters excess salt from their bloodstream',
                         'justificativa': '"Their supraorbital gland filters excess salt from the bloodstream."'},
                        {'enunciado': 'What are isabelline penguins?',
                         'alternativas': ['Penguins born with brown rather than black plumage',
                                          'Penguins with albinism',
                                          'The largest penguins',
                                          'Penguins that live in warmer climates'],
                         'resposta_correta': 'Penguins born with brown rather than black plumage',
                         'justificativa': 'About one in 50,000 penguins "are born with brown rather than black '
                                          'plumage"; these are isabelline.'}]}]


def upgrade() -> None:
    conexao = op.get_bind()
    existentes = set(conexao.execute(
        sa.select(readingtext.c.id_origem).where(readingtext.c.fonte == FONTE)).scalars())
    novos = [
        {**texto, "fonte": FONTE, "data_criacao": datetime(2026, 11, 21)}
        for texto in TEXTOS_RESERVA if texto["id_origem"] not in existentes
    ]
    if novos:
        op.bulk_insert(readingtext, novos)


def downgrade() -> None:
    conexao = op.get_bind()
    ids_origem = [texto["id_origem"] for texto in TEXTOS_RESERVA]
    da_reserva = (readingtext.c.fonte == FONTE) & readingtext.c.id_origem.in_(ids_origem)
    usados = sa.select(readingchallenge.c.texto_id)
    conexao.execute(sa.update(readingtext).where(da_reserva & readingtext.c.id.in_(usados))
                    .values(perguntas_reserva=sa.null()))  # NULL do SQL, e não o texto JSON "null"
    conexao.execute(sa.delete(readingtext).where(da_reserva & readingtext.c.id.not_in(usados)))
