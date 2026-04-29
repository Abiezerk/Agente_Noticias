import os
import json
import requests
import pytz
from datetime import datetime, timedelta

TIJUANA_TZ = pytz.timezone('America/Tijuana')


# ─────────────────────────────────────────────
# UTILIDAD: calcular ventanas de tiempo correctas
# ─────────────────────────────────────────────
def calcular_ventanas():
    hoy = datetime.now(TIJUANA_TZ)

    # CAPA 1: desde el domingo pasado hasta hoy
    dias_desde_domingo = (hoy.weekday() + 1) % 7  # lunes=0 → domingo fue hace 1 día, domingo=0 → hoy
    domingo_pasado = hoy - timedelta(days=dias_desde_domingo)

    # CAPA 2: desde hoy hasta el próximo domingo
    dias_hasta_domingo = (6 - hoy.weekday()) % 7  # 0 si hoy es domingo, n días si no
    if dias_hasta_domingo == 0:
        dias_hasta_domingo = 7  # si hoy ES domingo, apunta al siguiente
    proximo_domingo = hoy + timedelta(days=dias_hasta_domingo)

    return (
        domingo_pasado.strftime('%Y-%m-%d'),
        hoy.strftime('%Y-%m-%d'),
        proximo_domingo.strftime('%Y-%m-%d'),
    )


# ─────────────────────────────────────────────
# TRADUCCIÓN AL ESPAÑOL vía deep-translator (gratis, sin API key)
# ─────────────────────────────────────────────
def traducir_titulares(titulares_con_prefijo: list[str]) -> list[str]:
    try:
        from deep_translator import GoogleTranslator
        traducidos = []
        for item in titulares_con_prefijo:
            partes = item.split(' ', 1)
            emoji  = partes[0]
            texto  = partes[1] if len(partes) > 1 else ''
            try:
                texto_es = GoogleTranslator(source='auto', target='es').translate(texto)
            except Exception:
                texto_es = texto  # fallback al original si falla uno
            traducidos.append(f"{emoji} {texto_es}")
        return traducidos
    except Exception as e:
        print(f"⚠️ Fallo en traducción: {e} — usando titulares en inglés.")
        return titulares_con_prefijo


# ─────────────────────────────────────────────
# CAPA 1: NOTICIAS (domingo pasado → hoy)
# ─────────────────────────────────────────────
def obtener_noticias_geopoliticas(desde: str, hasta: str):
    api_key = os.getenv('NEWS_API_KEY')
    if not api_key:
        return ["⚠️ NEWS_API_KEY no configurada en Secrets."], []

    query = '(war OR conflict OR fed OR fomc OR "interest rates" OR inflation OR recession) AND (economy OR market OR gold OR oil)'
    url = (
        f'https://newsapi.org/v2/everything'
        f'?q={query}'
        f'&from={desde}'
        f'&to={hasta}'
        f'&sortBy=publishedAt'
        f'&pageSize=8'
        f'&apiKey={api_key}'
    )

    titulares     = []
    raw_titulares = []
    keywords_guerra = ['war', 'attack', 'missile', 'conflict', 'strike', 'troops', 'invasion']
    keywords_fed    = ['fed', 'fomc', 'rate', 'powell', 'inflation', 'cpi', 'pce']

    try:
        res = requests.get(url, timeout=30)
        res.raise_for_status()
        articulos = res.json().get('articles', [])

        for art in articulos[:6]:
            titulo = art.get('title') or 'Sin título'
            titulo_limpio = titulo.split(' - ')[0].strip()
            titulo_lower  = titulo_limpio.lower()
            raw_titulares.append(titulo_lower)

            if any(w in titulo_lower for w in keywords_guerra):
                prefix = "⚔️"
            elif any(w in titulo_lower for w in keywords_fed):
                prefix = "🏛️"
            else:
                prefix = "📰"

            titulares.append(f"{prefix} {titulo_limpio}")

    except requests.exceptions.HTTPError as e:
        return [f"❌ Error NewsAPI HTTP {e.response.status_code}"], []
    except Exception as e:
        return [f"❌ Fallo noticias: {str(e)}"], []

    if not titulares:
        return ["🔹 Panorama geopolítico en calma aparente."], []

    titulares = traducir_titulares(titulares)
    return titulares, raw_titulares


# ─────────────────────────────────────────────
# CAPA 2: CALENDARIO ECONÓMICO (hoy → próximo domingo)
# ─────────────────────────────────────────────
def obtener_calendario_alto_impacto(desde: str, hasta: str):
    api_key = os.getenv('FINNHUB_API_KEY')
    if not api_key:
        return ["⚠️ FINNHUB_API_KEY no configurada en Secrets."]

    url = f'https://finnhub.io/api/v1/calendar/economic?from={desde}&to={hasta}&token={api_key}'

    eventos_formateados = []
    try:
        res = requests.get(url, timeout=30)
        res.raise_for_status()
        eventos = res.json().get('economicCalendar', [])
        eventos_alto = [e for e in eventos if e.get('impact', '').lower() == 'high']

        for e in eventos_alto[:10]:
            pais   = e.get('country', '??').upper()
            evento = e.get('event', 'Evento desconocido')
            fecha  = e.get('time', '') or 'TBD'
            prev   = e.get('prev', '')
            est    = e.get('estimate', '')

            # Mostramos fecha completa (día/mes) ya que cubre toda la semana
            try:
                dt = datetime.strptime(fecha[:10], '%Y-%m-%d')
                fecha_fmt = dt.strftime('%a %d/%m').capitalize()
            except Exception:
                fecha_fmt = fecha[:10]

            linea = f"🔴 **{fecha_fmt}** | {pais}: {evento}"
            if est:
                linea += f" | Est: {est}"
            if prev:
                linea += f" | Prev: {prev}"

            eventos_formateados.append(linea)

    except requests.exceptions.HTTPError as e:
        return [f"❌ Error FinnHub HTTP {e.response.status_code}"]
    except Exception as e:
        return [f"❌ Fallo calendario: {str(e)}"]

    return eventos_formateados if eventos_formateados else ["🔹 Sin eventos de alto impacto esta semana."]


# ─────────────────────────────────────────────
# CAPA 3: SESGO + RECOMENDACIONES ESPECÍFICAS
# Para XAUUSD, US30 y US500
# ─────────────────────────────────────────────
def analizar_sesgo_y_recomendaciones(raw_titulares: list[str], calendario: list[str]) -> tuple[str, str, int]:
    texto_total   = " ".join(raw_titulares).lower()
    cal_texto     = " ".join(calendario).lower()

    tiene_guerra   = any(w in texto_total for w in ['war', 'attack', 'missile', 'invasion', 'conflict'])
    tiene_fed      = any(w in texto_total + cal_texto for w in ['fed', 'fomc', 'rate', 'powell', 'cpi', 'pce', 'nfp', 'interest rate'])
    tiene_recesion = any(w in texto_total for w in ['recession', 'downturn', 'contraction', 'gdp'])
    tiene_inflacion = any(w in texto_total + cal_texto for w in ['inflation', 'cpi', 'pce'])

    # Sesgo principal
    if tiene_guerra and tiene_fed:
        sesgo = "🔥 RIESGO EXTREMO: Guerra + FED activos simultáneamente"
        color = 0x7B0000
        recomendaciones = (
            "**XAUUSD 🥇:** Sesgo fuertemente alcista. Refugio seguro activo. "
            "Buscar largos en retrocesos, evitar cortos.\n"
            "**US30 📊:** Alta volatilidad. Sin dirección clara — evitar posiciones de swing, "
            "solo scalps en zonas de soporte confirmado.\n"
            "**US500 📈:** Igual que US30. Presión vendedora probable. "
            "Esperar datos antes de entrar."
        )
    elif tiene_guerra:
        sesgo = "⚠️ RISK-OFF: Tensión Geopolítica dominante"
        color = 0x990000
        recomendaciones = (
            "**XAUUSD 🥇:** Alcista. Demanda de refugio activa. "
            "Priorizar largos, stops ajustados bajo soportes clave.\n"
            "**US30 📊:** Bajista probable. Índices bajo presión vendedora. "
            "Cautela con largos, cortos en resistencias.\n"
            "**US500 📈:** Igual presión bajista. Evitar compras en zona de resistencia semanal."
        )
    elif tiene_fed and tiene_inflacion:
        sesgo = "⚖️ MACRO CRÍTICO: FED + Datos de Inflación en la semana"
        color = 0x0055FF
        recomendaciones = (
            "**XAUUSD 🥇:** Volátil. Si datos de inflación > estimado → bajista para Oro. "
            "Si < estimado → alcista. No entrar antes del dato.\n"
            "**US30 📊:** Alta sensibilidad. Dato hawkish → caída. Dato dovish → rally. "
            "Esperar reacción inicial y operar el retroceso.\n"
            "**US500 📈:** Mismo comportamiento que US30. "
            "Gestionar tamaño de posición — semana de alta volatilidad."
        )
    elif tiene_fed:
        sesgo = "⚖️ VOLATILIDAD MACRO: Evento FED en el radar"
        color = 0x0055FF
        recomendaciones = (
            "**XAUUSD 🥇:** Neutral-volátil. Esperar definición post-FED para operar dirección.\n"
            "**US30 📊:** Posible expansión de rango. Reducir tamaño de posición esta semana.\n"
            "**US500 📈:** Similar. Priorizar gestión de riesgo sobre búsqueda de setups."
        )
    elif tiene_recesion:
        sesgo = "📉 SESGO BAJISTA MACRO: Riesgo de recesión en el radar"
        color = 0xFF8800
        recomendaciones = (
            "**XAUUSD 🥇:** Alcista a mediano plazo como refugio. "
            "Largo en soportes semanales.\n"
            "**US30 📊:** Bajista. Evitar largos en zona de resistencia. "
            "Cortos bajo mínimos previos con confirmación.\n"
            "**US500 📈:** Mismo sesgo bajista. Vigilar niveles de soporte macro."
        )
    else:
        sesgo = "🟢 NEUTRAL / TÉCNICO: Sin catalizador macro dominante"
        color = 0x2B2D31
        recomendaciones = (
            "**XAUUSD 🥇:** Operar niveles técnicos. Sin sesgo fundamental claro — "
            "respetar S/R del gráfico semanal y diario.\n"
            "**US30 📊:** Semana técnica. Buscar continuación de tendencia vigente "
            "en zonas de valor (EMA / retrocesos Fibonacci).\n"
            "**US500 📈:** Ídem. Priorizar setups de alta probabilidad con R:R mínimo 1:2."
        )

    return sesgo, recomendaciones, color


# ─────────────────────────────────────────────
# ORQUESTADOR PRINCIPAL
# ─────────────────────────────────────────────
def ejecutar_agente():
    webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
    if not webhook_url:
        print("❌ DISCORD_WEBHOOK_URL no configurada. Abortando.")
        return

    ahora = datetime.now(TIJUANA_TZ).strftime('%d/%m/%Y %H:%M')
    domingo_pasado, hoy_str, proximo_domingo = calcular_ventanas()

    print(f"📅 Noticias: {domingo_pasado} → {hoy_str}")
    print(f"📅 Calendario: {hoy_str} → {proximo_domingo}")

    noticias, raw_titulares = obtener_noticias_geopoliticas(domingo_pasado, hoy_str)
    calendario              = obtener_calendario_alto_impacto(hoy_str, proximo_domingo)
    sesgo, recomendaciones, color = analizar_sesgo_y_recomendaciones(raw_titulares, calendario)

    def safe_value(lista):
        texto = "\n".join(lista)
        return texto[:1024] if texto else "Sin datos disponibles."

    payload = {
        "content": "@everyone 🛰️ **Sentinel v2.1: Reporte Semanal de Inteligencia**",
        "embeds": [{
            "title": f"🛡️ INTELIGENCIA DE MERCADO | {ahora} (Tijuana)",
            "color": color,
            "fields": [
                {
                    "name": f"🌍 CAPA 1 — Noticias Macro & Geopolíticas (Dom {domingo_pasado} → Hoy)",
                    "value": safe_value(noticias),
                    "inline": False
                },
                {
                    "name": f"📅 CAPA 2 — Calendario Alto Impacto (Hoy → Dom {proximo_domingo})",
                    "value": safe_value(calendario),
                    "inline": False
                },
                {
                    "name": "🎯 CAPA 3 — Sesgo Semanal",
                    "value": f"**{sesgo}**",
                    "inline": False
                },
                {
                    "name": "📌 Recomendaciones por Instrumento",
                    "value": recomendaciones[:1024],
                    "inline": False
                }
            ],
            "footer": {"text": "Sentinel v2.1 | Tijuana Local Time | Datos: NewsAPI + FinnHub"}
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
