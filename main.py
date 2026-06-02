from fastapi import FastAPI, Request, Form, HTTPException 
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from youtube_transcript_api import YouTubeTranscriptApi 
from requests import Session
import re 

# Alguns novos imports serão necessários para implementar o Token Bucket e a Cache:
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from limits import parse
from database import salvar_na_cache, carregar_da_cache

# Imports necessários para a geração de áudio (Waves)
import yt_dlp
import asyncio
import os
import subprocess
import traceback

# Começamos definindo o limitador:
# Ele servirá para restringir a quantidade de requisições que o usuário poderá fazer ao Youtube
limitador = Limiter(key_func=get_remote_address)
app = FastAPI()
app.state.limiter = limitador

# DICIONÁRIO DE CADEADOS PARA DOWNLOADS SIMULTÂNEOS
download_locks = {}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], #permitindo qualquer site
    allow_methods=["*"], #quais "verbos" HTTP o site pode acessar, nesse caso permitindo todos
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory=["templates", "templates/Partials"])

# para evitar bloqueios cookie do Youtube
session = Session()

# ROTAS E NAVEGAÇÃO

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={
            "pagina":"/pagina1"
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

# GET para pegar as legendas, adaptado para a Cache e o Token Bucket:

@app.get("/api/legenda")
async def obter_legenda(request: Request, url: str):
    video_id = limpar_url_extrair_id(url)
    if not video_id:
        raise HTTPException(status_code=400, detail="URL do YouTube inválida.")
    
    # Aqui vem a parte mais importante: 
    # Definir quantos tokens o usuário tem, para cada certo período de tempo.
    limite = parse("5/5 minute") # Tomei a liberdade de fornecer inicialmente 5 tokens para o usuário poder gastar.
    # A cada 5 minutos, a quantidade de tokens do usuário(bucket) reseta para 5 novamente.
    # Se achar 5 minutos demais, basta trocar o segundo 5 da linha de código acima pela quantidade de minutos que desejar =)
    ip_do_usuario = get_remote_address(request)
    cache = carregar_da_cache(video_id)

    if cache:
        # Se o vídeo estiver na cache, não é necessário descontar um token, pois puxamos as legendas da memória:
        dados_do_usuario = limitador.limiter.get_window_stats(limite, ip_do_usuario, "obter_legenda")
        tokens_restantes = dados_do_usuario.remaining
        # Retornamos os dados da cache, e o saldo de tokens:
        return JSONResponse(content={
            "dados": cache,
            "tokens_restantes": tokens_restantes
        })
    
    # Se o usuário gastar todos os seus tokens e zerar seu saldo, um JSON avisando isso é mostrado para o usuário:
    if not limitador.limiter.hit(limite, ip_do_usuario, "obter_legenda"):
        return JSONResponse(
            status_code=429,
            content={"detail": "O limite de 5 tokens foi atingido. Espere 5 minutos para ter mais 5 tokens.", "tokens_restantes": 0}
        )
    
    # Obtendo novamente o saldo de tokens do usuário:
    dados_do_usuario = limitador.limiter.get_window_stats(limite, ip_do_usuario, "obter_legenda")
    tokens_restantes = dados_do_usuario.remaining

    # Se o código chegar nas próximas linhas, é porque o vídeo é novo. Logo, 1 token deve ser cobrado do usuário.
    # Como a ID do vídeo não está na memória e usuário ainda tem tokens para gastar nesse ponto do código, aí sim uma requisição ao Youtube deve ser feita:
    try:
        youtube_api = YouTubeTranscriptApi(http_client=session)
        lista_de_legendas = youtube_api.list(video_id)
        legenda_manual_ingles = lista_de_legendas.find_manually_created_transcript(['en'])
        blocos_brutos = legenda_manual_ingles.fetch()
        
        legendas_formatadas = []
        texto_anterior = ""

        for bloco in blocos_brutos:
            texto_limpo = " ".join(bloco.text.split())
            
            # Aqui, vem a parte da limpeza das legendas. Os objetivos são:
            # Limpar blocos de duração pequena demais (duração menor ou igual a 1 segundo).
            # Remover legendas repetidas.

            if texto_limpo and bloco.duration >= 1.0 and texto_limpo != texto_anterior:
                tempo_fim_calculado = bloco.start + bloco.duration
                legendas_formatadas.append({
                    "id_do_bloco": len(legendas_formatadas),
                    "texto_limpo": texto_limpo,    
                    "tempo_inicio": bloco.start,
                    "tempo_fim": tempo_fim_calculado
                })

                texto_anterior = texto_limpo

        # É necessário então sobrescrever a cache com o novo vídeo:
        salvar_na_cache(video_id, legendas_formatadas)

        # Depois, basta retornar as legendas, juntamente com os tokens restantes que o usuário possui:
        return JSONResponse(content={
            "dados": legendas_formatadas,
            "tokens_restantes": tokens_restantes
        })

    except Exception as e:
        mensagem_de_erro = str(e)
        if "No transcript found" in mensagem_de_erro or "Could not find" in mensagem_de_erro:
            raise HTTPException(status_code=404, detail="Vídeo sem legenda manual em inglês.")
        
        print(f"Erro técnico: {e}")
        raise HTTPException(status_code=500, detail="Erro ao processar legendas.")


# --- INTEGRAÇÃO DO SISTEMA DE ÁUDIO (WAVES) ---

def _baixar_audio_sync(url: str, audio_base: str):
    """Executa o download do yt_dlp de forma síncrona — chamado via executor."""
    ydl_opts = {
        "format": "bestaudio[ext=m4a]/bestaudio",
        "outtmpl": audio_base,
        "quiet": True,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl: # type: ignore
        ydl.download([url])

def _cortar_audio_sync(inicio_f: float, fim_f: float, audio_base: str, bloco_wav: str):
    """Executa o FFmpeg de forma síncrona via executor para driblar o erro do Windows."""
    comando = [
        "ffmpeg",
        "-y",
        "-ss", str(inicio_f),
        "-to", str(fim_f),
        "-i", audio_base,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "44100",
        "-ac", "1",
        bloco_wav
    ]
    # Roda o comando escondendo os logs do ffmpeg no terminal
    resultado = subprocess.run(comando, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    if resultado.returncode != 0:
        raise RuntimeError(f"ffmpeg encerrou com código {resultado.returncode}")


@app.get("/api/audio")
async def obter_audio(url: str, inicio: str, fim: str):
    os.makedirs("audio", exist_ok=True)

    try:
        inicio_f = float(inicio)
        fim_f = float(fim)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Parâmetros 'inicio' e 'fim' devem ser números.")

    video_id = limpar_url_extrair_id(url)
    if not video_id:
        raise HTTPException(status_code=400, detail="URL do YouTube inválida.")

    audio_base = f"audio/{video_id}.m4a"
    bloco_wav = f"audio/{video_id}_{inicio_f:.2f}_{fim_f:.2f}.wav"

    # CACHE DO BLOCO
    if os.path.exists(bloco_wav):
        print("CACHE HIT BLOCO")
        return FileResponse(bloco_wav, media_type="audio/wav")

    loop = asyncio.get_event_loop()

    # --- PROTEÇÃO CONTRA RACE CONDITION ---
    
    # Cria um cadeado específico para este vídeo, se não existir
    if video_id not in download_locks:
        download_locks[video_id] = asyncio.Lock()

    # Só permite que uma requisição por vez entre neste bloco
    async with download_locks[video_id]:
        # Verifica NOVAMENTE se o arquivo existe (pois a requisição anterior pode ter acabado de criá-lo)
        if not os.path.exists(audio_base):
            print(f"BAIXANDO ÁUDIO BASE ({video_id})...")
            try:
                await loop.run_in_executor(None, _baixar_audio_sync, url, audio_base)
            except Exception as e:
                print("=== ERRO AO BAIXAR ÁUDIO ===")
                traceback.print_exc()
                raise HTTPException(status_code=500, detail="Erro ao baixar áudio base.")
                
    # --- FIM DA PROTEÇÃO ---

    # CORTE DO BLOCO — Todas as requisições podem cortar o áudio base simultaneamente
    try:
        print(f"GERANDO BLOCO {inicio_f:.2f} -> {fim_f:.2f}")
        await loop.run_in_executor(None, _cortar_audio_sync, inicio_f, fim_f, audio_base, bloco_wav)

        return FileResponse(bloco_wav, media_type="audio/wav")

    except Exception as e:
        print("=== ERRO AO GERAR BLOCO ===")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Erro ao gerar bloco.")