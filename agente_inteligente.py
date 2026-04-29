import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import pytz

def obtener_datos_fuentes_multiples():
    """Navega por múltiples fuentes para correlacionar sentimiento."""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    urls = [
        "https://mx.investing.com/news/economy",
        "https://www.reuters.com/business/finance/",
        "https://www.dailyfx.com/espanol/noticias-forex"
    ]
    
    titulares = []
    for url in urls:
        try:
            res = requests.get(url, headers=headers, timeout=8)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                # Extraer titulares según la estructura de cada sitio
                items = soup.find_all(['h2', 'h3', 'a'], limit=10)
                for item in items:
                    texto = item.get_text(strip=True)
                    if len(texto) > 30: titulares.append(texto)
        except:
            continue
    return list(set(titulares)) # Eliminar duplicados

def analizar_logica_trading(titulares, es_domingo):
    """Correlación de datos y generación de conclusiones propias."""
    # Diccionario de pesos para el análisis de sentimiento
    pesos = {
        'alcista': 1, 'sube': 1, 'crecimiento': 1, 'recuperación': 1, 'fuerte': 1,
        'bajista': -1, 'cae': -1, 'recesión': -1, 'inflación': -1, 'riesgo': -1, 'caída': -1
    }
    
    score = 0
    for t in titulares:
        for palabra, valor in pesos.items():
            if palabra in t.lower(): score += valor

    if score > 2:
        sesgo = "ALCISTA (Risk-On)"
        concl = "La marea es fuerte. Priorizar compras en activos de riesgo (Acciones/Crypto) y debilidad en el Dólar."
    elif score < -2:
        sesgo = "BAJISTA (Risk-Off)"
        concl = "Sentimiento de refugio. El mercado teme la macro. Buscar ventas en índices y fortaleza en Oro/Dólar."
    else:
        sesgo = "NEUTRAL / CAUTELA"
        concl = "Falta de catalizadores claros. Operar rangos cortos y evitar dejar posiciones abiertas en noticias rojas."

    return sesgo, concl

def generar_fechas_dinamicas(hoy):
    """Ajusta el calendario según el día de ejecución."""
    es_domingo = hoy.weekday() == 6
    calendario = []
    
    if es_domingo:
        # Si es domingo, mirar de lunes a viernes de la semana entrante
        inicio = hoy + timedelta(days=1)
    else:
        # Si es entre semana, mirar lo que resta (hoy hasta viernes)
        inicio = hoy
        
    for i in range(5):
        dia = inicio + timedelta(days=i)
        if dia.weekday() < 5: # Solo lunes a viernes
            calendario.append({
                "fecha": dia.strftime('%d/%m (%a)'),
                "evento": "Análisis de Volatilidad Previsto",
                "impacto": "🔴" if i < 2 else "🟠"
            })
            if es_domingo and len(calendario) == 5: break
            if not es_domingo and dia.weekday() == 4: break # Parar en viernes
            
    return calendario

def enviar_reporte():
    tz = pytz.timezone('America/Tijuana')
    hoy = datetime.now(tz)
    
    titulares = obtener_datos_fuentes_multiples()
    sesgo, conclusion = analizar_logica_trading(titulares, hoy.weekday() == 6)
    calendario = generar_fechas_dinamicas(hoy)
    
    # Construcción del texto de noticias (Capa 1)
    resumen_macro = "\n".join([f"• {t}" for t in titulares[:5]]) if titulares else "Error de conexión con fuentes macro."
    
    # Construcción del calendario (Capa 2)
    texto_cal = "\n".join([f"{e['impacto']} **{e['fecha']}**: {e['evento']}" for e in calendario])

    payload = {
        "content": "@everyone 🧠 **Agente de Inteligencia Macro - Ejecución Dinámica**",
        "embeds": [{
            "title": f"🏛️ SISTEMA DE 3 CAPAS | {hoy.strftime('%d/%m/%Y')}",
            "color": 0x2f3136, # Gris oscuro profesional
            "fields": [
                {
                    "name": "🌊 CAPA 1: Correlación Macro",
                    "value": resumen_macro,
                    "inline": False
                },
                {
                    "name": "📅 CAPA 2: Calendario Proyectado",
                    "value": texto_cal,
                    "inline": False
                },
                {
                    "name": f"🎯 CAPA 3: Sesgo Detectado: {sesgo}",
                    "value": f"**Análisis del Agente:** {conclusion}",
                    "inline": False
                }
            ],
            "footer": {"text": "Ejecución dinámica basada en análisis de sentimiento real."}
        }]
    }
    
    requests.post(os.getenv('DISCORD_WEBHOOK_URL'), json=payload)

if __name__ == "__main__":
    enviar_reporte()
