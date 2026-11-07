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
    let aoMudarVelocidade = null; // avisado só quando o USUÁRIO muda a velocidade (a página salva a preferência)
    let volume = 1;               // 0 (mudo) a 1 (100%)
    let volumeAntesDoMudo = 1;    // para onde o volume volta ao desligar o mudo
    let aoMudarVolume = null;     // avisado só quando o USUÁRIO muda o volume (a página salva a preferência)

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
                // O <video> não informa o status HTTP do erro. Se a sessão venceu (B13: o vídeo exige login), esta
                // consulta passa pelo api.js e leva ao login; senão, segue a mensagem de sempre.
                await api.videos.status(videoId).catch(() => {});
                if (minhaCarga !== carga) return false;
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

    // Velocidade inicial válida dentro da faixa do slider (templates/partials/player.html); senão, 1x.
    function velocidadeInicial(valor) {
        const slider = elemento("velocidade");
        const [minima, maxima] = slider ? [Number(slider.min), Number(slider.max)] : [0.25, 1.5];
        return Number.isFinite(valor) && valor > 0 ? Math.min(maxima, Math.max(minima, valor)) : 1;
    }

    // Volume inicial entre 0 e 1; sem um valor válido, 100%.
    function volumeInicial(valor) {
        return Number.isFinite(valor) ? Math.min(1, Math.max(0, valor)) : 1;
    }

    // opcoes.velocidade / opcoes.volume: preferências salvas do usuário (B8 / B9.2). Sem elas, 1x e 100%.
    async function criar(elementoId, videoId, opcoes = {}) {
        destruir();
        velocidade = velocidadeInicial(opcoes.velocidade);
        volume = volumeInicial(opcoes.volume);
        volumeAntesDoMudo = volume || 1;
        video = document.createElement("video");
        video.playsInline = true;
        video.preload = "auto";
        video.disablePictureInPicture = true;
        video.disableRemotePlayback = true;
        video.setAttribute("controlsList", "nodownload noplaybackrate noremoteplayback");
        video.oncontextmenu = (evento) => evento.preventDefault();
        video.onplay = video.onpause = atualizarControles;
        video.volume = volume;
        elemento(elementoId).replaceChildren(video);
        conectarControles();
        return carregarVideo(videoId);
    }

    function conectarControles() {
        const slider = elemento("velocidade");
        elemento("pausar").onclick = alternarPausa;
        elemento("bloqueioPlayer").onclick = alternarPausa;
        slider.oninput = () => mudarVelocidadePeloUsuario(Number(slider.value));
        slider.ondblclick = () => mudarVelocidadePeloUsuario(1);
        const sliderVolume = elemento("volume");
        if (sliderVolume) {
            sliderVolume.oninput = () => mudarVolumePeloUsuario(Number(sliderVolume.value));
            sliderVolume.ondblclick = () => mudarVolumePeloUsuario(1);
            elemento("mudo").onclick = alternarMudo;
        }
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
        atualizarControlesDeVolume();
    }

    function atualizarControlesDeVolume() {
        const slider = elemento("volume");
        if (!slider) return;
        slider.disabled = !liberado;
        slider.value = volume;
        slider.style.setProperty("--progresso", `${volume * 100}%`);
        elemento("volumeValor").textContent = `${Math.round(volume * 100)}%`;
        const mudo = elemento("mudo");
        mudo.disabled = !liberado;
        mudo.title = volume === 0 ? "Ativar o som" : "Silenciar";
        mudo.setAttribute("aria-label", mudo.title);
        // Ícone conforme o nível: sem som, baixo, alto.
        mudo.querySelector("i").className = `fa ${volume === 0 ? "fa-volume-off" : volume < 0.5 ? "fa-volume-down" : "fa-volume-up"}`;
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
        volume = 1;
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

    function mudarVelocidadePeloUsuario(nova) {
        definirVelocidade(nova);
        aoMudarVelocidade?.(nova);
    }

    function definirVolume(novo) {
        volume = novo;
        if (video) video.volume = novo;
        atualizarControles();
    }

    function mudarVolumePeloUsuario(novo) {
        if (novo > 0) volumeAntesDoMudo = novo;
        definirVolume(novo);
        aoMudarVolume?.(novo);
    }

    // Clique no alto-falante: silencia, ou volta ao volume de antes do mudo.
    function alternarMudo() {
        if (!liberado) return;
        mudarVolumePeloUsuario(volume > 0 ? 0 : volumeAntesDoMudo || 1);
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
        // Recebe a nova velocidade quando o usuário mexe no slider (ou dá duplo clique para voltar a 1x).
        aoMudarVelocidade: (callback) => { aoMudarVelocidade = callback; },
        // Recebe o novo volume (0 a 1) quando o usuário mexe no controle de volume ou no botão de mudo.
        aoMudarVolume: (callback) => { aoMudarVolume = callback; },
        volume: () => volume,
        velocidade: () => velocidade,
    };
})();
