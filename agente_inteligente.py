import yfinance as yf
import os
import requests
from datetime import datetime
import pytz

def obtener_datos_reales():
    # Sensores de activos clave para tus cBots
    sensores = yf.Tickers('GC=F ^GSPC EURUSD=X')
    titulares = []
    
    try:
        # Combinamos noticias de Oro y S&P500 para mayor cobertura
        raw_data = sensores.tickers['GC=F'].news + sensores.tickers['^GSPC'].news
        
        for n in raw_data:
            # Extracción robusta del título
            texto = n.get('title') or n.get('headline')
            if not texto: continue
            
            # Si el titular es real, lo añadimos (quitamos la plantilla de "Noticia de mercado")
            if len(texto) > 10:
                # Marcamos con 🔴 si detecta algo crítico, si no, con 🔹
                icon = "🔴" if any(c in texto.lower() for c in ['fed', 'war', 'rates', 'fomc', 'conflict']) else "🔹"
                titulares.append(f"{icon} {texto}")

        # Si por algún motivo Yahoo no devuelve nada, usamos una fuente alternativa de respaldo
        if not titulares:
            titulares = ["⚠️ Sin titulares recientes en Yahoo Finance. Revisar flujo en cTrader."]
            
    except Exception as e:
        titulares = [f"❌ Error técnico en Capa 1: {str(e)}"]

    # Capa 2: Eventos confirmados para hoy Miércoles 29/04
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
