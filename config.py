# Configuración centralizada
CONFIG = {
    'log_dir': r"XXXXX",
    'exe_path': r"XXXXXXXXX",  # Ruta donde se guardará el .exe
    'max_log_size': 50 * 1024 * 1024,  # 50 MB
    'log_rotation': 5,
    'email_interval': 30,  # minuto
    'email': {
        'smtp_server': 'smtp.gmail.com',
        'smtp_port': 587,
        'sender': 'XXXXXXXX@gmail.com',
        'password': 'XXXXXXX',
        'recipient': 'XXXXXX'
    }
} 