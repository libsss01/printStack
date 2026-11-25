global LAST_PRINT_TIMES
global SHARED_CONFIG
import base64
import os
import sys
import subprocess
import socket
import tempfile
import json
import threading
from io import BytesIO
from datetime import datetime
from PIL import Image
Image.MAX_IMAGE_PIXELS = 2000000
import PIL
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from functools import wraps
import re
import logging
import time


log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
SHARED_CONFIG = {'connection_type': 'bluetooth_direct', 'system_printer_name': '', 'mac_address': '', 'usb_port': '', 'bluetooth_speed': 5}
GUI_APP = None
SYSTEM_LOGS = []
LOG_LOCK = threading.Lock()
PRINT_LOCK = threading.Lock()
LAST_PRINT_TIMES = []
RATE_LIMIT_LOCK = threading.Lock()
app = Flask(__name__)


def load_server_port():
    try:
        config_path = get_config_path()
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                cfg = json.load(f)
                return int(cfg.get('server_port', 20726))
    except Exception:
        pass
    return 20726





def get_config_path():
    appdata = os.getenv('APPDATA')
    if appdata:
        config_dir = os.path.join(appdata, 'PrintStack')
    else:
        config_dir = os.path.join(os.path.expanduser('~'), '.printstack')
    try:
        os.makedirs(config_dir, exist_ok=True)
    except Exception as e:
        print(f'Impossible de creer le repertoire de configuration {config_dir}: {e}')
        return 'config.json'
    target_path = os.path.join(config_dir, 'config.json')
    if not os.path.exists(target_path):
        if getattr(sys, 'frozen', False):
            app_dir = os.path.dirname(sys.executable)
        else:
            app_dir = os.path.dirname(os.path.abspath(__file__))
        candidate_paths = [os.path.join(app_dir, 'config.json'), os.path.join(os.getcwd(), 'config.json')]
        for cand in candidate_paths:
            if os.path.abspath(cand) == os.path.abspath(target_path):
                continue
            else:
                if os.path.exists(cand):
                    try:
                        with open(cand, 'r') as src, open(target_path, 'w') as dest:
                                dest.write(src.read())
                        print(f'Configuration migree de {cand} vers {target_path}')
                    except Exception as e:
                        print(f'Erreur de migration de {cand}: {e}')
                    else:
                        return target_path
    return target_path


def log_message(level, msg):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = {'timestamp': timestamp, 'level': level, 'message': msg}
    with LOG_LOCK:
        SYSTEM_LOGS.append(log_entry)
        if len(SYSTEM_LOGS) > 100:
            SYSTEM_LOGS.pop(0)
    try:
        log_file = get_log_file_path()
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f'[{level}] {timestamp} - {sanitize_log_input(msg)}\n')
    except Exception as e:
        print(f'Erreur ecriture log fichier: {e}')
    print(f'[{level}] {timestamp} - {msg}')



def load_allowed_origins():
    try:
        config_path = get_config_path()
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
                allowed_origins:list = config.get('allowed_origins', ['http://localhost:20726'])

                if not isinstance(allowed_origins, list):
                    return ['http://localhost:20726']

                for i, origin in enumerate(allowed_origins):
                    if not isinstance(origin, str) or not (origin.startswith('http://') or origin.startswith('https://')):
                        allowed_origins[i] = 'http://localhost:20726'
                        log_message("WARNING", f"L'origin est invalide. Veuillez écrire une origin valide {origin}" )

                return allowed_origins
    except Exception:
        pass
    return ['http://localhost:20726']





def validate_origin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        origin = request.headers.get('Origin', '')
        if origin and origin not in ALLOWED_ORIGINS:
            log_message('WARNING', f'Requete bloquee depuis une origine non autorisee: {origin}')
            return (jsonify({'error': 'Origine non autorisee'}), 403)
        else:
            return f(*args, **kwargs)
    return decorated_function
USB_PATH_PATTERNS = [re.compile('^/dev/usb/lp\\d+$'), re.compile('^(\\\\\\\\\\.\\\\)?COM\\d{1,2}$', re.IGNORECASE), re.compile('^(\\\\\\\\\\.\\\\)?LPT\\d$', re.IGNORECASE)]


def is_valid_usb_path(path):
    """N\'autorise que les chemins de peripheriques USB d\'impression legitimes."""
    return any((pattern.match(path) for pattern in USB_PATH_PATTERNS))
MAC_ADDRESS_PATTERN = re.compile('^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$')


def is_valid_mac_address(mac):
    """N\'autorise que les adresses MAC au format XX:XX:XX:XX:XX:XX."""
    return bool(MAC_ADDRESS_PATTERN.match(mac))


def sanitize_log_input(text, max_length=500):
    """Supprime les caracteres de controle et limite la longueur pour eviter l\'injection de log."""
    if not isinstance(text, str):
        text = str(text)
    cleaned = text.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
    return cleaned[:max_length]

def limit_print_rate(limit=10, period=60):
    """Limite le nombre de requetes d\'impression a \'limit\' par \'period\' secondes."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            global LAST_PRINT_TIMES
            now = time.time()
            with RATE_LIMIT_LOCK:
                LAST_PRINT_TIMES = [t for t in LAST_PRINT_TIMES if now - t < period]
                if len(LAST_PRINT_TIMES) >= limit:
                    log_message('WARNING', f'Rate limit atteint. Blocage de l\'impression ({limit} impressions max par {period}s).')
                    return (jsonify({'error': 'Trop de requetes d\'impression. Veuillez patienter avant de reessayer.'}), 429)
                else:
                    LAST_PRINT_TIMES.append(now)
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def get_log_file_path():
    try:
        config_path = get_config_path()
        return os.path.join(os.path.dirname(config_path), 'printstack_server.log')
    except Exception:
        return 'printstack_server.log'

def send_payload_to_printer(payload):
    with PRINT_LOCK:
        conn_type = SHARED_CONFIG.get('connection_type', 'system_printer')
    if conn_type == 'bluetooth_direct':
        mac = SHARED_CONFIG.get('mac_address')
        if not mac:
            raise Exception('Aucune imprimante Bluetooth configurée.')
        else:
            def connect_bt(mac_address, timeout):
                if sys.platform == 'win32':
                    af_bth = getattr(socket, 'AF_BTH', 32)
                    bthproto = getattr(socket, 'BTHPROTO_RFCOMM', 3)
                    s = socket.socket(af_bth, socket.SOCK_STREAM, bthproto)
                else:
                    af_bt = getattr(socket, 'AF_BLUETOOTH', 31)
                    btproto = getattr(socket, 'BTPROTO_RFCOMM', 3)
                    s = socket.socket(af_bt, socket.SOCK_STREAM, btproto)
                s.settimeout(timeout)
                s.connect((mac_address, 1))
                return s
            try:
                sock = connect_bt(mac, 8)
            except OSError as e:
                log_message('WARNING', f'Première tentative Bluetooth échouée ({e}). Lancement d\'un rafraîchissement...')
                try:
                    if sys.platform == 'win32':
                        subprocess.run(['powershell', '-Command', 'Get-PnpDevice -Class Bluetooth -ErrorAction SilentlyContinue'], capture_output=True, stdin=subprocess.DEVNULL, creationflags=134217728)
                    else:
                        subprocess.run(['bluetoothctl', 'devices'], capture_output=True)
                    time.sleep(1)
                    sock = connect_bt(mac, 15)
                except Exception as e2:
                    raise Exception(f'Impossible de se connecter à l\'imprimante Bluetooth même après rafraîchissement. Vérifiez qu\'elle est allumée. Détail: {e2}')
            bt_speed = int(SHARED_CONFIG.get('bluetooth_speed', 5))
            if bt_speed == 5:
                sock.sendall(payload)
            else:
                chunk_configs = {1: (64, 0.1), 2: (128, 0.05), 3: (256, 0.02), 4: (512, 0.01)}
                chunk_size, delay = chunk_configs.get(bt_speed, (256, 0.02))
                log_message('INFO', f'Envoi fragmenté (Vitesse {bt_speed}) : chunks de {chunk_size} octets, pause de {int(delay * 1000)}ms')
                for i in range(0, len(payload), chunk_size):
                    chunk = payload[i:i + chunk_size]
                    sock.sendall(chunk)
                    time.sleep(delay)
            sock.close()
            log_message('SUCCESS', f'Impression Bluetooth réussie sur {mac}')
    else:
        if conn_type == 'usb_direct':
            usb_port = SHARED_CONFIG.get('usb_port')
            if not usb_port or 'Aucun' in usb_port:
                raise Exception('Aucun port USB configuré.')
            else:
                if not os.path.exists(usb_port):
                    raise Exception(f'Le port {usb_port} n\'existe pas. L\'imprimante est-elle débranchée ?')
                else:
                    try:
                        with open(usb_port, 'wb') as f:
                            f.write(payload)
                            f.flush()
                        log_message('SUCCESS', f'Impression USB direct réussie sur {usb_port}')
                    except PermissionError:
                        raise Exception('Permission refusée. Déconnectez puis reconnectez votre session Linux pour appliquer les droits d\'accès USB.')
        else:
            printer_name = SHARED_CONFIG.get('system_printer_name')
            if not printer_name or printer_name == 'Aucune imprimante disponible':
                raise Exception('Aucune imprimante système n\'est configurée.')
            else:
                if sys.platform == 'win32':
                    try:
                        import win32print
                    except ImportError:
                        raise Exception('Le module pywin32 n\'est pas installé. Lancez: pip install pywin32')
                    hPrinter = win32print.OpenPrinter(printer_name)
                    try:
                        win32print.StartDocPrinter(hPrinter, 1, ('Ticket', None, 'RAW'))
                        win32print.StartPagePrinter(hPrinter)
                        win32print.WritePrinter(hPrinter, payload)
                        win32print.EndPagePrinter(hPrinter)
                        win32print.EndDocPrinter(hPrinter)
                        log_message('SUCCESS', f'Impression système réussie sur \'{printer_name}\' (Windows)')
                    finally:
                        win32print.ClosePrinter(hPrinter)
                else:
                    with tempfile.NamedTemporaryFile(delete=False) as f:
                        f.write(payload)
                        f.flush()
                        tmp_name = f.name
                    try:
                        result = subprocess.run(['lp', '-d', printer_name, '-o', 'raw', tmp_name], capture_output=True, text=True)
                        if result.returncode != 0:
                            raise Exception(f'Erreur d\'impression CUPS: {result.stderr}')
                        else:
                            log_message('SUCCESS', f'Impression CUPS réussie sur \'{printer_name}\'')
                    finally:
                        if os.path.exists(tmp_name):
                            os.remove(tmp_name)


def get_resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    else:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

SERVER_PORT = load_server_port()
ALLOWED_ORIGINS = load_allowed_origins()
CORS(app, origins=ALLOWED_ORIGINS, supports_credentials=False)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 Mo
    
@app.route('/demo')
def demo_page():
    """Demo applicatif à consulter"""
    """Page de test d\'impression accessible via http://localhost:20726/demo"""
    try:
        return send_file(get_resource_path('pos_demo.html'))
    except Exception:
        return ('Fichier pos_demo.html introuvable', 404)

    
@app.route('/api/status', methods=['GET'])
@validate_origin
def get_status():
    return jsonify({'status': 'ACTIVE', 'port': SERVER_PORT, 'host': 'localhost', 'config': SHARED_CONFIG})


def scan_printers():
    printers = []
    try:
        if sys.platform == 'win32':
            import win32print
            printers_raw = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)
            printers = [p[2] for p in printers_raw]
        else:
            result = subprocess.run(['lpstat', '-p'], capture_output=True, text=True)
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if line.startswith('printer '):
                        parts = line.split(' ')
                        if len(parts) >= 2:
                            printers.append(parts[1])
    except Exception as e:
        log_message('ERROR', f'Erreur lors du scan des imprimantes: {e}')
    return printers



def scan_usb_direct():
    ports = []
    if sys.platform != 'win32':
        import glob
        ports = glob.glob('/dev/usb/lp*')
    return ports


def scan_bluetooth():
    devices = []
    try:
        if sys.platform == 'win32':
            ps_cmd = 'Get-PnpDevice -Class Bluetooth -ErrorAction SilentlyContinue | Select-Object -Property FriendlyName, InstanceId | ConvertTo-Json'
            creation_flags = getattr(subprocess, 'CREATE_NO_WINDOW', 134217728)
            result = subprocess.run(['powershell', '-Command', ps_cmd], capture_output=True, text=True, errors='ignore', stdin=subprocess.DEVNULL, creationflags=creation_flags)
            if result.returncode == 0 and result.stdout and result.stdout.strip():
                try:
                    data = json.loads(result.stdout)
                    if isinstance(data, dict):
                        data = [data]
                    for item in data:
                        name = item.get('FriendlyName')
                        iid = item.get('InstanceId')
                        if name and iid and ('DEV_' in iid.upper()):
                            parts = iid.upper().split('DEV_')
                            if len(parts) > 1:
                                mac_raw = parts[1][:12]
                                if len(mac_raw) == 12:
                                    mac = ':'.join((mac_raw[i:i + 2] for i in range(0, 12, 2)))
                                    friendly = f'{name} - {mac}'
                                    if friendly not in [d['friendly'] for d in devices]:
                                        devices.append({'mac': mac, 'name': name, 'friendly': friendly})
                except json.JSONDecodeError:
                    pass
        else:
            result = subprocess.run(['bluetoothctl', 'devices'], capture_output=True, text=True)
            if result.stdout:
                lines = result.stdout.strip().splitlines()
                for line in lines:
                    if line.startswith('Device '):
                        parts = line.split(' ', 2)
                        if len(parts) >= 3:
                            mac = parts[1]
                            name = parts[2]
                            devices.append({'mac': mac, 'name': name, 'friendly': f'{name} - {mac}'})
    except Exception as e:
        log_message('ERROR', f'Erreur lors du scan bluetooth: {e}')
    return devices


@app.route('/api/printers', methods=['GET'])
@validate_origin
def get_printers():
    device_type = request.args.get('type', 'usb')
    if device_type == 'bluetooth':
        bt_devices = scan_bluetooth()
        res = []
        current_mac = SHARED_CONFIG.get('mac_address', '')
        for dev in bt_devices:
            res.append({'id': dev['mac'], 'name': dev['name'], 'friendly': dev['friendly'], 'status': 'Appairé', 'selected': dev['mac'].lower() == current_mac.lower()})
        return jsonify(res)
    else:
        sys_printers = scan_printers()
        usb_ports = scan_usb_direct()
        res = []
        current_printer = SHARED_CONFIG.get('system_printer_name', '')
        current_usb = SHARED_CONFIG.get('usb_port', '')
        current_conn = SHARED_CONFIG.get('connection_type', '')
        for prn in sys_printers:
            res.append({'id': prn, 'name': prn, 'status': 'Prêt', 'selected': prn == current_printer and current_conn == 'system_printer', 'mode': 'system_printer'})
        for port in usb_ports:
            res.append({'id': port, 'name': f'Direct USB ({port})', 'status': 'Direct USB', 'selected': port == current_usb and current_conn == 'usb_direct', 'mode': 'usb_direct'})
        return jsonify(res)


    
@app.route('/api/config', methods=['POST'])
@validate_origin
def update_config():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):

        log_message('WARNING', f'Format de la requête non prise en charge')
        return (jsonify({'error': 'Format de la requete invalide'}), 400)
    
    if not data:
        return (jsonify({'error': 'Données manquantes'}), 400)
    else:
        conn_type = data.get('connection_type')
        if conn_type not in ['system_printer', 'bluetooth_direct', 'usb_direct']:
            return (jsonify({'error': 'Type de connexion invalide'}), 400)
        else:
            SHARED_CONFIG['connection_type'] = conn_type
            if conn_type == 'system_printer':
                SHARED_CONFIG['system_printer_name'] = data.get('system_printer_name', '')
            else:
                if conn_type == 'bluetooth_direct':
                    mac_value = data.get('mac_address', '')
                    if mac_value and (not is_valid_mac_address(mac_value)):
                        log_message('WARNING', f'Tentative de configuration Bluetooth avec une adresse MAC invalide: {sanitize_log_input(mac_value)}')
                        return (jsonify({'error': 'Adresse MAC invalide. Format attendu: XX:XX:XX:XX:XX:XX'}), 400)
                    else:
                        SHARED_CONFIG['mac_address'] = mac_value
                else:
                    if conn_type == 'usb_direct':
                        usb_port_value = data.get('usb_port', '')
                        if usb_port_value and (not is_valid_usb_path(usb_port_value)):
                            log_message('WARNING', f'Tentative de configuration USB avec un chemin non autorise: {usb_port_value}')
                            return (jsonify({'error': 'Chemin USB invalide. Seuls les peripheriques /dev/usb/lpX sont autorises.'}), 400)
                        else:
                            SHARED_CONFIG['usb_port'] = usb_port_value
            if 'bluetooth_speed' in data:
                SHARED_CONFIG['bluetooth_speed'] = int(data['bluetooth_speed'])
            try:
                config_path = get_config_path()
                current_disk_config = {}
                if os.path.exists(config_path):
                    with open(config_path, 'r') as f:
                        current_disk_config = json.load(f)
                current_disk_config['connection_type'] = conn_type
                if conn_type == 'system_printer':
                    current_disk_config['system_printer_name'] = SHARED_CONFIG['system_printer_name']
                else:
                    if conn_type == 'bluetooth_direct':
                        current_disk_config['mac_address'] = data.get('friendly_name', SHARED_CONFIG['mac_address'])
                    else:
                        if conn_type == 'usb_direct':
                            current_disk_config['usb_port'] = SHARED_CONFIG['usb_port']
                if 'bluetooth_speed' in SHARED_CONFIG:
                    current_disk_config['bluetooth_speed'] = SHARED_CONFIG['bluetooth_speed']
                with open(config_path, 'w') as f:
                    json.dump(current_disk_config, f)
                log_message('INFO', f'Configuration mise à jour via l\'API: {conn_type} - {SHARED_CONFIG.get("system_printer_name") or SHARED_CONFIG.get("mac_address") or SHARED_CONFIG.get("usb_port")}')
                if GUI_APP:
                    GUI_APP.after(0, GUI_APP.load_config_from_shared)
                return jsonify({'success': True})
            except Exception as e:
                log_message('ERROR', f'Erreur lors de la sauvegarde de la config: {e}')
                return (jsonify({'error': str(e)}), 500)


            
@app.route('/api/restart', methods=['POST'])
@validate_origin
def restart_server_api():
    log_message('WARNING', 'Demande de redémarrage de l\'application reçue...')
    if GUI_APP:
        GUI_APP.after(0, GUI_APP.restart_app)
        return jsonify({'success': True, 'message': 'Redémarrage de l\'application initié'})
    else:
        def self_restart():
            import time
            time.sleep(1)
            python = sys.executable
            os.execl(python, python, *sys.argv)
        import threading
        threading.Thread(target=self_restart).start()
        return jsonify({'success': True, 'message': 'Redémarrage du serveur autonome initié'})

@app.route('/print/image',methods=['POST'])
@validate_origin
@limit_print_rate(limit=10, period=60)
def print_image():
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            log_message('WARNING', f'Contenu de la requête invalide (Liste..).')
            return (jsonify({'error': 'Contenu de la requete invalide'}), 400)
        
        content = data.get('content', '')

        if not content:
            return (jsonify({'error': 'Contenue de la requete manquante'}), 400)
        else:
            log_message('INFO', f"Job d\'impression reçu d'image")
            payload = b''
            if not isinstance(content, str):
                log_message('WARNING', f' Type invalide : chaîne base64 attendue. Tout autre type est invalide')
                return (jsonify({'error': 'Type accepté : Chaine de caractère . Veuillez donner un base64 étant une image'}), 400)
            if ',' in content:
                content = content.split(',')[1]
            img_data = base64.b64decode(content, validate=True)
            img = Image.open(BytesIO(img_data))
            if img.width > 384:
                ratio = 384.0 / float(img.width)
                new_height = int(float(img.height) * float(ratio))
                img = img.resize((384, new_height), Image.Resampling.LANCZOS)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            from escpos.printer import Dummy
            dummy = Dummy()
            dummy.image(img)
            dummy.cut()
            payload = dummy.output    
            send_payload_to_printer(payload)
        return jsonify({'success': True})
        
    except base64.binascii.Error:
        log_message("ERROR", f"La valeur donne n'est pas une image : {sanitize_log_input(content)}")
        return (jsonify({'error': "La valeur donnee ne correspond pas a une image"}), 400)
    except PIL.UnidentifiedImageError:
        log_message("ERROR", f"La valeur donné n'est pas une image : {sanitize_log_input(content)}")
        return (jsonify({'error': "L'image ne peut etre ouverte ou n'est pas reconnu"}), 400)
    except Exception as e:
        log_message('ERROR', f'Échec de l\'impression : {sanitize_log_input(str(e))}')
        return (jsonify({'error': 'Erreur interne lors de l\'impression. Consultez les logs du serveur.'}), 500)

@app.route('/print/text', methods=['POST'])
@validate_origin
@limit_print_rate(limit=10, period=60)
def print_text():
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            log_message('WARNING', f'Format de la requête non prise en charge.')
            return (jsonify({'error': 'Format de la requete invalide'}), 400)

        if not data :
            log_message('WARNING', f'Contenu de la requête vide.')
            return (jsonify({'error': 'Veuillez entrer  les données demandés'}), 400)
        else:
            content:str = data.get('content', '')
            if not content:
                return (jsonify({'error': 'Contenu de la requete manquante'}), 400)
            
            if not isinstance(content, str):
                log_message('WARNING', f'Type d\'impression non autorise pour ce mode')
                return (jsonify({'error': 'Type de contenu non supporté. Valeur acceptee: text'}), 400)
                
            else:
                log_message('INFO', f'Job d\'impression de text reçu  ')
                payload = b''
                init_cmd = b'\x1b@'
                text_cmd = str(content).encode('utf-8')
                feed_cmd = b'\n\n\n\x1dV\x00'
                payload = init_cmd + text_cmd + feed_cmd
                send_payload_to_printer(payload)
        return jsonify({'success': True})

    except Exception as e:
        log_message('ERROR', f'Échec de l\'impression : {sanitize_log_input(str(e))}')
        return (jsonify({'error': 'Erreur interne lors de l\'impression. Consultez les logs du serveur.'}), 500)


@app.route('/print/esc-pos', methods=['POST'])
@validate_origin
@limit_print_rate(limit=10, period=60)
def print_raw():
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            log_message('WARNING', f'Format de la requête non prise en charge')
            return (jsonify({'error': 'Format de la requete invalide'}), 400)

        if not data :
            log_message('WARNING', f'Contenu de la requête vide.')
            return (jsonify({'error': 'Veuillez entrer  les données demandés'}), 400)
        else:
            command = data.get('data', '')
            if not command:
                log_message('WARNING', f'Aucune commande ESC/POS a été envoyé.')
                return (jsonify({'error': 'Champs vide. Veuillez donner en entree une commande ESC/POS'}), 400)
            if isinstance(command, str):
                command_decoded = base64.b64decode(command, validate=True)
                send_payload_to_printer(command_decoded)
                return jsonify({'success': True})
            else:
                log_message('WARNING', f' Type invalide : chaîne base64 attendue. Tout autre type est invalide')
                return (jsonify({'error': 'Type accepté : Chaine de caractère . Veuillez donner en entree une commande ESC/POS'}), 400)
            
    except base64.binascii.Error:
            log_message("ERROR", f'Commande ESC/POS non valide : {sanitize_log_input(str(command))}')
            return (jsonify({'error': 'Commandes ESC/POS invalide'}), 400)
    except Exception as e:
        log_message('ERROR', f'Échec de l\'impression : {sanitize_log_input(str(e))}')
        return (jsonify({'error': 'Erreur interne lors de l\'impression. Consultez les logs du serveur.'}), 500)
    

    
def run_server():
    log_message('INFO', f'Démarrage du serveur Flask sur http://localhost:{SERVER_PORT}')
    app.run(host='127.0.0.1', port=SERVER_PORT, debug=False, use_reloader=False)


if __name__ == '__main__':
    run_server()