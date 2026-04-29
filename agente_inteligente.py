import os
import requests
from datetime import datetime, timedelta
import pytz

def obtener_datos_api():
    api_key = os.getenv('FINANCIAL_API_KEY')
    tz = pytz.timezone('America/Tijuana')
    hoy = datetime.now(tz)
    
    # 1. CAPA 1: Noticias Macro (Sentiment)
    url_news = f"https://financialmodelingprep.com/api/v3/fmp_articles?page=0&apikey={api_key}"
    noticias_raw = requests.get(url_news).json()
    titulares = [n['title'] for n in noticias_raw[:5]] # Tomamos los 5 más recientes
    
    # 2. CAPA 2: Calendario Dinámico
    # Si es domingo, vemos la semana que viene. Si es entre semana, lo que falta.
    inicio = hoy if hoy.weekday() < 5 else hoy + timedelta(days=1)
    fin = inicio + timedelta(days=5)
    
    url_cal = f"https://financialmodelingprep.com/api/v3/economic_calendar?from={inicio.strftime('%Y-%m-%d')}&to={fin.strftime('%Y-%m-%d')}&apikey={api_key}"
    calendario_raw = requests.get(url_cal).json()
    
    # Filtrar solo eventos de alto impacto (High)
    eventos = [e for e in calendario_raw if e.get('impact') == 'High'][:5]
    
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
                {"name": "🌊 CAPA 1: Marea Macro (Noticias Reales)", "value": texto_macro if titulares else "Sin noticias relevantes.", "inline": False},
                {"name": "⚡ CAPA 2: Ráfagas (Calendario de Alto Impacto)", "value": texto_cal if texto_cal else "Sin eventos rojos detectados.", "inline": False},
                {"name": f"🎯 CAPA 3: La Vela (Sesgo: {sesgo})", "value": f"**Conclusión:** {conclusion}", "inline": False}
            ],
            "footer": {"text": "Datos provistos por Financial Modeling Prep API"}
        }]
    }
    requests.post(webhook_url, json=payload)

if __name__ == "__main__":
    enviar_reporte()
