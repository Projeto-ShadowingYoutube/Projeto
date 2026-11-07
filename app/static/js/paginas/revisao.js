// Página de revisão (templates/paginas/revisao.html): passa pelos Cards de um Deck que estão na hora de revisar.
import { Avaliacao } from "../componentes/avaliacao.js";
import { Gravador } from "../componentes/gravador.js";
import { Legenda } from "../componentes/legenda.js";
import { Player } from "../componentes/player.js";
import { api } from "../nucleo/api.js";
import { mostrarErro } from "../nucleo/interface.js";
import { salvarPendentes, salvarVelocidade } from "../nucleo/configuracoes.js";
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
            Legenda.mostrarAviso("A data de revisão dos Cards desse Deck ainda não chegou, ou esse Deck não possui Cards.");
            return;
        }

        estado.cards = cards;
        mostrarCard(0);
        // O vídeo começa na velocidade salva do usuário (vem no HTML da página).
        const carregandoVideo = Player.criar("player", cards[0].video_id, { velocidade: Number(raiz.dataset.velocidade) });
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
    iniciar(raiz.dataset.deckId);

    return () => {
        estado.ativa = false;
        Player.destruir();
        Player.aoAtualizarTempo(null);
        Player.aoMudarVelocidade(null);
        salvarPendentes();
        Gravador.encerrar();
        Legenda.fecharPopup();
    };
});
