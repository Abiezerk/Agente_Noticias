import os
import requests
from datetime import datetime, timedelta
import pytz

def obtener_datos_api():
    # El script saca la llave única de tus secrets de GitHub
    api_key = os.getenv('FINANCIAL_API_KEY')
    tz = pytz.timezone('America/Tijuana')
    hoy = datetime.now(tz)
    
    # --- CAPA 1: MERCADO GENERAL (Noticias de Acciones y Macro) ---
    # Este link nos da el "sentimiento" global (La Marea)
    url_noticias = f"https://financialmodelingprep.com/api/v3/stock_news?limit=10&apikey={api_key}"
    
    # --- CAPA 2: MERCADO ECONÓMICO (Calendario de Divisas/Forex) ---
    # Este link nos da las noticias rojas (Las Ráfagas)
    inicio = hoy.strftime('%Y-%m-%d')
    fin = (hoy + timedelta(days=5)).strftime('%Y-%m-%d')
    url_calendario = f"https://financialmodelingprep.com/api/v3/economic_calendar?from={inicio}&to={fin}&apikey={api_key}"

    try:
        # Petición 1: Noticias
        res_news = requests.get(url_noticias).json()
        titulares = [n['title'] for n in res_news[:5]] if isinstance(res_news, list) else ["Error en Noticias"]

        # Petición 2: Calendario
        res_cal = requests.get(url_calendario).json()
        eventos = [e for e in res_cal if e.get('impact') == 'High'][:5] if isinstance(res_cal, list) else []

        return titulares, eventos
    except Exception as e:
        print(f"Error técnico: {e}")
        return ["Error de conexión"], []

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
