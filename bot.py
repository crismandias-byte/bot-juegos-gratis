import discord
from discord.ext import tasks, commands
import requests
from flask import Flask
from threading import Thread
import os
import datetime
import google.generativeai as genai

# === CONFIGURACIÓN DE IA (GEMINI) ===
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-1.5-flash')

# === SERVIDOR WEB PARA RENDER ===
app = Flask('')
@app.route('/')
def home(): return "Bot de IA Multitarea Online"
def run(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
def keep_alive(): Thread(target=run).start()

# === CONFIGURACIÓN DISCORD ===
TOKEN = os.environ.get('DISCORD_TOKEN')
CANAL_ID = 123456789012345678  # Poné acá tu ID de canal de Discord

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# === MEMORIAS Y FILTROS ===
enviados = set()
juegos_actuales_en_oferta = []
ultima_conexion_repositorios = "Aún no se ha realizado el primer chequeo."

# LISTA NEGRA: Si el título tiene alguna de estas palabras, el bot lo ignora por completo
LISTA_NEGRA = ["beta", "loot", "dlc", "pack", "skin", "add-on", "alpha", "currency", "monedas", "pass", "prologue", "demo"]

def es_juego_completo(titulo):
    titulo_lower = titulo.lower()
    for palabra in LISTA_NEGRA:
        if palabra in titulo_lower:
            return False
    return "100%" in titulo_lower or "free" in titulo_lower or "gratis" in titulo_lower

# === MONITOREO MULTI-FUENTE ===
@tasks.loop(minutes=30)
async def revisar_ofertas():
    global ultima_conexion_repositorios, juegos_actuales_en_oferta
    canal = bot.get_channel(CANAL_ID)
    if not canal: return

    nuevas_tiendas_revisadas = []
    headers = {'User-Agent': 'MiAlertaDeJuegosBotIA v3.0'}

    # ------------------------------------------------------------------
    # FUENTE 1: REDDIT (r/GameDeals y r/FreeGameFindings)
    # ------------------------------------------------------------------
    subreddits = ["GameDeals", "FreeGameFindings"]
    for sub in subreddits:
        try:
            res = requests.get(f"https://www.reddit.com/r/{sub}/new.json?limit=10", headers=headers)
            if res.status_code == 200:
                posts = res.json()['data']['children']
                for post in posts:
                    data = post['data']
                    titulo = data['title']
                    
                    if es_juego_completo(titulo) and data['id'] not in enviados:
                        plataforma = "Steam/PC" if "steam" in titulo.lower() else "Multiplataforma"
                        await enviar_alerta(canal, plataforma, titulo, data['url'], data['id'])
                nuevas_tiendas_revisadas.append(f"Reddit (r/{sub})")
        except Exception as e: print(f"Error en Reddit {sub}: {e}")

    # ------------------------------------------------------------------
    # FUENTE 2: GAMERPOWER / GAMEDROP API (Filtrado nativo por juegos)
    # ------------------------------------------------------------------
    try:
        # El parámetro '?type=game' le dice a su base de datos que NO queremos loot ni betas
        res = requests.get("https://www.gamerpower.com/api/giveaways?type=game")
        if res.status_code == 200:
            giveaways = res.json()
            for g in giveaways:
                g_id = f"gp_{g['id']}"  # ID único para no mezclar con Reddit
                titulo = g['title']
                if g_id not in enviados and not any(p in titulo.lower() for p in LISTA_NEGRA):
                    await enviar_alerta(canal, g['platforms'], titulo, g['open_giveaway_url'], g_id)
            nuevas_tiendas_revisadas.append("GamerPower/GameDrop API")
    except Exception as e: print(f"Error en GamerPower: {e}")

    # ------------------------------------------------------------------
    # FUENTE 3: EPIC GAMES STORE (API Oficial de Regalos)
    # ------------------------------------------------------------------
    try:
        url_epic = "https://store-site-backend-ecomm-static-public.ak.epicgames.com/freeGamesPromotions"
        res = requests.get(url_epic)
        if res.status_code == 200:
            elementos = res.json()['data']['Catalog']['searchStore']['elements']
            for item in elementos:
                promociones = item.get('promotions')
                if promociones and promociones.get('promotionalOffers'):
                    # Verificamos si está gratis AHORA (precio 0)
                    if item['price']['totalPrice']['discountPrice'] == 0:
                        epic_id = f"epic_{item['id']}"
                        titulo = item['title']
                        slug = item.get('productSlug') or item.get('catalogNs', {}).get('mappings', [{}])[0].get('pageSlug', '')
                        url_final = f"https://store.epicgames.com/p/{slug}"
                        
                        if epic_id not in enviados and not any(p in titulo.lower() for p in LISTA_NEGRA):
                            await enviar_alerta(canal, "Epic Games Store 🛒", titulo, url_final, epic_id)
            nuevas_tiendas_revisadas.append("Epic Games Official")
    except Exception as e: print(f"Error en Epic Games API: {e}")

    # Actualizar estado para la IA
    ahora = datetime.datetime.now().strftime("%H:%M:%S")
    ultima_conexion_repositorios = f"Exitosa a las {ahora}. Fuentes integradas y limpias: {', '.join(nuevas_tiendas_revisadas)}."

async def enviar_alerta(canal, plataforma, titulo, url, unique_id):
    global juegos_actuales_en_oferta
    info = f"{titulo} [{plataforma}]"
    if info not in juegos_actuales_en_oferta:
        juegos_actuales_en_oferta.append(info)
        
    mensaje = (
        f"🚨 **¡JUEGO COMPLETO GRATIS!** 🚨\n"
        f"🎮 **Plataforma:** {plataforma}\n"
        f"📝 **Título:** {titulo}\n"
        f"🔗 **Link de descarga:** {url}\n"
        f"_"
    )
    await canal.send(mensaje)
    enviados.add(unique_id)

# === EVENTO DE CHAT CON IA ===
@bot.event
async def on_message(message):
    if message.author == bot.user: return

    if bot.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel):
        contexto_ia = (
            "Eres 'CazadorDeOfertas', un bot con Inteligencia Artificial experto en videojuegos.\n"
            "Tu misión estricta es avisar solo sobre JUEGOS COMPLETOS. Tienes prohibido aceptar betas, loot, DLCs o demos.\n"
            f"Tu reporte técnico actual para responder al usuario es:\n"
            f"- Estado de repositorios: {ultima_conexion_repositorios}\n"
            f"- Juegos limpios y completos disponibles hoy: {', '.join(juegos_actuales_en_oferta) if juegos_actuales_en_oferta else 'Ninguno nuevo por el momento, todo limpio.'}\n\n"
            "Responde de forma muy fluida, humana y natural. Si te preguntan si ya chequeaste todo o si hay juegos, "
            "usa estos datos para darles seguridad de que tu filtro anti-loot y anti-betas está funcionando impecable."
        )
        
        prompt = f"{contexto_ia}\nUsuario: {message.content}"
        
        async with message.channel.typing():
            try:
                respuesta = model.generate_content(prompt)
                await message.reply(respuesta.text)
            except Exception as e:
                await message.reply("Me dio un lag mental con la IA. Volvé a intentar.")

    await bot.process_commands(message)

@bot.event
async def on_ready():
    print(f'✅ Bot Multi-Fuente conectado como {bot.user}')
    revisar_ofertas.start()
    keep_alive()

bot.run(TOKEN)
