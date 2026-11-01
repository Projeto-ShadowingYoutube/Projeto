// Player de vídeo usado pela página de estudo e pela de revisão. Toca um trecho (início/fim) em loop.
//
// O vídeo é baixado pelo servidor (app/services/midia.py) e tocado num <video> sem controles: não aparece nada
// da interface do YouTube, e pausa/velocidade são feitas pela barra de templates/partials/player.html.
// Enquanto o servidor baixa o vídeo, o progresso aparece no botão "Iniciar Estudos" e sobre o vídeo.
import { api } from "../nucleo/api.js";
import { mostrarErro } from "../nucleo/interface.js";

export const Player = (() => {
    const INTERVALO_STATUS = 700; // ms entre as consultas do progresso do download

    let video = null;
    let videoAtual = null;
    let carga = 0;            // muda a cada troca de vídeo: cargas antigas que terminam depois são ignoradas
    let trecho = { inicio: 0, fim: 0 };
    // O navegador só deixa tocar vídeo com som depois de um clique do usuário (botão "Iniciar Estudos").
    let liberado = false;
    let velocidade = 1;
    let suspenso = false;     // pausado por suspender() (ex.: enquanto o usuário ouve a própria gravação)
    let loopId = null;
    let aoAtualizarTempo = null;

    const elemento = (id) => document.getElementById(id);
    const esperar = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
    const pausado = () => !video || video.paused;

    function mostrarAviso(texto) {
        const aviso = elemento("avisoPlayer");
        if (!aviso) return;
        aviso.textContent = texto || "";
        aviso.hidden = !texto;
        const botao = elemento("protecaoButton");
        if (botao && !liberado) botao.textContent = texto || "Iniciar Estudos";
    }

    // Espera o servidor terminar de baixar o vídeo, mostrando o progresso.
    async function esperarDownload(videoId, minhaCarga) {
        for (;;) {
            const status = await api.videos.status(videoId);
            if (minhaCarga !== carga) return false;
            if (status.pronto) return true;
            mostrarAviso(`Baixando o vídeo... ${Math.round(status.progresso * 100)}%`);
            await esperar(INTERVALO_STATUS);
        }
    }

    async function carregarVideo(videoId) {
        const minhaCarga = ++carga;
        videoAtual = videoId;
        pararLoop();
        video.pause();
        // Tira o vídeo anterior, para não tocá-lo enquanto o novo baixa.
        video.removeAttribute("src");
        video.load();
        mostrarAviso("Preparando o vídeo...");
        try {
            if (!(await esperarDownload(videoId, minhaCarga))) return false;
            video.src = api.videos.url(videoId);
            await new Promise((resolve, reject) => {
                video.onloadedmetadata = resolve;
                video.onerror = () => reject(new Error("O navegador não conseguiu abrir o vídeo."));
            });
        } catch (erro) {
            if (minhaCarga === carga) {
                mostrarAviso("Vídeo indisponível.");
                mostrarErro(erro.message);
            }
            return false;
        }
        if (minhaCarga !== carga) return false;
        mostrarAviso(null);
        video.playbackRate = velocidade;
        video.currentTime = trecho.inicio;
        if (liberado) {
            tocar();
            iniciarLoop();
        }
        return true;
    }

    async function criar(elementoId, videoId) {
        destruir();
        video = document.createElement("video");
        video.playsInline = true;
        video.preload = "auto";
        video.disablePictureInPicture = true;
        video.disableRemotePlayback = true;
        video.setAttribute("controlsList", "nodownload noplaybackrate noremoteplayback");
        video.oncontextmenu = (evento) => evento.preventDefault();
        video.onplay = video.onpause = atualizarControles;
        elemento(elementoId).replaceChildren(video);
        conectarControles();
        return carregarVideo(videoId);
    }

    function conectarControles() {
        const slider = elemento("velocidade");
        elemento("pausar").onclick = alternarPausa;
        elemento("bloqueioPlayer").onclick = alternarPausa;
        slider.oninput = () => definirVelocidade(Number(slider.value));
        slider.ondblclick = () => definirVelocidade(1);
        atualizarControles();
    }

    function atualizarControles() {
        const botaoPausar = elemento("pausar");
        if (botaoPausar) {
            botaoPausar.disabled = !liberado;
            botaoPausar.title = pausado() ? "Continuar" : "Pausar";
            botaoPausar.querySelector("i").className = pausado() ? "fa fa-play" : "fa fa-pause";
        }
        const slider = elemento("velocidade");
        if (slider) {
            slider.disabled = !liberado;
            slider.value = velocidade;
            // Preenche a trilha até o valor atual (o CSS usa a variável --progresso).
            slider.style.setProperty("--progresso", `${((velocidade - slider.min) / (slider.max - slider.min)) * 100}%`);
        }
        const valor = elemento("velocidadeValor");
        if (valor) valor.textContent = `${velocidade.toFixed(2)}x`;
    }

    function destruir() {
        carga++;
        pararLoop();
        if (video) {
            video.pause();
            video.removeAttribute("src");
            video.load(); // libera a conexão com o servidor
        }
        video = null;
        videoAtual = null;
        liberado = false;
        suspenso = false;
        velocidade = 1;
    }

    function tocar() {
        suspenso = false;
        video.play().catch(() => {}); // play() é rejeitado se uma pausa vier logo depois; não é erro
    }

    // Ao mudar de frase o vídeo volta a tocar, mesmo que estivesse pausado.
    function tocarTrecho(inicio, fim, videoId = videoAtual) {
        trecho = { inicio, fim };
        if (!video) return;
        if (videoId !== videoAtual) {
            carregarVideo(videoId);
            return;
        }
        if (!video.src) return; // ainda baixando: carregarVideo começa no trecho novo
        video.currentTime = inicio;
        if (liberado) {
            tocar();
            iniciarLoop();
        }
    }

    // Leva o vídeo para "decorrido" segundos após o início do trecho (clique ou arraste na onda).
    function irPara(decorrido) {
        if (!video?.src || !liberado) return;
        const limitado = Math.max(0, Math.min(decorrido, trecho.fim - trecho.inicio - 0.05));
        video.currentTime = trecho.inicio + limitado;
        aoAtualizarTempo?.(limitado);
    }

    function alternarPausa() {
        if (!video?.src || !liberado) return;
        pausado() ? tocar() : video.pause();
    }

    // Pausa o vídeo por um momento; retomar() só volta a tocar se fui eu quem pausou.
    function suspender() {
        if (!video?.src || !liberado || pausado()) return;
        video.pause();
        suspenso = true;
    }

    function retomar() {
        if (suspenso && pausado()) tocar();
        suspenso = false;
    }

    function definirVelocidade(nova) {
        velocidade = nova;
        if (video) video.playbackRate = nova;
        atualizarControles();
    }

    function liberar() {
        liberado = true;
        atualizarControles();
        if (!video?.src) return; // ainda baixando: carregarVideo começa a tocar quando terminar
        video.currentTime = trecho.inicio;
        tocar();
        iniciarLoop();
    }

    function iniciarLoop() {
        pararLoop();
        const verificar = () => {
            if (!video) return;
            if (video.currentTime >= trecho.fim - 0.05 || video.currentTime < trecho.inicio - 0.5) {
                video.currentTime = trecho.inicio;
            }
            aoAtualizarTempo?.(video.currentTime - trecho.inicio);
            loopId = requestAnimationFrame(verificar);
        };
        verificar();
    }

    function pararLoop() {
        if (loopId) cancelAnimationFrame(loopId);
        loopId = null;
    }

    return {
        criar,
        destruir,
        tocarTrecho,
        irPara,
        suspender,
        retomar,
        liberar,
        // Recebe a cada frame quantos segundos se passaram desde o início do trecho.
        aoAtualizarTempo: (callback) => { aoAtualizarTempo = callback; },
        velocidade: () => velocidade,
    };
})();
