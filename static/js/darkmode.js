document.addEventListener('click', function(event) {
    let botao = document.getElementById('mode');
    
    // [NOVO]: Simplificação absurda do Dark Mode!
    // Antigamente injetavam variáveis HEX uma por uma no JS.
    // Agora, nós apenas trocamos o atributo `data-theme` na tag <html>.
    // O arquivo style.css faz todo o resto do trabalho pesado sozinho.
    if(event.target.closest('#mode')) {
        const root = document.documentElement;
        const currentTheme = root.getAttribute('data-theme');
        
        if (currentTheme === 'dark') {
            root.setAttribute('data-theme', 'light');
            botao.innerText = '🌙';
        } else {
            root.setAttribute('data-theme', 'dark');
            botao.innerText = '☀️';
        }
    }
});