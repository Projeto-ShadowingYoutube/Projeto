from fastapi import FastAPI, Request, Form, HTTPException 
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from youtube_transcript_api import YouTubeTranscriptApi 
from requests import Session
import re 

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], #permitindo qualquer site
    allow_methods=["*"], #quais "verbos" HTTP o site pode acessar, nesse caso permitindo todos
    allow_headers=["*"], #
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory=["templates", "templates/Partials"])

# para evitar bloqueios cookie do YouTube
session = Session()

# ROTAS E NAVEGAÇÃO 

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
            request=request, 
            name="home.html", 
            context={
                "pagina":"/pagina1",
            }
        )

@app.get("/pagina1", response_class=HTMLResponse)
async def pag1(request: Request):
    if (not "HX-Request" in request.headers):
        return templates.TemplateResponse(
            request,
            "home.html",
            context={
                "pagina":"/pagina1",
            }
        )
    return templates.TemplateResponse(request, "pagina1.html")

@app.get("/legenda", response_class=HTMLResponse)
async def pagina2(request: Request):
    if (not "HX-Request" in request.headers):
        return templates.TemplateResponse(
            request=request,
            name="home.html",
            context={"pagina": "/legenda"}
        )
    return templates.TemplateResponse(
            request=request, 
            name="pagina2.html", 
        ) 

@app.get("/revisao",response_class=HTMLResponse)
async def revisar(request:Request):
    if (not "HX-Request" in request.headers):
        return templates.TemplateResponse(
            request=request,
            name="home.html",
            context={"pagina": "/revisao"}
        )
    return templates.TemplateResponse(
            request=request, 
            name="pagina3.html", 
        )

# ROTAS DE API E DADOS 

def limpar_url_extrair_id(url: str):
    padrao = r'(?:v=|/|be/)([0-9A-Za-z_-]{11})'
    encaixou = re.search(padrao, url)
    if encaixou:
        return encaixou.group(1)
    else:
        return None

@app.get("/api/legenda")
async def obter_legenda(url: str):
    video_id = limpar_url_extrair_id(url)
    if not video_id:
        raise HTTPException(status_code=400, detail="URL do YouTube inválida.")
    
    try:
        youtube_api = YouTubeTranscriptApi(http_client=session)
        lista_de_legendas = youtube_api.list(video_id)
        legenda_manual_ingles = lista_de_legendas.find_manually_created_transcript(['en'])
        blocos_de_legenda = legenda_manual_ingles.fetch()
        
        legendas_formatadas = []

        for index, bloco in enumerate(blocos_de_legenda):
            texto_limpo = " ".join(bloco.text.split())
            
            tempo_fim_calculado = bloco.start + bloco.duration
            
            legendas_formatadas.append({
                "id_do_bloco": index,      
                "texto_limpo": texto_limpo,    
                "tempo_inicio": bloco.start,    
                "tempo_fim": tempo_fim_calculado 
            })

        return legendas_formatadas

    except Exception as e:
        mensagem_de_erro = str(e)
        if "No transcript found" in mensagem_de_erro or "Could not find" in mensagem_de_erro:
            raise HTTPException(status_code=404, detail="Vídeo sem legenda manual em inglês.")
        
        print(f"Erro técnico: {e}")
        raise HTTPException(status_code=500, detail="Erro ao processar legendas.")