import discord
from discord.ext import tasks, commands
import requests
from flask import Flask
from threading import Thread
import os
import datetime
from google import genai  # <-- Nuevo SDK oficial moderno

# === CONFIGURACIÓN DE IA (NUEVA API GOOGLE GENAI) ===
# El cliente inicializa automáticamente usando la variable GEMINI_API_KEY del sistema
ai_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
MODELO_IA = 'gemini-2.5-flash'  # Usamos la última versión estable y ultra rápida

# === SERVIDOR WEB PARA MANTENERLO VIVO EN RENDER ===
app = Flask('')
@app.route('/')
def home(): return "Bot de IA Multitarea Profesional Online"
def run(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
def keep_alive(): Thread(target=run).start()

# === CONFIGURACIÓN DISCORD ===
TOKEN = os.environ.get('DISCORD_TOKEN')
CANAL_ID = 1505367783804895375  # Reemplazá con tu ID de canal de Discord

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# === MEMORIAS Y FILTROS ===
enviados = set()
juegos_actuales_en_oferta = []
ultima_conexion_repositorios = "Aún no se ha realizado el primer chequeo."

LISTA_NEGRA = ["beta", "loot", "dlc", "pack", "skin", "add-on", "alpha", "currency", "monedas", "pass", "prologue", "demo"]

def es_juego_completo(titulo):
    titulo_lower = titulo.lower()
    for palabra in LISTA_NEGRA:
        if palabra in titulo_lower:
            return False
    return "100%" in titulo_lower or "free" in titulo_lower or "gratis" in titulo_lower

# === MONITOREO AUTOMÁTICO MULTI-FUENTE ===
@tasks.loop(minutes=30)
async def revisar_ofertas():
    global ultima_conexion_repositorios, juegos_actuales_en_oferta
    canal = bot.get_channel(CANAL_ID)
    
    # Si el canal no existe, ahora el bot dejará registro para que la IA lo sepa
    if not canal:
        print(f"❌ ERROR CRÍTICO: No se encontró el canal con ID {CANAL_ID}. El escaneo automático se canceló.")
        ultima_conexion_repositorios = "Fallida: El ID del canal de Discord (`CANAL_ID`) es incorrecto o el bot no tiene permisos para escribir ahí."
        return

    nuevas_tiendas_revisadas = []
    headers = {'User-Agent': 'FreeGameSearcherAPP v4.0'}

    # 1. REDDIT
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

    # 2. GAMERPOWER / GAMEDROP API
    try:
        res = requests.get("https://www.gamerpower.com/api/giveaways?type=game")
        if res.status_code == 200:
            giveaways = res.json()
            for g in giveaways:
                g_id = f"gp_{g['id']}"
                titulo = g['title']
                if g_id not in enviados and not any(p in titulo.lower() for p in LISTA_NEGRA):
                    await enviar_alerta(canal, g['platforms'], titulo, g['open_giveaway_url'], g_id)
            nuevas_tiendas_revisadas.append("GamerPower API")
    except Exception as e: print(f"Error en GamerPower: {e}")

    # 3. EPIC GAMES STORE OFFICIAL
    try:
        url_epic = "https://store-site-backend-ecomm-static-public.ak.epicgames.com/freeGamesPromotions"
        res = requests.get(url_epic)
        if res.status_code == 200:
            elementos = res.json()['data']['Catalog']['searchStore']['elements']
            for item in elementos:
                promociones = item.get('promotions')
                if promociones and promociones.get('promotionalOffers'):
                    if item['price']['totalPrice']['discountPrice'] == 0:
                        epic_id = f"epic_{item['id']}"
                        titulo = item['title']
                        slug = item.get('productSlug') or item.get('catalogNs', {}).get('mappings', [{}])[0].get('pageSlug', '')
                        url_final = f"https://store.epicgames.com/p/{slug}"
                        
                        if epic_id not in enviados and not any(p in titulo.lower() for p in LISTA_NEGRA):
                            await enviar_alerta(canal, "Epic Games Store 🛒", titulo, url_final, epic_id)
            nuevas_tiendas_revisadas.append("Epic Games Official")
    except Exception as e: print(f"Error en Epic Games API: {e}")

    ahora = datetime.datetime.now().strftime("%H:%M:%S")
    ultima_conexion_repositorios = f"Exitosa a las {ahora}. Fuentes limpias: {', '.join(nuevas_tiendas_revisadas)}."

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

# === EVENTO DE CHAT CON IA MODERNA ===
@bot.event
async def on_message(message):
    if message.author == bot.user: return

    if bot.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel):
        contexto_ia = (
            "Eres 'FreeGameSearcher', un bot de Discord experto en rastrear videojuegos completos y gratuitos.\n"
            "Tu política estricta: NO aceptas betas, DLCs, loot ni monedas virtuales. Solo juegos base completos.\n"
            f"Tu estado actual del sistema es:\n"
            f"- Repositorios revisados: {ultima_conexion_repositorios}\n"
            f"- Juegos activos hoy en tu radar: {', '.join(juegos_actuales_en_oferta) if juegos_actuales_en_oferta else 'Ninguno nuevo por el momento, todo controlado.'}\n\n"
            "Responde con fluidez, naturalidad y un toque gamer. Dale seguridad al usuario de que estás patrullando las tiendas sin parar."
        )
        
        prompt_final = f"{contexto_ia}\nUsuario dice: {message.content}"
        
        async with message.channel.typing():
            try:
                # Sintaxis moderna del nuevo SDK de Google
                respuesta = ai_client.models.generate_content(
                    model=MODELO_IA,
                    contents=prompt_final
                )
                await message.reply(respuesta.text)
            except Exception as e:
                print(f"❌ ERROR REAL DE GEMINI: {e}")
                await message.reply("Me dio un lag mental con mi nueva IA. Volvé a intentar en un toque.")

    await bot.process_commands(message)

@bot.event
async def on_ready():
    print(f'✅ Bot Profesional conectado como {bot.user}')
    
    # Notificación visual en Discord al encender
    canal = bot.get_channel(CANAL_ID)
    if canal:
        await canal.send("🚀 **¡FreeGameSearcher Online!** Sistema actualizado con la última tecnología de IA. Patrullando tiendas en segundo plano... ¡Hablame cuando quieras!")
        
    revisar_ofertas.start()
    keep_alive()

bot.run(TOKEN)
