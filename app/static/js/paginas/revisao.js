// Página de revisão (templates/paginas/revisao.html): passa pelos Cards de um Deck que estão na hora de revisar.
import { Avaliacao } from "../componentes/avaliacao.js";
import { criarEstadoVazio } from "../componentes/estado-vazio.js";
import { Gravador } from "../componentes/gravador.js";
import { Legenda } from "../componentes/legenda.js";
import { Player } from "../componentes/player.js";
import { api } from "../nucleo/api.js";
import { mostrarErro } from "../nucleo/interface.js";
import { salvarPendentes, salvarVelocidade, salvarVolume } from "../nucleo/configuracoes.js";
import { navegarPara, registrarPagina } from "../nucleo/paginas.js";

registrarPagina("revisao", (raiz) => {
    const estado = { ativa: true, cards: [], indice: 0 };
    const elemento = (id) => document.getElementById(id);
    const botoes = ["facil", "medio", "dificil", "delete"].map(elemento);

    function habilitarBotoes(habilitar) {
        botoes.forEach((botao) => { botao.disabled = !habilitar; });
    }

    function mostrarCard(indice) {
        estado.indice = indice;
        const card = estado.cards[indice];
        Legenda.mostrar(card.texto_legenda, { duracao: card.end_time - card.start_time });
        Legenda.carregarTempos(card.video_id, card.start_time, card.end_time);
        Player.tocarTrecho(card.start_time, card.end_time, card.video_id);
        Gravador.prepararFrase(`card-${card.id}`, card.end_time - card.start_time, {
            videoId: card.video_id, inicio: card.start_time, fim: card.end_time, texto: card.texto_legenda,
        });
    }

    function avancar() {
        if (estado.indice < estado.cards.length) {
            mostrarCard(estado.indice);
            return;
        }
        alert("Você finalizou a revisão dos Cards deste deck.");
        navegarPara("/decks");
    }

    async function avaliar(dificuldade) {
        const card = estado.cards[estado.indice];
        habilitarBotoes(false);
        try {
            await api.cards.avaliar(card.id, dificuldade);
            estado.indice++;
            avancar();
        } catch (erro) {
            mostrarErro(`Erro ao salvar a revisão: ${erro.message}`);
        } finally {
            habilitarBotoes(true);
        }
    }

    async function deletarCard() {
        const card = estado.cards[estado.indice];
        if (!confirm("Deseja mesmo excluir este card permanentemente?")) return;
        try {
            await api.cards.deletar(card.id);
            // O próximo Card passa a ocupar o mesmo índice.
            estado.cards.splice(estado.indice, 1);
            avancar();
        } catch (erro) {
            mostrarErro(`Não foi possível deletar este card: ${erro.message}`);
        }
    }

    // "Daqui a quanto tempo": hoje às 18:30 / amanhã (08/11) / em 7 dias (14/11).
    function quando(dataIso) {
        const data = new Date(dataIso); // horário de Brasília, sem fuso (como o servidor grava)
        const dia = data.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
        const meiaNoite = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
        const dias = Math.round((meiaNoite(data) - meiaNoite(new Date())) / 86400000);
        if (dias <= 0) return `hoje às ${data.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`;
        return dias === 1 ? `amanhã (${dia})` : `em ${dias} dias (${dia})`;
    }

    // Nada para revisar agora (B12): o Deck está vazio, ou tudo foi revisado e há uma data para voltar.
    async function mostrarRevisaoVazia(deckId) {
        Legenda.mostrarAviso("Nenhum Card para revisar agora.");
        let deck = null;
        try {
            deck = (await api.decks.listar()).find((d) => d.id === Number(deckId)) ?? null;
        } catch {
            // Sem o resumo, mostra a mensagem genérica abaixo.
        }
        if (!estado.ativa) return;
        const irParaDecks = { rotulo: "Voltar aos Decks", aoClicar: () => navegarPara("/decks") };
        const estudar = { rotulo: "Estudar um vídeo", aoClicar: () => navegarPara("/") };
        let conteudo;
        if (deck && deck.quantidade_total === 0) {
            conteudo = {
                titulo: "Este Deck ainda não tem Cards",
                texto: "Salve frases com o marcador 🔖 durante o estudo de um vídeo e escolha este Deck.",
                acoes: [{ ...estudar, principal: true }, irParaDecks],
            };
        } else if (deck?.proxima_revisao) {
            conteudo = {
                titulo: "Tudo revisado! 🎉",
                texto: `Próxima revisão deste Deck: ${quando(deck.proxima_revisao)}.`,
                acoes: [{ ...irParaDecks, principal: true }, estudar],
            };
        } else {
            conteudo = {
                titulo: "Nenhum Card para revisar agora",
                texto: "Volte mais tarde, ou estude um vídeo novo.",
                acoes: [{ ...irParaDecks, principal: true }, estudar],
            };
        }
        elemento("revisaoVaziaConteudo").replaceChildren(criarEstadoVazio(conteudo));
        elemento("revisaoVazia").style.display = "flex";
    }

    async function iniciar(deckId) {
        habilitarBotoes(false);
        if (!deckId) {
            mostrarErro("Nenhum Deck foi selecionado para revisão.");
            return;
        }

        let cards;
        try {
            cards = await api.decks.cardsParaRevisar(deckId);
        } catch (erro) {
            mostrarErro(erro.message);
            return;
        }
        if (!estado.ativa) return;

        if (!cards.length) {
            await mostrarRevisaoVazia(deckId);
            return;
        }

        estado.cards = cards;
        mostrarCard(0);
        // O vídeo começa na velocidade salva do usuário (vem no HTML da página).
        const carregandoVideo = Player.criar("player", cards[0].video_id, {
            velocidade: Number(raiz.dataset.velocidade), volume: Number(raiz.dataset.volume),
        });
        Gravador.atualizarTempoEsperado(); // o timer do primeiro Card já usa a velocidade salva
        await carregandoVideo;
        if (!estado.ativa) return;
        elemento("protecaoButton").disabled = false;
        habilitarBotoes(true);
    }

    elemento("facil").onclick = () => avaliar("facil");
    elemento("medio").onclick = () => avaliar("medio");
    elemento("dificil").onclick = () => avaliar("dificil");
    elemento("delete").onclick = deletarCard;
    elemento("gravar").onclick = Gravador.alternar;
    elemento("ouvirGravacao").onclick = Gravador.reproduzir;
    Gravador.configurar({
        velocidade: Player.velocidade,
        aoReproduzir: (tocando) => (tocando ? Player.suspender() : Player.retomar()),
        avaliar: api.avaliarFala,
        mostrarAvaliacao: (avaliacao) => Avaliacao.mostrar(avaliacao, estado.cards[estado.indice]?.texto_legenda ?? ""),
    });
    elemento("protecaoButton").onclick = () => {
        elemento("protecaoPlayer").style.display = "none";
        Player.liberar();
    };

    Legenda.reiniciar();
    Player.aoAtualizarTempo(Legenda.destacar);
    Player.aoMudarVelocidade((velocidade) => {
        Gravador.atualizarTempoEsperado();
        salvarVelocidade(velocidade);
    });
    Player.aoMudarVolume(salvarVolume);
    iniciar(raiz.dataset.deckId);

    return () => {
        estado.ativa = false;
        Player.destruir();
        Player.aoAtualizarTempo(null);
        Player.aoMudarVelocidade(null);
        Player.aoMudarVolume(null);
        salvarPendentes();
        Gravador.encerrar();
        Legenda.fecharPopup();
    };
});
