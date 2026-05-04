import os
import requests
import anthropic
import pytz
from datetime import datetime, timedelta

TIJUANA_TZ = pytz.timezone('America/Tijuana')

# ─────────────────────────────────────────────────────────────
# Mapeo de símbolos internos → símbolo Twelve Data (candles M15)
# Twelve Data soporta estos símbolos nativamente en plan gratuito:
#   XAUUSD  → XAU/USD   (oro spot forex)
#   US30    → DJIA      (Dow Jones, requiere plan Basic+)
#             alternativa ETF: DIA (SPDR Dow Jones ETF, NYSE)
#   NAS100  → NDX       (Nasdaq 100 index)
#             alternativa ETF: QQQ (Invesco QQQ ETF, NASDAQ)
#
# Temporalidad: M15 (resolución 15 minutos)
# Rango: 7 días → ~480 velas reales (excluye fines de semana)
#   Forex XAU/USD: ~96 velas/día (24h) → ~480 en 5 días hábiles
#   Índices/ETFs:  ~26 velas/día (6.5h mercado USA) → ~130 en 5 días
# EMAs, RSI y ATR calculados sobre cierres de 15 minutos.
# ─────────────────────────────────────────────────────────────

# Constantes de temporalidad M15
M15_VELAS_POR_DIA  = 96   # máximo forex (24h × 4); índices usan menos (~26/día)
M15_DIAS           = 7
M15_TOTAL_VELAS    = M15_VELAS_POR_DIA * M15_DIAS  # techo, la API devuelve las reales
# Períodos de indicadores en unidades de velas M15
EMA_RAPIDA         = 50   # ≈ 12.5h  (equivalente a EMA12 en H4)
EMA_LENTA          = 200  # ≈ 50h    (equivalente a EMA50 en H4)
RSI_PERIODO        = 14   # estándar Wilder, sobre cierres M15
ATR_PERIODO        = 14   # estándar, sobre rangos verdaderos M15

# Twelve Data: símbolo principal y tipo de instrumento
# type: 'forex' usa /time_series directo; 'etf'/'stock' también usa /time_series
TWELVE_DATA_SYMBOLS = {
    "XAUUSD": {"symbol": "XAU/USD",  "tipo": "forex"},
    "US30":   {"symbol": "DIA",      "tipo": "etf"},    # SPDR Dow Jones ETF (proxy US30)
    "NAS100": {"symbol": "QQQ",      "tipo": "etf"},    # Invesco QQQ ETF (proxy NAS100)
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
#  CAPA 0 — PRECIOS Y ANÁLISIS TÉCNICO + PERFIL DE VOLUMEN
# ════════════════════════════════════════════════════════════
def obtener_candles_twelvedata(simbolo: str, tipo: str, dias: int = M15_DIAS) -> list[dict]:
    """
    Descarga velas M15 de los últimos `dias` días desde Twelve Data.
    Endpoint: /time_series?interval=15min&outputsize=N
    Plan gratuito: 8 req/min, 800 req/día.

    Twelve Data devuelve las velas en orden DESCENDENTE (más reciente primero).
    Esta función las invierte para dejarlas en orden cronológico ascendente.

    Retorna lista de dicts: datetime, open, high, low, close, volume.
    """
    api_key = os.getenv('TWELVE_DATA_API_KEY')
    if not api_key:
        print(f"  ⚠️  TWELVE_DATA_API_KEY no configurada")
        return []

    # Twelve Data usa outputsize para limitar cantidad de velas.
    # Pedimos el máximo razonable para cubrir 7 días:
    #   Forex: ~96 velas/día × 7 = 672 (pedimos 700 con margen)
    #   ETFs:  ~26 velas/día × 7 = 182 (pedimos 200 con margen)
    outputsize = 700 if tipo == 'forex' else 200

    # Para ETFs/stocks necesitamos especificar exchange para obtener M15 extendido
    exchange_param = ""
    if tipo == 'etf':
        exchange_param = "&exchange=NASDAQ"

    url = (
        f"https://api.twelvedata.com/time_series"
        f"?symbol={simbolo}"
        f"&interval=15min"
        f"&outputsize={outputsize}"
        f"&timezone=UTC"
        f"{exchange_param}"
        f"&apikey={api_key}"
    )

    try:
        res = requests.get(url, timeout=30)
        res.raise_for_status()
        data = res.json()

        # Twelve Data retorna {"status": "error", "message": "..."} en errores
        if data.get('status') == 'error':
            print(f"  ⚠️  Twelve Data error para {simbolo}: {data.get('message', 'desconocido')}")
            return []

        valores = data.get('values', [])
        if not valores:
            print(f"  ⚠️  Twelve Data: sin valores para {simbolo}")
            return []

        # Convertir y filtrar al rango de días solicitado
        fecha_limite = datetime.utcnow() - timedelta(days=dias)
        candles = []
        for v in reversed(valores):          # invertir: Twelve Data viene desc → asc
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

        print(f"  📥 {simbolo} ({tipo}): {len(candles)} velas M15 descargadas")
        return candles

    except Exception as e:
        print(f"  ❌ Error obteniendo candles M15 Twelve Data {simbolo}: {e}")
        return []


def calcular_ema(precios: list[float], periodo: int) -> list[float]:
    """Exponential Moving Average."""
    if len(precios) < periodo:
        return []
    k = 2 / (periodo + 1)
    ema = [sum(precios[:periodo]) / periodo]
    for precio in precios[periodo:]:
        ema.append(precio * k + ema[-1] * (1 - k))
    return ema


def calcular_rsi(precios: list[float], periodo: int = 14) -> float | None:
    """RSI clásico de Wilder."""
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
    rs = avg_g / avg_p
    return round(100 - (100 / (1 + rs)), 2)


def calcular_atr(candles: list[dict], periodo: int = 7) -> float:
    """Average True Range."""
    trs = []
    for i in range(1, len(candles)):
        h = candles[i]['high']
        l = candles[i]['low']
        pc = candles[i - 1]['close']
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    if not trs:
        return 0.0
    return round(sum(trs[-periodo:]) / min(len(trs), periodo), 4)


def calcular_perfil_volumen(candles: list[dict], num_niveles: int = 20) -> dict:
    """
    Volume Profile simplificado:
    - Divide el rango total en `num_niveles` buckets de precio.
    - Distribuye el volumen de cada vela proporcionalmente por rango.
    - Identifica HVN (High Volume Node) y LVN (Low Volume Node).
    Retorna dict con: hvn, lvn, poc (Point of Control), vah, val.
    """
    if not candles:
        return {}

    precio_min = min(c['low'] for c in candles)
    precio_max = max(c['high'] for c in candles)
    rango = precio_max - precio_min
    if rango == 0:
        return {}

    bucket_size = rango / num_niveles
    buckets = [0.0] * num_niveles

    for c in candles:
        vol = c['volume'] if c['volume'] > 0 else 1  # fallback para pares sin volumen real
        vela_rango = c['high'] - c['low']
        if vela_rango == 0:
            idx = int((c['close'] - precio_min) / bucket_size)
            idx = min(idx, num_niveles - 1)
            buckets[idx] += vol
            continue
        # Distribuir volumen de la vela entre los buckets que toca
        for b in range(num_niveles):
            b_low  = precio_min + b * bucket_size
            b_high = b_low + bucket_size
            overlap = max(0, min(c['high'], b_high) - max(c['low'], b_low))
            buckets[b] += vol * (overlap / vela_rango)

    vol_total = sum(buckets)
    if vol_total == 0:
        return {}

    # POC = bucket con mayor volumen
    poc_idx = buckets.index(max(buckets))
    poc_price = precio_min + (poc_idx + 0.5) * bucket_size

    # VAH / VAL: zona que contiene el 70% del volumen alrededor del POC
    acum, vah_idx, val_idx = 0, poc_idx, poc_idx
    target = vol_total * 0.70
    lo, hi = poc_idx, poc_idx
    while acum < target and (lo > 0 or hi < num_niveles - 1):
        expand_lo = buckets[lo - 1] if lo > 0 else 0
        expand_hi = buckets[hi + 1] if hi < num_niveles - 1 else 0
        if expand_lo >= expand_hi and lo > 0:
            lo -= 1
            acum += buckets[lo]
        elif hi < num_niveles - 1:
            hi += 1
            acum += buckets[hi]
        else:
            lo -= 1
            acum += buckets[lo]
    val_price = precio_min + (lo + 0.5) * bucket_size
    vah_price = precio_min + (hi + 0.5) * bucket_size

    # HVN: top 3 buckets fuera de la VA que también son picos locales
    hvn_buckets = sorted(
        [(i, v) for i, v in enumerate(buckets) if i < lo or i > hi],
        key=lambda x: x[1], reverse=True
    )[:3]
    hvn_prices = sorted([precio_min + (i + 0.5) * bucket_size for i, _ in hvn_buckets])

    # LVN: bottom 3 buckets (valles locales de volumen)
    lvn_buckets = sorted(
        [(i, v) for i, v in enumerate(buckets) if v > 0],
        key=lambda x: x[1]
    )[:3]
    lvn_prices = sorted([precio_min + (i + 0.5) * bucket_size for i, _ in lvn_buckets])

    return {
        'poc':  round(poc_price, 4),
        'vah':  round(vah_price, 4),
        'val':  round(val_price, 4),
        'hvn':  [round(p, 4) for p in hvn_prices],
        'lvn':  [round(p, 4) for p in lvn_prices],
        'rango_min': round(precio_min, 4),
        'rango_max': round(precio_max, 4),
    }


def analizar_tendencia(candles: list[dict]) -> str:
    """
    Tendencia basada en EMA50 vs EMA200 sobre cierres M15.
    EMA50  M15 ≈ 12.5 horas  (tendencia corto plazo intradía)
    EMA200 M15 ≈ 50 horas    (tendencia estructural de la semana)
    """
    if len(candles) < EMA_RAPIDA + 1:
        return f"insuficientes datos (se necesitan ≥{EMA_RAPIDA + 1} velas M15)"
    closes = [c['close'] for c in candles]
    ema_r  = calcular_ema(closes, EMA_RAPIDA)
    ema_l  = calcular_ema(closes, min(EMA_LENTA, len(closes)))
    slope  = closes[-1] - closes[max(0, len(closes) - M15_VELAS_POR_DIA)]  # pendiente del último día

    if ema_r and ema_l:
        if ema_r[-1] > ema_l[-1] and slope > 0:
            return f"alcista (EMA{EMA_RAPIDA} > EMA{EMA_LENTA}, pendiente positiva en M15)"
        elif ema_r[-1] < ema_l[-1] and slope < 0:
            return f"bajista (EMA{EMA_RAPIDA} < EMA{EMA_LENTA}, pendiente negativa en M15)"
        elif ema_r[-1] > ema_l[-1] and slope <= 0:
            return f"alcista estructural / pullback intradiario (EMA{EMA_RAPIDA} > EMA{EMA_LENTA})"
        else:
            return f"bajista estructural / rebote intradiario (EMA{EMA_RAPIDA} < EMA{EMA_LENTA})"
    return "lateral (datos insuficientes para EMAs completas)"


def obtener_analisis_tecnico_instrumentos() -> tuple[dict, str]:
    """
    Obtiene y analiza velas M15 (7 días) de cada instrumento via Twelve Data.
    Indicadores calculados en temporalidad M15:
      - EMA50 y EMA200 para tendencia
      - RSI(14) sobre cierres M15
      - ATR(14) sobre rangos verdaderos M15
      - Perfil de Volumen completo (POC, VAH, VAL, HVN, LVN)
    """
    api_key = os.getenv('TWELVE_DATA_API_KEY')
    if not api_key:
        return {}, "TWELVE_DATA_API_KEY no configurada – análisis técnico no disponible."

    resumen_dict = {}
    bloques_texto = []

    for instrumento, cfg in TWELVE_DATA_SYMBOLS.items():
        simbolo = cfg['symbol']
        tipo    = cfg['tipo']

        candles = obtener_candles_twelvedata(simbolo, tipo, dias=M15_DIAS)
        if not candles:
            resumen_dict[instrumento] = {'error': f'Sin datos de precio ({simbolo})'}
            bloques_texto.append(f"{instrumento}: Sin datos disponibles desde Twelve Data ({simbolo}).")
            continue

        closes        = [c['close'] for c in candles]
        precio_actual = closes[-1]
        precio_inicio = closes[0]
        cambio_pct    = round(((precio_actual - precio_inicio) / precio_inicio) * 100, 2)

        tendencia = analizar_tendencia(candles)
        rsi       = calcular_rsi(closes, RSI_PERIODO)
        atr       = calcular_atr(candles, ATR_PERIODO)
        perfil    = calcular_perfil_volumen(candles, num_niveles=40)

        # Interpretación RSI
        if rsi is not None:
            if rsi > 70:   rsi_interp = "sobrecomprado"
            elif rsi < 30: rsi_interp = "sobrevendido"
            else:          rsi_interp = "neutral"
        else:
            rsi_interp = "N/A"

        resumen_dict[instrumento] = {
            'simbolo_fuente': simbolo,
            'precio_actual':  precio_actual,
            'cambio_7d_pct':  cambio_pct,
            'tendencia':      tendencia,
            'rsi':            rsi,
            'rsi_interp':     rsi_interp,
            'atr_m15':        atr,
            'perfil_volumen': perfil,
            'num_velas':      len(candles),
        }

        # Texto para el prompt de Claude
        hvn_str = ", ".join(str(p) for p in perfil.get('hvn', [])) or "N/A"
        lvn_str = ", ".join(str(p) for p in perfil.get('lvn', [])) or "N/A"
        muestra_velas = candles[-8:]

        bloque = (
            f"=== {instrumento} ({simbolo}) — Temporalidad M15 ===\n"
            f"Fuente: Twelve Data | Velas procesadas: {len(candles)} M15 ({M15_DIAS} días)\n"
            f"Rango 7d: {perfil.get('rango_min', 'N/A')} – {perfil.get('rango_max', 'N/A')}\n"
            f"Precio actual (último cierre M15): {precio_actual}\n"
            f"Cambio 7d: {cambio_pct:+.2f}%\n"
            f"Tendencia (EMA{EMA_RAPIDA}/EMA{EMA_LENTA} en M15): {tendencia}\n"
            f"RSI({RSI_PERIODO}) M15: {rsi} ({rsi_interp})\n"
            f"ATR({ATR_PERIODO}) M15: {atr}  [volatilidad por vela de 15 min]\n"
            f"ATR diario estimado: ~{round(atr * M15_VELAS_POR_DIA, 4) if atr else 'N/A'}\n"
            f"Perfil de Volumen (7 días, 40 niveles):\n"
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
        print(f"  ✅ {instrumento}: precio={precio_actual} | RSI={rsi} | velas={len(candles)}")

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
    keywords_fed    = ['fed', 'fomc', 'rate', 'powell', 'inflation', 'cpi', 'pce']

    try:
        res = requests.get(url, timeout=30)
        res.raise_for_status()
        articulos = res.json().get('articles', [])
        for art in articulos[:6]:
            titulo = art.get('title') or 'Sin titulo'
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
    raw_eventos = []
    try:
        res = requests.get(url, timeout=30)
        res.raise_for_status()
        eventos = res.json().get('economicCalendar', [])
        eventos_alto = [e for e in eventos if e.get('impact', '').lower() == 'high']
        for e in eventos_alto[:10]:
            pais  = e.get('country', '??').upper()
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
        return [f"Error FinnHub HTTP {e.response.status_code}"], []
    except Exception as e:
        return [f"Fallo calendario: {str(e)}"], []

    if not eventos_formateados:
        return ["Sin eventos de alto impacto esta semana."], []

    return eventos_formateados, raw_eventos


# ════════════════════════════════════════════════════════════
#  CAPA 3 — RECOMENDACIONES IA (macro + técnico integrado)
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
            {"XAUUSD": ["ANTHROPIC_API_KEY no configurada."], "US30": [], "NAS100": []},
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
        f"══ CAPA 3: ANÁLISIS TÉCNICO + PERFIL DE VOLUMEN (últimos 7 días, datos reales) ══\n"
        f"{analisis_tecnico_texto}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"INSTRUCCIONES:\n"
        f"1. Sintetiza el contexto macro + técnico para cada instrumento.\n"
        f"2. Los rangos de precios en tus recomendaciones DEBEN ser coherentes con los precios "
        f"   actuales mostrados en la Capa 3 (precio actual y rango 7d). No inventes rangos.\n"
        f"3. Usa los niveles HVN como soporte/resistencia clave y LVN como zonas de aceleración.\n"
        f"4. El POC es el nivel de equilibrio; las operaciones se plantean desde VAH/VAL.\n\n"
        f"Responde EXACTAMENTE con este formato (respeta los prefijos):\n\n"
        f"SESGO: [sesgo semanal en una línea]\n\n"
        f"XAUUSD: [recomendación con niveles reales de entrada, objetivo y stop loss]\n"
        f"US30: [recomendación con niveles reales de entrada, objetivo y stop loss]\n"
        f"NAS100: [recomendación con niveles reales de entrada, objetivo y stop loss]\n\n"
        f"Máximo 3 oraciones por instrumento. Sé directo y accionable. "
        f"Los precios DEBEN reflejar los valores reales del mercado actual."
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=2048,
            system=(
                "Eres un analista de mercados financieros con 35 años de experiencia y un CI de 180. "
                "Combinas análisis técnico (EMA, RSI, ATR, perfil de volumen con HVN/LVN/POC/VAH/VAL) "
                "con análisis macro y geopolítico. "
                "REGLA CRÍTICA: Los rangos de precio en tus recomendaciones deben ser 100% coherentes "
                "con los precios reales proporcionados en el análisis técnico. Nunca uses rangos obsoletos. "
                "Responde siempre en español. Sé preciso, directo y profesional. "
                "Usa exactamente los prefijos SESGO:, XAUUSD:, US30:, NAS100: en tu respuesta."
            ),
            messages=[{"role": "user", "content": prompt_usuario}]
        )

        respuesta = message.content[0].text.strip()
        lineas    = respuesta.split('\n')

        # Extraer sesgo
        sesgo_linea = next((l for l in lineas if l.upper().startswith('SESGO:')), None)
        sesgo = sesgo_linea.split(':', 1)[1].strip() if sesgo_linea else "Ver recomendaciones abajo"

        # Parsear bloques por instrumento
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

        # Fallback si el parseo falló
        if not any(bloques.values()):
            recomendaciones_full = '\n'.join(
                l for l in lineas if not l.upper().startswith('SESGO:') and l.strip()
            ).strip()
            mitad = len(recomendaciones_full) // 3
            bloques['XAUUSD'] = [recomendaciones_full[:mitad]]
            bloques['US30']   = [recomendaciones_full[mitad:2*mitad]]
            bloques['NAS100'] = [recomendaciones_full[2*mitad:]]

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
            {"XAUUSD": [f"No se pudieron obtener recomendaciones: {str(e)}"], "US30": [], "NAS100": []},
            0x888888
        )


# ════════════════════════════════════════════════════════════
#  ENVÍO A DISCORD
# ════════════════════════════════════════════════════════════
def formatear_campo_tecnico(instrumento: str, datos: dict) -> str:
    """Genera un resumen compacto del análisis técnico M15 para Discord."""
    if 'error' in datos:
        return datos['error']
    pv  = datos.get('perfil_volumen', {})
    hvn = ", ".join(str(p) for p in pv.get('hvn', [])) or "N/A"
    lvn = ", ".join(str(p) for p in pv.get('lvn', [])) or "N/A"
    fuente = datos.get('simbolo_fuente', '?')
    return (
        f"💲 **{instrumento}** (via {fuente}) — Precio: **{datos['precio_actual']}** ({datos['cambio_7d_pct']:+.2f}% 7d) | Velas M15: {datos.get('num_velas','?')}\n"
        f"📈 Tendencia (EMA{EMA_RAPIDA}/EMA{EMA_LENTA} M15): {datos['tendencia']}\n"
        f"⚡ RSI({RSI_PERIODO}) M15: {datos['rsi']} — {datos['rsi_interp']}\n"
        f"📏 ATR({ATR_PERIODO}) M15: {datos['atr_m15']}\n"
        f"🗂️ POC: {pv.get('poc','N/A')} | VAH: {pv.get('vah','N/A')} | VAL: {pv.get('val','N/A')}\n"
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

    # ── Capa 0: Análisis técnico + perfil de volumen ────────
    print("🔍 Obteniendo precios y análisis técnico...")
    resumen_tecnico, analisis_tecnico_texto = obtener_analisis_tecnico_instrumentos()

    # ── Capa 1: Noticias ────────────────────────────────────
    print("📰 Obteniendo noticias...")
    noticias, raw_titulares = obtener_noticias_geopoliticas(domingo_pasado, hoy_str)

    # ── Capa 2: Calendario ──────────────────────────────────
    print("📅 Obteniendo calendario económico...")
    resultado_calendario = obtener_calendario_alto_impacto(hoy_str, proximo_domingo)
    if isinstance(resultado_calendario, tuple):
        calendario, raw_eventos = resultado_calendario
    else:
        calendario, raw_eventos = resultado_calendario, []

    # ── Capa 3: IA con contexto completo ────────────────────
    print("🤖 Generando recomendaciones con Claude...")
    sesgo, bloques, color = obtener_recomendaciones_ia(
        raw_titulares, raw_eventos, analisis_tecnico_texto,
        domingo_pasado, hoy_str
    )

    def safe_value(lista):
        texto = "\n".join(lista)
        return texto[:1024] if texto else "Sin datos disponibles."

    fields = [
        {
            "name": f"📊 CAPA 0 — Análisis Técnico + Perfil de Volumen (7d)",
            "value": (
                "\n\n".join(
                    formatear_campo_tecnico(inst, resumen_tecnico.get(inst, {'error': 'N/A'}))
                    for inst in ['XAUUSD', 'US30', 'NAS100']
                )
            )[:1024],
            "inline": False
        },
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
            "name": "📌 Recomendaciones — XAUUSD (Claude AI)",
            "value": ('\n'.join(bloques.get('XAUUSD', [])))[:1024] or "Sin datos.",
            "inline": False
        },
        {
            "name": "📌 Recomendaciones — US30 (Claude AI)",
            "value": ('\n'.join(bloques.get('US30', [])))[:1024] or "Sin datos.",
            "inline": False
        },
        {
            "name": "📌 Recomendaciones — NAS100 (Claude AI)",
            "value": ('\n'.join(bloques.get('NAS100', [])))[:1024] or "Sin datos.",
            "inline": False
        },
    ]

    payload = {
        "content": "@everyone 🛰️ **Sentinel v2.5: Reporte Semanal de Inteligencia**",
        "embeds": [{
            "title": f"🛡️ INTELIGENCIA DE MERCADO | {ahora} (Tijuana)",
            "color": color,
            "fields": fields,
            "footer": {
                "text": "Sentinel v2.5 | Tijuana Local Time | Datos: NewsAPI + FinnHub + Twelve Data M15 | IA: Claude Sonnet"
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
