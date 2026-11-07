// Página de estudo (templates/paginas/estudo.html): carrega as legendas do vídeo e navega frase a frase.
import { Avaliacao } from "../componentes/avaliacao.js";
import { escolherDeck } from "../componentes/escolha-deck.js";
import { Gravador } from "../componentes/gravador.js";
import { Legenda } from "../componentes/legenda.js";
import { Player } from "../componentes/player.js";
import { Waveform } from "../componentes/waveform.js";
import { api } from "../nucleo/api.js";
import {
    atualizarTokens, contagemRegressiva, esconderCarregamento, formatarTempo, mostrarCarregamento, mostrarErro,
} from "../nucleo/interface.js";
import { salvarPendentes, salvarVelocidade } from "../nucleo/configuracoes.js";
import { navegarPara, registrarPagina } from "../nucleo/paginas.js";

registrarPagina("estudo", (raiz) => {
    const estado = { ativa: true, videoId: null, frases: [], indice: 0, salvas: new Set(), cancelarContagem: null };
    const elemento = (id) => document.getElementById(id);

    const urlDoAudio = (frase) => api.videos.urlAudio(estado.videoId, frase.tempo_inicio, frase.tempo_fim);

    function mostrarFrase(indice) {
        estado.indice = indice;
        const frase = estado.frases[indice];
        const duracao = frase.tempo_fim - frase.tempo_inicio;

        Legenda.mostrar(frase.texto_limpo, { temposPalavras: frase.tempos_palavras, duracao });
        Legenda.carregarTempos(estado.videoId, frase.tempo_inicio, frase.tempo_fim);
        marcarSalvo(estado.salvas.has(indice));
        elemento("contadorFrase").textContent = `${indice + 1} / ${estado.frases.length}`;
        elemento("anterior").disabled = indice === 0;
        elemento("proximo").disabled = indice === estado.frases.length - 1;

        // O vídeo muda na hora; o waveform carrega em paralelo e não bloqueia a navegação.
        Player.tocarTrecho(frase.tempo_inicio, frase.tempo_fim);
        Gravador.prepararFrase(`frase-${indice}`, duracao, {
            videoId: estado.videoId, inicio: frase.tempo_inicio, fim: frase.tempo_fim, texto: frase.texto_limpo,
        });
        Waveform.carregar(urlDoAudio(frase), duracao);

        // Pré-carrega o áudio das próximas 2 frases, para a troca ser instantânea.
        estado.frases.slice(indice + 1, indice + 3).forEach((proxima) => fetch(urlDoAudio(proxima)).catch(() => {}));
    }

    function marcarSalvo(salvo) {
        const botao = elemento("salvar");
        botao.classList.toggle("salvo", salvo);
        botao.title = salvo ? "Card salvo" : "Salvar Card";
        botao.querySelector("i").className = salvo ? "fa fa-bookmark" : "fa fa-bookmark-o";
    }

    async function salvarCard() {
        const indice = estado.indice;
        const frase = estado.frases[indice];
        const deckId = await escolherDeck();
        if (deckId === null) return;
        try {
            await api.decks.salvarCard(deckId, {
                video_id: estado.videoId,
                texto_legenda: frase.texto_limpo,
                start_time: frase.tempo_inicio,
                end_time: frase.tempo_fim,
            });
            estado.salvas.add(indice);
            if (indice === estado.indice) marcarSalvo(true);
        } catch (erro) {
            if (erro.status === 409) alert(`⚠️ ${erro.message}`);
            else mostrarErro(`Erro ao salvar: ${erro.message}`);
        }
    }

    // 429 "limite_de_tokens": mostra quanto falta para renovar e o que dá para fazer enquanto isso (revisar Decks).
    // O limite só é informado: nada é tentado de novo sozinho. Quando a contagem termina, a pessoa pode carregar.
    function mostrarSemTokens(segundos) {
        const contagem = elemento("contagemTokens");
        const tentar = elemento("semTokensTentar");
        tentar.hidden = true;
        elemento("modalSemTokens").style.display = "flex";
        estado.cancelarContagem?.();
        estado.cancelarContagem = contagemRegressiva(
            segundos,
            (restante) => { contagem.textContent = formatarTempo(restante); },
            () => {
                contagem.textContent = "0:00 (renovados!)";
                tentar.hidden = false;
            },
        );
    }

    async function iniciarSessao(link) {
        if (!link) {
            mostrarErro("Nenhum link de vídeo foi informado.");
            return;
        }

        mostrarCarregamento("Extraindo legendas e preparando áudio...");
        let dados;
        try {
            dados = await api.legendas(link);
        } catch (erro) {
            if (erro.codigo === "limite_de_tokens") {
                atualizarTokens(0, erro.dados.tentar_novamente_em);
                mostrarSemTokens(erro.dados.tentar_novamente_em);
                return;
            }
            mostrarErro(erro.message);
            return;
        } finally {
            esconderCarregamento();
        }
        if (!estado.ativa) return;

        atualizarTokens(dados.tokens_restantes, dados.renova_em);
        estado.videoId = dados.video_id;
        estado.frases = dados.dados;
        if (!estado.frases.length) {
            mostrarErro("Não foi encontrada nenhuma frase nas legendas desse vídeo.");
            return;
        }

        elemento("textologs").textContent = dados.aviso_legenda;
        const ultimoToken = elemento("avisoUltimoToken");
        ultimoToken.hidden = !(dados.tokens_restantes === 0 && dados.renova_em);
        if (!ultimoToken.hidden) {
            ultimoToken.textContent = `Este foi seu último token. Novos tokens em ${formatarTempo(dados.renova_em)}.`;
        }
        elemento("modalLegendaTitulo").style.display = "flex";

        mostrarFrase(0);
        // O vídeo começa na velocidade salva do usuário (vem no HTML da página).
        const carregandoVideo = Player.criar("player", estado.videoId, { velocidade: Number(raiz.dataset.velocidade) });
        Gravador.atualizarTempoEsperado(); // o timer da primeira frase já usa a velocidade salva
        await carregandoVideo;
        if (estado.ativa) elemento("protecaoButton").disabled = false;
    }

    elemento("anterior").onclick = () => estado.indice > 0 && mostrarFrase(estado.indice - 1);
    elemento("proximo").onclick = () => estado.indice < estado.frases.length - 1 && mostrarFrase(estado.indice + 1);
    elemento("salvar").onclick = salvarCard;
    elemento("gravar").onclick = Gravador.alternar;
    elemento("ouvirGravacao").onclick = Gravador.reproduzir;
    elemento("botaoContinuar").onclick = () => { elemento("modalLegendaTitulo").style.display = "none"; };
    elemento("semTokensDecks").onclick = () => navegarPara("/decks");
    elemento("semTokensInicio").onclick = () => navegarPara("/");
    elemento("semTokensTentar").onclick = () => location.reload(); // só aparece quando os tokens já renovaram
    elemento("protecaoButton").onclick = () => {
        elemento("protecaoPlayer").style.display = "none";
        Player.liberar();
    };

    Legenda.reiniciar();
    Player.aoMudarVelocidade((velocidade) => {
        Gravador.atualizarTempoEsperado();
        salvarVelocidade(velocidade); // fica salva na conta (com atraso, para não salvar a cada passo do slider)
    });
    Player.aoAtualizarTempo((decorrido) => {
        Waveform.atualizarCursor(decorrido);
        Legenda.destacar(decorrido);
    });
    // Clicar ou arrastar o cursor da onda leva o vídeo para aquele ponto (pausado durante o arraste).
    Waveform.conectar({ buscar: Player.irPara, inicioArraste: Player.suspender, fimArraste: Player.retomar });
    Gravador.configurar({
        velocidade: Player.velocidade,
        // Enquanto o usuário ouve a própria gravação, o vídeo fica pausado.
        aoReproduzir: (tocando) => (tocando ? Player.suspender() : Player.retomar()),
        avaliar: api.avaliarFala,
        mostrarAvaliacao: (avaliacao) => Avaliacao.mostrar(avaliacao, estado.frases[estado.indice]?.texto_limpo ?? ""),
    });
    iniciarSessao(raiz.dataset.link);

    return () => {
        estado.ativa = false;
        estado.cancelarContagem?.();
        Player.destruir();
        Player.aoAtualizarTempo(null);
        Player.aoMudarVelocidade(null);
        salvarPendentes(); // saiu da página logo depois de mexer no slider: salva agora
        Waveform.conectar(null);
        Gravador.encerrar();
        Waveform.destruir();
        Legenda.fecharPopup();
    };
});
