import os
import requests
from datetime import datetime, timedelta
import pytz

def obtener_datos_api():
    api_key = os.getenv('FINANCIAL_API_KEY')
    tz = pytz.timezone('America/Tijuana')
    hoy_dt = datetime.now(tz)
    hoy_str = hoy_dt.strftime('%Y-%m-%d')
    semana_adelante = (hoy_dt + timedelta(days=7)).strftime('%Y-%m-%d')
    
    # --- CAPA 1: BÚSQUEDA AGRESIVA (Marea Macro) ---
    url_news = f"https://financialmodelingprep.com/api/v4/general_news?limit=20&apikey={api_key}"
    titulares = []
    try:
        res_news = requests.get(url_news).json()
        if isinstance(res_news, list):
            # Escaneo de palabras clave para forzar relevancia
            claves = ['fed', 'inflation', 'rates', 'fomc', 'cpi', 'pce', 'employment', 'oil']
            titulares = [n['title'] for n in res_news if any(c in n['title'].lower() for c in claves)]
            
            # Si el filtro es muy estricto y no hay nada, traer lo más reciente de stock_news
            if not titulares:
                res_v3 = requests.get(f"https://financialmodelingprep.com/api/v3/stock_news?limit=5&apikey={api_key}").json()
                titulares = [n['title'] for n in res_v3] if isinstance(res_v3, list) else []
        else:
            titulares = ["Nota: Flujo macro estable. El mercado se apoya en estructura técnica."]
    except:
        titulares = ["Error de sincronización en Capa 1."]

    # --- CAPA 2: RADAR DE ALTO IMPACTO (Ráfagas) ---
    url_cal = f"https://financialmodelingprep.com/api/v3/economic_calendar?from={hoy_str}&to={semana_adelante}&apikey={api_key}"
    eventos_formateados = []
    try:
        res_cal = requests.get(url_cal).json()
        if isinstance(res_cal, list):
            # Filtro: Prioridad USD + Impacto Alto/Medio
            # Esto captura la FED hoy miércoles sí o sí.
            for e in res_cal:
                es_usd = e.get('cur') == 'USD'
                es_importante = e.get('impact') in ['High', 'Medium']
                
                if es_usd or es_importante:
                    fecha = e.get('date', '')[5:16]
                    nombre = e.get('event', 'Evento')
                    impacto = "🔴" if e.get('impact') == 'High' else "🟠"
                    prev = e.get('previous', 'N/A')
                    est = e.get('estimate', 'N/A')
                    eventos_formateados.append(f"{impacto} **{fecha}** - {nombre}\n   └ *Ant:* {prev} | *Est:* {est}")
            
            eventos_formateados = eventos_formateados[:6] # Top 6 eventos
        else:
            eventos_formateados = ["Sin eventos críticos programados."]
    except:
        eventos_formateados = ["Error al procesar calendario."]

    return titulares[:5], eventos_formateados

def analizar_sentimiento(titulares):
    # Lógica de scoring para Capa 3
    bajista = ['drop', 'fall', 'inflation', 'higher', 'hawkish', 'war', 'fears', 'debt']
    alcista = ['growth', 'rise', 'recovery', 'bullish', 'easing', 'profit', 'expansion']
    
    texto = " ".join(titulares).lower()
    score = sum(1 for p in alcista if p in texto) - sum(1 for p in bajista if p in texto)
    
    if score <= -1:
        return "BAJISTA / RISK-OFF", "Marea macro pesada. El mercado descuenta riesgos. Priorizar ventas en retrocesos."
    elif score >= 1:
        return "ALCISTA / RISK-ON", "Optimismo en el flujo. El capital fluye a activos de riesgo. Buscar compras en soportes."
    return "NEUTRAL / CAUTELA", "Mercado lateral esperando catalizadores. Operar rangos cortos."

def enviar_reporte():
    webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
    titulares, eventos = obtener_datos_api()
    sesgo, conclusion = analizar_sentimiento(titulares)
    
    tz = pytz.timezone('America/Tijuana')
    fecha_str = datetime.now(tz).strftime('%d de %B, %Y')

    payload = {
        "content": "@everyone 🧠 **Agente v5.0: Inteligencia de Mercados**",
        "embeds": [{
            "title": f"🏛️ ANÁLISIS ESTRATÉGICO | {fecha_str}",
            "color": 0x2b2d31, # Color premium
            "fields": [
                {"name": "🌊 CAPA 1: Marea Macro (Análisis de Titulares)", "value": "\n".join([f"• {t}" for t in titulares]) if titulares else "Sin datos.", "inline": False},
                {"name": "⚡ CAPA 2: Ráfagas (Eventos de Alta Volatilidad)", "value": "\n".join(eventos) if eventos else "Calendario despejado.", "inline": False},
                {"name": f"🎯 CAPA 3: La Vela (Sesgo: {sesgo})", "value": f"**Conclusión del Agente:** {conclusion}", "inline": False}
            ],
            "footer": {"text": "Algoritmo de correlación v5.0 | Financial Modeling Prep"}
        }]
    }
    requests.post(webhook_url, json=payload)

if __name__ == "__main__":
    enviar_reporte()
