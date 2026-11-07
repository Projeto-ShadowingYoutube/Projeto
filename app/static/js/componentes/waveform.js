// Waveform de referência: desenha o áudio original da frase com o WaveSurfer, ocupando toda a largura.
// Desde o B9, a onda vem pronta do servidor (GET /api/videos/{id}/waveform: peaks de 0 a 1, guardados no banco) e o
// WaveSurfer só a desenha: o navegador não baixa nem decodifica mais o áudio da frase.
// A onda do microfone (voice.js) usa a mesma escala: a largura toda corresponde à duração da frase.
// Clicar na onda, ou arrastar o cursor vermelho, avisa a página (que leva o vídeo para aquele instante).
export const Waveform = (() => {
    let wavesurfer = null;
    let cargaAtual = 0;
    let duracao = 0;
    let acoes = null; // { buscar(segundos), inicioArraste(), fimArraste() }, definidas pela página
    let arrastando = false;

    // Nunca lança erro: se a onda não carregar, mostra o aviso no lugar dela.
    // url: a da rota /waveform (api.videos.urlWaveform).
    async function carregar(url, duracaoFrase) {
        const carga = ++cargaAtual;
        duracao = duracaoFrase;
        atualizarCursor(0);

        try {
            // Busca a onda nova antes de apagar a antiga, para a troca não piscar.
            const resposta = await fetch(url);
            const dados = await resposta.json().catch(() => null);
            if (!resposta.ok || !dados?.peaks) {
                throw new Error(dados?.detail || "Erro ao buscar a onda da frase.");
            }
            if (carga !== cargaAtual) return; // O usuário já mudou de frase.

            destruir();
            const container = document.getElementById("waveform");
            container.replaceChildren();

            wavesurfer = WaveSurfer.create({
                container,
                waveColor: "#93c5fd",
                progressColor: "#2563eb",
                cursorWidth: 0,
                barWidth: 2,
                barGap: 1,
                barRadius: 2,
                height: 140,
                normalize: true,
                interact: false,
                // A onda pronta: com peaks + duration, o WaveSurfer desenha sem áudio (e setTime continua pintando
                // o progresso, que acompanha o vídeo em atualizarCursor).
                peaks: [dados.peaks],
                duration: dados.duracao,
            });
            await new Promise((pronto) => wavesurfer.once("ready", pronto));
        } catch (erro) {
            if (carga !== cargaAtual) return;
            console.error("Erro ao carregar o waveform:", erro);
            mostrarFalha(`Onda da frase indisponível: ${erro.message}`);
        }
    }

    function mostrarFalha(mensagem) {
        destruir();
        const container = document.getElementById("waveform");
        if (!container) return;
        const aviso = document.createElement("p");
        aviso.className = "waveform-falha";
        aviso.textContent = mensagem;
        container.replaceChildren(aviso);
    }

    // "decorrido" = segundos desde o início da frase no vídeo.
    function atualizarCursor(decorrido) {
        const cursor = document.getElementById("waveCursor");
        if (!cursor || !duracao) return;
        const limitado = Math.max(0, Math.min(decorrido, duracao));
        cursor.style.left = `${(limitado / duracao) * 100}%`;
        if (wavesurfer?.getDuration() > 0) wavesurfer.setTime(Math.min(limitado, wavesurfer.getDuration()));
    }

    // O clique e o arraste são tratados no container (e não pelo WaveSurfer), assim funcionam até
    // enquanto a onda carrega. Pointer events cobrem mouse e toque.
    function buscar(evento) {
        const caixa = evento.currentTarget.getBoundingClientRect();
        const fracao = Math.max(0, Math.min(1, (evento.clientX - caixa.left) / caixa.width));
        acoes.buscar(fracao * duracao);
    }

    function iniciarArraste(evento) {
        if (!duracao || !acoes || evento.button !== 0) return;
        arrastando = true;
        evento.currentTarget.setPointerCapture(evento.pointerId); // continua recebendo o movimento fora da onda
        evento.currentTarget.classList.add("arrastando");
        acoes.inicioArraste?.();
        buscar(evento);
    }

    function moverArraste(evento) {
        if (arrastando) buscar(evento);
    }

    function terminarArraste(evento) {
        if (!arrastando) return;
        arrastando = false;
        evento.currentTarget.classList.remove("arrastando");
        acoes.fimArraste?.();
    }

    function destruir() {
        try {
            wavesurfer?.destroy();
        } catch {}
        wavesurfer = null;
    }

    return {
        carregar,
        mostrarFalha,
        atualizarCursor,
        // Liga (ou, com null, desliga) o clique/arraste na onda.
        conectar: (novasAcoes) => {
            acoes = novasAcoes;
            arrastando = false;
            const container = document.getElementById("waveformContainer");
            if (!container) return;
            container.onpointerdown = acoes ? iniciarArraste : null;
            container.onpointermove = acoes ? moverArraste : null;
            container.onpointerup = container.onpointercancel = acoes ? terminarArraste : null;
        },
        destruir: () => { cargaAtual++; destruir(); },
    };
})();
