import requests
from bs4 import BeautifulSoup
import os
from datetime import datetime
import pytz

def obtener_calendario_real():
    # Usamos un Proxy para evitar que GitHub sea bloqueado
    # Puedes usar ScraperAPI (5000 peticiones gratis al mes)
    SCRAPER_API_KEY = os.getenv('SCRAPER_API_KEY') 
    target_url = "https://www.investing.com/economic-calendar/"
    
    # Si no tienes la key de ScraperAPI aún, el código intentará conexión directa con headers limpios
    if SCRAPER_API_KEY:
        url = f"http://api.scraperapi.com?api_key={SCRAPER_API_KEY}&url={target_url}"
    else:
        url = target_url

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    eventos_finales = []
    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code != 200:
            return [f"⚠️ Bloqueo detectado (Status {response.status_code}). Necesitas SCRAPER_API_KEY."]
            
        soup = BeautifulSoup(response.content, 'html.parser')
        tabla = soup.find('table', {'id': 'economicCalendarData'})
        filas = tabla.find_all('tr', {'class': 'js-event-item'})
        
        for fila in filas:
            # Detectamos las estrellas de impacto
            impacto_td = fila.find('td', {'class': 'sentiment'})
            estrellas = impacto_td.find_all('i', {'class': 'grayFullBullishIcon'})
            
            if len(estrellas) >= 3: # Solo Alta Volatilidad
                hora = fila.find('td', {'class': 'time'}).text.strip()
                pais = fila.find('td', {'class': 'flagCur'}).text.strip()
                evento = fila.find('td', {'class': 'event'}).text.strip()
                eventos_finales.append(f"🔴 **{hora}** | {pais}: {evento}")

    except Exception as e:
        return [f"❌ Error de conexión: {str(e)}"]

    return eventos_finales[:8] if eventos_finales else ["🔹 Sin noticias de alto impacto hoy."]

def enviar_reporte():
    webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
    tz = pytz.timezone('America/Tijuana')
    fecha_hoy = datetime.now(tz).strftime('%d/%m/%Y %H:%M')
    
    eventos = obtener_calendario_real()
    
    payload = {
        "embeds": [{
            "title": f"🛰️ RADAR MACRO RECURRENTE | {fecha_hoy}",
            "color": 0x00ff00 if "🔴" in str(eventos) else 0x2b2d31,
            "fields": [
                {"name": "📅 Calendario de Alta Volatilidad", "value": "\n".join(eventos), "inline": False},
                {"name": "⚙️ Estado del Sistema", "value": "Extracción dinámica vía Proxy.", "inline": True}
            ],
            "footer": {"text": "Tijuana Local Time | Agente v11.0"}
        }]
    }
    requests.post(webhook_url, json=payload)

if __name__ == "__main__":
    enviar_reporte()
