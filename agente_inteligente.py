import os
import requests
import anthropic
import pytz
from datetime import datetime, timedelta

TIJUANA_TZ = pytz.timezone('America/Tijuana')


def calcular_ventanas():
    hoy = datetime.now(TIJUANA_TZ)
    dias_desde_domingo = (hoy.weekday() + 1) % 7
    if dias_desde_domingo == 0:
        dias_desde_domingo = 7
    domingo_pasado = hoy - timedelta(days=dias_desde_domingo)
    dias_hasta_domingo = (6 - hoy.weekday()) % 7
    if dias_hasta_domingo == 0:
        dias_hasta_domingo = 7
    proximo_domingo = hoy + timedelta(days=dias_hasta_domingo)
    return (
        domingo_pasado.strftime('%Y-%m-%d'),
        hoy.strftime('%Y-%m-%d'),
        proximo_domingo.strftime('%Y-%m-%d'),
    )


def traducir_titulares(titulares_con_prefijo):
    try:
        from deep_translator import GoogleTranslator
        traducidos = []
        for item in titulares_con_prefijo:
            partes = item.split(' ', 1)
            emoji = partes[0]
            texto = partes[1] if len(partes) > 1 else ''
            try:
                texto_es = GoogleTranslator(source='auto', target='es').translate(texto)
            except Exception:
                texto_es = texto
            traducidos.append(f"{emoji} {texto_es}")
        return traducidos
    except Exception as e:
        print(f"Fallo traduccion: {e}")
        return titulares_con_prefijo


def obtener_noticias_geopoliticas(desde, hasta):
    api_key = os.getenv('NEWS_API_KEY')
    if not api_key:
        return ["NEWS_API_KEY no configurada."], []

    query = '(war OR conflict OR fed OR fomc OR "interest rates" OR inflation OR recession) AND (economy OR market OR gold OR oil)'
    url = (
        f'https://newsapi.org/v2/everything'
        f'?q={query}&from={desde}&to={hasta}'
        f'&sortBy=publishedAt&pageSize=8&apiKey={api_key}'
    )

    titulares = []
    raw_titulares = []
    keywords_guerra = ['war', 'attack', 'missile', 'conflict', 'strike', 'troops', 'invasion']
    keywords_fed = ['fed', 'fomc', 'rate', 'powell', 'inflation', 'cpi', 'pce']

    try:
        res = requests.get(url, timeout=30)
        res.raise_for_status()
        articulos = res.json().get('articles', [])
        for art in articulos[:6]:
            titulo = art.get('title') or 'Sin titulo'
            titulo_limpio = titulo.split(' - ')[0].strip()
            titulo_lower = titulo_limpio.lower()
            raw_titulares.append(titulo_lower)
            if any(w in titulo_lower for w in keywords_guerra):
                prefix = "\u2694\ufe0f"
            elif any(w in titulo_lower for w in keywords_fed):
                prefix = "\U0001f3db\ufe0f"
            else:
                prefix = "\U0001f4f0"
            titulares.append(f"{prefix} {titulo_limpio}")
    except requests.exceptions.HTTPError as e:
        return [f"Error NewsAPI HTTP {e.response.status_code}"], []
    except Exception as e:
        return [f"Fallo noticias: {str(e)}"], []

    if not titulares:
        return ["Panorama geopolitico en calma aparente."], []

    titulares = traducir_titulares(titulares)
    return titulares, raw_titulares


def obtener_calendario_alto_impacto(desde, hasta):
    api_key = os.getenv('FINNHUB_API_KEY')
    if not api_key:
        return ["FINNHUB_API_KEY no configurada."], []

    url = f'https://finnhub.io/api/v1/calendar/economic?from={desde}&to={hasta}&token={api_key}'

    eventos_formateados = []
    raw_eventos = []
    try:
        res = requests.get(url, timeout=30)
        res.raise_for_status()
        eventos = res.json().get('economicCalendar', [])
        eventos_alto = [e for e in eventos if e.get('impact', '').lower() == 'high']
        for e in eventos_alto[:10]:
            pais = e.get('country', '??').upper()
            evento = e.get('event', 'Evento desconocido')
            fecha = e.get('time', '') or 'TBD'
            prev = e.get('prev', '')
            est = e.get('estimate', '')
            raw_eventos.append(f"{pais}: {evento} (Est: {est}, Prev: {prev})")
            try:
                dt = datetime.strptime(fecha[:10], '%Y-%m-%d')
                fecha_fmt = dt.strftime('%a %d/%m').capitalize()
            except Exception:
                fecha_fmt = fecha[:10]
            linea = f"\U0001f534 **{fecha_fmt}** | {pais}: {evento}"
            if est:
                linea += f" | Est: {est}"
            if prev:
                linea += f" | Prev: {prev}"
            eventos_formateados.append(linea)
    except requests.exceptions.HTTPError as e:
        return [f"Error FinnHub HTTP {e.response.status_code}"], []
    except Exception as e:
        return [f"Fallo calendario: {str(e)}"], []

    if not eventos_formateados:
        return ["Sin eventos de alto impacto esta semana."], []

    return eventos_formateados, raw_eventos


def obtener_recomendaciones_ia(raw_titulares, raw_eventos, desde_noticias, hasta_noticias):
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        return (
            "SESGO NO DISPONIBLE",
            {"XAUUSD": ["ANTHROPIC_API_KEY no configurada."], "US30": [], "NAS100": []},
            0x888888
        )

    noticias_texto = "\n".join(raw_titulares) if raw_titulares else "Sin noticias disponibles."
    calendario_texto = "\n".join(raw_eventos) if raw_eventos else "Sin eventos de alto impacto."

    prompt_usuario = (
        f"Aqui estan los datos recopilados por el agente Sentinel esta semana:\n\n"
        f"NOTICIAS MACRO Y GEOPOLITICAS ({desde_noticias} a {hasta_noticias}):\n"
        f"{noticias_texto}\n\n"
        f"CALENDARIO ECONOMICO DE ALTO IMPACTO (proximos dias):\n"
        f"{calendario_texto}\n\n"
        f"Con base en esta informacion proporciona:\n"
        f"1. Una linea de SESGO SEMANAL.\n"
        f"2. Recomendaciones concretas de trading para esta semana.\n\n"
        f"Usa exactamente este formato (respeta los prefijos):\n"
        f"SESGO: [tu sesgo aqui]\n\n"
        f"XAUUSD: [recomendacion oro]\n"
        f"US30: [recomendacion dow jones]\n"
        f"NAS100: [recomendacion nasdaq 100]\n\n"
        f"Maximo 3 oraciones por instrumento. Se directo y accionable."
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=2048,
            system=(
                "Eres un analista de mercados financieros con 35 anos de experiencia y un CI de 180. "
                "Interpreta las noticias recopiladas y da recomendaciones para los instrumentos solicitados. "
                "Responde siempre en espanol. Se preciso, directo y profesional. "
                "Usa exactamente los prefijos SESGO:, XAUUSD:, US30:, NAS100: en tu respuesta."
            ),
            messages=[{"role": "user", "content": prompt_usuario}]
        )

        respuesta = message.content[0].text.strip()
        lineas = respuesta.split('\n')

        # Extraer sesgo
        sesgo_linea = next((l for l in lineas if l.upper().startswith('SESGO:')), None)
        sesgo = sesgo_linea.split(':', 1)[1].strip() if sesgo_linea else "Ver recomendaciones abajo"

        # Parsear cada instrumento en su propio bloque
        instrumentos = ['XAUUSD', 'US30', 'NAS100']
        bloques = {k: [] for k in instrumentos}
        clave_actual = None

        for linea in lineas:
            if linea.upper().startswith('SESGO:'):
                continue
            for inst in instrumentos:
                if linea.upper().startswith(inst + ':') or linea.upper().startswith(inst + ' '):
                    clave_actual = inst
                    break
            if clave_actual:
                bloques[clave_actual].append(linea.strip())

        bloque_1 = ('\n\n'.join([
            '\n'.join(bloques['XAUUSD']),
            '\n'.join(bloques['US30'])
        ])).strip()

        bloque_2 = '\n'.join(bloques['NAS100']).strip()

        # Fallback si el parseo fallo
        if not bloque_1 and not bloque_2:
            recomendaciones_full = '\n'.join(
                l for l in lineas if not l.upper().startswith('SESGO:') and l.strip()
            ).strip()
            mitad = len(recomendaciones_full) // 2
            bloque_1 = recomendaciones_full[:mitad]
            bloque_2 = recomendaciones_full[mitad:]

        # Color segun sesgo
        sesgo_lower = sesgo.lower()
        if any(w in sesgo_lower for w in ['extremo', 'guerra', 'war', 'critico']):
            color = 0x7B0000
        elif any(w in sesgo_lower for w in ['risk-off', 'bajista', 'tension', 'conflict']):
            color = 0x990000
        elif any(w in sesgo_lower for w in ['fed', 'macro', 'volatil', 'inflacion']):
            color = 0x0055FF
        elif any(w in sesgo_lower for w in ['alcista', 'bullish', 'positivo']):
            color = 0x00AA44
        else:
            color = 0x2B2D31

        return f"\U0001f916 {sesgo}", bloques, color

    except Exception as e:
        return (
            "Error IA",
            {"XAUUSD": [f"No se pudieron obtener recomendaciones de Claude: {str(e)}"], "US30": [], "NAS100": []},
            0x888888
        )


def ejecutar_agente():
    webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
    if not webhook_url:
        print("DISCORD_WEBHOOK_URL no configurada. Abortando.")
        return

    ahora = datetime.now(TIJUANA_TZ).strftime('%d/%m/%Y %H:%M')
    domingo_pasado, hoy_str, proximo_domingo = calcular_ventanas()

    print(f"Noticias: {domingo_pasado} -> {hoy_str}")
    print(f"Calendario: {hoy_str} -> {proximo_domingo}")

    noticias, raw_titulares = obtener_noticias_geopoliticas(domingo_pasado, hoy_str)
    resultado_calendario = obtener_calendario_alto_impacto(hoy_str, proximo_domingo)

    if isinstance(resultado_calendario, tuple):
        calendario, raw_eventos = resultado_calendario
    else:
        calendario = resultado_calendario
        raw_eventos = []

    sesgo, bloques, color = obtener_recomendaciones_ia(
        raw_titulares, raw_eventos, domingo_pasado, hoy_str
    )

    def safe_value(lista):
        texto = "\n".join(lista)
        return texto[:1024] if texto else "Sin datos disponibles."

    fields = [
        {
            "name": f"\U0001f30d CAPA 1 \u2014 Noticias Macro & Geopoliticas (Dom {domingo_pasado} \u2192 Hoy)",
            "value": safe_value(noticias),
            "inline": False
        },
        {
            "name": f"\U0001f4c5 CAPA 2 \u2014 Calendario Alto Impacto (Hoy \u2192 Dom {proximo_domingo})",
            "value": safe_value(calendario),
            "inline": False
        },
        {
            "name": "\U0001f3af CAPA 3 \u2014 Sesgo Semanal IA",
            "value": f"**{sesgo}**",
            "inline": False
        },
        {
            "name": "\U0001f4cc Recomendaciones \u2014 XAUUSD (Claude AI)",
            "value": ('\n'.join(bloques.get('XAUUSD', [])))[:1024] or "Sin datos.",
            "inline": False
        },
        {
            "name": "\U0001f4cc Recomendaciones \u2014 US30 (Claude AI)",
            "value": ('\n'.join(bloques.get('US30', [])))[:1024] or "Sin datos.",
            "inline": False
        },
        {
            "name": "\U0001f4cc Recomendaciones \u2014 NAS100 (Claude AI)",
            "value": ('\n'.join(bloques.get('NAS100', [])))[:1024] or "Sin datos.",
            "inline": False
        },
    ]

    payload = {
        "content": "@everyone \U0001f6f0\ufe0f **Sentinel v2.2: Reporte Semanal de Inteligencia**",
        "embeds": [{
            "title": f"\U0001f6e1\ufe0f INTELIGENCIA DE MERCADO | {ahora} (Tijuana)",
            "color": color,
            "fields": fields,
            "footer": {"text": "Sentinel v2.2 | Tijuana Local Time | Datos: NewsAPI + FinnHub | IA: Claude Sonnet"}
        }]
    }

    try:
        r = requests.post(webhook_url, json=payload, timeout=15)
        if r.status_code == 204:
            print("Reporte enviado correctamente a Discord.")
        else:
            print(f"Discord respondio con codigo {r.status_code}: {r.text}")
    except Exception as e:
        print(f"Error enviando a Discord: {str(e)}")


if __name__ == "__main__":
    ejecutar_agente()
