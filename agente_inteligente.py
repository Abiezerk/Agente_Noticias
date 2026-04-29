import os
import requests
import pytz
from datetime import datetime, timedelta

# --- CONFIGURACIÓN DE ZONA HORARIA ---
TIJUANA_TZ = pytz.timezone('America/Tijuana')

# ─────────────────────────────────────────────
# CAPA 1: NOTICIAS GEOPOLÍTICAS Y MACRO (NewsAPI)
# Fix: query en inglés, sin filtro de idioma para máximo volumen
# ─────────────────────────────────────────────
def obtener_noticias_geopoliticas():
    api_key = os.getenv('NEWS_API_KEY')
    if not api_key:
        return ["⚠️ NEWS_API_KEY no configurada en Secrets."], []

    query = '(war OR conflict OR fed OR fomc OR "interest rates" OR inflation OR recession) AND (economy OR market OR gold OR oil)'
    url = (
        f'https://newsapi.org/v2/everything'
        f'?q={query}'
        f'&sortBy=publishedAt'
        f'&pageSize=8'
        f'&apiKey={api_key}'
    )

    titulares = []
    keywords_guerra = ['war', 'attack', 'missile', 'conflict', 'strike', 'troops', 'invasion']
    keywords_fed    = ['fed', 'fomc', 'rate', 'powell', 'inflation', 'cpi', 'pce']
    raw_titulares   = []  # para el análisis de sesgo

    try:
        res = requests.get(url, timeout=30)
        res.raise_for_status()
        articulos = res.json().get('articles', [])

        for art in articulos[:6]:
            titulo = art.get('title') or 'Sin título'
            titulo_limpio = titulo.split(' - ')[0].strip()  # Quita la fuente al final
            titulo_lower = titulo_limpio.lower()
            raw_titulares.append(titulo_lower)

            if any(w in titulo_lower for w in keywords_guerra):
                prefix = "⚔️"
            elif any(w in titulo_lower for w in keywords_fed):
                prefix = "🏛️"
            else:
                prefix = "📰"

            titulares.append(f"{prefix} {titulo_limpio}")

    except requests.exceptions.HTTPError as e:
        titulares = [f"❌ Error NewsAPI HTTP {e.response.status_code}"]
    except Exception as e:
        titulares = [f"❌ Fallo noticias: {str(e)}"]

    if not titulares:
        titulares = ["🔹 Panorama geopolítico en calma aparente."]

    return titulares, raw_titulares


# ─────────────────────────────────────────────
# CAPA 2: CALENDARIO ECONÓMICO (FinnHub - API gratuita, no bloquea GitHub)
# Fix: reemplaza ScraperAPI/Investing.com que siempre fallaba
# FinnHub free tier: 60 req/min, perfecto para este caso
# ─────────────────────────────────────────────
def obtener_calendario_alto_impacto():
    api_key = os.getenv('FINNHUB_API_KEY')
    if not api_key:
        return ["⚠️ FINNHUB_API_KEY no configurada en Secrets."]

    hoy = datetime.now(TIJUANA_TZ)
    # Ventana: hoy + próximos 3 días (cubre fin de semana si corre viernes)
    fecha_inicio = hoy.strftime('%Y-%m-%d')
    fecha_fin    = (hoy + timedelta(days=3)).strftime('%Y-%m-%d')

    url = f'https://finnhub.io/api/v1/calendar/economic?from={fecha_inicio}&to={fecha_fin}&token={api_key}'

    eventos_formateados = []
    try:
        res = requests.get(url, timeout=30)
        res.raise_for_status()
        data = res.json()
        eventos = data.get('economicCalendar', [])

        # Solo impacto alto (FinnHub usa 'high' en el campo impact)
        eventos_alto = [e for e in eventos if e.get('impact', '').lower() == 'high']

        for e in eventos_alto[:8]:
            pais   = e.get('country', '??').upper()
            evento = e.get('event', 'Evento desconocido')
            hora   = e.get('time', '') or 'TBD'
            prev   = e.get('prev', '')
            est    = e.get('estimate', '')

            linea = f"🔴 **{hora[:5]}** | {pais}: {evento}"
            if est:
                linea += f" | Est: {est}"
            if prev:
                linea += f" | Prev: {prev}"

            eventos_formateados.append(linea)

    except requests.exceptions.HTTPError as e:
        return [f"❌ Error FinnHub HTTP {e.response.status_code}"]
    except Exception as e:
        return [f"❌ Fallo calendario: {str(e)}"]

    return eventos_formateados if eventos_formateados else ["🔹 Sin eventos de alto impacto en los próximos 3 días."]


# ─────────────────────────────────────────────
# CAPA 3: ANÁLISIS DE SESGO
# Fix: ya no hace .lower() sobre emojis, analiza las keywords directas
# ─────────────────────────────────────────────
def analizar_sesgo(raw_titulares: list[str], calendario: list[str]) -> tuple[str, int]:
    texto_total = " ".join(raw_titulares).lower()
    cal_texto   = " ".join(calendario).lower()

    tiene_guerra  = any(w in texto_total for w in ['war', 'attack', 'missile', 'invasion', 'conflict'])
    tiene_fed     = any(w in texto_total + cal_texto for w in ['fed', 'fomc', 'rate', 'powell', 'cpi', 'pce', 'nfp'])
    tiene_recesion = any(w in texto_total for w in ['recession', 'downturn', 'contraction', 'gdp'])

    if tiene_guerra and tiene_fed:
        return "🔥 RISK-OFF EXTREMO: Guerra + FED", 0x7B0000
    elif tiene_guerra:
        return "⚠️ RISK-OFF / Tensión Geopolítica → XAU/USD alcista, JPY fuerte", 0x990000
    elif tiene_fed:
        return "⚖️ VOLATILIDAD MACRO: Evento FED/Datos → esperar dirección en USD", 0x0055FF
    elif tiene_recesion:
        return "📉 SESGO BAJISTA MACRO: Riesgo de recesión en el radar", 0xFF8800
    else:
        return "🟢 NEUTRAL / TÉCNICO: Sin catalizador macro dominante", 0x2B2D31


# ─────────────────────────────────────────────
# ORQUESTADOR PRINCIPAL
# Fix: todas las env vars incluidas en el YML + manejo de errores en POST
# ─────────────────────────────────────────────
def ejecutar_agente():
    webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
    if not webhook_url:
        print("❌ DISCORD_WEBHOOK_URL no configurada. Abortando.")
        return

    ahora = datetime.now(TIJUANA_TZ).strftime('%d/%m/%Y %H:%M')

    # Recolección
    noticias, raw_titulares = obtener_noticias_geopoliticas()
    calendario              = obtener_calendario_alto_impacto()

    # Análisis de sesgo con keywords reales (no emojis)
    sesgo, color = analizar_sesgo(raw_titulares, calendario)

    # Validación de campos para evitar embeds vacíos (Discord rechaza campos vacíos)
    def safe_value(lista):
        texto = "\n".join(lista)
        return texto[:1024] if texto else "Sin datos disponibles."  # Límite Discord

    payload = {
        "content": "@everyone 🛰️ **Sentinel v2.0: Reporte de Inteligencia**",
        "embeds": [{
            "title": f"🛡️ INTELIGENCIA DE MERCADO | {ahora} (Tijuana)",
            "color": color,
            "fields": [
                {
                    "name": "🌍 CAPA 1 — Noticias Macro & Geopolíticas",
                    "value": safe_value(noticias),
                    "inline": False
                },
                {
                    "name": "📅 CAPA 2 — Calendario Económico Alto Impacto (3 días)",
                    "value": safe_value(calendario),
                    "inline": False
                },
                {
                    "name": "🎯 CAPA 3 — Sesgo del Mercado",
                    "value": f"**{sesgo}**",
                    "inline": False
                }
            ],
            "footer": {"text": "Sentinel v2.0 | Tijuana Local Time | Datos: NewsAPI + FinnHub"}
        }]
    }

    try:
        r = requests.post(webhook_url, json=payload, timeout=15)
        if r.status_code == 204:
            print("✅ Reporte enviado correctamente a Discord.")
        else:
            print(f"⚠️ Discord respondió con código {r.status_code}: {r.text}")
    except Exception as e:
        print(f"❌ Error enviando a Discord: {str(e)}")


if __name__ == "__main__":
    ejecutar_agente()
