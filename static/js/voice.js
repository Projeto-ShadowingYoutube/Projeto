// VARIÁVEIS GLOBAIS DE RECONHECIMENTO E ÁUDIO
let recognition;
let audioCtx, analyser, dataArray;
let isRecording = false;

// VARIÁVEIS DE CONTROLE DE TEMPO E WAVEFORM 
let recordingStartTime = null;
let recordingLimit = null;
let timerAnimation = null;
let waveformHistory = [];

function initSpeech() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SR) {
        // Modal de Erro global
        const erroModal = document.getElementById("erroModal"); 
        const erroText = document.getElementById("erro");
        if (erroModal && erroText) {
            erroText.innerText = "Speech API não suportada neste navegador.";
            erroModal.style.display = "block";
        }
        return;
    }

    recognition = new SR();
    recognition.lang = "en-US";
    recognition.interimResults = true;
    recognition.continuous = true;

    recognition.onresult = e => {
        let text = "";
        for (let i = e.resultIndex; i < e.results.length; i++) {
            text += e.results[i][0].transcript;
        }

        const transcript = document.getElementById("transcript");
        if (transcript) {
            transcript.innerText = text;
        }
    };

    recognition.onend = () => {};
}

async function initAudio() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

    audioCtx = new AudioContext();
    analyser = audioCtx.createAnalyser();
    analyser.fftSize = 2048;
    analyser.smoothingTimeConstant = 0.85;

    const src = audioCtx.createMediaStreamSource(stream);
    src.connect(analyser);

    dataArray = new Uint8Array(analyser.fftSize);
}

// =========================================================================
// TIMERS 
// =========================================================================

function calcularLimiteDeTempo() {
    const duracaoBase = endTime - startTime;
    return duracaoBase + 0.7; // 0.7s de margem
}

function ajustarLarguraWaveMicrofone(totalSeconds) {
    const canvas = document.getElementById("wave");
    if (!canvas) return 700;

    const pxPerSec = window.WAVE_PX_PER_SEC || WAVE_PX_PER_SEC;
    const largura = Math.max(700, Math.ceil(totalSeconds * pxPerSec));
    
    canvas.width = largura;
    canvas.style.width = `${largura}px`;

    return largura;
}

function iniciarTimerVisual() {
    const progress = document.getElementById("timerProgress");
    const texto = document.getElementById("timerTexto");

    function atualizar() {
        if (!isRecording) return;

        const agora = performance.now();
        const elapsed = (agora - recordingStartTime) / 1000;
        const porcentagem = Math.min((elapsed / recordingLimit) * 100, 100);

        if (progress) progress.style.width = `${porcentagem}%`;
        if (texto) texto.innerText = `${elapsed.toFixed(1)}s / ${recordingLimit.toFixed(1)}s`;

        // Parada automática exata ao invés de depender de "Silêncio"
        if (elapsed >= recordingLimit) {
            stopRecording();
            return;
        }

        timerAnimation = requestAnimationFrame(atualizar);
    }

    atualizar();
}

function resetarTimerVisual() {
    const progress = document.getElementById("timerProgress");
    const texto = document.getElementById("timerTexto");

    if (progress) progress.style.width = "0%";
    if (texto) texto.innerText = "0.0s / 0.0s";
}

// =========================================================================
// RENDERIZAÇÃO DA WAVE (Com Histórico e Grade visual)
// =========================================================================

function drawWave() {
    const canvas = document.getElementById("wave");
    if (!canvas || !analyser) return;

    const ctx = canvas.getContext("2d");
    analyser.getByteTimeDomainData(dataArray);

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Fundo transparente para Dark Mode/Light Mode
    ctx.fillStyle = "transparent";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Grade horizontal sutil
    ctx.strokeStyle = "rgba(128,128,128,0.15)";
    ctx.lineWidth = 1;
    for (let y = 20; y < canvas.height; y += 20) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(canvas.width, y);
        ctx.stroke();
    }

    ctx.strokeStyle = "rgba(128,128,128,0.3)";
    ctx.beginPath();
    ctx.moveTo(0, canvas.height / 2);
    ctx.lineTo(canvas.width, canvas.height / 2);
    ctx.stroke();

    let sum = 0;

    for (let i = 0; i < dataArray.length; i++) {
        const v = dataArray[i] / 128.0;
        sum += Math.abs(v - 1);
    }

    const volume = sum / dataArray.length;

    waveformHistory.push(volume);

    const maxWavePoints = Math.max(220, Math.floor(canvas.width / 4));
    if (waveformHistory.length > maxWavePoints) {
        waveformHistory.shift();
    }

    const centerY = canvas.height / 2;
    const stepX = canvas.width / maxWavePoints;

    waveformHistory.forEach((amp, i) => {
        const x = i * stepX;
        const amplitude = Math.max(2, amp * 420);

        // Sombra azul clara
        ctx.fillStyle = "rgba(59,130,246,0.18)";
        ctx.fillRect(x, centerY - amplitude / 2, 4, amplitude);

        // Miolo azul forte
        ctx.fillStyle = "#3b82f6";
        ctx.fillRect(x, centerY - amplitude / 2, 2, amplitude);
    });

    if (isRecording) {
        requestAnimationFrame(drawWave);
    }
}

// =========================================================================
// CONTROLE DE MICROFONE
// =========================================================================

function startRecording() {
    if (isRecording) return;

    // NOVA visibilidade dos elementos 
    const wave = document.getElementById("wave");
    const transcript = document.getElementById("transcript");
    const micBtn = document.getElementById("gravar");

    if (transcript) {
        transcript.innerText = "Listening...";
    }

    if (!recognition) initSpeech();

    initAudio().then(() => {
        waveformHistory = [];

        isRecording = true;
        recordingLimit = calcularLimiteDeTempo();
        recordingStartTime = performance.now();
        
        ajustarLarguraWaveMicrofone(recordingLimit);
        resetarTimerVisual();

        if (micBtn) micBtn.classList.add("recording");

        recognition.start();
        iniciarTimerVisual();
        drawWave();
    }).catch((err) => {
        //  de erro caso o usuário negue permissão de microfone
        const erroModal = document.getElementById('erroModal');
        const erroText = document.getElementById('erro');
        if(erroModal && erroText) {
            erroText.innerText = "Erro: Permita o uso do microfone no navegador.";
            erroModal.style.display = "block";
        }
    });
}

function stopRecording() {
    isRecording = false;

    const micBtn = document.getElementById("gravar");
    if (micBtn) micBtn.classList.remove("recording");

    if (recognition) recognition.stop();

    if (timerAnimation) {
        cancelAnimationFrame(timerAnimation);
        timerAnimation = null;
    }
}