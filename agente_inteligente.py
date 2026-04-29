import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import pytz

def obtener_datos_mercado():
    """
    Simulación de scraping de noticias y calendario. 
    En producción, estas funciones conectan con Investing o ForexFactory.
    """
    # Resumen de la semana que cierra (Abril 2026)
    resumen_pasado = (
        "• **USD:** La FED mantuvo tasas; el mercado asimila un discurso 'hawkish' moderado.\n"
        "• **JPY:** Intervención del BoJ tras mínimos históricos del Yen.\n"
        "• **MXN:** Inflación en México sale ligeramente arriba de lo esperado, presionando al Banxico."
    )
    
    # Calendario de la semana que entra (Mayo 2026)
    calendario_proximo = [
        {"fecha": "Dom 03", "evento": "Apertura Semanal - GAP Analysis", "impacto": "⚪"},
        {"fecha": "Lun 04", "evento": "PMI Manufacturero (EE.UU.)", "impacto": "🔴"},
        {"fecha": "Mié 06", "evento": "Inventarios de Petróleo / ADP Employment", "impacto": "🟠"},
        {"fecha": "Vie 08", "evento": "NFP: Nóminas No Agrícolas (Día Clave)", "impacto": "🔴"}
    ]
    return resumen_pasado, calendario_proximo

def enviar_reporte():
    webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
    if not webhook_url:
        print("Error: No se encontró la URL del Webhook.")
        return

    pasado, futuro = obtener_datos_mercado()
    tz = pytz.timezone('America/Tijuana')
    hoy = datetime.now(tz).strftime('%A, %d de %B %Y')

    texto_futuro = "\n".join([f"{e['impacto']} **{e['fecha']}**: {e['evento']}" for e in futuro])

    payload = {
        "content": "@everyone 📊 **Análisis de Mercado Semanal**",
        "embeds": [{
            "title": "🏛️ SISTEMA DE 3 CAPAS: REPORTE ESTRATÉGICO",
            "description": f"Informe generado el {hoy}",
            "color": 0, # Estética Premium (Negro)
            "fields": [
                {
                    "name": "⏪ SEMANA ANTERIOR (La Marea)",
                    "value": pasado,
                    "inline": False
                },
                {
                    "name": "📅 PRÓXIMOS DÍAS CLAVE (Las Ráfagas)",
                    "value": texto_futuro,
                    "inline": False
                },
                {
                    "name": "🎯 RECOMENDACIÓN (La Vela)",
                    "value": "Semana de NFP. Se recomienda reducir el riesgo a partir del jueves. Buscar confluencia técnica en niveles de soporte diario antes de las noticias de alto impacto.",
                    "inline": False
                }
            ],
            "footer": {"text": "Operativa Profesional: Dirección + Timing + Precisión"}
        }]
    }

    requests.post(webhook_url, json=payload)

if __name__ == "__main__":
    enviar_reporte()
