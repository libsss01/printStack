#!/bin/bash
echo "Construction de l'executable PrintStack pour Linux..."

echo "1. Installation des dependances..."
pip install -r requirements.txt
pip install pyinstaller

echo "2. Compilation de l'application..."
# L'option --onedir cree un dossier avec tous les fichiers (plus rapide au lancement).
# L'option --windowed evite d'afficher la console noire de commande.
# L'option --add-data copie le dossier assets dans la distribution finale (utiliser ':' sur Linux au lieu de ';').
pyinstaller --noconfirm --onedir --windowed --add-data "assets:assets" --add-data "pos_demo.html:." --collect-all escpos --name "PrintStack" main_gui.py

echo
echo "Termine. L'executable se trouve dans le dossier 'dist/PrintStack'."
