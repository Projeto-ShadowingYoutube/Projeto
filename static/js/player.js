// CODIGO YOUTUBE PLAYER

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

function extractVideoId(url) {
    try {
        const u = new URL(url);
        return u.searchParams.get("v") || u.pathname.split("/").pop();
    } catch {
        return null;
    }
}

function loadVideo(videoId) {
    // 1. Verifica se o player existe na memória E já carregou suas funções
    if (player && typeof player.cueVideoById === 'function') {
        try {
            // 2. Pega o elemento HTML (iframe) do player antigo
            const iframe = player.getIframe();
            
            // 3. Verifica se o HTMX NÃO apagou o iframe da tela
            if (document.body.contains(iframe)) {
                player.cueVideoById({ videoId, startSeconds: startTime });
                return; // Tudo certo, reaproveitamos o player e encerramos a função!
            }
        } catch (error) {
            console.log("Player antigo perdido na transição. Recriando...");
        }
    }

    // 4. Se chegou aqui, é porque o HTMX recarregou a página 2 e o HTML antigo sumiu,
    // ou o player deu erro na tentativa anterior. Criamos um zero bala!
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
}

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