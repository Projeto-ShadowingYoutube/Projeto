// [MANTIDO]: A lógica avançada da API de Web Speech,
// o processamento de áudio via AudioContext e a detecção de silêncio (SILENCE_DELAY)
// foram mantidos intactos.

let recognition;
let audioCtx, analyser, dataArray;
let isRecording = false;
let silenceTimer = null;

const SILENCE_DELAY = 1200;

function initSpeech() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
        // [NOVO - MELHORIA IA]: Integração do erro de Speech API com os modais de erro visuais.
        const erroModal = document.getElementById('erroMicModal');
        const erroText = document.getElementById('erroMic');
        if(erroModal) {
            erroText.innerText="Speech API não suportada neste navegador.";
            erroModal.style.display="block";
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
        
        // [NOVO - MELHORIA IA]: Busca dinâmica do elemento para evitar o erro de elemento nulo do HTMX.
        const transcript = document.getElementById("transcript");
        if (transcript) transcript.innerText = text;
    };

    recognition.onend = () => {};
}

async function initAudio() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioCtx = new AudioContext();
    analyser = audioCtx.createAnalyser();
    const src = audioCtx.createMediaStreamSource(stream);
    src.connect(analyser);
    dataArray = new Uint8Array(analyser.fftSize);
}

function drawWave() {
    // [NOVO]: Puxa o canvas dinamicamente a cada frame. 
    // Como o HTMX recria o HTML, usar uma variável global para o Canvas faria a animação parar.
    const canvas = document.getElementById("wave");
    if (!canvas) return; 
    
    const ctx = canvas.getContext("2d");
    analyser.getByteTimeDomainData(dataArray);

    ctx.fillStyle = "#ffffff"; // [NOVO]: Fundo branco/transparente adaptado ao tema
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    ctx.beginPath();
    let slice = canvas.width / dataArray.length;
    let x = 0;
    let sum = 0;

    for (let i = 0; i < dataArray.length; i++) {
        let v = dataArray[i] / 128;
        let y = (v - 1) * canvas.height / 2 + canvas.height / 2;
        sum += Math.abs(v - 1);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
        x += slice;
    }

    ctx.strokeStyle = "#3b82f6"; // Azul bonito para a onda
    ctx.lineWidth = 2;
    ctx.stroke();

    let volume = sum / dataArray.length;
    if (volume < 0.01) {
        if (!silenceTimer) {
            silenceTimer = setTimeout(() => {
                stopRecording();
            }, SILENCE_DELAY);
        }
    } else {
        if (silenceTimer) {
            clearTimeout(silenceTimer);
            silenceTimer = null;
        }
    }

    if (isRecording) requestAnimationFrame(drawWave);
}

function startRecording() {
    if (isRecording) return;
    
    // [NOVO]: É AQUI que revelamos a Onda e a caixa de Transcrição
    // que estavam escondidas. Elas aparecem instantaneamente ao clicar no microfone vermelho.
    const wave = document.getElementById("wave");
    const transcript = document.getElementById("transcript");
    const micBtn = document.getElementById("gravar");

    if (wave) wave.style.display = "block"; 
    if (transcript) {
        transcript.style.display = "block"; 
        transcript.innerText = "Listening...";
    }

    if (!recognition) initSpeech();

    initAudio().then(() => {
        isRecording = true;
        if (micBtn) micBtn.classList.add("recording");
        recognition.start();
        drawWave();
    }).catch((err) => {
        const erroModal = document.getElementById('erroModal');
        const erroText = document.getElementById('erro');
        if(erroModal) {
            erroText.innerText="Erro: Permita o uso do microfone no navegador.";
            erroModal.style.display="block";
        }
    });
}

function stopRecording() {
    isRecording = false;
    const micBtn = document.getElementById("gravar");
    if (micBtn) micBtn.classList.remove("recording");
    if (recognition) recognition.stop();
    if (silenceTimer) {
        clearTimeout(silenceTimer);
        silenceTimer = null;
    }
}