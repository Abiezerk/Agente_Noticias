import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import pytz

def obtener_datos_internet():
    # Simulamos el raspado de fuentes como Investing/Bankinter para el 2026
    # En un entorno real, aquí usarías requests.get('url_calendario')
    noticias_semana_pasada = (
        "• **FED (30 Abril):** Mantuvo tasas en 3.6%. Powell sugiere pausa ante inflación persistente.\n"
        "• **BoJ (29 Abril):** Sin cambios en 0.75%, incertidumbre por tensiones en Oriente Medio.\n"
        "• **México:** PIB mostró ralentización al inicio del trimestre; flujos externos estables."
    )
    
    calendario_proximo = [
        {"fecha": "01/05", "evento": "Día del Trabajo (Festivo Global - Baja Liquidez)", "impacto": "🔴"},
        {"fecha": "04/05", "evento": "Reunión del Eurogrupo (Sentimiento EUR)", "impacto": "🟠"},
        {"fecha": "05/05", "evento": "Reunión ECOFIN", "impacto": "🟡"},
        {"fecha": "08/05", "evento": "Revisión Rating Grecia (Fitch)", "impacto": "🟡"}
    ]
    return noticias_semana_pasada, calendario_proximo

def enviar_reporte():
    noticias_pasadas, proxima_semana = obtener_datos_internet()
    tz = pytz.timezone('America/Tijuana')
    hoy = datetime.now(tz).strftime('%d/%m/%Y')

    # Construcción del reporte detallado
    texto_calendario = "\n".join([f"{e['impacto']} **{e['fecha']}**: {e['evento']}" for e in proxima_semana])

    payload = {
        "embeds": [{
            "title": f"🏛️ INFORME DE MERCADOS | SEMANA DEL {hoy}",
            "color": 0, # Estética Old Money (Negro)
            "fields": [
                {
                    "name": "⏪ LO QUE DEJÓ LA SEMANA (Análisis Macro)",
                    "value": noticias_pasadas,
                    "inline": False
                },
                {
                    "name": "📅 CALENDARIO SEMANA ENTRANTE (Capas 1 y 2)",
                    "value": texto_calendario,
                    "inline": False
                },
                {
                    "name": "🎯 RECOMENDACIÓN TÉCNICA (Capa 3)",
                    "value": "Dado el festivo del 1 de mayo, se prevé baja volatilidad el viernes. Buscar setups de alta precisión el martes/miércoles alineados con el sesgo neutral de la Fed.",
                    "inline": False
                }
            ],
            "footer": {"text": "Alinea Dirección (Macro), Timing (Noticias) y Precisión (Gráfico)."}
        }]
    }

    requests.post(os.getenv('DISCORD_WEBHOOK_URL'), json=payload)

if __name__ == "__main__":
    enviar_reporte()
