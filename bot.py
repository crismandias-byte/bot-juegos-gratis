import discord
from discord.ext import tasks, commands
import requests
from flask import Flask
from threading import Thread
import os

# === TRUCO PARA MANTENERLO VIVO EN RENDER ===
app = Flask('')

@app.route('/')
def home():
    return "¡El bot está encendido y funcionando!"

def run():
    # Render nos asigna un puerto automáticamente
    puerto = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=puerto)

def keep_alive():
    t = Thread(target=run)
    t.start()
# ============================================

TOKEN = os.environ.get('DISCORD_TOKEN')
CANAL_ID = 1505367783804895375  # Tu ID de canal de Discord

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

enviados = set()

@bot.event
async def on_ready():
    print(f'✅ Bot conectado como {bot.user}')
    revisar_ofertas.start()

@tasks.loop(minutes=30)
async def revisar_ofertas():
    canal = bot.get_channel(CANAL_ID)
    if not canal:
        return

    url = "https://www.reddit.com/r/GameDeals/new.json?limit=12"
    headers = {'User-Agent': 'MiAlertaDeJuegosBot v1.0'}
    
    try:
        respuesta = requests.get(url, headers=headers)
        if respuesta.status_code == 200:
            posts = respuesta.json()['data']['children']
            for post in posts:
                data = post['data']
                post_id = data['id']
                titulo = data['title'].lower()
                url_juego = data['url']
                
                if post_id in enviados:
                    continue
                
                if "100%" in titulo or "free" in titulo or "gratis" in titulo:
                    mensaje = (
                        f"🚨 **¡JUEGO GRATIS DETECTADO!** 🚨\n"
                        f"🎮 **Título:** {data['title']}\n"
                        f"🔗 **Link para reclamar:** {url_juego}\n"
                        f"_"
                    )
                    await canal.send(mensaje)
                    enviados.add(post_id)
    except Exception as e:
        print(f"Error: {e}")

# Activamos el servidor web justo antes de encender el bot
keep_alive()
bot.run(TOKEN)