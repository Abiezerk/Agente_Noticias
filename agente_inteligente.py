import os
import requests
from datetime import datetime, timedelta
import pytz

def obtener_datos_finnhub():
    api_key = os.getenv('FINNHUB_API_KEY')
    tz = pytz.timezone('America/Tijuana')
    hoy = datetime.now(tz)
    
    # --- CAPA 1: NOTICIAS GEOPOLÍTICAS Y DE GUERRA ---
    url_news = f"https://finnhub.io/api/v1/news?category=general&token={api_key}"
    noticias_finales = []
    try:
        res_news = requests.get(url_news).json()
        # Filtro de guerra y conflicto para tus pares
        claves_conflicto = ['war', 'conflict', 'missile', 'attack', 'geopolitical', 'oil', 'sanctions']
        noticias_finales = [n['headline'] for n in res_news if any(c in n['headline'].lower() for c in claves_conflicto)]
        
        if not noticias_finales:
            noticias_finales = [n['headline'] for n in res_news[:5]]
    except:
        noticias_finales = ["Error conectando a Finnhub News."]

    # --- CAPA 2: CALENDARIO ECONÓMICO REAL ---
    url_cal = f"https://finnhub.io/api/v1/calendar/economic?token={api_key}"
    eventos_reporte = []
    try:
        res_cal = requests.get(url_cal).json().get('economicCalendar', [])
        # Filtramos eventos de hoy y mañana con impacto 3 (alto) o 2 (medio)
        hoy_str = hoy.strftime('%Y-%m-%d')
        for e in res_cal:
            if e['time'].startswith(hoy_str) and e['impact'] >= 2:
                eventos_reporte.append(
                    f"🔴 **{e['time'][11:16]}** - {e['event']} ({e['country']})\n"
                    f"   └ *Actual:* {e.get('actual', 'Esperando')} | *Prev:* {e['previous']}"
                )
    except:
        eventos_reporte = ["Error en Calendario Finnhub."]

    return noticias_finales[:5], eventos_reporte[:5]

def enviar_reporte():
    webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
    noticias, eventos = obtener_datos_finnhub()
    
    # Lógica de Sesgo
    texto_total = " ".join(noticias).lower()
    if 'war' in texto_total or 'conflict' in texto_total:
        sesgo, color = "RISK-OFF / REFUGIO (ORO/USD)", 0xff0000
        concl = "Tensiones bélicas detectadas. El flujo busca refugio en Oro y USD. Cuidado con cortos en activos de riesgo."
    else:
        sesgo, color = "NEUTRAL / TÉCNICO", 0x2b2d31
        concl = "Sin alertas de conflicto inmediatas. Operar bajo estructura de mercado estándar."

    payload = {
        "embeds": [{
            "title": f"⚔️ REPORTE DE GUERRA Y MACRO | {datetime.now().strftime('%d/%m/%Y')}",
            "color": color,
            "fields": [
                {"name": "🌍 CAPA 1: Marea Geopolítica", "value": "\n".join([f"• {n}" for n in noticias]), "inline": False},
                {"name": "📅 CAPA 2: Ráfagas (Calendario Real de Hoy)", "value": "\n".join(eventos) if eventos else "Sin noticias rojas para las próximas horas.", "inline": False},
                {"name": "🎯 CAPA 3: Sesgo Global", "value": f"**{sesgo}**\n{concl}", "inline": False}
            ]
        }]
    }
    requests.post(webhook_url, json=payload)

if __name__ == "__main__":
    enviar_reporte()
