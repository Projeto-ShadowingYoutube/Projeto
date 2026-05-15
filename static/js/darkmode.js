document.addEventListener('click', function(event) {
    let botao = document.getElementById('mode');
    
    // Verifica se o clique foi no botão de tema ou dentro dele
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