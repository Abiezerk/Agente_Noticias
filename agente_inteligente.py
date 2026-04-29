import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import pytz

def analizar_sentimiento(titulares):
    """Analiza los titulares para determinar un sesgo dinámico."""
    palabras_alcistas = ['crece', 'sube', 'alcista', 'recupera', 'positivo', 'ganancias', 'growth', 'bullish']
    palabras_bajistas = ['cae', 'baja', 'bajista', 'inflación', 'riesgo', 'pérdida', 'recesión', 'bearish']
    
    score = 0
    texto_completo = " ".join(titulares).lower()
    
    for p in palabras_alcistas: score += texto_completo.count(p)
    for p in palabras_bajistas: score -= texto_completo.count(p)
    
    if score > 0: return "ALCISTA (Risk-On)", "Buscar confirmaciones de compra en niveles de soporte tras retrocesos."
    if score < 0: return "BAJISTA (Risk-Off)", "Priorizar ventas en resistencias clave. Evitar activos de riesgo si la macro presiona."
    return "NEUTRAL / RANGO", "Mercado indeciso. Esperar ruptura de rangos claros antes de ejecutar."

def obtener_datos_mercado():
    url_noticias = "https://mx.investing.com/news/economy"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    titulares_lista = []
    try:
        response = requests.get(url_noticias, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        elementos = soup.select('.articleItem .title')[:5]
        titulares_lista = [t.get_text(strip=True) for t in elementos]
        resumen_macro = "\n".join([f"• {t}" for t in titulares_lista])
    except:
        resumen_macro = "• Error al conectar. Revisar volatilidad manualmente."
        titulares_lista = []

    # Capa 2: Calendario Dinámico
    hoy = datetime.now()
    calendario = [
        {"fecha": (hoy + timedelta(days=1)).strftime('%d/%m'), "evento": "Apertura Semanal / GAP Analysis", "impacto": "⚪"},
        {"fecha": (hoy + timedelta(days=3)).strftime('%d/%m'), "evento": "Datos de Inflación / PIB (Estimados)", "impacto": "🔴"},
        {"fecha": (hoy + timedelta(days=5)).strftime('%d/%m'), "evento": "Cierre Semanal / Ajuste de Cartera", "impacto": "🟠"}
    ]

    # Capa 3: Generación de Conclusiones Propias
    sesgo, recomendacion = analizar_sentimiento(titulares_lista)
    
    return resumen_macro, calendario, sesgo, recomendacion

def enviar_reporte():
    webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
    if not webhook_url: return

    macro, calendario, sesgo, recomendacion = obtener_datos_mercado()
    tz = pytz.timezone('America/Tijuana')
    fecha_str = datetime.now(tz).strftime('%d de %B, %Y')

    texto_futuro = "\n".join([f"{e['impacto']} **{e['fecha']}**: {e['evento']}" for e in calendario])

    payload = {
        "content": "@everyone 📊 **Análisis Autónomo del Agente**",
        "embeds": [{
            "title": f"🏛️ ESTRATEGIA PROFESIONAL | {fecha_str}",
            "color": 0 if "ALCISTA" not in sesgo else 3066993, # Negro o Verde si es alcista
            "fields": [
                {
                    "name": "🌊 CAPA 1: Marea Macro (Basado en Noticias Reales)",
                    "value": macro if macro else "Sin datos recientes.",
                    "inline": False
                },
                {
                    "name": "⚡ CAPA 2: Ráfagas (Calendario Proyectado)",
                    "value": texto_futuro,
                    "inline": False
                },
                {
                    "name": f"🎯 CAPA 3: La Vela (Sesgo: {sesgo})",
                    "value": f"**Conclusión del Agente:** {recomendacion}",
                    "inline": False
                }
            ],
            "footer": {"text": "Análisis computado mediante correlación de sentimiento y calendario."}
        }]
    }
    requests.post(webhook_url, json=payload)

if __name__ == "__main__":
    enviar_reporte()
