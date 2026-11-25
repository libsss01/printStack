import threading
import sys
import subprocess
import socket
import json
import os
import time
import customtkinter as ctk
import tkinter.messagebox as messagebox
from PIL import Image, ImageTk
import pystray
from print_server import run_server, SHARED_CONFIG, SYSTEM_LOGS, get_config_path, LOG_LOCK
import print_server
CONFIG_FILE = get_config_path()



def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_config_file(config):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f)
    except Exception as e:
        print('Erreur sauvegarde config:', e)



# Palette dérivée du logo PrintStack (bleu des feuilles, anthracite de l'imprimante,
# gris des couches, voyant turquoise).
COLOR_PRIMARY = '#0f5e8c'        # bleu de la feuille du haut
COLOR_SECONDARY = '#0b4a6f'      # bleu foncé (survol, titres de cartes)
COLOR_ACCENT = '#22a6c4'         # voyant turquoise
COLOR_BG = '#f5f7f9'
COLOR_CARD_BG = '#ffffff'
COLOR_CARD_BORDER = '#d5dbe1'
COLOR_TEXT_PRIMARY = '#1f2329'   # anthracite du corps de l'imprimante
COLOR_TEXT_MUTED = '#5f6b78'     # gris des couches intermédiaires
COLOR_ON_PRIMARY = '#ffffff'
COLOR_HOVER_LIGHT = '#e6f0f6'    # survol des boutons transparents
COLOR_HOVER_NEUTRAL = '#e3e8ed'
COLOR_SURFACE_MUTED = '#eef2f5'  # fonds de champs / conteneurs internes
COLOR_SEPARATOR = '#e3e8ed'
COLOR_BADGE_BG = '#d6e8f3'
COLOR_SELECTED_BG = '#f0f6fa'
COLOR_DARK_TOOLBAR = '#262b33'
COLOR_DARK_CONSOLE = '#1b1f24'
COLOR_DARK_HOVER = '#3a4250'
COLOR_RESTART_BG = '#d3eef5'
COLOR_RESTART_HOVER = '#bfe5ef'
# Couleurs sémantiques (état / erreur) : volontairement conservées.
COLOR_SUCCESS = '#2e7d32'
COLOR_ERROR = '#ba1a1a'
ctk.set_appearance_mode('Light')
ctk.set_default_color_theme('blue')

ICON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'images', 'icon.ico')
HEADER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'images', 'logoheader.png')
TRAY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'images', 'printstack_logo.png')

class CockpitApp(ctk.CTk):
    # ***<module>.CockpitApp: Failure: Different bytecode
    """CockpitApp"""
    def __init__(self):
        super().__init__()
        self.title('PrintStack Manager')
        self.geometry('880x560')
        self.minsize(800, 480)
        self.configure(fg_color=COLOR_BG)
        try:
            self.iconbitmap(ICON_PATH)
        except Exception:
            pass
        self.protocol('WM_DELETE_WINDOW', self.on_closing)
        self.check_single_instance()
        self.printer_var = ctk.StringVar()
        self.mac_address_var = ctk.StringVar()
        self.usb_port_var = ctk.StringVar()
        self.conn_type_var = ctk.StringVar(value='bluetooth_direct')
        self.test_text_var = ctk.StringVar(value='Test d\'impression 58mm OK!')
        self.server_status_var = ctk.StringVar(value='ACTIF')
        self.server_thread = None
        self.icon_obj = None
        self.config_data = load_config()
        self.server_port = int(self.config_data.get('server_port', 20726))
        print_server.SERVER_PORT = self.server_port
        self.saved_printer = self.config_data.get('system_printer_name', '')
        self.saved_mac = self.config_data.get('mac_address', '')
        self.saved_usb_port = self.config_data.get('usb_port', '')
        self.saved_conn_type = self.config_data.get('connection_type', 'bluetooth_direct')
        self.saved_bt_speed = int(self.config_data.get('bluetooth_speed', 5))
        self.bt_speed_var = ctk.StringVar(value=str(self.saved_bt_speed))
        self.conn_type_var.set(self.saved_conn_type)
        SHARED_CONFIG['connection_type'] = self.saved_conn_type
        SHARED_CONFIG['bluetooth_speed'] = self.saved_bt_speed
        print_server.GUI_APP = self
        self.last_log_count = 0
        self.is_scanning = False
        self.last_scan_results = None
        self.setup_ui()
        if self.saved_printer:
            self.printer_var.set(self.saved_printer)
            SHARED_CONFIG['system_printer_name'] = self.saved_printer
        if self.saved_mac:
            self.mac_address_var.set(self.saved_mac)
            SHARED_CONFIG['mac_address'] = self.saved_mac.split(' - ')[(-1)].strip() if ' - ' in self.saved_mac else self.saved_mac.strip()
        if self.saved_usb_port:
            self.usb_port_var.set(self.saved_usb_port)
            SHARED_CONFIG['usb_port'] = self.saved_usb_port
        self.toggle_server()
        self.scan_all()
        self.update_speed_card_state()
        self.poll_logs()
        if len(sys.argv) > 1 and sys.argv[1] == '--minimized':
                self.after(100, self.show_in_tray)



    def setup_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0)
        self.header_frame = ctk.CTkFrame(self, height=100, corner_radius=0, fg_color=COLOR_CARD_BG, border_color=COLOR_CARD_BORDER, border_width=1)
        self.header_frame.grid(row=0, column=0, sticky='ew')
        self.header_frame.grid_propagate(True)
        self.header_frame.grid_columnconfigure(0, weight=0)
        self.header_frame.grid_columnconfigure(1, weight=1)
        self.title_container = ctk.CTkFrame(self.header_frame, fg_color='transparent')
        self.title_container.grid(row=0, column=0, padx=(20, 10), pady=12, sticky='w')
        if os.path.exists(HEADER_PATH):
            try:
                logo_img = Image.open(HEADER_PATH)
                self.logo_ctk = ctk.CTkImage(light_image=logo_img, dark_image=logo_img, size=(145,48))
                self.logo_img_label = ctk.CTkLabel(self.title_container, image=self.logo_ctk, text='')
                self.logo_img_label.grid(row=0, column=0, padx=(5, 10))
            except Exception:
                pass
        self.nav_container = ctk.CTkFrame(self.header_frame, fg_color='transparent')
        self.nav_container.grid(row=0, column=1, padx=(10, 20), pady=12, sticky='e')
        self.nav_container.grid_rowconfigure(0, weight=1)
        self.nav_container.grid_rowconfigure(1, weight=0)
        self.tabs = {}
        self.tab_buttons = {}
        self.tab_indicators = {}
        tab_names = [('dashboard', 'Dashboard'), ('journal', 'Journal'), ('settings', 'Réglages')]
        for i, (tab_id, tab_label) in enumerate(tab_names):
            btn = ctk.CTkButton(
                self.nav_container,
                text=tab_label,
                font=ctk.CTkFont(family='PT Sans', size=11, weight='bold'),
                fg_color='transparent',
                hover_color=COLOR_HOVER_LIGHT,
                text_color=COLOR_TEXT_MUTED,
                height=28,
                corner_radius=0,
                command=lambda tid=tab_id: self.switch_tab(tid)
            )
            btn.grid(row=0, column=i, padx=8, pady=(5, 0), sticky='ew')
            self.tab_buttons[tab_id] = btn
            indicator = ctk.CTkFrame(self.nav_container, height=3, corner_radius=0, fg_color='transparent')
            indicator.grid(row=1, column=i, padx=8, pady=0, sticky='ew')
            self.tab_indicators[tab_id] = indicator
        self.content_container = ctk.CTkFrame(self, fg_color='transparent')
        self.content_container.grid(row=1, column=0, sticky='nsew', padx=20, pady=20)
        self.content_container.grid_columnconfigure(0, weight=1)
        self.content_container.grid_rowconfigure(0, weight=1)
        self.tab_frames = {}
        self.tab_frames['dashboard'] = self.create_dashboard_frame()
        self.tab_frames['journal'] = self.create_journal_frame()
        self.tab_frames['settings'] = self.create_settings_frame()
        self.switch_tab('dashboard')
        self.footer_frame = ctk.CTkFrame(self, height=40, corner_radius=0, fg_color=COLOR_BG, border_color=COLOR_CARD_BORDER, border_width=1)
        self.footer_frame.grid(row=2, column=0, sticky='ew')
        self.footer_frame.grid_propagate(False)
        self.footer_frame.grid_columnconfigure(0, weight=1)
        self.footer_label = ctk.CTkLabel(self.footer_frame, text='Made in Dakar - PrintStack -  Sénégal 2026', font=ctk.CTkFont(family='PT Sans', size=11), text_color=COLOR_TEXT_MUTED)
        self.footer_label.grid(row=0, column=0, padx=20, pady=8, sticky='w')
        self.blink_status()



    def blink_status(self):
        if hasattr(self, 'state_dot_lbl') and self.state_dot_lbl.winfo_exists():
                import math
                t = (math.sin(time.time() * 2.5) + 1.0) / 2.0
                status = self.server_status_var.get()
                if status == 'ACTIF':
                    r = int(46 + 119 * t)
                    g = int(125 + 89 * t)
                    b = int(50 + 117 * t)
                else:
                    r = int(186 + 69 * t)
                    g = int(26 + 179 * t)
                    b = int(26 + 184 * t)
                color_hex = f'#{r:02x}{g:02x}{b:02x}'
                self.state_dot_lbl.configure(text_color=color_hex)
                if hasattr(self, 'state_text_lbl') and self.state_text_lbl.winfo_exists():
                        self.state_text_lbl.configure(text_color=color_hex)
        self.after(50, self.blink_status)


    def switch_tab(self, tab_id):
        for frame in self.tab_frames.values():
            frame.grid_forget()
        self.tab_frames[tab_id].grid(row=0, column=0, sticky='nsew')
        for tid, btn in self.tab_buttons.items():
            indicator = self.tab_indicators[tid]
            if tid == tab_id:
                btn.configure(text_color=COLOR_PRIMARY)
                indicator.configure(fg_color=COLOR_PRIMARY)
            else:
                btn.configure(text_color=COLOR_TEXT_MUTED)
                indicator.configure(fg_color='transparent')



    def create_dashboard_frame(self):
        frame = ctk.CTkFrame(self.content_container, fg_color='transparent')
        frame.grid_columnconfigure(0, minsize=400, weight=0)
        frame.grid_columnconfigure(1, weight=1)
        frame.grid_rowconfigure(0, weight=0)
        frame.grid_rowconfigure(1, weight=1)
        status_card = ctk.CTkFrame(frame, fg_color=COLOR_CARD_BG, border_color=COLOR_CARD_BORDER, border_width=1, corner_radius=12, height=95)
        status_card.grid(row=0, column=0, sticky='nsew', padx=(0, 10), pady=(0, 10))
        status_card.grid_propagate(False)
        status_card.grid_columnconfigure(0, weight=1)
        status_card.grid_columnconfigure(1, weight=0)
        status_card.grid_columnconfigure(2, weight=0)
        status_title = ctk.CTkLabel(status_card, text='SERVEUR', font=ctk.CTkFont(family='PT Sans', size=12, weight='bold'), text_color=COLOR_SECONDARY)
        status_title.grid(row=0, column=0, padx=15, pady=(10, 2), sticky='w')
        self.state_dot_lbl = ctk.CTkLabel(status_card, text='●', font=ctk.CTkFont(family='PT Sans', size=14), text_color=COLOR_SUCCESS)
        self.state_dot_lbl.grid(row=0, column=1, padx=(0, 4), pady=(10, 2), sticky='e')
        self.state_text_lbl = ctk.CTkLabel(status_card, text='ACTIF', font=ctk.CTkFont(family='PT Sans', size=11, weight='bold'), text_color=COLOR_SUCCESS)
        self.state_text_lbl.grid(row=0, column=2, padx=(0, 15), pady=(10, 2), sticky='e')
        info_frame = ctk.CTkFrame(status_card, fg_color=COLOR_SURFACE_MUTED, corner_radius=6)
        info_frame.grid(row=1, column=0, columnspan=3, padx=15, pady=(4, 10), sticky='ew')
        info_frame.grid_columnconfigure(0, weight=1)
        info_frame.grid_columnconfigure(1, weight=1)
        addr_label_lbl = ctk.CTkLabel(info_frame, text='API', font=ctk.CTkFont(family='PT Sans', size=10, weight='bold'), text_color=COLOR_TEXT_MUTED)
        addr_label_lbl.grid(row=0, column=0, padx=10, pady=5, sticky='w')
        self.addr_lbl = ctk.CTkLabel(info_frame, text=f'localhost:{self.server_port}', font=ctk.CTkFont(family='JetBrains Mono', size=11, weight='bold'), text_color=COLOR_TEXT_PRIMARY)
        self.addr_lbl.grid(row=0, column=1, padx=10, pady=5, sticky='e')
        print_card = ctk.CTkFrame(frame, fg_color=COLOR_CARD_BG, border_color=COLOR_CARD_BORDER, border_width=1, corner_radius=12)
        print_card.grid(row=1, column=0, sticky='nsew', padx=(0, 10), pady=(10, 0))
        print_card.grid_columnconfigure(0, weight=1)
        print_card.grid_rowconfigure(2, weight=1)
        print_title = ctk.CTkLabel(print_card, text='Impression Rapide', font=ctk.CTkFont(family='PT Sans', size=15, weight='bold'), text_color=COLOR_SECONDARY)
        print_title.grid(row=0, column=0, padx=20, pady=(15, 2), sticky='w')
        print_desc = ctk.CTkLabel(print_card, text='Texte à imprimer immédiatement.', font=ctk.CTkFont(family='PT Sans', size=11), text_color=COLOR_TEXT_MUTED)
        print_desc.grid(row=1, column=0, padx=20, pady=(0, 5), sticky='w')
        self.test_entry = ctk.CTkTextbox(print_card, font=ctk.CTkFont(family='PT Sans', size=12), border_width=1, border_color=COLOR_CARD_BORDER, fg_color=COLOR_BG)
        self.test_entry.insert('1.0', self.test_text_var.get())
        self.test_entry.grid(row=2, column=0, padx=20, pady=(0, 10), sticky='nsew')
        self.btn_test_print = ctk.CTkButton(print_card, text='Lancer', font=ctk.CTkFont(family='PT Sans', size=11, weight='bold'), fg_color=COLOR_PRIMARY, hover_color=COLOR_SECONDARY, text_color=COLOR_ON_PRIMARY, height=32, command=self.test_print)
        self.btn_test_print.grid(row=3, column=0, padx=20, pady=(0, 5), sticky='ew')
        self.btn_refresh = ctk.CTkButton(print_card, text='Actualiser', font=ctk.CTkFont(family='PT Sans', size=11, weight='bold'), fg_color='transparent', text_color=COLOR_PRIMARY, border_color=COLOR_PRIMARY, border_width=1, hover_color=COLOR_HOVER_LIGHT, height=32, command=self.scan_all)
        self.btn_refresh.grid(row=4, column=0, padx=20, pady=(5, 15), sticky='ew')
        config_parent = ctk.CTkFrame(frame, fg_color='transparent')
        config_parent.grid(row=0, column=1, rowspan=2, sticky='nsew', padx=(10, 0))
        config_parent.grid_columnconfigure(0, weight=1)
        config_parent.grid_rowconfigure(0, weight=0)
        config_parent.grid_rowconfigure(1, weight=0)
        config_parent.grid_rowconfigure(2, weight=1)
        mode_card = ctk.CTkFrame(config_parent, fg_color=COLOR_CARD_BG, border_color=COLOR_CARD_BORDER, border_width=1, corner_radius=12, height=95)
        mode_card.grid(row=0, column=0, sticky='ew', pady=(0, 10))
        mode_card.grid_propagate(False)
        mode_card.grid_columnconfigure(0, weight=1)
        mode_title = ctk.CTkLabel(mode_card, text='MODE DE CONNEXION', font=ctk.CTkFont(family='PT Sans', size=12, weight='bold'), text_color=COLOR_SECONDARY)
        mode_title.grid(row=0, column=0, padx=20, pady=(12, 2), sticky='w')
        self.mode_btn_container = ctk.CTkFrame(mode_card, fg_color=COLOR_SURFACE_MUTED, corner_radius=8, border_color=COLOR_CARD_BORDER, border_width=1)
        self.mode_btn_container.grid(row=1, column=0, padx=20, pady=(2, 10), sticky='ew')
        self.mode_btn_container.grid_columnconfigure(0, weight=1)
        self.mode_btn_container.grid_columnconfigure(1, weight=1)
        self.btn_mode_bt = ctk.CTkButton(self.mode_btn_container, text='BLUETOOTH', font=ctk.CTkFont(family='PT Sans', size=11, weight='bold'), fg_color=COLOR_PRIMARY if self.saved_conn_type == 'bluetooth_direct' else 'transparent', text_color=COLOR_ON_PRIMARY if self.saved_conn_type == 'bluetooth_direct' else COLOR_TEXT_MUTED, hover_color=COLOR_SECONDARY if self.saved_conn_type == 'bluetooth_direct' else COLOR_HOVER_NEUTRAL, height=30, corner_radius=6, command=lambda: self.set_conn_mode('bluetooth_direct'))
        self.btn_mode_bt.grid(row=0, column=0, padx=3, pady=3, sticky='ew')
        self.btn_mode_usb = ctk.CTkButton(self.mode_btn_container, text='USB', font=ctk.CTkFont(family='PT Sans', size=11, weight='bold'), fg_color=COLOR_PRIMARY if self.saved_conn_type != 'bluetooth_direct' else 'transparent', text_color=COLOR_ON_PRIMARY if self.saved_conn_type != 'bluetooth_direct' else COLOR_TEXT_MUTED, hover_color=COLOR_SECONDARY if self.saved_conn_type != 'bluetooth_direct' else COLOR_HOVER_NEUTRAL, height=30, corner_radius=6, command=lambda: self.set_conn_mode('system_printer'))
        self.btn_mode_usb.grid(row=0, column=1, padx=3, pady=3, sticky='ew')
        self.speed_card = ctk.CTkFrame(config_parent, fg_color=COLOR_CARD_BG, border_color=COLOR_CARD_BORDER, border_width=1, corner_radius=12, height=105)
        self.speed_card.grid(row=1, column=0, sticky='ew', pady=(0, 10))
        self.speed_card.grid_propagate(False)
        self.speed_card.grid_columnconfigure(0, weight=1)
        speed_title = ctk.CTkLabel(self.speed_card, text='VITESSE D\'IMPRESSION BLUETOOTH', font=ctk.CTkFont(family='PT Sans', size=12, weight='bold'), text_color=COLOR_SECONDARY)
        speed_title.grid(row=0, column=0, padx=20, pady=(10, 2), sticky='w')
        self.speed_selector = ctk.CTkSegmentedButton(self.speed_card, values=['1 (Lent)', '2', '3', '4', '5 (Rapide)'], font=ctk.CTkFont(family='PT Sans', size=11, weight='bold'), selected_color=COLOR_PRIMARY, selected_hover_color=COLOR_SECONDARY, height=30, command=self.set_bt_speed)
        self.speed_selector.grid(row=1, column=0, padx=20, pady=(2, 2), sticky='ew')
        speed_labels = {1: '1 (Lent)', 2: '2', 3: '3', 4: '4', 5: '5 (Rapide)'}
        self.speed_selector.set(speed_labels.get(self.saved_bt_speed, '5 (Rapide)'))
        speed_desc = ctk.CTkLabel(self.speed_card, text='Réduisez la vitesse si l\'impression s\'arrête en cours de route.', font=ctk.CTkFont(family='PT Sans', size=10, slant='italic'), text_color=COLOR_TEXT_MUTED)
        speed_desc.grid(row=2, column=0, padx=20, pady=(2, 5), sticky='w')
        self.printers_card = ctk.CTkFrame(config_parent, fg_color=COLOR_CARD_BG, border_color=COLOR_CARD_BORDER, border_width=1, corner_radius=12)
        self.printers_card.grid(row=2, column=0, sticky='nsew', pady=(0, 0))
        self.printers_card.grid_columnconfigure(0, weight=1)
        self.printers_card.grid_rowconfigure(0, weight=0)
        self.printers_card.grid_rowconfigure(1, weight=1)
        printers_header = ctk.CTkFrame(self.printers_card, fg_color='transparent')
        printers_header.grid(row=0, column=0, sticky='ew', padx=20, pady=(15, 10))
        printers_header.grid_columnconfigure(0, weight=1)
        printers_header.grid_columnconfigure(1, weight=0)
        printers_header.grid_columnconfigure(2, weight=0)
        printers_title = ctk.CTkLabel(printers_header, text='SÉLECTION DE L\'IMPRIMANTE', font=ctk.CTkFont(family='PT Sans', size=14, weight='bold'), text_color=COLOR_SECONDARY)
        printers_title.grid(row=0, column=0, sticky='w')
        self.printers_count_lbl = ctk.CTkLabel(printers_header, text='0 DÉTECTÉE', font=ctk.CTkFont(family='PT Sans', size=10, weight='bold'), fg_color=COLOR_BADGE_BG, text_color=COLOR_PRIMARY, corner_radius=12, width=80, height=20)
        self.printers_count_lbl.grid(row=0, column=1, sticky='e')
        self.btn_refresh_printers = ctk.CTkButton(printers_header, text='⟳', font=ctk.CTkFont(size=14, weight='bold'), fg_color='transparent', text_color=COLOR_PRIMARY, hover_color=COLOR_HOVER_LIGHT, width=26, height=20, corner_radius=4, command=self.scan_all)
        self.btn_refresh_printers.grid(row=0, column=2, padx=(5, 0), sticky='e')
        self.printers_scroll = ctk.CTkScrollableFrame(self.printers_card, fg_color='transparent')
        self.printers_scroll.grid(row=1, column=0, sticky='nsew', padx=20, pady=(0, 15))
        self.printers_scroll.grid_columnconfigure(0, weight=1)
        return frame


    
    def create_journal_frame(self):
        frame = ctk.CTkFrame(self.content_container, fg_color=COLOR_CARD_BG, border_color=COLOR_CARD_BORDER, border_width=1, corner_radius=12)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=0)
        frame.grid_rowconfigure(1, weight=1)
        toolbar = ctk.CTkFrame(frame, fg_color=COLOR_DARK_TOOLBAR, height=50, corner_radius=0)
        toolbar.grid(row=0, column=0, sticky='ew')
        toolbar.grid_propagate(False)
        toolbar.grid_columnconfigure(0, weight=1)
        toolbar.grid_columnconfigure(1, weight=0)
        toolbar_title = ctk.CTkLabel(toolbar, text='💻  JOURNAL D\'ACTIVITÉ SYSTÈME', font=ctk.CTkFont(family='PT Sans', size=12, weight='bold'), text_color=COLOR_ON_PRIMARY)
        toolbar_title.grid(row=0, column=0, padx=20, pady=12, sticky='w')
        btn_container = ctk.CTkFrame(toolbar, fg_color='transparent')
        btn_container.grid(row=0, column=1, padx=20, pady=8, sticky='e')
        btn_clear = ctk.CTkButton(btn_container, text='EFFACER', font=ctk.CTkFont(family='PT Sans', size=10, weight='bold'), fg_color='transparent', text_color=COLOR_ON_PRIMARY, border_color=COLOR_ON_PRIMARY, border_width=1, hover_color=COLOR_DARK_HOVER, width=80, height=26, command=self.clear_logs)
        btn_clear.grid(row=0, column=0, padx=5)
        btn_export = ctk.CTkButton(btn_container, text='EXPORTER', font=ctk.CTkFont(family='PT Sans', size=10, weight='bold'), fg_color='transparent', text_color=COLOR_ON_PRIMARY, border_color=COLOR_ON_PRIMARY, border_width=1, hover_color=COLOR_DARK_HOVER, width=80, height=26, command=self.export_logs)
        btn_export.grid(row=0, column=1, padx=5)
        self.log_console = ctk.CTkTextbox(frame, font=ctk.CTkFont(family='JetBrains Mono', size=12), fg_color=COLOR_DARK_CONSOLE, text_color=COLOR_ON_PRIMARY, corner_radius=0, border_width=0)
        self.log_console.grid(row=1, column=0, sticky='nsew')
        self.log_console.configure(state='disabled')
        return frame



    
    def create_settings_frame(self):
        frame = ctk.CTkFrame(self.content_container, fg_color=COLOR_CARD_BG, border_color=COLOR_CARD_BORDER, border_width=1, corner_radius=12)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=0)
        frame.grid_rowconfigure(1, weight=1)
        settings_title = ctk.CTkLabel(frame, text='Paramètres du Serveur', font=ctk.CTkFont(family='PT Sans', size=18, weight='bold'), text_color=COLOR_SECONDARY)
        settings_title.grid(row=0, column=0, padx=30, pady=(30, 20), sticky='w')
        form_container = ctk.CTkFrame(frame, fg_color='transparent')
        form_container.grid(row=1, column=0, padx=30, pady=0, sticky='nsw')
        form_container.grid_columnconfigure(0, weight=1)
        port_lbl = ctk.CTkLabel(form_container, text='Port du Serveur', font=ctk.CTkFont(family='PT Sans', size=13, weight='bold'), text_color=COLOR_TEXT_PRIMARY)
        port_lbl.grid(row=0, column=0, pady=(0, 2), sticky='w')
        port_entry_frame = ctk.CTkFrame(form_container, fg_color='transparent')
        port_entry_frame.grid(row=1, column=0, pady=(0, 10), sticky='ew')
        self.settings_port_entry = ctk.CTkEntry(port_entry_frame, width=200, font=ctk.CTkFont(family='JetBrains Mono', size=12), fg_color=COLOR_SURFACE_MUTED, border_width=1, border_color=COLOR_CARD_BORDER)
        self.settings_port_entry.insert(0, str(self.server_port))
        self.settings_port_entry.configure(state='disabled')
        self.settings_port_entry.grid(row=0, column=0, padx=(0, 10))
        btn_update_port = ctk.CTkButton(port_entry_frame, text='Mettre à jour', font=ctk.CTkFont(family='PT Sans', size=12, weight='bold'), fg_color=COLOR_PRIMARY, state='disabled', text_color=COLOR_ON_PRIMARY, height=30, width=120)
        btn_update_port.grid(row=0, column=1)
        config_file = get_config_path().replace("config.json", "")
        port_note = ctk.CTkLabel(form_container, text=f'Le port par défaut est 20726. (Pour modifier le port, veuillez éditer la clé server_port dans le config.json de votre repértoire {config_file} et redémarrer le serveur)', font=ctk.CTkFont(family='PT Sans', size=11, slant='italic'), text_color=COLOR_TEXT_MUTED)
        port_note.grid(row=2, column=0, pady=(0, 20), sticky='w')
        sep = ctk.CTkFrame(form_container, height=2, fg_color=COLOR_SEPARATOR)
        sep.grid(row=3, column=0, sticky='ew', pady=10)
        control_lbl = ctk.CTkLabel(form_container, text='Contrôle du Processus', font=ctk.CTkFont(family='PT Sans', size=13, weight='bold'), text_color=COLOR_TEXT_PRIMARY)
        control_lbl.grid(row=4, column=0, pady=(10, 5), sticky='w')
        btn_restart = ctk.CTkButton(form_container, text='🔄  Redémarrer le Serveur', font=ctk.CTkFont(family='PT Sans', size=14, weight='bold'), fg_color=COLOR_RESTART_BG, text_color=COLOR_SECONDARY, hover_color=COLOR_RESTART_HOVER, height=45, width=350, command=self.restart_app)
        btn_restart.grid(row=5, column=0, pady=(5, 10), sticky='ew')
        restart_note = ctk.CTkLabel(form_container, text='Le redémarrage relance le serveur d\'impression et l\'interface.', font=ctk.CTkFont(family='PT Sans', size=11, slant='italic'), text_color=COLOR_TEXT_MUTED)
        restart_note.grid(row=6, column=0, sticky='w')
        return frame



    
    def poll_logs(self):
        try:
            new_logs = []
            with LOG_LOCK:
                logs = print_server.SYSTEM_LOGS
                if len(logs) > self.last_log_count:
                    new_logs = list(logs[self.last_log_count:])
                    self.last_log_count = len(logs)
            if new_logs:
                self.log_console.configure(state='normal')
                for log in new_logs:
                    line = f'[{log["level"]}] {log["timestamp"]} - {log["message"]}\n'
                    self.log_console.insert('end', line)
                self.log_console.configure(state='disabled')
                self.log_console.see('end')
        except Exception as e:
            print(f'Erreur de rafraîchissement des logs: {e}')
        self.after(500, self.poll_logs)




    def clear_logs(self):
        self.log_console.configure(state='normal')
        self.log_console.delete('1.0', 'end')
        self.log_console.configure(state='disabled')
        print_server.SYSTEM_LOGS.clear()
        self.last_log_count = 0




    def export_logs(self):
        from tkinter import filedialog
        file_path = filedialog.asksaveasfilename(defaultextension='.txt', filetypes=[('Text files', '*.txt'), ('All files', '*.*')], title='Exporter le journal système')
        if file_path:
            try:
                logs = print_server.SYSTEM_LOGS
                with open(file_path, 'w', encoding='utf-8') as f:
                    for log in logs:
                        f.write(f'[{log["level"]}] {log["timestamp"]} - {log["message"]}\n')
                messagebox.showinfo('Exporté', 'Le journal d\'activité a été exporté avec succès.')
            except Exception as e:
                messagebox.showerror('Erreur', f'Impossible d\'exporter les logs: {e}')



    def set_conn_mode(self, mode):
        self.conn_type_var.set(mode)
        if mode == 'bluetooth_direct':
            self.btn_mode_bt.configure(fg_color=COLOR_PRIMARY, text_color=COLOR_ON_PRIMARY, hover_color=COLOR_SECONDARY)
            self.btn_mode_usb.configure(fg_color='transparent', text_color=COLOR_TEXT_MUTED, hover_color=COLOR_HOVER_NEUTRAL)
        else:
            self.btn_mode_usb.configure(fg_color=COLOR_PRIMARY, text_color=COLOR_ON_PRIMARY, hover_color=COLOR_SECONDARY)
            self.btn_mode_bt.configure(fg_color='transparent', text_color=COLOR_TEXT_MUTED, hover_color=COLOR_HOVER_NEUTRAL)
        self.save_config(show_msg=False)
        self.update_speed_card_state()
        self.last_scan_results = None
        self.start_scan()



    def set_bt_speed(self, value):
        speed_map = {'1 (Lent)': 1, '2': 2, '3': 3, '4': 4, '5 (Rapide)': 5}
        speed_val = speed_map.get(value, 5)
        self.bt_speed_var.set(str(speed_val))
        SHARED_CONFIG['bluetooth_speed'] = speed_val
        self.config_data['bluetooth_speed'] = speed_val
        save_config_file(self.config_data)
        print_server.log_message('INFO', f'Vitesse de transmission Bluetooth réglée sur {speed_val}')



    def update_speed_card_state(self):
        if not hasattr(self, 'speed_card') or not hasattr(self, 'printers_card'):
            return None
        else:
            mode = self.conn_type_var.get()
            if mode == 'bluetooth_direct':
                self.speed_card.grid(row=1, column=0, sticky='ew', pady=(0, 10))
                self.printers_card.grid(row=2, column=0, sticky='nsew', pady=(0, 0))
            else:
                self.speed_card.grid_forget()
                self.printers_card.grid(row=1, column=0, sticky='nsew', pady=(0, 0))


    def scan_all(self):
        self.last_scan_results = None
        self.start_scan()


    def start_scan(self):
        if self.is_scanning:
            return
        self.is_scanning = True
        self.render_printer_cards()


        def run_scan():
            try:
                mode = self.conn_type_var.get()
                if mode == 'bluetooth_direct':
                    devices = print_server.scan_bluetooth()
                    self.after(0, lambda: self.finish_scan(devices))
                else:
                    sys_printers = print_server.scan_printers()
                    usb_ports = print_server.scan_usb_direct()
                    self.after(0, lambda: self.finish_scan((sys_printers, usb_ports)))
            except Exception as e:
                self.after(0, lambda: self.finish_scan_error(e))
        threading.Thread(target=run_scan, daemon=True).start()


    def finish_scan(self, results):
        self.is_scanning = False
        self.last_scan_results = results
        self.render_printer_cards()


    def finish_scan_error(self, err):
        self.is_scanning = False
        self.last_scan_results = None
        self.render_printer_cards(error_msg=str(err))



    def render_printer_cards(self, error_msg=None):
        for widget in self.printers_scroll.winfo_children():
            widget.destroy()
        if self.is_scanning:
            self.printers_count_lbl.configure(text='ANALYSE...')
            scan_lbl = ctk.CTkLabel(self.printers_scroll, text='Analyse des périphériques en cours... 🔄', font=ctk.CTkFont(family='PT Sans', size=13, weight='bold'), text_color=COLOR_PRIMARY)
            scan_lbl.grid(row=0, column=0, padx=20, pady=40, sticky='ew')
        else:
            if error_msg:
                self.printers_count_lbl.configure(text='ERREUR')
                err_lbl = ctk.CTkLabel(self.printers_scroll, text=f'Erreur d\'analyse: {error_msg}', font=ctk.CTkFont(family='PT Sans', size=12), text_color=COLOR_ERROR)
                err_lbl.grid(row=0, column=0, padx=20, pady=20, sticky='ew')
            else:
                if self.last_scan_results is None:
                    self.start_scan()
                    return
                else:
                    mode = self.conn_type_var.get()
                    if mode == 'bluetooth_direct':
                        devices = self.last_scan_results
                        plural = '' if len(devices) == 1 else 'S'
                        self.printers_count_lbl.configure(text=f'{len(devices)} DÉTECTÉE{plural}')
                        if not devices:
                            no_device_lbl = ctk.CTkLabel(self.printers_scroll, text='Aucun périphérique Bluetooth appairé trouvé', font=ctk.CTkFont(family='PT Sans', size=12), text_color=COLOR_TEXT_MUTED)
                            no_device_lbl.grid(row=0, column=0, padx=20, pady=20)
                        else:
                            current_mac = SHARED_CONFIG.get('mac_address', '')
                            for i, dev in enumerate(devices):
                                is_selected = dev['mac'].lower() == current_mac.lower()
                                self.create_printer_card(i, dev['friendly'], 'Appairé', 'bluetooth', is_selected, dev)
                    else:
                        sys_printers, usb_ports = self.last_scan_results
                        total_devs = len(sys_printers) + len(usb_ports)
                        plural = '' if total_devs == 1 else 'S'
                        self.printers_count_lbl.configure(text=f'{total_devs} DÉTECTÉE{plural}')
                        if total_devs == 0:
                            no_device_lbl = ctk.CTkLabel(self.printers_scroll, text='Aucune imprimante détectée', font=ctk.CTkFont(family='PT Sans', size=12), text_color=COLOR_TEXT_MUTED)
                            no_device_lbl.grid(row=0, column=0, padx=20, pady=20)
                        else:
                            row_idx = 0
                            current_printer = SHARED_CONFIG.get('system_printer_name', '')
                            current_usb = SHARED_CONFIG.get('usb_port', '')
                            current_conn = SHARED_CONFIG.get('connection_type', '')
                            for prn in sys_printers:
                                is_selected = prn == current_printer and current_conn == 'system_printer'
                                dev_data = {'mode': 'system_printer', 'id': prn, 'name': prn}
                                self.create_printer_card(row_idx, prn, 'Prêt', 'print', is_selected, dev_data)
                                row_idx += 1
                            for port in usb_ports:
                                is_selected = port == current_usb and current_conn == 'usb_direct'
                                dev_data = {'mode': 'usb_direct', 'id': port, 'name': port}
                                self.create_printer_card(row_idx, f'Direct USB ({port})', 'Direct USB', 'usb', is_selected, dev_data)
                                row_idx += 1



    def create_printer_card(self, index, title, status, icon_name, is_selected, dev_data):
        card_border_color = COLOR_PRIMARY if is_selected else COLOR_CARD_BORDER
        card_bg = COLOR_SELECTED_BG if is_selected else COLOR_CARD_BG
        card_border_width = 2 if is_selected else 1
        card = ctk.CTkFrame(self.printers_scroll, fg_color=card_bg, border_color=card_border_color, border_width=card_border_width, corner_radius=8, height=60)
        card.grid(row=index, column=0, sticky='ew', pady=4, padx=2)
        card.grid_propagate(False)
        card.grid_columnconfigure(0, weight=0)
        card.grid_columnconfigure(1, weight=1)
        card.grid_columnconfigure(2, weight=0)
        card.grid_rowconfigure(0, weight=1)
        icon_symbol = '⚙️'
        if icon_name == 'bluetooth':
            icon_symbol = '🔵'
        else:
            if icon_name == 'print':
                icon_symbol = '🖨️'
            else:
                if icon_name == 'usb':
                    icon_symbol = '🔌'
        icon_lbl = ctk.CTkLabel(card, text=icon_symbol, font=ctk.CTkFont(size=20))
        icon_lbl.grid(row=0, column=0, padx=(15, 10), pady=10)
        info_frame = ctk.CTkFrame(card, fg_color='transparent')
        info_frame.grid(row=0, column=1, sticky='w', pady=10)
        info_frame.grid_columnconfigure(0, weight=1)
        info_frame.grid_rowconfigure(0, weight=1)
        info_frame.grid_rowconfigure(1, weight=1)
        title_lbl = ctk.CTkLabel(info_frame, text=title, font=ctk.CTkFont(family='PT Sans', size=12, weight='bold'), text_color=COLOR_TEXT_PRIMARY)
        title_lbl.grid(row=0, column=0, sticky='w')
        status_lbl = ctk.CTkLabel(info_frame, text=status, font=ctk.CTkFont(family='PT Sans', size=10), text_color=COLOR_TEXT_MUTED)
        status_lbl.grid(row=1, column=0, sticky='w')
        if is_selected:
            check_lbl = ctk.CTkLabel(card, text='✔️', font=ctk.CTkFont(size=14), text_color=COLOR_PRIMARY)
            check_lbl.grid(row=0, column=2, padx=15)


        def on_click(event=None):
            self.on_select_printer_card(dev_data)
        card.bind('<Button-1>', on_click)
        for child in card.winfo_children():
            child.bind('<Button-1>', on_click)
            for subchild in child.winfo_children():
                subchild.bind('<Button-1>', on_click)




    def on_select_printer_card(self, dev):
        mode = self.conn_type_var.get()
        if mode == 'bluetooth_direct':
            self.mac_address_var.set(dev['friendly'])
            SHARED_CONFIG['mac_address'] = dev['mac']
            SHARED_CONFIG['connection_type'] = 'bluetooth_direct'
        else:
            if dev['mode'] == 'system_printer':
                self.printer_var.set(dev['id'])
                SHARED_CONFIG['system_printer_name'] = dev['id']
                SHARED_CONFIG['connection_type'] = 'system_printer'
            else:
                if dev['mode'] == 'usb_direct':
                    self.usb_port_var.set(dev['id'])
                    SHARED_CONFIG['usb_port'] = dev['id']
                    SHARED_CONFIG['connection_type'] = 'usb_direct'
        self.save_config(show_msg=False)
        self.render_printer_cards()


        
    def load_config_from_shared(self):
        self.config_data = load_config()
        self.saved_printer = self.config_data.get('system_printer_name', '')
        self.saved_mac = self.config_data.get('mac_address', '')
        self.saved_usb_port = self.config_data.get('usb_port', '')
        self.saved_conn_type = self.config_data.get('connection_type', 'system_printer')
        self.saved_bt_speed = int(self.config_data.get('bluetooth_speed', 5))
        self.conn_type_var.set(self.saved_conn_type)
        self.bt_speed_var.set(str(self.saved_bt_speed))
        if self.saved_printer:
            self.printer_var.set(self.saved_printer)
        if self.saved_mac:
            self.mac_address_var.set(self.saved_mac)
        if self.saved_usb_port:
            self.usb_port_var.set(self.saved_usb_port)
        if hasattr(self, 'speed_selector'):
            speed_labels = {1: '1 (Lent)', 2: '2', 3: '3', 4: '4', 5: '5 (Rapide)'}
            self.speed_selector.set(speed_labels.get(self.saved_bt_speed, '5 (Rapide)'))
        if self.saved_conn_type == 'bluetooth_direct':
            self.btn_mode_bt.configure(fg_color=COLOR_PRIMARY, text_color=COLOR_ON_PRIMARY, hover_color=COLOR_SECONDARY)
            self.btn_mode_usb.configure(fg_color='transparent', text_color=COLOR_TEXT_MUTED, hover_color=COLOR_HOVER_NEUTRAL)
        else:
            self.btn_mode_usb.configure(fg_color=COLOR_PRIMARY, text_color=COLOR_ON_PRIMARY, hover_color=COLOR_SECONDARY)
            self.btn_mode_bt.configure(fg_color='transparent', text_color=COLOR_TEXT_MUTED, hover_color=COLOR_HOVER_NEUTRAL)
        self.render_printer_cards()
        self.update_speed_card_state()



    def save_config(self, show_msg=True):
        conn_type = self.conn_type_var.get()
        SHARED_CONFIG['connection_type'] = conn_type
        self.config_data['connection_type'] = conn_type
        if hasattr(self, 'bt_speed_var'):
            try:
                bt_speed = int(self.bt_speed_var.get())
                SHARED_CONFIG['bluetooth_speed'] = bt_speed
                self.config_data['bluetooth_speed'] = bt_speed
            except Exception:
                pass
        success = False
        if conn_type == 'system_printer':
            val = self.printer_var.get()
            if val and val != 'Aucune imprimante disponible':
                    SHARED_CONFIG['system_printer_name'] = val
                    self.config_data['system_printer_name'] = val
                    self.saved_printer = val
                    save_config_file(self.config_data)
                    success = True
                    if show_msg:
                        messagebox.showinfo('Succès', f'L\'imprimante système \'{val}\' est liée et sauvegardée.')
        else:
            if conn_type == 'bluetooth_direct':
                val = self.mac_address_var.get()
                if val and val not in ['Aucun peripherique appaire trouve', 'Aucun peripherique trouve']:
                        mac = val.split(' - ')[(-1)].strip() if ' - ' in val else val.strip()
                        SHARED_CONFIG['mac_address'] = mac
                        self.config_data['mac_address'] = val
                        self.saved_mac = val
                        save_config_file(self.config_data)
                        success = True
                        if show_msg:
                            messagebox.showinfo('Succès', f'L\'adresse MAC {mac} est liée et sauvegardée.')
            else:
                if conn_type == 'usb_direct':
                    val = self.usb_port_var.get()
                    if val and 'Aucun' not in val:
                            SHARED_CONFIG['usb_port'] = val
                            self.config_data['usb_port'] = val
                            self.saved_usb_port = val
                            save_config_file(self.config_data)
                            success = True
                            if show_msg:
                                messagebox.showinfo('Succès', f'Le port USB direct \'{val}\' est sauvegardé.')



    def test_print(self):
        conn_type = self.conn_type_var.get()
        text = self.test_entry.get('1.0', 'end-1c').strip()
        if not text:
            messagebox.showwarning('Attention', 'Veuillez saisir du texte à imprimer.')
            return
        else:
            init_cmd = b'\x1b@'
            text_cmd = text.encode('utf-8')
            feed_cmd = b'\n\n\n\x1dV\x00'
            payload = init_cmd + text_cmd + feed_cmd
            try:
                from print_server import send_payload_to_printer
                SHARED_CONFIG['connection_type'] = conn_type
                if conn_type == 'system_printer':
                    val = self.printer_var.get()
                    if not val or val == 'Aucune imprimante disponible':
                        messagebox.showwarning('Attention', 'Aucune imprimante sélectionnée.')
                        return
                    else:
                        SHARED_CONFIG['system_printer_name'] = val
                else:
                    if conn_type == 'bluetooth_direct':
                        val = self.mac_address_var.get()
                        if not val or val in ['Aucun peripherique trouve', 'Aucun peripherique appaire trouve']:
                            messagebox.showwarning('Attention', 'Aucune imprimante MAC spécifiée.')
                            return
                        else:
                            mac = val.split(' - ')[(-1)].strip() if ' - ' in val else val.strip()
                            SHARED_CONFIG['mac_address'] = mac
                    else:
                        val = self.usb_port_var.get()
                        if not val or 'Aucun' in val:
                            messagebox.showwarning('Attention', 'Aucun port USB spécifié.')
                            return
                        else:
                            SHARED_CONFIG['usb_port'] = val
                send_payload_to_printer(payload)
                messagebox.showinfo('Succès', 'Impression envoyée avec succès !')
            except Exception as e:
                messagebox.showerror('Erreur d\'impression', f'Échec de l\'impression : {e}')




    def toggle_server(self):
        if self.server_thread is None or not self.server_thread.is_alive():
            self.server_thread = threading.Thread(target=run_server, daemon=True)
            self.server_thread.start()




    def check_single_instance(self):
        self.ipc_port = 20727
        self.ipc_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.ipc_socket.bind(('127.0.0.1', self.ipc_port))
            self.ipc_socket.listen(1)
            def listen_for_others():
                while True:
                    try:
                        conn, addr = self.ipc_socket.accept()
                        data = conn.recv(1024)
                        if b'SHOW' in data:
                            self.after(0, self.restore_window)
                        conn.close()
                    except Exception:
                        continue
            threading.Thread(target=listen_for_others, daemon=True).start()
        except OSError:
            try:
                client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                client.connect(('127.0.0.1', self.ipc_port))
                client.sendall(b'SHOW')
                client.close()
            except Exception:
                pass
            else:
                pass
            print('Une instance est déjà en cours d\'exécution. Fermeture.')
            sys.exit(0)




    def restore_window(self):
        self.deiconify()
        self.attributes('-topmost', 1)
        self.attributes('-topmost', 0)
        self.focus_force()
        if hasattr(self, 'icon_obj') and self.icon_obj is not None:
                try:
                    self.icon_obj.stop()
                except Exception:
                    pass
                self.icon_obj = None



    def show_in_tray(self):
        self.withdraw()
        if hasattr(self, 'icon_obj') and self.icon_obj is None:
            try:
                if os.path.exists(TRAY_PATH):
                    image = Image.open(TRAY_PATH)
                else:
                    image = Image.new('RGB', (64, 64), color=(73, 109, 137))
                menu = pystray.Menu(pystray.MenuItem('Ouvrir', self.restore_from_tray, default=True), pystray.MenuItem('Quitter', self.quit_app_from_tray))
                self.icon_obj = pystray.Icon('PrintStack', image, 'Print Stack', menu)
                threading.Thread(target=self.icon_obj.run, daemon=True).start()
            except Exception as e:
                print(f'Erreur lors de la création de l\'icône: {e}')
                self.quit()

    def on_closing(self):
        self.show_in_tray()


    def restore_from_tray(self, icon, item):
        self.after(0, self.restore_window)


    def quit_app_from_tray(self, icon, item):
        if hasattr(self, 'icon_obj') and self.icon_obj is not None:
                self.icon_obj.stop()
        self.after(0, self.quit)
        self.after(100, lambda: os._exit(0))


    def restart_app(self):
        if hasattr(self, 'icon_obj') and self.icon_obj is not None:
                try:
                    self.icon_obj.stop()
                except Exception:
                    pass
        self.destroy()
        python = sys.executable
        os.execl(python, python, *sys.argv)

        
if __name__ == '__main__':
    app = CockpitApp()
    app.mainloop()