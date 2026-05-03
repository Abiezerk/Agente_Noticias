import os
import json
import requests
import anthropic
import pytz
from datetime import datetime, timedelta

TIJUANA_TZ = pytz.timezone('America/Tijuana')


# ─────────────────────────────────────────────
# UTILIDAD: calcular ventanas de tiempo correctas
# ─────────────────────────────────────────────
def calcular_ventanas():
    hoy = datetime.now(TIJUANA_TZ)

    # CAPA 1: desde el domingo pasado hasta hoy
    # FIX: si hoy ES domingo, retrocedemos 7 días extra para incluir el domingo anterior
    dias_desde_domingo = (hoy.weekday() + 1) % 7
    if dias_desde_domingo == 0:
        dias_desde_domingo = 7  # si hoy es domingo, tomar desde el domingo PASADO (7 días atrás)

    domingo_pasado = hoy - timedelta(days=dias_desde_domingo)

    # CAPA 2: desde hoy hasta el próximo domingo
    dias_hasta_domingo = (6 - hoy.weekday()) % 7
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
                texto_es = texto
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
    raw_eventos         = []
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

            raw_eventos.append(f"{pais}: {evento} (Est: {est}, Prev: {prev})")

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
        return [f"❌ Error FinnHub HTTP {e.response.status_code}"], []
    except Exception as e:
        return [f"❌ Fallo calendario: {str(e)}"], []

    if not eventos_formateados:
        return ["🔹 Sin eventos de alto impacto esta semana."], []

    return eventos_formateados, raw_eventos


# ─────────────────────────────────────────────
# CAPA 3: RECOMENDACIONES IA vía Claude API
# ─────────────────────────────────────────────
def obtener_recomendaciones_ia(
    raw_titulares: list[str],
    raw_eventos: list[str],
    desde_noticias: str,
    hasta_noticias: str
) -> tuple[str, str, int]:

    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        return (
            "⚠️ SESGO NO DISPONIBLE",
            "⚠️ ANTHROPIC_API_KEY no configurada — recomendaciones IA no disponibles.",
            0x888888
        )

    noticias_texto  = "\n".join(raw_titulares) if raw_titulares else "Sin noticias disponibles."
    calendario_texto = "\n".join(raw_eventos)  if raw_eventos  else "Sin eventos de alto impacto."

    prompt_usuario = f"""Aquí están los datos recopilados por el agente Sentinel esta semana:

📰 NOTICIAS MACRO & GEOPOLÍTICAS ({desde_noticias} → {hasta_noticias}):
{noticias_texto}

📅 CALENDARIO ECONÓMICO DE ALTO IMPACTO (próximos días):
{calendario_texto}

Con base en esta información, proporciona:
1. Una línea de SESGO SEMANAL (ej: "RISK-OFF — Tensión geopolítica dominante")
2. Recomendaciones concretas de trading para esta semana para los siguientes instrumentos:
   - XAUUSD (Oro)
   - US30 (Dow Jones)
   - US500 (S&P 500)
   - NAS100 (Nasdaq 100)

Formato de respuesta esperado:
SESGO: [tu sesgo aquí]

XAUUSD: [tu recomendación]
US30: [tu recomendación]
US500: [tu recomendación]
NAS100: [tu recomendación]

Sé directo, concreto y accionable. Máximo 3 oraciones por instrumento."""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            system=(
                "Eres un analista de mercados financieros con 35 años de experiencia y un CI de 180. "
                "Interpreta las noticias de la semana pasada hasta el día de hoy que recopiló el agente "
                "para ti y da recomendaciones para los instrumentos solicitados. "
                "Responde siempre en español. Sé preciso, directo y profesional."
            ),
            messages=[{"role": "user", "content": prompt_usuario}]
        )

        respuesta = message.content[0].text.strip()

        # Extraer sesgo de la primera línea
        lineas = respuesta.split('\n')
        sesgo_linea = next((l for l in lineas if l.upper().startswith('SESGO:')), None)
        sesgo = sesgo_linea.replace('SESGO:', '').replace('Sesgo:', '').strip() if sesgo_linea else "Ver recomendaciones abajo"

        # Las recomendaciones son todo menos la línea de sesgo
        recomendaciones = '\n'.join(
            l for l in lineas
            if not l.upper().startswith('SESGO:') and l.strip()
        ).strip()

        # Color según palabras clave en el sesgo
        sesgo_lower = sesgo.lower()
        if any(w in sesgo_lower for w in ['extremo', 'guerra', 'war', 'crítico']):
            color = 0x7B0000
        elif any(w in sesgo_lower for w in ['risk-off', 'bajista', 'tensión', 'conflict']):
            color = 0x990000
        elif any(w in sesgo_lower for w in ['fed', 'macro', 'volátil', 'inflación']):
            color = 0x0055FF
        elif any(w in sesgo_lower for w in ['alcista', 'bullish', 'positivo']):
            color = 0x00AA44
        else:
            color = 0x2B2D31

        return f"🤖 {sesgo}", recomendaciones, color

    except Exception as e:
        return (
            "❌ Error IA",
            f"No se pudieron obtener recomendaciones de Claude: {str(e)}",
            0x888888
        )


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
    resultado_calendario    = obtener_calendario_alto_impacto(hoy_str, proximo_domingo)

    # obtener_calendario_alto_impacto ahora devuelve una tupla (formateados, raw)
    if isinstance(resultado_calendario, tuple):
        calendario, raw_eventos = resultado_calendario
    else:
        calendario  = resultado_calendario  # fallback si solo devolvió lista (error)
        raw_eventos = []

    sesgo, recomendaciones, color = obtener_recomendaciones_ia(
        raw_titulares, raw_eventos, domingo_pasado, hoy_str
    )

    def safe_value(lista):
        texto = "\n".join(lista)
        return texto[:1024] if texto else "Sin datos disponibles."

    payload = {
        "content": "@everyone 🛰️ **Sentinel v2.2: Reporte Semanal de Inteligencia**",
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
                    "name": "🎯 CAPA 3 — Sesgo Semanal IA",
                    "value": f"**{sesgo}**",
                    "inline": False
                },
                {
                    "name": "📌 Recomendaciones por Instrumento (Claude AI)",
                    "value": recomendaciones[:1024],
                    "inline": False
                }
            ],
            "footer": {"text": "Sentinel v2.2 | Tijuana Local Time | Datos: NewsAPI + FinnHub | IA: Claude Sonnet"}
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
