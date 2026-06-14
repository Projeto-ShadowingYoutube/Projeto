// CODIGO YOUTUBE PLAYER

let player;
let loopRAF;

let startTime = 0;
let endTime = 0;

let currentVideoId;
let isPaused = false;

let playerReadyResolve = null;
let playerReadyPromise = Promise.resolve();

function handleLoadVideo() {
    const link = document.getElementById("youtubeLink").value;
    const id = extractVideoId(link);

    currentVideoId = id;
    loadVideo(id);
}

function extractVideoId(url) {
    try {
        const u = new URL(url);
        return u.searchParams.get("v") || u.pathname.split("/").pop();
    } catch {
        return null;
    }
}

function loadVideo(videoId) {
    // bug do HTMX ("cueVideoById is not a function"). O HTMX destrói o HTML antigo, mas o JS mantinha o player fantasma na memória.
    if (player && typeof player.cueVideoById === 'function') {
        try {
            const iframe = player.getIframe();
            if (document.body.contains(iframe)) {
                // Reaproveita o player sem recarregar!
                player.loadVideoById(videoId); 
                playerReadyPromise = Promise.resolve();
                return;
            }
        } catch (error) {
            console.log("Player antigo perdido na transição do HTMX. Recriando...");
        }
    }

    playerReadyPromise = new Promise(resolve => {
        playerReadyResolve = resolve;
    });

    player = new YT.Player("player", {
        videoId,
        events: {
            onReady: onReady,
            onError: onPlayerError
        }
    });
}

function onReady() {
    if (playerReadyResolve) {
        playerReadyResolve();
        playerReadyResolve = null;
    }

    if (currentVideoId) {
        player.cueVideoById({
            videoId: currentVideoId,
            startSeconds: startTime
        });
    }
    // MEMBRO 1: Mudança para não retirar a tela de carregamento assim que o vídeo está pronto 
    // const carregamento = document.getElementById('carregamento');
    

    // if (carregamento) carregamento.style.display = "none";
    const protecaoButton = document.getElementById('protecaoButton');
    if (protecaoButton) {
        protecaoButton.style.background = 'linear-gradient(90deg, #818cf8, #c084fc)';
        protecaoButton.disabled = false;
    }
}

function onPlayerError(e) {
    console.error("Erro no player do YouTube:", e);
}


function aguardarPlayerPronto() {
    return playerReadyPromise;
}

function playVideo() {
    if (!player) return;

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
        if (btn) btn.innerText = "Continuar";
    } else {
        player.playVideo();
        startLoop();
        if (btn) btn.innerText = "Pause";
    }

    isPaused = !isPaused;
}

function startLoop() {
    // Para um possível loop rodando antes de começar outro
    stopLoop();

    function check() {
        if (!player || typeof player.getCurrentTime !== "function") return;

        const currentTime = player.getCurrentTime();

        if (typeof atualizarWaveCursor === "function") {
            atualizarWaveCursor(currentTime);
        }

        // Loop da frase do vídeo
        if (currentTime >= endTime - 0.05) {
            player.seekTo(startTime, true);
        }

        loopRAF = requestAnimationFrame(check);
    }

    check();
}

function stopLoop() {
    if (loopRAF) {
        cancelAnimationFrame(loopRAF);
        loopRAF = null;
    }
}