@echo off
echo Construction de l'executable PrintStack pour Windows...

echo 1. Installation des dependances...
python -m pip install -r requirements.txt
python -m pip install pyinstaller

echo 2. Compilation de l'application...
rem L'option --onedir cree un dossier avec tous les fichiers (plus rapide au lancement).
rem L'option --windowed evite d'afficher la console noire de commande.
rem L'option --add-data copie le dossier assets dans la distribution finale.
python -m PyInstaller --noconfirm --onedir --windowed --add-data "assets;assets" --add-data "pos_demo.html;." --collect-all escpos --icon "assets\images\icon.ico" --name "PrintStack" main_gui.py

if %ERRORLEVEL% NEQ 0 (
    echo Erreur lors de la compilation. Regardez les messages d'erreur ci-dessus.
    pause
    exit /b %ERRORLEVEL%
)
echo.
echo Termine. L'executable se trouve dans le dossier 'dist\PrintStack'.
echo Vous pouvez maintenant utiliser Inno Setup avec 'setup.iss' pour creer l'installateur final.
pause
