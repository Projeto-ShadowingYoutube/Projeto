
let blocosDeEstudo = [];  // guarda o JSON com as frases 
let blocoAtualIndex = 0;  // qual frase o usuário está no momento

//  INICIAR SESSÃO

async function iniciarSessao(youtubeLink) {
    try {
        // tela carregamento na legenda
        const legendaDiv = document.getElementById('legenda');
        if (legendaDiv) legendaDiv.innerText = "Extraindo legendas do vídeo... Isso pode levar alguns segundos.";

        // Chama a API que pega a legenda
        const resposta = await fetch(`/api/legenda?url=${encodeURIComponent(youtubeLink)}`);
        
        if (!resposta.ok) { //aqui podemos colocar mensagem de erro diferente (MEMBRO 1)
            const erroData = await resposta.json();
            throw new Error(erroData.detail || "Erro ao carregar legenda. Verifique se o vídeo possui legendas manuais em inglês.");
        }

        // salva a lista de frases no estado global e zera o contador
        blocosDeEstudo = await resposta.json();
        blocoAtualIndex = 0;
        currentVideoId = extractVideoId(youtubeLink); 
        // legenda na tela
        carregarFraseAtual();
        //  comeca looping no video
        loadVideo(currentVideoId);

    } catch (erro) {
        const legendaDiv = document.getElementById('legenda');
        if (legendaDiv) legendaDiv.innerText = erro.message;
        console.error("Falha na integração:", erro);
    }
}

//  TELA E VÍDEO
function carregarFraseAtual() {
    // PRECISA TEM DADO AQUI se nao não faz nada
    if (!blocosDeEstudo || blocosDeEstudo.length === 0) return;

    // Pega o bloco
    const bloco = blocosDeEstudo[blocoAtualIndex];

    // Atualiza o texto legenda
    const legendaDiv = document.getElementById('legenda');
    if (legendaDiv) legendaDiv.innerText = bloco.texto_limpo;

    // Atualiza os tempos de corte para o looping
    startTime = bloco.tempo_inicio; //esta em voice.js
    endTime = bloco.tempo_fim; //esta em voice.js

    // Reseta gravação
    const panel = document.getElementById("panel");
    const transcript = document.getElementById("transcript");
    if (panel) panel.classList.add("hidden");
    if (transcript) transcript.innerText = "Fale algo...";

    // looping das partes
    if (player && typeof player.seekTo === 'function') {
        player.seekTo(startTime, true);
        player.playVideo();
        startLoop();
    }
}

// BOTÕES
document.addEventListener('click', function(event) {
    //protecaoPlayer
    if (event.target.id === 'protecaoButton') {
        document.getElementById('protecaoPlayer').style.display = "none";
        blocoAtualIndex++;
        carregarFraseAtual();
    }
    
    // Próxima Frase
    if (event.target.id === 'proximo') {
        if (blocoAtualIndex < blocosDeEstudo.length - 1) {
            blocoAtualIndex++;
            carregarFraseAtual();
        }
    }
    
    //Frase Anterior
    if (event.target.id === 'anterior') {
        if (blocoAtualIndex > 0) {
            blocoAtualIndex--;
            carregarFraseAtual();
        }
    }
    //salvar pro anki vai ficar aqui 
});