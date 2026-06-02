let blocosDeEstudo = []; // guarda o JSON com as frases 
let blocoAtualIndex = 0; // qual frase o usuário está no momento
currentVideoTitle = "Vídeo do Youtube"; // O título do vídeo do Youtube. Por padrão, deixarei ela inicialmente como essa string.
currentVideoId = ""; // O ID do vídeo.
startTime = 0; // O tempo de início da legenda.
endTime = 0; // O tempo de fim da legenda.


function mostrarCarregamento(mensagem) {
    const carregamento = document.getElementById("carregamento");
    const texto = document.getElementById("carregamentoTexto");
    if (texto && mensagem) texto.innerText = mensagem;
    if (carregamento) carregamento.style.display = "flex";
}

function esconderCarregamento() {
    const carregamento = document.getElementById("carregamento");
    if (carregamento) carregamento.style.display = "none";
}

async function iniciarSessao(youtubeLink) {
    try {
        const botaoIniciar = document.getElementById('protecaoButton');
        if (botaoIniciar) {
            botaoIniciar.style.background = "black";
            botaoIniciar.disabled = true;
        }

        // Aqui no início faz sentido ter a tela de carregamento!
        mostrarCarregamento("Extraindo legendas e preparando áudio...");

        const resposta = await fetch(`/api/legenda?url=${encodeURIComponent(youtubeLink)}`);
        const jsonResponse = await resposta.json();

        if (!resposta.ok) {
            if (jsonResponse.tokens_restantes !== undefined) {
                atualizarInterfaceTokens(jsonResponse.tokens_restantes);
            }
            throw new Error(jsonResponse.detail || "Erro ao carregar legenda.");
        }

        blocosDeEstudo = jsonResponse.dados;
        currentVideoTitle = jsonResponse.titulo_video;
        atualizarInterfaceTokens(jsonResponse.tokens_restantes);
        blocoAtualIndex = 0;
        currentVideoId = extractVideoId(youtubeLink);

        loadVideo(currentVideoId);

        let tentativas = 0;
        while (!document.getElementById("legenda") && tentativas < 50) {
            await new Promise(r => setTimeout(r, 100));
            tentativas++;
        }

        await carregarFraseAtual();

    } catch (erro) {
        const erroModal = document.getElementById("erroModal");
        const erroText = document.getElementById("erro");
        if (erroModal && erroText) {
            erroText.innerText = erro.message;
            erroModal.style.display = "block";
        }
        console.error("Falha na integração:", erro);
    } finally {
        esconderCarregamento();
    }
}

function atualizarInterfaceTokens(valor) {
    localStorage.setItem("tokens_restantes", valor);
    const el = document.getElementById("token-count");
    if (!el) return;
    el.innerText = valor;
    if (parseInt(valor) === 0) {
        el.classList.add("token-low");
    } else {
        el.classList.remove("token-low");
    }
}

async function carregarFraseAtual() {
    if (!blocosDeEstudo || blocosDeEstudo.length === 0) return;

    const bloco = blocosDeEstudo[blocoAtualIndex];

    const renderizarQuandoExistir = () => {
        const legendaDiv = document.getElementById("legenda");
        if (legendaDiv && typeof renderizarLegenda === "function") {
            renderizarLegenda(bloco.texto_limpo);
            return true;
        } else if (legendaDiv) {
            legendaDiv.innerText = bloco.texto_limpo;
            return true;
        }
        return false;
    };

    if (!renderizarQuandoExistir()) {
        await new Promise((resolve) => {
            const observer = new MutationObserver(() => {
                if (renderizarQuandoExistir()) {
                    observer.disconnect();
                    resolve();
                }
            });
            observer.observe(document.body, { childList: true, subtree: true });
            setTimeout(() => { observer.disconnect(); resolve(); }, 5000);
        });
    }

    const panel = document.getElementById("panel");
    const transcript = document.getElementById("transcript");

    if (panel) panel.classList.remove("hidden");

    startTime = bloco.tempo_inicio;
    endTime = bloco.tempo_fim;

    const tempoTotal = endTime - startTime;
    const link = new URLSearchParams(window.location.search).get("link");
    const audioURL = `/api/audio?url=${encodeURIComponent(link)}&inicio=${startTime}&fim=${endTime}`;

    if (transcript) {
        //transcript.style.display = "none"; tirei pra atualizar sem piscar
        transcript.innerText = "Fale algo...";
    }

    if (typeof resetarTimerVisual === "function") resetarTimerVisual();

    try {
        if (typeof carregarWaveform === "function") {
            await carregarWaveform(audioURL, tempoTotal);
        }

        if (typeof aguardarPlayerPronto === "function") {
            await aguardarPlayerPronto();
        }

        if (player && typeof player.seekTo === "function") {
            player.seekTo(startTime, true);
            player.playVideo();
            if (typeof startLoop === "function") startLoop();
        }

        // Continua fazendo o download silencioso das próximas 2 frases
        for (let i = blocoAtualIndex + 1; i <= blocoAtualIndex + 2; i++) {
            if (i >= blocosDeEstudo.length) continue;
            const prox = blocosDeEstudo[i];
            const proxURL = `/api/audio?url=${encodeURIComponent(link)}&inicio=${prox.tempo_inicio}&fim=${prox.tempo_fim}`;
            fetch(proxURL).catch(console.error);
        }
    } catch(e) {
        console.error(e);
    }
}

document.addEventListener("click", function(event) {
    if (event.target.id === "protecaoButton") {
        const overlay = document.getElementById("protecaoPlayer");
        if (overlay) overlay.style.display = "none";
    }

    if (event.target.id === "botaoErro") {
        const modal = document.getElementById("erroModal");
        if (modal) modal.style.display = "none";
    }

    if (event.target.id === "proximo") {
        if (blocoAtualIndex < blocosDeEstudo.length - 1) {
            blocoAtualIndex++;
            void carregarFraseAtual();
        }
    }

    if (event.target.id === "anterior") {
        if (blocoAtualIndex > 0) {
            blocoAtualIndex--;
            void carregarFraseAtual();
        }
    }
});

async function verificarVideo(event) {
    event.preventDefault(); 
    const input = document.querySelector('.url-input');
    const link = input ? input.value : null;
    if(!link) return;

    const btnLoad = document.querySelector('.btn-load');
    const textoOriginal = btnLoad.innerText;
    btnLoad.innerText = "VERIFICANDO...";
    btnLoad.disabled = true;

    try {
        const resposta = await fetch(`/api/legenda?url=${encodeURIComponent(link)}`);
        const jsonResponse = await resposta.json();

        if (!resposta.ok) {
            if (jsonResponse.tokens_restantes !== undefined) {
                atualizarInterfaceTokens(jsonResponse.tokens_restantes);
            }
            throw new Error(jsonResponse.detail || "Erro desconhecido ao carregar legenda.");
        }

        htmx.ajax('GET', `/legenda?link=${encodeURIComponent(link)}`, {target: 'main'}).then(() => {
            window.history.pushState(null, '', `/legenda?link=${encodeURIComponent(link)}`);
        });

    } catch (erro) {
        const erroModal = document.getElementById('erroModal');
        const erroText = document.getElementById('erro');
        if (erroModal && erroText) {
            erroText.innerText = erro.message;
            erroModal.style.display = "block";
        }
    } finally {
        if (btnLoad) {
            btnLoad.innerText = textoOriginal;
            btnLoad.disabled = false;
        }
    }
}