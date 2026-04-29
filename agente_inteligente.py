import os
import requests
from datetime import datetime, timedelta
import pytz

def obtener_datos_api():
    api_key = os.getenv('FINANCIAL_API_KEY')
    tz = pytz.timezone('America/Tijuana')
    hoy = datetime.now(tz)
    
    # 1. CAPA 1: Noticias (Usando el endpoint estable de stock_news)
    # Este link funciona para planes gratuitos y no es 'Legacy'
    url_news = f"https://financialmodelingprep.com/api/v3/stock_news?limit=10&apikey={api_key}"
    
    try:
        res_news = requests.get(url_news).json()
        # Verificamos si la respuesta es la lista de noticias esperada
        if isinstance(res_news, list):
            titulares = [n['title'] for n in res_news[:5]]
        else:
            titulares = ["Nota: Configurando acceso a noticias estables..."]
    except:
        titulares = ["Error de conexión con el servidor de noticias."]

    # 2. CAPA 2: Calendario (Ampliamos a impacto High y Medium)
    inicio = hoy.strftime('%Y-%m-%d')
    fin = (hoy + timedelta(days=7)).strftime('%Y-%m-%d') # Ampliamos a 7 días
    url_cal = f"https://financialmodelingprep.com/api/v3/economic_calendar?from={inicio}&to={fin}&apikey={api_key}"
    
    try:
        res_cal = requests.get(url_cal).json()
        if isinstance(res_cal, list):
            # Filtramos noticias de impacto Alto (Rojo) y Medio (Naranja)
            eventos = [e for e in res_cal if e.get('impact') in ['High', 'Medium']][:5]
        else:
            eventos = []
    except:
        eventos = []

    return titulares, eventos

def analizar_sentimiento(titulares):
    # Lógica de conclusión propia del agente
    palabras_peligro = ['inflation', 'rate hike', 'fall', 'drop', 'risk', 'crisis', 'war']
    score = sum(1 for t in titulares if any(p in t.lower() for p in palabras_peligro))
    
    if score > 2:
        return "BAJISTA / RISK-OFF", "La marea macro es turbulenta. El capital busca refugio. Priorizar ventas en índices."
    return "ALCISTA / NEUTRAL", "Sentimiento estable. Buscar continuaciones de tendencia técnica en soportes clave."

def enviar_reporte():
    webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
    titulares, eventos = obtener_datos_api()
    sesgo, conclusion = analizar_sentimiento(titulares)
    
    tz = pytz.timezone('America/Tijuana')
    fecha_reporte = datetime.now(tz).strftime('%d/%m/%Y')

    # Formatear Capa 1
    texto_macro = "\n".join([f"• {t}" for t in titulares])
    
    # Formatear Capa 2 (Noticias con nombre y por qué importan)
    texto_cal = ""
    for e in eventos:
        texto_cal += f"🔴 **{e['date'][5:10]} - {e['event']}** ({e['cur']})\n   └ *Prev:* {e['previous']} | *Est:* {e['estimate']}\n"

    payload = {
        "content": "@everyone 🧠 **Agente Activo: Análisis de 3 Capas**",
        "embeds": [{
            "title": f"🏛️ REPORTE ESTRATÉGICO | {fecha_reporte}",
            "color": 0x000000,
            "fields": [
                {"name": "🌊 CAPA 1: Marea Macro", "value": texto_macro if titulares else "Sin noticias relevantes.", "inline": False},
                {"name": "⚡ CAPA 2: Calendario de Alto Impacto", "value": texto_cal if texto_cal else "Sin eventos rojos detectados.", "inline": False},
                {"name": f"🎯 CAPA 3: Sesgo - {sesgo}", "value": f"**Conclusión:** {conclusion}", "inline": False}
            ],
            "footer": {"text": "Datos provistos por Financial Modeling Prep API"}
        }]
    }
    requests.post(webhook_url, json=payload)

if __name__ == "__main__":
    enviar_reporte()
