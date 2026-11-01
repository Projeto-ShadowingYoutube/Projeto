// Gravação da voz do usuário: reconhecimento de fala (transcrição), onda do microfone, timer e reprodução.
//
// Tempo da gravação, pensado para ser justo com quem está aprendendo:
// - O relógio só começa quando o usuário começa a falar (até ESPERA_MAXIMA aguardando).
// - O tempo esperado é o da frase na velocidade em que o vídeo está tocando: a 0.75x, a frase
//   ouvida dura 1/0.75 da original, e é esse ritmo que o usuário está imitando.
// - Há folga: a gravação pode durar até FOLGA_PROPORCIONAL × esperado + FOLGA_FIXA.
// - A gravação termina sozinha quando o usuário para de falar, sem precisar esperar o relógio:
//   SILENCIO_FINAL de silêncio depois de já ter falado boa parte da frase, ou SILENCIO_LONGO em
//   qualquer momento (quem fala rápido não fica esperando; pausas curtas no meio da frase não cortam).
// - No fim, o ritmo vira feedback ("no ritmo", "x% mais lenta") em vez de cortar a fala.
//
// Cada frase guarda o próprio estado (onda, transcrição, áudio para ouvir, avaliação): voltar a uma
// frase já praticada mostra tudo de novo.
//
// Ao fim de cada gravação, a página recebe o áudio para avaliar (opção "avaliar") e o resultado é
// mostrado pela opção "mostrarAvaliacao".
//
// A onda é desenhada pelo TEMPO (e não por frame). A largura toda vale o tempo esperado, a mesma escala
// da onda original; se a fala passar disso, a escala aumenta e uma linha tracejada marca o fim esperado.
import { mostrarErro } from "../nucleo/interface.js";

export const Gravador = (() => {
    const LIMIAR_MINIMO = 0.02;       // volume (RMS) mínimo considerado fala
    const PRE_INICIO = 0.1;           // s: a fala começa um pouco antes de o volume passar do limiar
    const CAUDA = 0.15;               // s: a fala termina um pouco depois do último volume alto
    const ESPERA_MAXIMA = 8;          // s aguardando a fala antes de desistir
    const QUADROS_DE_RUIDO = 15;      // quadros usados para medir o ruído de fundo
    const SILENCIO_FINAL = 1.0;       // s de silêncio que encerram a gravação...
    const FRACAO_MINIMA_FALADA = 0.6; // ...depois de falar pelo menos esta fração do tempo esperado
    const SILENCIO_LONGO = 2.0;       // s de silêncio que encerram a gravação em qualquer momento
    const FOLGA_PROPORCIONAL = 1.5;
    const FOLGA_FIXA = 1.0;           // s
    const TOLERANCIA_RITMO = 0.15;    // até 15% de diferença conta como "no ritmo"
    const LARGURA_COLUNA = 3;         // px (em CSS) de cada barra da onda
    const MAX_FRASES_GUARDADAS = 30;
    const ESPERA_TRANSCRICAO = 600;   // ms: o reconhecimento entrega o resultado final logo depois de parar

    // Estado de cada frase: { chave, duracao, esperado, amostras: [[t, volume]], fala, transcricao, gravacao }
    const frases = new Map();
    let atual = null;

    let estado = "parado";            // "parado" | "aguardando" | "gravando"
    let sessao = null;                // dados da gravação em andamento (ver iniciar)
    let animacao = null;
    let reconhecimento = null;
    let microfone = null;             // { stream, contexto, analisador, amostras }
    let reproducao = null;            // { fonte, inicio, animacao }
    const OPCOES_PADRAO = { velocidade: () => 1, aoReproduzir: null, avaliar: null, mostrarAvaliacao: () => {} };
    let opcoes = { ...OPCOES_PADRAO };

    const elemento = (id) => document.getElementById(id);

    // "contexto" são os dados da frase que a página precisa para avaliar (vídeo, trecho, texto).
    function novoEstado(chave, duracao, contexto) {
        return {
            chave, duracao, contexto, esperado: duracao, amostras: [], fala: 0, transcricao: "",
            gravacao: null, avaliacao: null, // avaliacao: null | "avaliando" | "erro" | resultado do servidor
        };
    }

    // --- Troca de frase ---

    function prepararFrase(chave, duracao, contexto = null) {
        parar();
        pararReproducao();
        if (frases.has(chave)) {
            atual = frases.get(chave);
            frases.delete(chave); // reinsere no fim: o Map fica em ordem de uso
        } else {
            atual = novoEstado(chave, duracao, contexto);
        }
        frases.set(chave, atual);
        if (frases.size > MAX_FRASES_GUARDADAS) frases.delete(frases.keys().next().value);
        mostrarEstado();
    }

    function mostrarEstado() {
        // Frase ainda não gravada: o tempo esperado acompanha a velocidade atual do vídeo.
        if (!atual.fala) atual.esperado = atual.duracao / opcoes.velocidade();
        ajustarCanvas();
        desenharOnda();
        atualizarTimer(atual.fala);
        mostrarTranscricao(atual.transcricao || "Fale algo...");
        atualizarBotaoOuvir();
        opcoes.mostrarAvaliacao(atual.avaliacao);
    }

    function mostrarTranscricao(texto) {
        const transcricao = elemento("transcript");
        if (transcricao) transcricao.textContent = texto;
    }

    // --- Microfone e reconhecimento ---

    function criarReconhecimento() {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) return null;
        const novo = new SpeechRecognition();
        novo.lang = "en-US";
        novo.interimResults = true;
        novo.continuous = true;
        return novo;
    }

    async function prepararMicrofone() {
        if (microfone) {
            await microfone.contexto.resume();
            return;
        }
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const contexto = new AudioContext();
        const analisador = contexto.createAnalyser();
        analisador.fftSize = 2048;
        contexto.createMediaStreamSource(stream).connect(analisador);
        microfone = { stream, contexto, analisador, amostras: new Float32Array(analisador.fftSize) };
    }

    function medirVolume() {
        microfone.analisador.getFloatTimeDomainData(microfone.amostras);
        let soma = 0;
        for (const amostra of microfone.amostras) soma += amostra * amostra;
        return Math.sqrt(soma / microfone.amostras.length);
    }

    // --- Gravação ---

    async function iniciar() {
        if (estado !== "parado" || !atual) return;

        reconhecimento ??= criarReconhecimento();
        if (!reconhecimento) {
            mostrarErro("O reconhecimento de voz não é suportado neste navegador. Use o Chrome ou o Edge.");
            return;
        }
        try {
            await prepararMicrofone();
        } catch {
            mostrarErro("Permita o uso do microfone no navegador.");
            return;
        }
        pararReproducao();

        // Grava por cima da tentativa anterior desta frase.
        const frase = atual;
        frase.esperado = frase.duracao / opcoes.velocidade();
        frase.amostras = [];
        frase.fala = 0;
        frase.transcricao = "";
        frase.gravacao = null;
        frase.avaliacao = null;

        sessao = {
            frase,
            inicioEspera: performance.now(),
            inicioFala: 0,
            ultimaVoz: 0,          // s desde o início da fala
            ruido: { soma: 0, quadros: 0 },
            limiar: LIMIAR_MINIMO,
            gravador: iniciarGravadorDeAudio(),
        };
        estado = "aguardando";
        elemento("gravar")?.classList.add("recording");
        mostrarEstado();
        mostrarTranscricao("Pode falar...");

        reconhecimento.onresult = (evento) => {
            frase.transcricao = Array.from(evento.results, (resultado) => resultado[0].transcript).join("");
            if (frase === atual) mostrarTranscricao(frase.transcricao);
        };
        try {
            // O reconhecimento começa já, para não perder a primeira palavra.
            reconhecimento.start();
        } catch {
            // Já estava rodando: segue normalmente.
        }
        animacao = requestAnimationFrame(quadro);
    }

    function quadro() {
        if (estado === "parado") return;
        const agora = performance.now();
        const volume = medirVolume();
        const { frase, ruido } = sessao;

        if (estado === "aguardando") {
            // Os primeiros quadros medem o ruído do ambiente; fala é algo bem acima dele.
            if (ruido.quadros < QUADROS_DE_RUIDO) {
                ruido.soma += volume;
                ruido.quadros++;
            } else if (volume > Math.max(LIMIAR_MINIMO, (ruido.soma / ruido.quadros) * 3)) {
                sessao.limiar = Math.max(LIMIAR_MINIMO * 0.75, (ruido.soma / ruido.quadros) * 2);
                sessao.inicioFala = Math.max(agora - PRE_INICIO * 1000, sessao.gravador?.inicio ?? 0);
                estado = "gravando";
            } else if ((agora - sessao.inicioEspera) / 1000 > ESPERA_MAXIMA) {
                parar();
                return;
            }
        }

        if (estado === "gravando") {
            const decorrido = (agora - sessao.inicioFala) / 1000;
            frase.amostras.push([decorrido, volume]);
            if (volume > sessao.limiar) sessao.ultimaVoz = decorrido;
            frase.fala = decorrido;
            desenharOnda();
            atualizarTimer(decorrido);

            const silencio = decorrido - sessao.ultimaVoz;
            const falouBoaParte = sessao.ultimaVoz >= frase.esperado * FRACAO_MINIMA_FALADA;
            const terminouDeFalar = silencio >= (falouBoaParte ? SILENCIO_FINAL : SILENCIO_LONGO);
            const passouDoLimite = decorrido >= frase.esperado * FOLGA_PROPORCIONAL + FOLGA_FIXA;
            if (terminouDeFalar || passouDoLimite) {
                parar();
                return;
            }
        }
        animacao = requestAnimationFrame(quadro);
    }

    function parar() {
        if (estado === "parado") return;
        const estavaAguardando = estado === "aguardando";
        const { frase } = sessao;
        estado = "parado";
        cancelAnimationFrame(animacao);
        elemento("gravar")?.classList.remove("recording");
        reconhecimento?.stop();

        if (!estavaAguardando) {
            // O silêncio do fim não conta como fala.
            frase.fala = Math.min(frase.fala, sessao.ultimaVoz + CAUDA);
            frase.amostras = frase.amostras.filter(([t]) => t <= frase.fala);
        }
        finalizarGravadorDeAudio(sessao, !estavaAguardando);
        sessao = null;

        if (frase !== atual) return;
        mostrarEstado();
        if (estavaAguardando) {
            mostrarTranscricao("Nenhuma voz detectada no microfone. Tente de novo.");
        } else if (!frase.transcricao) {
            mostrarTranscricao("Não foi possível reconhecer a fala. Tente de novo.");
        }
    }

    function alternar() {
        estado === "parado" ? iniciar() : parar();
    }

    // --- Áudio gravado (para ouvir depois) ---

    function iniciarGravadorDeAudio() {
        if (!window.MediaRecorder) return null;
        const recorder = new MediaRecorder(microfone.stream);
        const partes = [];
        recorder.ondataavailable = (evento) => evento.data.size && partes.push(evento.data);
        recorder.start();
        return { recorder, partes, inicio: performance.now() };
    }

    // Guarda só o trecho da fala (o mesmo da onda), na frase em que foi gravado.
    function finalizarGravadorDeAudio({ gravador, frase, inicioFala }, houveFala) {
        if (!gravador || gravador.recorder.state === "inactive") return;
        const { recorder, partes, inicio } = gravador;
        const offset = (inicioFala - inicio) / 1000;
        recorder.onstop = async () => {
            if (!houveFala || !microfone || frase.fala <= 0) return;
            try {
                const blob = new Blob(partes, { type: recorder.mimeType });
                const buffer = await microfone.contexto.decodeAudioData(await blob.arrayBuffer());
                frase.gravacao = { buffer, offset, duracao: frase.fala };
                if (frase === atual) atualizarBotaoOuvir();
                avaliarGravacao(frase, blob, offset);
            } catch (erro) {
                console.error("Não foi possível preparar a gravação para ouvir:", erro);
            }
        };
        recorder.stop();
    }

    function avaliarGravacao(frase, blob, offset) {
        if (!opcoes.avaliar || !frase.contexto) return;
        const avaliar = opcoes.avaliar;
        const gravacao = frase.gravacao;
        frase.avaliacao = "avaliando";
        if (frase === atual) opcoes.mostrarAvaliacao(frase.avaliacao);

        setTimeout(async () => {
            let resultado;
            try {
                resultado = await avaliar({
                    contexto: frase.contexto,
                    gravacao: blob,
                    offset,
                    duracao: frase.fala,
                    transcricao: frase.transcricao,
                    velocidade: frase.duracao / frase.esperado,
                });
            } catch (erro) {
                console.error("Erro ao avaliar a fala:", erro);
                resultado = "erro";
            }
            // Se o usuário gravou de novo nesse meio-tempo, este resultado é de uma tentativa velha.
            if (frase.gravacao !== gravacao) return;
            frase.avaliacao = resultado;
            if (frase === atual) opcoes.mostrarAvaliacao(resultado);
        }, ESPERA_TRANSCRICAO);
    }

    function atualizarBotaoOuvir() {
        const botao = elemento("ouvirGravacao");
        if (!botao) return;
        botao.disabled = !atual?.gravacao;
        botao.title = reproducao ? "Parar" : "Ouvir minha gravação";
        botao.querySelector("i").className = reproducao ? "fa fa-stop" : "fa fa-play";
        botao.classList.toggle("tocando", Boolean(reproducao));
    }

    function reproduzir() {
        if (reproducao) {
            pararReproducao();
            return;
        }
        const gravacao = atual?.gravacao;
        if (!gravacao || estado !== "parado") return;

        const contexto = microfone.contexto;
        contexto.resume();
        const fonte = contexto.createBufferSource();
        fonte.buffer = gravacao.buffer;
        fonte.connect(contexto.destination);
        fonte.onended = () => reproducao?.fonte === fonte && pararReproducao();
        fonte.start(0, Math.max(0, gravacao.offset), gravacao.duracao);

        reproducao = { fonte, inicio: contexto.currentTime, animacao: null };
        opcoes.aoReproduzir?.(true);
        atualizarBotaoOuvir();

        const animar = () => {
            if (!reproducao) return;
            const decorrido = Math.min(contexto.currentTime - reproducao.inicio, gravacao.duracao);
            desenharOnda(decorrido);
            atualizarTimer(decorrido);
            reproducao.animacao = requestAnimationFrame(animar);
        };
        animar();
    }

    function pararReproducao() {
        if (!reproducao) return;
        const { fonte, animacao: quadroReproducao } = reproducao;
        reproducao = null;
        cancelAnimationFrame(quadroReproducao);
        try {
            fonte.stop();
        } catch {}
        if (atual) {
            desenharOnda();
            atualizarTimer(atual.fala);
        }
        atualizarBotaoOuvir();
        opcoes.aoReproduzir?.(false);
    }

    // --- Desenho e timer ---

    // Faz o canvas ter a resolução real da tela (o tamanho visível vem do CSS).
    function ajustarCanvas() {
        const canvas = elemento("wave");
        if (!canvas) return;
        const escala = window.devicePixelRatio || 1;
        canvas.width = Math.round(canvas.clientWidth * escala);
        canvas.height = Math.round(canvas.clientHeight * escala);
    }

    // Segundos que cabem na largura: o tempo esperado, ou mais se a fala passou dele.
    const escalaDeTempo = () => Math.max(atual.esperado, atual.fala) || 1;

    // "cursor" = segundos já tocados da gravação (durante a reprodução).
    function desenharOnda(cursor = null) {
        const canvas = elemento("wave");
        if (!canvas || !atual) return;
        const ctx = canvas.getContext("2d");
        const { width: largura, height: altura } = canvas;
        const centro = altura / 2;
        const dpr = window.devicePixelRatio || 1;
        const escala = escalaDeTempo();
        ctx.clearRect(0, 0, largura, altura);

        ctx.strokeStyle = "rgba(128,128,128,0.3)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(0, centro);
        ctx.lineTo(largura, centro);
        ctx.stroke();

        // Cada coluna mostra o maior volume do intervalo de tempo que ela cobre.
        const colunas = new Array(Math.max(1, Math.floor(canvas.clientWidth / LARGURA_COLUNA))).fill(null);
        for (const [t, volume] of atual.amostras) {
            const i = Math.min(colunas.length - 1, Math.floor((t / escala) * colunas.length));
            colunas[i] = Math.max(colunas[i] ?? 0, volume);
        }
        const larguraColuna = largura / colunas.length;
        let anterior = 0;
        colunas.forEach((volume, i) => {
            if (i * larguraColuna > (atual.fala / escala) * largura) return;
            // Coluna sem amostra (frame atrasado) repete a anterior.
            const valor = volume ?? anterior;
            anterior = valor;
            const tocada = cursor !== null && (i / colunas.length) * escala <= cursor;
            ctx.fillStyle = cursor === null ? "#3b82f6" : tocada ? "#2563eb" : "#93c5fd";
            const barra = Math.max(2, Math.min(1, valor * 6) * altura);
            ctx.fillRect(i * larguraColuna, centro - barra / 2, Math.max(1, larguraColuna - 1), barra);
        });

        // A fala passou do tempo esperado: marca onde o original termina.
        if (atual.fala > atual.esperado) {
            const x = (atual.esperado / escala) * largura;
            ctx.strokeStyle = "rgba(250, 204, 21, 0.9)";
            ctx.lineWidth = 2 * dpr;
            ctx.setLineDash([6 * dpr, 4 * dpr]);
            ctx.beginPath();
            ctx.moveTo(x, 0);
            ctx.lineTo(x, altura);
            ctx.stroke();
            ctx.setLineDash([]);
        }

        if (cursor !== null) {
            ctx.fillStyle = "#e74c3c";
            ctx.fillRect((cursor / escala) * largura - dpr, 0, 2 * dpr, altura);
        }
    }

    function descricaoDoRitmo() {
        if (estado !== "parado" || !atual.fala) return "";
        const diferenca = atual.fala / atual.esperado - 1;
        if (Math.abs(diferenca) <= TOLERANCIA_RITMO) return " · no ritmo ✓";
        const porcentagem = Math.round(Math.abs(diferenca) * 100);
        return diferenca > 0 ? ` · ${porcentagem}% mais lenta` : ` · ${porcentagem}% mais rápida`;
    }

    function atualizarTimer(decorrido) {
        const progresso = elemento("timerProgress");
        const texto = elemento("timerTexto");
        if (!atual) return;
        if (progresso) progresso.style.width = `${Math.min(decorrido / atual.esperado, 1) * 100}%`;
        if (texto) {
            const ritmo = reproducao ? "" : descricaoDoRitmo();
            texto.textContent = `${decorrido.toFixed(1)}s / ${atual.esperado.toFixed(1)}s${ritmo}`;
        }
    }

    // Libera o microfone (apaga o indicador de gravação do navegador) e esquece as frases ao sair da página.
    function encerrar() {
        parar();
        pararReproducao();
        microfone?.stream.getTracks().forEach((faixa) => faixa.stop());
        microfone?.contexto.close();
        microfone = null;
        frases.clear();
        atual = null;
        opcoes = { ...OPCOES_PADRAO };
    }

    return {
        // velocidade(): velocidade atual do vídeo; aoReproduzir(tocando): a página pausa o vídeo enquanto
        // o usuário ouve a própria gravação; avaliar(dados): Promise com a avaliação da gravação;
        // mostrarAvaliacao(avaliacao): exibe a avaliação da frase atual.
        configurar: (novasOpcoes) => { opcoes = { ...opcoes, ...novasOpcoes }; },
        prepararFrase,
        alternar,
        reproduzir,
        encerrar,
    };
})();
