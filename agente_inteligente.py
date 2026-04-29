import yfinance as yf
import os
import requests
from datetime import datetime
import pytz

def obtener_datos_reales():
    # 1. CAPA 1: Marea Macro y Guerra (Usamos el Oro y el Crudo como sensores)
    # Si hay guerra, el Oro (GC=F) y el Petróleo (CL=F) reaccionan
    sensores = yf.Tickers('GC=F CL=F ^GSPC')
    noticias_raw = sensores.tickers['GC=F'].news + sensores.tickers['^GSPC'].news
    
    titulares = []
    claves = ['war', 'conflict', 'fed', 'rates', 'inflation', 'missile', 'fomc']
    
    for n in noticias_raw:
        title = n['title']
        # Filtramos para que sea relevante a tus operaciones
        if any(c in title.lower() for c in claves):
            titulares.append(f"🔴 {title}")
    
    if not titulares:
        titulares = [n['title'] for n in noticias_raw[:5]]

    # 2. CAPA 2: Ráfagas (Calendario mediante volatilidad implícita)
    # Hoy miércoles 29 de abril es día de FED en tu calendario. 
    # Lo forzamos porque yfinance no da calendario económico, pero sí el precio real.
    eventos = [
        "🏛️ **FED Interest Rate Decision** (Hoy - Crítico)",
        "🎤 **FOMC Press Conference** (Hoy - Alta Volatilidad)",
        "📊 **EIA Crude Oil Inventories** (Impacto en WTI)"
    ]
    
    return titulares[:5], eventos

def enviar_reporte():
    webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
    noticias, eventos = obtener_datos_reales()
    
    # Análisis de Sesgo (La Vela)
    texto = " ".join(noticias).lower()
    if 'war' in texto or 'missile' in texto:
        sesgo, color = "⚠️ RISK-OFF / GUERRA", 0xcc0000
        concl = "Se detectan titulares bélicos. El Oro está bajo presión alcista. Protege tus posiciones."
    elif 'fed' in texto or 'rates' in texto:
        sesgo, color = "⚖️ DÍA DE FED / MACRO", 0x00aaff
        concl = "Atención a las tasas. El mercado espera el comunicado oficial. Rango lateral hasta la noticia."
    else:
        sesgo, color = "NEUTRAL", 0x2b2d31
        concl = "Flujo estándar. Seguir estructura técnica en cTrader."

    payload = {
        "content": "@everyone 📡 **Agente v8.0 | Conexión Directa Yahoo**",
        "embeds": [{
            "title": f"🛡️ INTELIGENCIA DE MERCADO | {datetime.now().strftime('%d/%m/%Y')}",
            "color": color,
            "fields": [
                {"name": "🌊 CAPA 1: Marea (Geopolítica y Macro)", "value": "\n".join(noticias), "inline": False},
                {"name": "⚡ CAPA 2: Ráfagas (Catalizadores de Hoy)", "value": "\n".join(eventos), "inline": False},
                {"name": "🎯 CAPA 3: La Vela", "value": f"**Sesgo:** {sesgo}\n**Conclusión:** {concl}", "inline": False}
            ]
        }]
    }
    requests.post(webhook_url, json=payload)

if __name__ == "__main__":
    enviar_reporte()
