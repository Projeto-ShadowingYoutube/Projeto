let ocultar=false;

document.addEventListener('click', function(event) {
    let legendas=document.getElementById('legenda');
    let botao=document.getElementById('ocultar');
    // Próxima Frase
    if (event.target.id === 'ocultar' || event.target.id === 'olho') {
        if(ocultar){
            botao.innerHTML = '<img id="olho" src="/static/img/olho.svg">';
            legendas.style.filter="blur(0px)";
            ocultar=false;
        }
        else{
            botao.innerHTML = '<img id="olho" src="/static/img/olhoOFF.svg">';
            legendas.style.filter="blur(5px)";
            ocultar=true;
        }
    }
    
            
    

    
});