import os
import time
import asyncio
import logging
import subprocess
import math
import requests
import shutil
import random
import sqlite3
import datetime
import base64
import sys
from pathlib import Path
from telethon import TelegramClient, events, utils, Button
from telethon.tl.types import DocumentAttributeFilename, InputFile, InputFileBig
from telethon.tl.functions.upload import SaveFilePartRequest, SaveBigFilePartRequest

# ═══════════════════════════════════════════════════════════════════
#    SUPER BOT v13.1 (LINUX UNIVERSAL FIX)
# ═══════════════════════════════════════════════════════════════════

logging.basicConfig(format='%(asctime)s | %(levelname)s | %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger("telethon").setLevel(logging.ERROR)

# ─────────────────────────────────────────────────────────────────────
#                         CONFIGURACION
# ─────────────────────────────────────────────────────────────────────
API_ID = 18693993
API_HASH = '382ee6b53bdd0df66a52ea9779c62424'
BOT_TOKEN = '8569421664:AAFSO-PLDzZ5WktO7nM60Uwflo_C6AZDWwk'

# ID DEL ADMIN
ADMIN_ID = 5338241603  

# Directorios (Rutas Absolutas Linux)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_PATH = os.path.join(BASE_DIR, 'downloads')

MAX_TG_SIZE = 2000 * 1024 * 1024  # 2000 MB

# ⚡ CONFIGURACIÓN LINUX ⚡
UPLOAD_WORKERS = 16
PART_SIZE_KB = 512       

Path(DOWNLOAD_PATH).mkdir(parents=True, exist_ok=True)

# Aria2
ARIA2_RPC_PORT = 6800
ARIA2_SECRET = "mysecrettoken"

CANCEL_FLAGS = {}

STYLE = {
    'title': '=' * 30, 'line': '-' * 30, 'rocket': '[RUN]', 
    'check': '[OK]', 'cross': '[X]', 'arrow': '->', 
    'download': '[DOWN]', 'upload': '[UP]', 'file': '[FILE]', 
    'speed': '[SPD]', 'time': '[TIME]', 'size': '[SIZE]', 
    'admin': '[ADM]', 'success': '[DONE]', 'error': '[ERR]', 
    'loading': '[...]', 'queue': '[Q]', 'split': '[CUT]', 
    'warn': '[!]', 'quota': '[%]', 'lock': '[LOCK]', 'cancel': '[STOP]'
}

db_path = "database.db"

# ═══════════════════════════════════════════════════════════════════
#                     MANEJO DE CIERRE (LINUX)
# ═══════════════════════════════════════════════════════════════════
def force_kill_processes():
    try:
        subprocess.run("pkill -9 aria2c", shell=True)
    except: pass

def signal_handler(sig, frame):
    print(f"\nAPAGANDO...")
    force_kill_processes()
    sys.exit(0) 

signal.signal(signal.SIGINT, signal_handler)

# ═══════════════════════════════════════════════════════════════════
#                     BASE DE DATOS
# ═══════════════════════════════════════════════════════════════════
class Database:
    def __init__(self):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_table()

    def create_table(self):
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, daily_limit_gb REAL, today_usage_bytes INTEGER, last_reset_date TEXT)''')
        self.conn.commit()

    def add_user(self, user_id, username, limit_gb):
        try:
            today = str(datetime.date.today())
            self.cursor.execute("INSERT OR REPLACE INTO users (user_id, username, daily_limit_gb, today_usage_bytes, last_reset_date) VALUES (?, ?, ?, ?, ?)", (user_id, username, limit_gb, 0, today))
            self.conn.commit(); return True
        except: return False

    def remove_user(self, user_id):
        self.cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        self.conn.commit(); return self.cursor.rowcount > 0

    def get_user(self, user_id):
        self.cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return self.cursor.fetchone()

    def get_all_users(self):
        self.cursor.execute("SELECT user_id, username, daily_limit_gb FROM users")
        return self.cursor.fetchall()

    def check_quota(self, user_id, file_size=0):
        if user_id == ADMIN_ID: return True
        user = self.get_user(user_id)
        if not user: return False
        today = str(datetime.date.today())
        if user[4] != today:
            self.cursor.execute("UPDATE users SET today_usage_bytes = 0, last_reset_date = ? WHERE user_id = ?", (today, user_id))
            self.conn.commit(); current_usage = 0
        else: current_usage = user[3]
        return (current_usage + file_size) <= (user[2] * 1024**3)

    def add_usage(self, user_id, bytes_used):
        if user_id == ADMIN_ID: return
        self.cursor.execute("UPDATE users SET today_usage_bytes = today_usage_bytes + ? WHERE user_id = ?", (bytes_used, user_id))
        self.conn.commit()

db = Database()

# ═══════════════════════════════════════════════════════════════════
#                     ARIA2 DOWNLOADER (LINUX FIXED)
# ═══════════════════════════════════════════════════════════════════
class Aria2Downloader:
    def __init__(self):
        self.rpc_url = f"http://localhost:{ARIA2_RPC_PORT}/jsonrpc"
        self.trackers = self.get_trackers()
        self.start_aria2()
    
    def get_trackers(self):
        try:
            url = "https://raw.githubusercontent.com/ngosang/trackerslist/master/trackers_best.txt"
            return ",".join([t.strip() for t in requests.get(url, timeout=5).text.split('\n') if t.strip()])
        except: return ""

    def is_running(self):
        try:
            return requests.post(self.rpc_url, json={"jsonrpc":"2.0","id":"test","method":"aria2.getVersion","params":[f"token:{ARIA2_SECRET}"]}, timeout=2).status_code == 200
        except: return False
    
    def start_aria2(self):
        if self.is_running(): return True
        
        if not shutil.which('aria2c'):
            print("❌ Error: aria2c no instalado. Ejecuta: sudo apt install aria2")
            return False
            
        try:
            # Matar procesos viejos para limpiar puertos
            subprocess.run("pkill -9 aria2c", shell=True)
            time.sleep(1)

            # COMANDO PURO Y LIMPIO PARA CUALQUIER VERSIÓN DE LINUX
            cmd = [
                'aria2c',
                '--enable-rpc',
                '--rpc-listen-all=false',
                f'--rpc-listen-port={ARIA2_RPC_PORT}',
                f'--rpc-secret={ARIA2_SECRET}',
                f'--dir={DOWNLOAD_PATH}',
                '--daemon=true',  # Modo Demonio
                '--no-conf',      # IGNORAR ARCHIVOS CONF VIEJOS (ESTO ARREGLA TU ERROR)
                '--max-connection-per-server=16',
                '--split=16',
                '--quiet=true',
                '--allow-overwrite=true'
            ]
            subprocess.Popen(cmd)
            
            # Esperar a que inicie
            for _ in range(5):
                time.sleep(1)
                if self.is_running(): 
                    print("✅ Aria2 iniciado correctamente.")
                    return True
            
            print("❌ Aria2 no respondió.")
            return False
        except Exception as e:
            print(f"Error starting aria2: {e}")
            return False
    
    def rpc(self, method, params=None):
        try:
            return requests.post(self.rpc_url, json={"jsonrpc":"2.0","id":"1","method":method,"params":[f"token:{ARIA2_SECRET}"]+(params or [])}, timeout=10).json().get('result')
        except: return None
    
    def add(self, url, is_torrent=False):
        opts = {"dir": DOWNLOAD_PATH}
        if is_torrent:
            opts.update({"bt-stop-timeout": "300", "seed-time": "0"})
            if self.trackers: opts['bt-tracker'] = self.trackers
        return self.rpc("aria2.addUri", [[url], opts])
    
    def add_torrent_blob(self, file_path):
        try:
            with open(file_path, "rb") as f:
                encoded = base64.b64encode(f.read()).decode('utf-8')
            opts = {"dir": DOWNLOAD_PATH, "bt-stop-timeout": "300", "seed-time": "0"}
            if self.trackers: opts['bt-tracker'] = self.trackers
            return self.rpc("aria2.addTorrent", [encoded, [], opts])
        except: return None
    
    def status(self, gid): return self.rpc("aria2.tellStatus", [gid])
    def remove(self, gid): self.rpc("aria2.remove", [gid])
    def force_remove(self, gid): self.rpc("aria2.forceRemove", [gid])

# ═══════════════════════════════════════════════════════════════════
#                     UTILIDADES
# ═══════════════════════════════════════════════════════════════════
def format_size(size_bytes):
    if size_bytes < 1024: return f"{size_bytes} B"
    elif size_bytes < 1024**2: return f"{size_bytes/1024:.1f} KB"
    elif size_bytes < 1024**3: return f"{size_bytes/1024**2:.2f} MB"
    else: return f"{size_bytes/1024**3:.2f} GB"

def format_time(seconds):
    if seconds <= 0: return "0s"
    if seconds < 60: return f"{int(seconds)}s"
    elif seconds < 3600: return f"{int(seconds//60)}m {int(seconds%60)}s"
    else: return f"{int(seconds//3600)}h {int((seconds%3600)//60)}m"

def create_bar(percentage):
    filled = int(percentage / 10) 
    return '█' * filled + '░' * (10 - filled)

def split_file_sync(file_path, chunk_size=MAX_TG_SIZE):
    parts = []
    file_size = os.path.getsize(file_path)
    if file_size <= chunk_size: return [file_path]
    part_num = 1
    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk: break
            part_name = f"{file_path}.part{part_num:03d}"
            with open(part_name, 'wb') as p: p.write(chunk)
            parts.append(part_name)
            part_num += 1
    try: os.remove(file_path)
    except: pass
    return parts

def download_torrent_file(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, allow_redirects=True, timeout=10)
        if resp.status_code == 200:
            name = f"metadata_{int(time.time())}.torrent"
            path = os.path.abspath(os.path.join(DOWNLOAD_PATH, name))
            with open(path, 'wb') as f: f.write(resp.content)
            return path
    except: pass
    return None

# ═══════════════════════════════════════════════════════════════════
#                     FAST UPLOADER
# ═══════════════════════════════════════════════════════════════════
class FastUploader:
    def __init__(self, client, file_path, filename, progress_callback=None, user_id=None):
        self.client = client
        self.file_path = file_path
        self.filename = filename
        self.callback = progress_callback
        self.user_id = user_id
        self.file_size = os.path.getsize(file_path)
        self.part_size = PART_SIZE_KB * 1024
        self.total_parts = math.ceil(self.file_size / self.part_size)
        self.uploaded = 0
        self.lock = asyncio.Lock()
        self.file_id = random.randint(1, 2**62)
        self.is_big = self.file_size > 10 * 1024 * 1024

    async def upload_chunk(self, index, file_obj):
        if self.user_id and CANCEL_FLAGS.get(self.user_id): return False
        try:
            file_obj.seek(index * self.part_size)
            data = file_obj.read(self.part_size)
            if not data: return False
            req = SaveBigFilePartRequest(self.file_id, index, self.total_parts, data) if self.is_big else SaveFilePartRequest(self.file_id, index, data)
            await self.client(req)
            async with self.lock:
                self.uploaded += len(data)
                if self.callback: await self.callback(self.uploaded, self.file_size)
            return True
        except: return False

    async def run(self):
        with open(self.file_path, 'rb') as f:
            tasks = []
            for i in range(self.total_parts):
                if self.user_id and CANCEL_FLAGS.get(self.user_id): return None
                tasks.append(self.upload_chunk(i, f))
                if len(tasks) >= UPLOAD_WORKERS:
                    await asyncio.gather(*tasks)
                    tasks = []
            if tasks: await asyncio.gather(*tasks)
        if self.user_id and CANCEL_FLAGS.get(self.user_id): return None
        return InputFileBig(self.file_id, self.total_parts, self.filename) if self.is_big else InputFile(self.file_id, self.total_parts, self.filename, md5_checksum='')

async def upload_file(client, chat_id, path, msg, name, header="", user_id=None):
    start = time.time()
    last_upd = 0
    async def progress(curr, total):
        if user_id and CANCEL_FLAGS.get(user_id): return
        nonlocal last_upd
        now = time.time()
        if now - last_upd < 3: return
        elapsed = now - start
        speed = curr / elapsed if elapsed > 0 else 0
        pct = (curr / total) * 100
        eta = (total - curr) / speed if speed > 0 else 0
        text = f"**{STYLE['upload']} SUBIENDO** {header}\n{STYLE['line']}\n`{create_bar(pct)}` **{pct:.1f}%**\n\n{STYLE['file']} `{name}`\n{STYLE['size']} {format_size(curr)} / {format_size(total)}\n{STYLE['speed']} {format_size(speed)}/s\n{STYLE['time']} ETA: {format_time(eta)}"
        try: await msg.edit(text, buttons=[Button.inline(f"{STYLE['cross']} Cancelar", data="cancel_task")]); last_upd = now
        except: pass

    try:
        uploader = FastUploader(client, path, name, progress, user_id=user_id)
        input_file = await uploader.run()
        if not input_file: return False 
        await client.send_file(chat_id, input_file, caption=f"{STYLE['file']} `{name}`", force_document=True, attributes=[DocumentAttributeFilename(name)])
        return True
    except Exception as e: return False

# ═══════════════════════════════════════════════════════════════════
#                     PROCESAMIENTO
# ═══════════════════════════════════════════════════════════════════
async def wait_metadata(aria2, gid, user_id):
    start = time.time()
    while time.time() - start < 120:
        if CANCEL_FLAGS.get(user_id): return None 
        s = aria2.status(gid)
        if not s: await asyncio.sleep(1); continue
        if s.get('status') == 'error': return None
        if s.get('followedBy'): gid = s['followedBy'][0]; continue
        meta = s.get('bittorrent', {}).get('info', {}).get('name')
        if meta and '[METADATA]' not in meta: return {'name': meta, 'gid': gid}
        if s.get('status') == 'complete':
             for f in s.get('files', []):
                 if f['path'] and '[METADATA]' not in f['path']: return {'name': os.path.basename(f['path']), 'gid': gid}
        await asyncio.sleep(1)
    return None

async def process(event, url_or_type, aria2):
    client = event.client; chat_id = event.chat_id; user_id = event.sender_id
    CANCEL_FLAGS[user_id] = False

    if not db.check_quota(user_id): await event.respond(f"**{STYLE['lock']} CUOTA AGOTADA**"); return

    msg = await event.respond(f"**{STYLE['queue']} INICIANDO...**", buttons=[Button.inline(f"{STYLE['cross']} Cancelar", data="cancel_task")])
    gid = None; is_torrent = False

    try:
        if url_or_type == "TG_FILE":
            await msg.edit(f"**{STYLE['loading']} Descargando .torrent...**", buttons=[Button.inline(f"{STYLE['cross']} Cancelar", data="cancel_task")])
            t_path = await event.download_media(file=os.path.join(DOWNLOAD_PATH, f"meta_{int(time.time())}.torrent"))
            if t_path and os.path.exists(t_path):
                gid = aria2.add_torrent_blob(t_path); is_torrent = True
                try: os.remove(t_path)
                except: pass
            else: await msg.edit(f"**{STYLE['error']} Error archivo**"); return
        else:
            url = url_or_type
            if url.endswith('.torrent') and url.startswith('http'):
                await msg.edit(f"**{STYLE['loading']} Descargando .torrent web...**", buttons=[Button.inline(f"{STYLE['cross']} Cancelar", data="cancel_task")])
                t_path = download_torrent_file(url)
                if t_path:
                    gid = aria2.add_torrent_blob(t_path); is_torrent = True
                    try: os.remove(t_path)
                    except: pass
                else: await msg.edit(f"**{STYLE['error']} Error .torrent**"); return
            elif url.startswith('magnet'): gid = aria2.add(url, True)
            else: gid = aria2.add(url, False)
            
        if not gid: await msg.edit(f"**{STYLE['error']} Error Aria2**"); return

        dl_name = "Archivo"
        if is_torrent or (isinstance(url_or_type, str) and url_or_type.startswith('magnet')):
            await msg.edit(f"**{STYLE['loading']} Metadatos...**", buttons=[Button.inline(f"{STYLE['cross']} Cancelar", data="cancel_task")])
            meta = await wait_metadata(aria2, gid, user_id)
            if meta: gid = meta['gid']; dl_name = meta['name']
            else:
                if CANCEL_FLAGS.get(user_id): await msg.edit(f"**{STYLE['cancel']} TAREA CANCELADA**"); return
                await msg.edit(f"**{STYLE['error']} Magnet/Torrent Muerto**"); aria2.remove(gid); return

        start_dl = time.time(); last_upd = 0
        while True:
            if CANCEL_FLAGS.get(user_id): aria2.force_remove(gid); await msg.edit(f"**{STYLE['cancel']} TAREA CANCELADA**"); return
            s = aria2.status(gid)
            if not s: await asyncio.sleep(1); continue
            if s.get('followedBy'): gid = s['followedBy'][0]; continue
            if s.get('status') == 'error': await msg.edit(f"**{STYLE['error']} Error:** `{s.get('errorMessage')}`"); return
            if s.get('status') == 'complete': break
            
            done = int(s.get('completedLength', 0)); total = int(s.get('totalLength', 0)); speed = int(s.get('downloadSpeed', 0))
            if total > 0 and not db.check_quota(user_id, total): aria2.remove(gid); await msg.edit(f"**{STYLE['warn']} Excede cuota**"); return
            if total > 0 and s.get('files'):
                try: dl_name = os.path.basename(max(s['files'], key=lambda x: int(x['length']))['path'])
                except: pass

            if time.time() - last_upd > 3 and total > 0:
                pct = (done/total)*100
                txt = f"**{STYLE['download']} DESCARGANDO**\n`{create_bar(pct)}` {pct:.1f}%\n{STYLE['file']} `{dl_name[:30]}`\n{STYLE['size']} {format_size(done)} / {format_size(total)}\n{STYLE['speed']} {format_size(speed)}/s"
                try: await msg.edit(txt, buttons=[Button.inline(f"{STYLE['cross']} Cancelar", data="cancel_task")]); last_upd = time.time()
                except: pass
            await asyncio.sleep(1)
        
        await msg.edit(f"**{STYLE['check']} COMPLETO**\nVerificando...", buttons=[Button.inline(f"{STYLE['cross']} Cancelar", data="cancel_task")])
        
        all_files = []
        for root, dirs, files_in_dir in os.walk(DOWNLOAD_PATH):
            for n in files_in_dir:
                if n.endswith(('.aria2', '.torrent')) or '[METADATA]' in n: continue
                p = os.path.join(root, n)
                try:
                    if os.path.getsize(p) > 0: all_files.append({'path': p, 'name': n, 'size': os.path.getsize(p)})
                except: pass
        
        all_files.sort(key=lambda x: x['size'], reverse=True)
        final_files = []
        loop = asyncio.get_running_loop()
        
        for f in all_files:
            if CANCEL_FLAGS.get(user_id): await msg.edit(f"**{STYLE['cancel']} TAREA CANCELADA**"); return
            if f['size'] > MAX_TG_SIZE:
                await msg.edit(f"**{STYLE['split']} DIVIDIENDO...**\n`{f['name']}`", buttons=[Button.inline(f"{STYLE['cross']} Cancelar", data="cancel_task")])
                parts = await loop.run_in_executor(None, split_file_sync, f['path'])
                for p in parts: final_files.append({'path': p, 'name': os.path.basename(p), 'size': os.path.getsize(p)})
            else: final_files.append(f)
        
        uploaded_bytes = 0
        for i, f in enumerate(final_files):
            if CANCEL_FLAGS.get(user_id): await msg.edit(f"**{STYLE['cancel']} TAREA CANCELADA**"); return
            f_num = f"[{i+1}/{len(final_files)}]"
            if await upload_file(client, chat_id, f['path'], msg, f['name'], f_num, user_id):
                uploaded_bytes += f['size']
                try: os.remove(f['path'])
                except: pass
            else:
                if CANCEL_FLAGS.get(user_id): await msg.edit(f"**{STYLE['cancel']} TAREA CANCELADA**"); return
        
        if not CANCEL_FLAGS.get(user_id):
            db.add_usage(user_id, uploaded_bytes)
            await msg.edit(f"**{STYLE['success']} FINALIZADO**\nArchivos: {len(final_files)}\nTotal: {format_size(uploaded_bytes)}\nTiempo: {format_time(time.time() - start_dl)}")

    except Exception as e:
        try: await msg.edit(f"**{STYLE['error']} ERROR:** `{str(e)[:100]}`")
        except: pass
    finally:
        if gid: aria2.remove(gid)
        for root, dirs, files in os.walk(DOWNLOAD_PATH, topdown=False):
            for name in dirs:
                try: os.rmdir(os.path.join(root, name))
                except: pass
            for name in files:
                try: os.remove(os.path.join(root, name))
                except: pass

async def worker(queue, aria2):
    while True:
        try:
            event, url_or_type = await queue.get()
            try: await process(event, url_or_type, aria2)
            except: pass
            finally: queue.task_done()
        except: pass

# ═══════════════════════════════════════════════════════════════════
#                     MAIN
# ═══════════════════════════════════════════════════════════════════
def get_admin_keyboard(): return [[Button.text("/users"), Button.text("/help_admin")], [Button.text("/miplan")]]
def get_user_keyboard(): return [[Button.text("/miplan"), Button.text("/support")]]

async def main():
    try: import cryptg; crypt_msg = f"{STYLE['check']} Cryptg: ACTIVO"
    except: crypt_msg = f"{STYLE['warn']} Cryptg: FALTA"
    print(f"\n{STYLE['title']}\n   {STYLE['rocket']} BOT v13.1 LINUX (UNIVERSAL)\n   {crypt_msg}\n{STYLE['title']}\n")
    
    aria2 = Aria2Downloader()
    if not aria2.is_running():
        if not aria2.start_aria2():
            print("ERROR FATAL: Aria2 no arranca.")
            return

    client = TelegramClient('linux_bot', API_ID, API_HASH)
    queue = asyncio.Queue()
    asyncio.create_task(worker(queue, aria2))
    
    @client.on(events.CallbackQuery(pattern=b'cancel_task'))
    async def cancel_handler(e):
        uid = e.sender_id; CANCEL_FLAGS[uid] = True
        await e.answer("Cancelando...", alert=False)

    @client.on(events.NewMessage(pattern='/start'))
    async def start(e):
        uid = e.sender_id
        if uid == ADMIN_ID: await e.respond(f"**👋 Admin**", buttons=get_admin_keyboard())
        elif db.check_quota(uid): await e.respond(f"**👋 Bienvenido**", buttons=get_user_keyboard())
        else: await e.respond(f"**{STYLE['lock']} SIN ACCESO**")

    @client.on(events.NewMessage(pattern='/support'))
    async def support(e): await e.respond(f"📞 Soporte: @CarlosAle0077")

    @client.on(events.NewMessage(pattern='/help_admin'))
    async def help_adm(e):
        if e.sender_id != ADMIN_ID: return
        await e.respond("**👮‍♂️ ADMIN:**\n`/add @user GB`\n`/ban @user`\n`/users`")

    @client.on(events.NewMessage(pattern='/add'))
    async def add(e):
        if e.sender_id != ADMIN_ID: return
        try:
            _, user, gb = e.text.split(); u_obj = await client.get_entity(user)
            if db.add_user(u_obj.id, user, float(gb)): await e.respond(f"{STYLE['check']} Agregado")
        except: await e.respond("Uso: `/add @user 5`")

    @client.on(events.NewMessage(pattern='/ban'))
    async def ban(e):
        if e.sender_id != ADMIN_ID: return
        try:
            u_obj = await client.get_entity(e.text.split()[1])
            if db.remove_user(u_obj.id): await e.respond(f"{STYLE['cross']} Baneado")
        except: await e.respond("Uso: `/ban @user`")

    @client.on(events.NewMessage(pattern='/users'))
    async def lst(e):
        if e.sender_id != ADMIN_ID: return
        users = db.get_all_users(); msg = f"**{STYLE['admin']} LISTA:**\n"
        for u in users: msg += f"👤 {u[1]} ({u[2]}GB)\n"
        await e.respond(msg)

    @client.on(events.NewMessage(pattern='/miplan'))
    async def plan(e):
        if e.sender_id == ADMIN_ID: await e.respond(f"**{STYLE['admin']} ILIMITADO**"); return
        u = db.get_user(e.sender_id)
        if not u: await e.respond("Sin plan."); return
        limit = u[2] * 1024**3; used = u[3]; pct = (used/limit)*100
        await e.respond(f"**{STYLE['quota']} PLAN:**\nUsado: {format_size(used)} / {u[2]}GB\n`{create_bar(pct)}` {pct:.1f}%")

    @client.on(events.NewMessage)
    async def handler(e):
        if not db.check_quota(e.sender_id): return
        
        if e.document and e.file.name and e.file.name.lower().endswith('.torrent'):
            pos = queue.qsize() + 1
            if pos > 1: await e.respond(f"**{STYLE['queue']} En cola: #{pos}**")
            await queue.put((e, "TG_FILE")); return

        if e.text:
            url = e.text.strip()
            if url.startswith(('http', 'magnet')):
                pos = queue.qsize() + 1
                if pos > 1: await e.respond(f"**{STYLE['queue']} En cola: #{pos}**")
                await queue.put((e, url))

    print(f"{STYLE['check']} Conectando..."); await client.start(bot_token=BOT_TOKEN)
    print(f"{STYLE['check']} ONLINE"); await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
