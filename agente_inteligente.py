import os
import math
import requests
import anthropic
import pytz
from datetime import datetime, timedelta

TIJUANA_TZ = pytz.timezone('America/Tijuana')

# ─────────────────────────────────────────────────────────────
# Fuente de precios: Twelve Data — solo XAUUSD (oro spot)
# Temporalidad M15, 7 días.
# ─────────────────────────────────────────────────────────────

M15_VELAS_POR_DIA  = 96
M15_DIAS           = 7
M15_TOTAL_VELAS    = M15_VELAS_POR_DIA * M15_DIAS
EMA_RAPIDA         = 50
EMA_LENTA          = 200
RSI_PERIODO        = 14
ATR_PERIODO        = 14

TWELVE_DATA_SYMBOLS = {
    "XAUUSD": {
        "candidatos": [("XAU/USD", "forex")],
    },
}


# ════════════════════════════════════════════════════════════
#  UTILIDADES DE FECHA
# ════════════════════════════════════════════════════════════
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


# ════════════════════════════════════════════════════════════
#  CAPA 0 — PRECIOS Y ANÁLISIS TÉCNICO (solo XAUUSD)
# ════════════════════════════════════════════════════════════
def diagnosticar_twelve_data() -> str:
    api_key = os.getenv('TWELVE_DATA_API_KEY')
    if not api_key:
        return "TWELVE_DATA_API_KEY no está definida en las variables de entorno."
    try:
        r = requests.get(
            f"https://api.twelvedata.com/api_usage?apikey={api_key}",
            timeout=10
        )
        if r.status_code == 403:
            return f"HTTP 403 — posible bloqueo de red. Body: {r.text[:120]}"
        if r.status_code == 401:
            return "HTTP 401 — API key inválida o expirada."
        if r.status_code != 200:
            return f"HTTP {r.status_code} inesperado. Body: {r.text[:120]}"
        data = r.json()
        if data.get('status') == 'error':
            return f"Twelve Data error: {data.get('message', 'desconocido')}"
        plan  = data.get('plan', '?')
        usado = data.get('current_usage', '?')
        limit = data.get('daily_limit', '?')
        print(f"  🔑 Twelve Data OK — plan={plan} | uso hoy={usado}/{limit}")
        return 'ok'
    except requests.exceptions.ConnectionError as e:
        return f"Sin conexión a api.twelvedata.com: {e}"
    except Exception as e:
        return f"Error inesperado: {type(e).__name__}: {e}"


def obtener_candles_twelvedata(simbolo: str, tipo: str, dias: int = M15_DIAS) -> list[dict]:
    api_key = os.getenv('TWELVE_DATA_API_KEY')
    if not api_key:
        return []

    outputsize = 700 if tipo == 'forex' else 250

    url = (
        f"https://api.twelvedata.com/time_series"
        f"?symbol={simbolo}"
        f"&interval=15min"
        f"&outputsize={outputsize}"
        f"&timezone=UTC"
        f"&apikey={api_key}"
    )

    try:
        res = requests.get(url, timeout=30)

        if res.status_code == 403 and 'allowlist' in res.text.lower():
            print(f"  🚫 {simbolo}: dominio bloqueado por proxy de red.")
            return []
        if res.status_code == 401:
            print(f"  🔑 {simbolo}: API key inválida o expirada.")
            return []

        res.raise_for_status()
        data = res.json()

        if data.get('status') == 'error':
            codigo = data.get('code', '?')
            msg    = data.get('message', 'desconocido')
            print(f"  ⚠️  Twelve Data [{simbolo}] error {codigo}: {msg}")
            return []

        valores = data.get('values', [])
        if not valores:
            print(f"  ⚠️  Twelve Data: sin valores para {simbolo}")
            return []

        fecha_limite = datetime.utcnow() - timedelta(days=dias)
        candles = []
        for v in reversed(valores):
            try:
                dt = datetime.strptime(v['datetime'], '%Y-%m-%d %H:%M:%S')
            except ValueError:
                dt = datetime.strptime(v['datetime'], '%Y-%m-%d')
            if dt < fecha_limite:
                continue
            candles.append({
                'datetime': v['datetime'],
                'open':     float(v['open']),
                'high':     float(v['high']),
                'low':      float(v['low']),
                'close':    float(v['close']),
                'volume':   float(v.get('volume', 0) or 0),
            })

        if not candles:
            primera = valores[-1]['datetime'] if valores else '?'
            ultima  = valores[0]['datetime']  if valores else '?'
            print(f"  ⚠️  {simbolo}: {len(valores)} velas fuera del rango ({primera} → {ultima}).")
            return []

        print(f"  📥 {simbolo}: {len(candles)} velas M15 | "
              f"{candles[0]['datetime']} → {candles[-1]['datetime']}")
        return candles

    except requests.exceptions.ConnectionError as e:
        print(f"  ❌ {simbolo}: sin conexión — {e}")
        return []
    except requests.exceptions.Timeout:
        print(f"  ❌ {simbolo}: timeout >30s")
        return []
    except Exception as e:
        print(f"  ❌ {simbolo}: {type(e).__name__}: {e}")
        return []


# ════════════════════════════════════════════════════════════
#  INDICADORES TÉCNICOS
# ════════════════════════════════════════════════════════════
def calcular_ema(precios: list[float], periodo: int) -> list[float]:
    if len(precios) < periodo:
        return []
    k = 2 / (periodo + 1)
    ema = [sum(precios[:periodo]) / periodo]
    for precio in precios[periodo:]:
        ema.append(precio * k + ema[-1] * (1 - k))
    return ema


def calcular_rsi(precios: list[float], periodo: int = 14) -> float | None:
    if len(precios) < periodo + 1:
        return None
    ganancias, perdidas = [], []
    for i in range(1, len(precios)):
        diff = precios[i] - precios[i - 1]
        ganancias.append(max(diff, 0))
        perdidas.append(max(-diff, 0))
    avg_g = sum(ganancias[-periodo:]) / periodo
    avg_p = sum(perdidas[-periodo:]) / periodo
    if avg_p == 0:
        return 100.0
    return round(100 - (100 / (1 + avg_g / avg_p)), 2)


def calcular_atr(candles: list[dict], periodo: int = 14) -> float:
    trs = []
    for i in range(1, len(candles)):
        h  = candles[i]['high']
        l  = candles[i]['low']
        pc = candles[i - 1]['close']
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if not trs:
        return 0.0
    return round(sum(trs[-periodo:]) / min(len(trs), periodo), 4)


def calcular_perfil_volumen(candles: list[dict], tick: float = 1.0) -> dict:
    """
    Perfil de Volumen de Rango Fijo anclado exactamente al rango de precios observado.
    bucket_size = $1 (tick operativo de XAUUSD).
    El histograma va de floor(precio_min) a ceil(precio_max) — sin buckets vacíos fuera del rango.
    HVN/LVN se detectan solo en el rango interior (excluyendo 5% de cada extremo).
    """
    if not candles:
        return {}

    import math as _math
    precio_min = min(c['low']  for c in candles)
    precio_max = max(c['high'] for c in candles)
    if precio_max - precio_min == 0:
        return {}

    # Anclar exactamente al rango real — sin desplazamiento por alineación de tick
    p_ini       = float(_math.floor(precio_min))
    p_fin       = float(_math.ceil(precio_max))
    num_niveles = max(1, int((p_fin - p_ini) / tick) + 1)
    buckets     = [0.0] * num_niveles

    for c in candles:
        vol = c['volume'] if c['volume'] > 0 else (c['high'] - c['low'])
        if vol <= 0:
            vol = 1.0
        vela_rango = c['high'] - c['low']
        if vela_rango < 1e-8:
            idx = min(int((c['close'] - p_ini) / tick), num_niveles - 1)
            if 0 <= idx < num_niveles:
                buckets[idx] += vol
            continue
        b_ini = max(0,              int((c['low']  - p_ini) / tick))
        b_fin = min(num_niveles-1,  int((c['high'] - p_ini) / tick))
        for b in range(b_ini, b_fin + 1):
            b_low  = p_ini + b * tick
            b_high = b_low + tick
            overlap = max(0.0, min(c['high'], b_high) - max(c['low'], b_low))
            if overlap > 0:
                buckets[b] += vol * (overlap / vela_rango)

    vol_total = sum(buckets)
    if vol_total == 0:
        return {}

    # POC
    poc_idx   = buckets.index(max(buckets))
    poc_price = p_ini + (poc_idx + 0.5) * tick

    # Value Area (70% bilateral desde el POC)
    target = vol_total * 0.70
    acum   = buckets[poc_idx]
    lo, hi = poc_idx, poc_idx
    while acum < target and (lo > 0 or hi < num_niveles - 1):
        izq = buckets[lo-1] if lo > 0            else -1.0
        der = buckets[hi+1] if hi < num_niveles-1 else -1.0
        if izq >= der and lo > 0:
            lo -= 1; acum += buckets[lo]
        elif hi < num_niveles - 1:
            hi += 1; acum += buckets[hi]
        else:
            break
    val_price = p_ini + (lo + 0.5) * tick
    vah_price = p_ini + (hi + 0.5) * tick

    # HVN y LVN solo en rango interior (excluir 5% de cada extremo)
    margen = max(2, int(num_niveles * 0.05))
    hvn_lista, lvn_lista = [], []
    for i in range(margen, num_niveles - margen):
        v_prev, v_curr, v_next = buckets[i-1], buckets[i], buckets[i+1]
        precio_c = p_ini + (i + 0.5) * tick
        if v_curr > v_prev and v_curr > v_next:
            hvn_lista.append((v_curr, precio_c))
        if v_curr > 0 and v_curr < v_prev and v_curr < v_next:
            lvn_lista.append((v_curr, precio_c))

    hvn_lista.sort(reverse=True)
    lvn_lista.sort()
    hvn_prices = sorted(round(p, 2) for _, p in hvn_lista[:4])
    lvn_prices = sorted(round(p, 2) for _, p in lvn_lista[:4])

    return {
        'poc':        round(poc_price, 2),
        'vah':        round(vah_price, 2),
        'val':        round(val_price, 2),
        'hvn':        hvn_prices,
        'lvn':        lvn_prices,
        'rango_min':  round(precio_min, 2),
        'rango_max':  round(precio_max, 2),
        'num_niveles': num_niveles,
    }


def analizar_tendencia(candles: list[dict]) -> str:
    if len(candles) < EMA_RAPIDA + 1:
        return f"insuficientes datos (se necesitan ≥{EMA_RAPIDA + 1} velas M15)"
    closes = [c['close'] for c in candles]
    ema_r  = calcular_ema(closes, EMA_RAPIDA)
    ema_l  = calcular_ema(closes, min(EMA_LENTA, len(closes)))
    slope  = closes[-1] - closes[max(0, len(closes) - M15_VELAS_POR_DIA)]
    if ema_r and ema_l:
        if ema_r[-1] > ema_l[-1] and slope > 0:
            return f"alcista (EMA{EMA_RAPIDA} > EMA{EMA_LENTA}, pendiente positiva en M15)"
        elif ema_r[-1] < ema_l[-1] and slope < 0:
            return f"bajista (EMA{EMA_RAPIDA} < EMA{EMA_LENTA}, pendiente negativa en M15)"
        elif ema_r[-1] > ema_l[-1]:
            return f"alcista estructural / pullback intradiario (EMA{EMA_RAPIDA} > EMA{EMA_LENTA})"
        else:
            return f"bajista estructural / rebote intradiario (EMA{EMA_RAPIDA} < EMA{EMA_LENTA})"
    return "lateral (datos insuficientes para EMAs completas)"


def obtener_analisis_tecnico_instrumentos() -> tuple[dict, str]:
    """Solo XAUUSD vía Twelve Data."""
    print("🔍 Verificando Twelve Data...")
    diag = diagnosticar_twelve_data()
    if diag != 'ok':
        msg = f"⚠️ Twelve Data no disponible: {diag}"
        print(f"  {msg}")
        return {}, msg

    resumen_dict  = {}
    bloques_texto = []

    for instrumento, cfg in TWELVE_DATA_SYMBOLS.items():
        candidatos = cfg['candidatos']
        candles    = []
        simbolo_ok = None
        tipo_ok    = None

        for simbolo, tipo in candidatos:
            print(f"  🔎 {instrumento}: probando {simbolo} ({tipo})...")
            candles = obtener_candles_twelvedata(simbolo, tipo, dias=M15_DIAS)
            if candles:
                simbolo_ok = simbolo
                tipo_ok    = tipo
                break
            print(f"     ↳ Sin datos para {simbolo}.")

        if not candles:
            candidatos_str = ", ".join(s for s, _ in candidatos)
            resumen_dict[instrumento] = {'error': f'Sin datos ({candidatos_str})'}
            bloques_texto.append(f"{instrumento}: Sin datos disponibles.")
            continue

        closes        = [c['close'] for c in candles]
        precio_actual = closes[-1]
        precio_inicio = closes[0]
        cambio_pct    = round(((precio_actual - precio_inicio) / precio_inicio) * 100, 2)

        tendencia = analizar_tendencia(candles)
        rsi       = calcular_rsi(closes, RSI_PERIODO)
        atr       = calcular_atr(candles, ATR_PERIODO)
        # Perfil de Volumen de Rango Fijo: $1 por bucket (resolución operativa XAUUSD)
        perfil    = calcular_perfil_volumen(candles)

        if rsi is not None:
            if rsi > 70:   rsi_interp = "sobrecomprado"
            elif rsi < 30: rsi_interp = "sobrevendido"
            else:          rsi_interp = "neutral"
        else:
            rsi_interp = "N/A"

        resumen_dict[instrumento] = {
            'simbolo_fuente': simbolo_ok,
            'precio_actual':  precio_actual,
            'cambio_7d_pct':  cambio_pct,
            'tendencia':      tendencia,
            'rsi':            rsi,
            'rsi_interp':     rsi_interp,
            'atr_m15':        atr,
            'perfil_volumen': perfil,
            'num_velas':      len(candles),
        }

        hvn_str       = ", ".join(str(p) for p in perfil.get('hvn', [])) or "N/A"
        lvn_str       = ", ".join(str(p) for p in perfil.get('lvn', [])) or "N/A"
        muestra_velas = candles[-8:]

        bloque = (
            f"=== {instrumento} ({simbolo_ok}) — Temporalidad M15 ===\n"
            f"Fuente: Twelve Data | Velas: {len(candles)} M15 ({M15_DIAS} días)\n"
            f"Rango 7d: {perfil.get('rango_min', 'N/A')} – {perfil.get('rango_max', 'N/A')}\n"
            f"Precio actual (último cierre M15): {precio_actual}\n"
            f"Cambio 7d: {cambio_pct:+.2f}%\n"
            f"Tendencia (EMA{EMA_RAPIDA}/EMA{EMA_LENTA} M15): {tendencia}\n"
            f"RSI({RSI_PERIODO}) M15: {rsi} ({rsi_interp})\n"
            f"ATR({ATR_PERIODO}) M15: {atr}\n"
            f"Perfil de Volumen:\n"
            f"  POC (Point of Control): {perfil.get('poc', 'N/A')}\n"
            f"  VAH (Value Area High):  {perfil.get('vah', 'N/A')}\n"
            f"  VAL (Value Area Low):   {perfil.get('val', 'N/A')}\n"
            f"  HVN (soporte/resistencia fuerte): {hvn_str}\n"
            f"  LVN (zona de baja liquidez):      {lvn_str}\n"
            f"Últimas 8 velas M15:\n"
        )
        for c in muestra_velas:
            bloque += f"  {c['datetime']}: O={c['open']} H={c['high']} L={c['low']} C={c['close']}\n"

        bloques_texto.append(bloque)
        print(f"  ✅ {instrumento}: precio={precio_actual} | RSI={rsi} | "
              f"POC={perfil.get('poc','?')} | buckets=${perfil.get('bucket_size','?')} × {perfil.get('num_niveles','?')} | velas={len(candles)}")

    return resumen_dict, "\n\n".join(bloques_texto)


# ════════════════════════════════════════════════════════════
#  CAPA 1 — NOTICIAS
# ════════════════════════════════════════════════════════════
def traducir_titulares(titulares_con_prefijo):
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

    titulares     = []
    raw_titulares = []
    keywords_guerra = ['war', 'attack', 'missile', 'conflict', 'strike', 'troops', 'invasion']
    keywords_fed    = ['fed', 'fomc', 'rate', 'powell', 'inflation', 'cpi', 'pce']

    try:
        res = requests.get(url, timeout=30)
        res.raise_for_status()
        articulos = res.json().get('articles', [])
        for art in articulos[:6]:
            titulo        = art.get('title') or 'Sin titulo'
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
        return [f"Error NewsAPI HTTP {e.response.status_code}"], []
    except Exception as e:
        return [f"Fallo noticias: {str(e)}"], []

    if not titulares:
        return ["Panorama geopolitico en calma aparente."], []

    titulares = traducir_titulares(titulares)
    return titulares, raw_titulares


# ════════════════════════════════════════════════════════════
#  CAPA 2 — CALENDARIO ECONÓMICO
# ════════════════════════════════════════════════════════════
def obtener_calendario_alto_impacto(desde, hasta):
    api_key = os.getenv('FINNHUB_API_KEY')
    if not api_key:
        return ["FINNHUB_API_KEY no configurada."], []

    url = f'https://finnhub.io/api/v1/calendar/economic?from={desde}&to={hasta}&token={api_key}'

    eventos_formateados = []
    raw_eventos         = []
    try:
        res = requests.get(url, timeout=30)
        res.raise_for_status()
        eventos      = res.json().get('economicCalendar', [])
        eventos_alto = [e for e in eventos if e.get('impact', '').lower() == 'high']
        for e in eventos_alto[:10]:
            pais   = e.get('country', '??').upper()
            evento = e.get('event', 'Evento desconocido')
            fecha  = e.get('time', '') or 'TBD'
            prev   = e.get('prev', '')
            est    = e.get('estimate', '')
            raw_eventos.append(f"{pais}: {evento} (Est: {est}, Prev: {prev})")
            try:
                dt        = datetime.strptime(fecha[:10], '%Y-%m-%d')
                fecha_fmt = dt.strftime('%a %d/%m').capitalize()
            except Exception:
                fecha_fmt = fecha[:10]
            linea = f"🔴 **{fecha_fmt}** | {pais}: {evento}"
            if est:  linea += f" | Est: {est}"
            if prev: linea += f" | Prev: {prev}"
            eventos_formateados.append(linea)
    except requests.exceptions.HTTPError as e:
        return [f"Error FinnHub HTTP {e.response.status_code}"], []
    except Exception as e:
        return [f"Fallo calendario: {str(e)}"], []

    if not eventos_formateados:
        return ["Sin eventos de alto impacto esta semana."], []

    return eventos_formateados, raw_eventos


# ════════════════════════════════════════════════════════════
#  CAPA 3 — RECOMENDACIONES IA (solo XAUUSD)
# ════════════════════════════════════════════════════════════
def obtener_recomendaciones_ia(
    raw_titulares: list,
    raw_eventos: list,
    analisis_tecnico_texto: str,
    desde_noticias: str,
    hasta_noticias: str,
):
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        return (
            "SESGO NO DISPONIBLE",
            {"XAUUSD": ["ANTHROPIC_API_KEY no configurada."]},
            0x888888
        )

    noticias_texto   = "\n".join(raw_titulares) if raw_titulares else "Sin noticias disponibles."
    calendario_texto = "\n".join(raw_eventos)   if raw_eventos   else "Sin eventos de alto impacto."

    prompt_usuario = (
        f"Eres el agente Sentinel. Tienes acceso a tres capas de información:\n\n"
        f"══ CAPA 1: NOTICIAS MACRO & GEOPOLÍTICAS ({desde_noticias} → {hasta_noticias}) ══\n"
        f"{noticias_texto}\n\n"
        f"══ CAPA 2: CALENDARIO ECONÓMICO DE ALTO IMPACTO (próximos días) ══\n"
        f"{calendario_texto}\n\n"
        f"══ CAPA 3: ANÁLISIS TÉCNICO + PERFIL DE VOLUMEN XAUUSD (últimos 7 días, datos reales) ══\n"
        f"{analisis_tecnico_texto}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"INSTRUCCIONES:\n"
        f"1. Los rangos de precio DEBEN ser coherentes con los precios reales de la Capa 3.\n"
        f"2. Usa HVN como soporte/resistencia, LVN como zonas de aceleración, POC como equilibrio.\n"
        f"3. Máximo 3 oraciones. Directo y accionable.\n\n"
        f"FORMATO OBLIGATORIO — responde EXACTAMENTE así, sin texto adicional antes ni después:\n\n"
        f"SESGO: <sesgo en una línea enfocado en oro y contexto macro>\n"
        f"---\n"
        f"XAUUSD: <recomendación con entrada, objetivo y stop loss exactos>\n"
    )

    try:
        client  = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            system=(
                "Eres un analista de mercados financieros especializado en oro (XAUUSD) "
                "con 35 años de experiencia. Combinas análisis técnico (EMA, RSI, ATR, "
                "perfil de volumen con HVN/LVN/POC/VAH/VAL) con análisis macro y geopolítico. "
                "REGLA CRÍTICA: Los rangos de precio deben ser 100% coherentes con los precios "
                "reales del análisis técnico proporcionado. Nunca uses rangos obsoletos. "
                "Responde siempre en español. Sé preciso, directo y profesional. "
                "Usa exactamente los prefijos SESGO: y XAUUSD: en tu respuesta."
            ),
            messages=[{"role": "user", "content": prompt_usuario}]
        )

        respuesta = message.content[0].text.strip()
        sesgo     = "Ver recomendación abajo"
        bloques   = {'XAUUSD': []}

        # Parser primario: delimitador '---'
        secciones = respuesta.split('---')
        for seccion in secciones:
            seccion = seccion.strip()
            if not seccion:
                continue
            if seccion.upper().startswith('SESGO:'):
                sesgo = seccion.split(':', 1)[1].strip()
            elif seccion.upper().startswith('XAUUSD:'):
                bloques['XAUUSD'] = [seccion.strip()]

        # Fallback: parseo línea a línea
        if not any(bloques.values()):
            clave_actual = None
            for linea in respuesta.split('\n'):
                linea_up = linea.upper().strip()
                if linea_up.startswith('SESGO:'):
                    sesgo        = linea.split(':', 1)[1].strip()
                    clave_actual = None
                    continue
                if linea_up.startswith('XAUUSD:') or linea_up.startswith('XAUUSD '):
                    clave_actual = 'XAUUSD'
                    bloques['XAUUSD'] = [linea.strip()]
                    continue
                if clave_actual and linea.strip():
                    bloques[clave_actual].append(linea.strip())

        # Color según sesgo
        sesgo_lower = sesgo.lower()
        if any(w in sesgo_lower for w in ['extremo', 'guerra', 'war', 'critico']):
            color = 0x7B0000
        elif any(w in sesgo_lower for w in ['risk-off', 'bajista', 'tension', 'conflict', 'defensivo']):
            color = 0x990000
        elif any(w in sesgo_lower for w in ['fed', 'macro', 'volatil', 'inflacion']):
            color = 0x0055FF
        elif any(w in sesgo_lower for w in ['alcista', 'bullish', 'positivo']):
            color = 0x00AA44
        else:
            color = 0x2B2D31

        return f"🤖 {sesgo}", bloques, color

    except Exception as e:
        return (
            "Error IA",
            {"XAUUSD": [f"No se pudieron obtener recomendaciones: {str(e)}"]},
            0x888888
        )


# ════════════════════════════════════════════════════════════
#  ENVÍO A DISCORD
# ════════════════════════════════════════════════════════════
def formatear_campo_tecnico(datos: dict) -> str:
    """Resumen Capa 0 XAUUSD para Discord: POC, VAH, VAL, HVN, LVN."""
    if 'error' in datos:
        return f"⚠️ {datos['error']}"
    pv  = datos.get('perfil_volumen', {})
    hvn = ", ".join(str(p) for p in pv.get('hvn', [])) or "N/A"
    lvn = ", ".join(str(p) for p in pv.get('lvn', [])) or "N/A"
    return (
        f"💲 **XAUUSD** — **{datos['precio_actual']}** ({datos['cambio_7d_pct']:+.2f}% 7d) | {datos.get('num_velas','?')} velas M15\n"
        f"📈 {datos['tendencia']}\n"
        f"🗂️ POC: **{pv.get('poc','N/A')}** | VAH: {pv.get('vah','N/A')} | VAL: {pv.get('val','N/A')}\n"
        f"🟢 HVN: {hvn}\n"
        f"🔸 LVN: {lvn}"
    )[:1024]


def ejecutar_agente():
    webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
    if not webhook_url:
        print("DISCORD_WEBHOOK_URL no configurada. Abortando.")
        return

    ahora = datetime.now(TIJUANA_TZ).strftime('%d/%m/%Y %H:%M')
    domingo_pasado, hoy_str, proximo_domingo = calcular_ventanas()

    print(f"📅 Noticias: {domingo_pasado} → {hoy_str}")
    print(f"📅 Calendario: {hoy_str} → {proximo_domingo}")

    # ── Capa 0: XAUUSD análisis técnico ─────────────────────
    print("🔍 Obteniendo precios y análisis técnico XAUUSD...")
    resumen_tecnico, analisis_tecnico_texto = obtener_analisis_tecnico_instrumentos()

    # ── Capa 1: Noticias ─────────────────────────────────────
    print("📰 Obteniendo noticias...")
    noticias, raw_titulares = obtener_noticias_geopoliticas(domingo_pasado, hoy_str)

    # ── Capa 2: Calendario ───────────────────────────────────
    print("📅 Obteniendo calendario económico...")
    resultado_calendario = obtener_calendario_alto_impacto(hoy_str, proximo_domingo)
    if isinstance(resultado_calendario, tuple):
        calendario, raw_eventos = resultado_calendario
    else:
        calendario, raw_eventos = resultado_calendario, []

    # ── Capa 3: IA ───────────────────────────────────────────
    print("🤖 Generando recomendación XAUUSD con Claude...")
    sesgo, bloques, color = obtener_recomendaciones_ia(
        raw_titulares, raw_eventos, analisis_tecnico_texto,
        domingo_pasado, hoy_str
    )

    def safe_value(lista):
        texto = "\n".join(lista)
        return texto[:1024] if texto else "Sin datos disponibles."

    # Capa 0 — XAUUSD
    datos_xau = resumen_tecnico.get('XAUUSD')
    if datos_xau:
        campo_capa0 = {
            "name":   "📊 CAPA 0 — XAUUSD (M15, 7d)",
            "value":  formatear_campo_tecnico(datos_xau),
            "inline": False
        }
    else:
        motivo = analisis_tecnico_texto or "Sin datos — revisar logs del servidor."
        campo_capa0 = {
            "name":   "📊 CAPA 0 — XAUUSD (M15)",
            "value":  f"⚠️ {motivo[:500]}",
            "inline": False
        }

    fields = [
        campo_capa0,
        {
            "name":   f"🌍 CAPA 1 — Noticias Macro & Geopolíticas (Dom {domingo_pasado} → Hoy)",
            "value":  safe_value(noticias),
            "inline": False
        },
        {
            "name":   f"📅 CAPA 2 — Calendario Alto Impacto (Hoy → Dom {proximo_domingo})",
            "value":  safe_value(calendario),
            "inline": False
        },
        {
            "name":   "🎯 CAPA 3 — Sesgo Semanal IA",
            "value":  f"**{sesgo}**",
            "inline": False
        },
        {
            "name":   "📌 Recomendaciones — XAUUSD (Claude AI)",
            "value":  ('\n'.join(bloques.get('XAUUSD', [])))[:1024] or "Sin datos.",
            "inline": False
        },
    ]

    payload = {
        "content": "@everyone 🛰️ **Sentinel v2.9: Reporte Semanal de Inteligencia**",
        "embeds": [{
            "title":  f"🛡️ INTELIGENCIA DE MERCADO — XAUUSD | {ahora} (Tijuana)",
            "color":  color,
            "fields": fields,
            "footer": {
                "text": "Sentinel v2.9 | Tijuana Local Time | Datos: NewsAPI + FinnHub + Twelve Data M15 | IA: Claude Sonnet"
            }
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
