var WAVE_PX_PER_SEC = 100;

window.WAVE_PX_PER_SEC = WAVE_PX_PER_SEC;

var wavesurfer = null;
var waveformLoadToken = 0;
var currentWaveformLimitSeconds = 0;
var wavesurferDecodificado = false;

function calcularLarguraWaveform(totalSeconds) {
    return Math.max(700, Math.ceil(totalSeconds * WAVE_PX_PER_SEC));
}

function prepararWaveformContainer(totalSeconds) {
    currentWaveformLimitSeconds = totalSeconds;
}

function garantirCursorWaveform() {
    var cursor = document.getElementById("waveCursor");
    if (!cursor) {
        cursor = document.createElement("div");
        cursor.id = "waveCursor";
    }
    return cursor;
}

function atualizarWaveCursor(currentTime) {
    var cursor = document.getElementById("waveCursor");
    if (!cursor) return;

    var total = currentWaveformLimitSeconds || Math.max(0.1, endTime - startTime);
    var elapsed = Math.max(0, Math.min(total, currentTime - startTime));
    var pct = total > 0 ? (elapsed / total) * 100 : 0;

    cursor.style.left = `${Math.max(0, Math.min(100, pct))}%`;

    if (wavesurfer && wavesurferDecodificado && typeof wavesurfer.setTime === "function") {
        var duration = wavesurfer.getDuration();
        if (Number.isFinite(duration) && duration > 0 && Number.isFinite(elapsed)) {
            try { 
                wavesurfer.setTime(elapsed);             
            } catch (e) {
                // WaveSurfer ainda inicializando internamente, ignora
            }
        }
    }
}
//alterei essa funcao pra deixar ela insta
async function carregarWaveform(url, totalSeconds = null) {
    var token = ++waveformLoadToken;

    try {
        // A MÁGICA DO NO-FLICKER:
        // 1. Baixamos o novo áudio ANTES de apagar a onda antiga.
        var resposta = await fetch(url);
        if (!resposta.ok) throw new Error("Erro na rede ao buscar áudio.");
        
        var blob = await resposta.blob();
        if (blob.size < 100) console.error("⚠️ ALERTA: Áudio gerado vazio (0 bytes).");
        var blobUrl = URL.createObjectURL(blob);

        // Se o usuário clicou muito rápido em "Próximo", abortamos a renderização velha
        if (token !== waveformLoadToken) return;

        // 2. SÓ AGORA (quando o áudio novo já está pronto) apagamos a onda antiga.
        // Isso faz com que a troca seja instantânea!
        if (wavesurfer) {
            wavesurferDecodificado = false;
            try { await wavesurfer.destroy(); } catch (e) {}
            wavesurfer = null;
        }

        var paiContainer = document.getElementById("waveformContainer");
        if (!paiContainer) throw new Error("Container pai não encontrado.");

        paiContainer.innerHTML = "";

        var novaDivWave = document.createElement("div");
        novaDivWave.id = "waveform";
        novaDivWave.style.width = "100%";
        novaDivWave.style.height = "140px";
        paiContainer.appendChild(novaDivWave);

        paiContainer.style.position = "relative";
        paiContainer.appendChild(garantirCursorWaveform());

        // 3. Renderiza a onda nova
        wavesurfer = WaveSurfer.create({
            container: novaDivWave,
            waveColor: "#93c5fd",
            progressColor: "#2563eb",
            cursorColor: "transparent",
            cursorWidth: 1,
            barWidth: 2,
            barGap: 1,
            barRadius: 2,
            height: 140,
            normalize: true
        });

        return await new Promise((resolve, reject) => {
            var settled = false;
            var finish = (result) => {
                if (settled) return; settled = true;
                if (token !== waveformLoadToken) return;
                resolve(result);
            };
            var fail = (err) => {
                if (settled) return; settled = true;
                if (token !== waveformLoadToken) return;
                reject(err);
            };

            wavesurfer.on("ready", () => {
                if (token !== waveformLoadToken) return;
                currentWaveformLimitSeconds = wavesurfer.getDuration();
                wavesurferDecodificado = true;
                finish(wavesurfer);
            });

            wavesurfer.on("error", (err) => {
                fail(err);
            });

            wavesurfer.load(blobUrl); 
        });

    } catch (err) {
        console.error("ERRO AO CARREGAR WAVEFORM:", err);
        throw err;
    }
}

window.calcularLarguraWaveform = calcularLarguraWaveform;
window.prepararWaveformContainer = prepararWaveformContainer;
window.atualizarWaveCursor = atualizarWaveCursor;
window.carregarWaveform = carregarWaveform;