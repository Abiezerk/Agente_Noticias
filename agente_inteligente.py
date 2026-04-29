import os
import requests
from bs4 import BeautifulSoup
import pytz
from datetime import datetime

# --- CONFIGURACIÓN DE ZONA HORARIA ---
TIJUANA_TZ = pytz.timezone('America/Tijuana')

def obtener_calendario_alto_impacto():
    """Extrae eventos de 3 estrellas de Investing usando bypass de Proxy."""
    api_key = os.getenv('SCRAPER_API_KEY')
    target_url = "https://www.investing.com/economic-calendar/"
    # El parámetro render=true es vital para saltar protecciones de JavaScript
    proxy_url = f"http://api.scraperapi.com?api_key={api_key}&url={target_url}&render=true"
    
    eventos = []
    try:
        # Timeout extendido a 120s porque el renderizado de Chrome remoto es lento
        response = requests.get(proxy_url, timeout=120)
        if response.status_code != 200:
            return [f"⚠️ Error de Proxy: Status {response.status_code}. Revisa SCRAPER_API_KEY."]

        soup = BeautifulSoup(response.content, 'html.parser')
        filas = soup.select('tr.js-event-item')

        for fila in filas:
            # Filtro de impacto (3 estrellas/toros)
            impacto = fila.select('td.sentiment i.grayFullBullishIcon')
            if len(impacto) >= 3:
                hora = fila.select_one('td.time').text.strip()
                pais = fila.select_one('td.flagCur').text.strip()
                nombre = fila.select_one('td.event').text.strip()
                eventos.append(f"🔴 **{hora}** | {pais}: {nombre}")
    except Exception as e:
        return [f"❌ Fallo en conexión de calendario: {str(e)}"]

    return eventos[:8] if eventos else ["🔹 No se detectaron eventos críticos para hoy."]

def obtener_noticias_geopoliticas():
    """Obtiene noticias reales de guerra y macroeconomía vía NewsAPI."""
    api_key = os.getenv('NEWS_API_KEY')
    # Query optimizada para tus pares operativos (Oro, Crudo, USD)
    query = '(war OR conflict OR fed OR fomc OR "interest rates") AND (finance OR economy)'
    url = f'https://newsapi.org/v2/everything?q={query}&sortBy=publishedAt&language=es&apiKey={api_key}'
    
    titulares = []
    try:
        res = requests.get(url, timeout=30).json()
        articulos = res.get('articles', [])
        
        for art in articulos[:5]:
            titulo = art.get('title', 'Sin título')
            # Categorización visual
            prefix = "⚔️" if any(w in titulo.lower() for w in ['guerra', 'conflicto', 'misil', 'ataque']) else "🏛️"
            titulares.append(f"{prefix} {titulo}")
    except:
        titulares = ["⚠️ No se pudo sincronizar el radar de noticias."]
        
    return titulares if titulares else ["🔹 Panorama geopolítico en calma aparente."]

def ejecutar_agente():
    """Orquesta la recolección y el envío del reporte a Discord."""
    webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
    ahora = datetime.now(TIJUANA_TZ).strftime('%d/%m/%Y %H:%M')
    
    # 1. Recolección de Capas
    noticias = obtener_noticias_geopoliticas()
    calendario = obtener_calendario_alto_impacto()
    
    # 2. Análisis de Sesgo (Capa 3)
    noticias_str = " ".join(noticias).lower()
    if "⚔️" in noticias_str:
        sesgo, color = "⚠️ RISK-OFF / GUERRA", 0x990000 # Rojo Guerra
    elif "fed" in noticias_str or "rate" in noticias_str:
        sesgo, color = "⚖️ VOLATILIDAD MACRO", 0x0055ff # Azul FED
    else:
        sesgo, color = "NEUTRAL / TÉCNICO", 0x2b2d31 # Gris Estándar

    # 3. Construcción del Mensaje
    payload = {
        "content": "@everyone 🛰️ **Sentinel v12.0: Reporte Automatizado**",
        "embeds": [{
            "title": f"🛡️ INTELIGENCIA DE MERCADO | {ahora}",
            "color": color,
            "fields": [
                {"name": "🌍 CAPA 1: Marea Geopolítica (Noticias Reales)", "value": "\n".join(noticias), "inline": False},
                {"name": "📅 CAPA 2: Calendario de Alto Impacto (Live)", "value": "\n".join(calendario), "inline": False},
                {"name": "🎯 CAPA 3: Sesgo del Agente", "value": f"**{sesgo}**\nActualizado dinámicamente según flujo de datos.", "inline": False}
            ],
            "footer": {"text": "Local Time Tijuana | Auditoría de Grado Industrial"}
        }]
    }
    
    requests.post(webhook_url, json=payload)

if __name__ == "__main__":
    ejecutar_agente()
