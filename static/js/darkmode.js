let dark=false;
var root = document.querySelector(':root');
document.addEventListener('click', function(event) {
    let botao=document.getElementById('mode');
    if( event.target.id==='mode' || event.target.id==='modeSVG' ){
        if(dark){
            root.style.setProperty('--bg', '#f4f4f4');
            root.style.setProperty('--bg-button', '#333');
            root.style.setProperty('--button-hover', '#555');
            root.style.setProperty('--titulo', 'black');
            root.style.setProperty('--border', 'rgba(0,0,0,0.2)');
            botao.innerHTML = '<img id="modeSVG" src="/static/img/lightMode.svg">';
            dark=false;
        }
        else{
            root.style.setProperty('--bg', '#222222');
            root.style.setProperty('--bg-button', '#111');
            root.style.setProperty('--button-hover', '#333');
            root.style.setProperty('--titulo', 'white');
            root.style.setProperty('--border', 'rgba(255, 255, 255, 0.2)');
            botao.innerHTML = '<img id="modeSVG" src="/static/img/darkMode.svg">';
            dark=true;
        }
    }
});