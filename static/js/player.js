// CODIGO YOUTUBE PLAYER

// [MANTIDO]: As variáveis globais e controle de tempo originais foram mantidas.
let player, loopRAF;
let startTime = 0, endTime = 0; 
let currentVideoId;
let isPaused = false;

function handleLoadVideo() {
    const link = document.getElementById("youtubeLink").value;
    const id = extractVideoId(link);
    currentVideoId = id;
    loadVideo(id);
}

// [MANTIDO]: Excelente uso de Regex e URL API para extrair o ID.
function extractVideoId(url) {
    try {
        const u = new URL(url);
        return u.searchParams.get("v") || u.pathname.split("/").pop();
    } catch {
        return null;
    }
}

function loadVideo(videoId) {
    // [NOVO]: Solução para o bug do HTMX ("cueVideoById is not a function").
    // O HTMX destrói o HTML antigo, mas o JS mantinha o player fantasma na memória.
    // Passo 1: Verifica se o player existe e está com as funções carregadas.
    if (player && typeof player.cueVideoById === 'function') {
        try {
            // Passo 2: Pega o iframe gerado pelo YouTube.
            const iframe = player.getIframe();
            
            // Passo 3: Verifica se o iframe AINDA está grudado na tela atual (document.body).
            if (document.body.contains(iframe)) {
                player.cueVideoById({ videoId, startSeconds: startTime });
                return; // Tudo certo, reaproveita o player sem recarregar!
            }
        } catch (error) {
            console.log("Player antigo perdido na transição do HTMX. Recriando...");
        }
    }

    // [NOVO]: Se o iframe sumiu (porque mudou de página), criamos um player do zero na nova div.
    player = new YT.Player("player", {
        videoId,
        events: { onReady: onReady }
    });
}

function onReady() {
    player.cueVideoById({
        videoId: currentVideoId,
        startSeconds: startTime
    });

    //MUDANÇA MEMBRO 1:SAIR DO CARREGAMENTO E LIBERAR BOTÃO QUANDO PRONTO
    document.getElementById('carregamento').style.display = "none"; 
    //Debloquear Botão
    document.getElementById('protecaoButton').style.background='linear-gradient(90deg, #818cf8, #c084fc)';
    document.getElementById('protecaoButton').disabled=false;
}

// [MANTIDO]: Toda a lógica de play, pause e loop via requestAnimationFrame
function playVideo() {
    player.seekTo(startTime, true);
    player.playVideo();
    startLoop();
}

function togglePause() {
    if (!player) return;

    const btn = document.getElementById("toggleBtn");

    if (!isPaused) {
        player.pauseVideo();
        stopLoop();
        if(btn) btn.innerText = "Continuar";
    } else {
        player.playVideo();
        startLoop();
        if(btn) btn.innerText = "Pause";
    }

    isPaused = !isPaused;
}

function startLoop() {
    function check() {
        let t = player.getCurrentTime();
        if (t >= endTime - 0.05) {
            player.seekTo(startTime, true);
        }
        loopRAF = requestAnimationFrame(check);
    }
    check();
}

function stopLoop() {
    cancelAnimationFrame(loopRAF);
}