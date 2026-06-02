function renderizarLegenda(frase) {
    const legendaDiv = document.getElementById("legenda");
    if (!legendaDiv) return;

    legendaDiv.innerHTML = frase
        .split(/\s+/)
        .filter(Boolean)
        .map(palavra => `<span class="palavra-legenda">${palavra}</span>`)
        .join(" ");

    legendaDiv.querySelectorAll(".palavra-legenda").forEach(span => {
        span.addEventListener("click", (e) => {
            e.stopPropagation();
            const palavra = span.textContent.replace(/[^a-zA-Z'-]/g, "").toLowerCase();
            if (palavra) abrirPopupPalavra(span, palavra);
        });
    });
}

function normalizarPalavra(palavra) {
    let base = palavra.replace(/[^\w\-']/g, '').toLowerCase();
    
    // Expansão de contrações
    const contractions = {
        "i'm": "i am", "i've": "i have", "i'll": "i will", "i'd": "i would",
        "you're": "you are", "you've": "you have", "you'll": "you will", "you'd": "you would",
        "he's": "he is", "he'll": "he will", "she's": "she is", "she'll": "she will",
        "it's": "it is", "it'll": "it will", "we're": "we are", "we've": "we have",
        "we'll": "we will", "they're": "they are", "they've": "they have",
        "they'll": "they will", "don't": "do not", "doesn't": "does not",
        "didn't": "did not", "can't": "cannot", "won't": "will not",
        "shouldn't": "should not", "wouldn't": "would not", "couldn't": "could not"
    };
    if (contractions[base]) return contractions[base];
    
    // Palavras com hífen: tenta a primeira parte
    if (base.includes('-')) {
        return base.split('-')[0];
    }
    return base;
}

async function abrirPopupPalavra(spanEl, palavra) {
    fecharPopup();
    const popup = document.createElement("div");
    popup.id = "popupPalavra";
    popup.innerHTML = `<span class="popup-loading">Buscando...</span>`;
    document.body.appendChild(popup);
    posicionarPopup(popup, spanEl);

    const tentarBusca = async (pal) => {
        const res = await fetch(`https://api.dictionaryapi.dev/api/v2/entries/en/${pal}`);
        if (!res.ok) throw new Error("not found");
        return res.json();
    };

    try {
        let data;
        try {
            data = await tentarBusca(palavra);
        } catch (e) {
            const normalizada = normalizarPalavra(palavra);
            if (normalizada !== palavra) {
                data = await tentarBusca(normalizada);
            } else {
                throw e;
            }
        }
        const entrada = data[0];
        const definicao = entrada.meanings?.[0]?.definitions?.[0]?.definition || "";
        const exemplo = entrada.meanings?.[0]?.definitions?.[0]?.example || "";
        const fonetica = entrada.phonetic || entrada.phonetics?.find(p => p.text)?.text || "";
        const audioURL = entrada.phonetics?.find(p => p.audio)?.audio || "";

        popup.innerHTML = `
            <div class="popup-header">
                <span class="popup-palavra">${entrada.word}</span>
                ${fonetica ? `<span class="popup-fonetica">/${fonetica}/</span>` : ""}
            </div>
            ${definicao ? `<div class="popup-definicao">${definicao}</div>` : ""}
            ${exemplo ? `<div class="popup-exemplo">"${exemplo}"</div>` : ""}
            ${audioURL ? `<button class="popup-audio-btn">🔊 Ouvir</button>` : ""}
        `;
        if (audioURL) {
            popup.querySelector(".popup-audio-btn").addEventListener("click", (e) => {
                e.stopPropagation();
                new Audio(audioURL).play();
            });
        }
    } catch (e) {
        popup.innerHTML = `<div class="popup-erro">Palavra não encontrada</div>`;
    }
    posicionarPopup(popup, spanEl);
}

function posicionarPopup(popup, spanEl) {
    const rect = spanEl.getBoundingClientRect();
    const scrollY = window.scrollY;
    const scrollX = window.scrollX;
    
    const popupHeight = popup.offsetHeight;
    const popupWidth = popup.offsetWidth;
    
    let top = rect.top + scrollY - popupHeight - 10;
    let left = rect.left + scrollX + (rect.width / 2) - (popupWidth / 2);
    
    if (top < scrollY + 10) {
        top = rect.bottom + scrollY + 10;
    }
    
    left = Math.max(10, Math.min(left, window.innerWidth + scrollX - popupWidth - 10));
    
    popup.style.top = `${top}px`;
    popup.style.left = `${left}px`;
}

function fecharPopup() {
    const existing = document.getElementById("popupPalavra");
    if (existing) existing.remove();
}

document.addEventListener("click", (e) => {
    if (!e.target.closest("#popupPalavra") && !e.target.classList.contains("palavra-legenda")) {
        fecharPopup();
    }
});

window.renderizarLegenda = renderizarLegenda;