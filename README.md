SENTINEL — AGENTE DE INTELIGENCIA FINANCIERA PARA DISCORD
==========================================================

Envia un reporte diario de XAUUSD (Oro) a tu servidor de Discord con:
- Analisis tecnico M15 (EMA, RSI, ATR, Perfil de Volumen)
- Noticias macro y geopoliticas de la semana
- Calendario economico de alto impacto
- Sesgo semanal y recomendacion de trade generada por Claude AI

Se ejecuta automaticamente de lunes a domingo a las 4:00 AM Tijuana (11:00 UTC)
usando GitHub Actions. No necesitas servidor propio.


CUENTAS QUE NECESITAS CREAR
============================

1. ANTHROPIC (Claude AI) — genera el analisis con IA
   Registro: console.anthropic.com
   - Crea una cuenta, ve a API Keys > Create Key
   - Agrega minimo $5 USD en Billing para activar el uso
   - Costo: ~$0.08/mes (26 ejecuciones x ~$0.003 por llamada)

2. NEWSAPI — noticias financieras y geopoliticas
   Registro: newsapi.org/register
   - El plan gratuito es suficiente (100 requests/dia)
   - Costo: $0/mes

3. FINNHUB — calendario economico (FOMC, CPI, NFP, etc.)
   Registro: finnhub.io/register
   - El plan gratuito es suficiente (60 llamadas/minuto)
   - Costo: $0/mes

4. TWELVE DATA — precios XAUUSD en temporalidad M15
   Registro: twelvedata.com/register
   - El plan gratuito es suficiente (800 creditos/dia, Sentinel usa ~1/dia)
   - Costo: $0/mes

5. DISCORD — webhook para recibir el reporte
   - Abre tu servidor > canal deseado > Editar Canal > Integraciones > Webhooks
   - Crea un nuevo webhook y copia la URL
   - Costo: $0/mes


COSTO TOTAL MENSUAL
===================

  Anthropic (Claude)    ~$0.08
  NewsAPI                $0.00
  Finnhub                $0.00
  Twelve Data            $0.00
  Discord                $0.00
  GitHub Actions         $0.00
  ---------------------------------
  TOTAL                 ~$0.08/mes


INSTALACION
===========

1. Haz fork de este repositorio en tu cuenta de GitHub

2. Ve a Settings > Secrets and variables > Actions > New repository secret
   Agrega estos 5 secrets con exactamente estos nombres:

     ANTHROPIC_API_KEY       -> tu clave de Anthropic
     DISCORD_WEBHOOK_URL     -> la URL del webhook de Discord
     NEWS_API_KEY            -> tu clave de NewsAPI (o alternativa)
     FINNHUB_API_KEY         -> tu clave de Finnhub
     TWELVE_DATA_API_KEY     -> tu clave de Twelve Data

3. Ve a la pestana Actions y activa los workflows si aparece un aviso

4. Para probar manualmente: Actions > Sentinel v2.1 > Run workflow
   En ~60 segundos debe llegar el reporte a tu canal de Discord

5. Listo. A partir de ahi se ejecuta solo cada dia.


ARCHIVOS DEL PROYECTO
=====================

  agente_inteligente.py   -> logica principal del agente
  requirements.txt        -> dependencias Python
  agente.yml              -> configuracion de GitHub Actions


AVISO
=====

Este proyecto es solo con fines educativos e informativos.
Las recomendaciones de Sentinel no son asesoramiento financiero.
Opera siempre con tu propio criterio.
