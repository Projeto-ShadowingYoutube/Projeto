
let blocosDeEstudo = [];  // guarda o JSON com as frases 
let blocoAtualIndex = 0;  // qual frase o usuário está no momento

//  INICIAR SESSÃO

async function iniciarSessao(youtubeLink) {
    try {
        
        // tela carregamento na legenda
        let carregamento=document.getElementById('carregamento')
        carregamento.style.display="flex";
        // if (legendaDiv) legendaDiv.innerText = "Extraindo legendas do vídeo... Isso pode levar alguns segundos.";

        // Chama a API que pega a legenda
        const legendaDiv = document.getElementById('legenda');

        const resposta = await fetch(`/api/legenda?url=${encodeURIComponent(youtubeLink)}`);
        
        carregamento.style.display = "none";

        const jsonResponse = await resposta.json(); // Aqui recebemos o objeto completo
        
        if (!resposta.ok) { //aqui podemos colocar mensagem de erro diferente (MEMBRO 1)
            // Se der erro (como o 429), tentamos atualizar os tokens se o servidor enviou
            if (jsonResponse.tokens_restantes !== undefined) {
                atualizarInterfaceTokens(jsonResponse.tokens_restantes);
            }
            const erroData = await resposta.json();
            throw new Error(erroData.detail || "Erro ao carregar legenda. Verifique se o vídeo possui legendas manuais em inglês.");
        }

        // salva a lista de frases no estado global e zera o contador

        // ATENÇÃO AQUI
        // Antigamente 'jsonResponse' era a lista direta. 
        // Agora a lista está em 'jsonResponse.dados'
        blocosDeEstudo = jsonResponse.dados;
        
        // Atualizamos o contador na tela
        atualizarInterfaceTokens(jsonResponse.tokens_restantes);
        
        blocoAtualIndex = 0;
        currentVideoId = extractVideoId(youtubeLink); 
        
        carregarFraseAtual();
        loadVideo(currentVideoId);

    } catch (erro) {
        //modal do Erro
        const erroModal=document.getElementById('erroModal');
        const erroText=document.getElementById('erro');
        if(erroModal) {
            erroText.innerText=erro.message;
            erroModal.style.display="block";
        }
        console.error("Falha na integração:", erro);
    }
}

// Função auxiliar para atualizar os tokens (semana 2 membro 2)
function atualizarInterfaceTokens(valor) {
    // Salva na memória do navegador para a Home consultar depois
    localStorage.setItem('tokens_restantes', valor);

    // Atualiza o elemento visual se ele existir na página atual
    const el = document.getElementById('token-count');
    if (el) {
        el.innerText = valor;
        
        // Troca a cor se chegar a zero
        if (parseInt(valor) === 0) {
            el.classList.add('token-low'); // Usando a classe CSS que sugerimos antes
        } else {
            el.classList.remove('token-low');
        }
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

    //botão de erro
    if(event.target.id==='botaoErro'){
        document.getElementById('erroModal').style.display = "none";
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