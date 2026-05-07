# 🗣️ Projeto Shadowing App

Plataforma interativa para prática de *Shadowing* em inglês, utilizando vídeos do YouTube e reconhecimento de voz em tempo real para sincronia e avaliação de pronúncia.

## 🚀 Como rodar o projeto localmente

**1. Clone o repositório e entre na pasta:**
```bash
git clone [https://github.com/SEU_USUARIO/NOME_DO_REPO.git](https://github.com/SEU_USUARIO/NOME_DO_REPO.git)
cd NOME_DO_REPO

# No Windows
python -m venv venv
venv\Scripts\activate

pip install -r requirements.txt

python -m uvicorn main:app --reload