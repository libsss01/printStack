# PrintStack

Serveur d'impression local pour imprimantes thermiques **ESC/POS** (tickets de caisse), avec une interface graphique de configuration.

PrintStack tourne sur le poste de l'utilisateur et expose une petite API HTTP sur `localhost`. Une application web ou un logiciel de caisse peut ainsi imprimer sans pilote particulier :

- du **texte** ;
- des **images** (logo, reçu généré, etc.) ;
- des **commandes ESC/POS brutes**, pour garder un contrôle total sur la mise en page, l'ouverture du tiroir-caisse, la découpe…

## Fonctionnalités

- Trois modes de connexion à l'imprimante : **Bluetooth direct**, **USB direct**, ou **imprimante système** (Windows).
- Interface graphique pour choisir l'imprimante, voir les journaux et redémarrer le serveur.
- Application réduite dans la zone de notification plutôt que fermée.
- Page de démonstration intégrée (`/demo`).
- Protections : liste d'origines autorisées, limite de 10 impressions par minute, taille de requête limitée à 10 Mo.

## Prérequis

- **Python 3.14** (version testée)
- Windows ou Linux
- Sous Linux, Tkinter doit être installé à part :
  ```bash
  sudo apt install python3-tk
  ```

## Installation

```bash
git clone <url-du-depot>
cd printStack

python -m venv .venv
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
```

## Lancement

```bash
python main_gui.py
```

L'interface démarre et lance le serveur sur `http://localhost:20726`. Ouvrez `http://localhost:20726/demo` pour faire un premier test d'impression.

Pour lancer le serveur seul, sans interface :

```bash
python print_server.py
```

> Fermer la fenêtre ne quitte pas l'application : elle reste dans la zone de notification. Pour l'arrêter vraiment, faites un clic droit sur l'icône puis **Quitter**.

## Configuration

La configuration est stockée dans un fichier `config.json` situé ici :

| Système | Emplacement |
|---|---|
| Windows | `%APPDATA%\PrintStack\config.json` |
| Linux / macOS | `~/.printstack/config.json` |

**Seul ce fichier est lu.** Au tout premier lancement, si un `config.json` se trouve à côté de l'exécutable ou dans le dossier courant, il est copié vers cet emplacement. Ensuite, il n'est plus jamais relu.

Les réglages d'imprimante se font depuis l'interface graphique. Le port et les origines autorisées se modifient **à la main** dans le fichier (servez-vous de `config.example.json` comme modèle), puis il faut redémarrer l'application.

| Clé | Rôle | Valeur par défaut |
|---|---|---|
| `server_port` | Port d'écoute du serveur | `20726` |
| `allowed_origins` | Origines web autorisées à appeler l'API (voir [Sécurité](#sécurité)) | `["http://localhost:20726"]` |
| `connection_type` | `bluetooth_direct`, `usb_direct` ou `system_printer` | `bluetooth_direct` |
| `mac_address` | Adresse MAC de l'imprimante Bluetooth | — |
| `usb_port` | Chemin du périphérique USB (`/dev/usb/lp0`, `COM3`…) | — |
| `system_printer_name` | Nom de l'imprimante système (Windows) | — |
| `bluetooth_speed` | Vitesse d'envoi Bluetooth | `5` |

Exemple :

```json
{
  "server_port": 20726,
  "allowed_origins": ["http://localhost:20726", "http://127.0.0.1:20726"],
  "connection_type": "usb_direct",
  "usb_port": "/dev/usb/lp0"
}
```

Une origine invalide (qui n'est pas une chaîne commençant par `http://` ou `https://`) est remplacée par la valeur par défaut, et un avertissement est écrit dans le journal.

## Sécurité

Le serveur écoute uniquement sur `127.0.0.1` : il n'est pas joignable depuis le réseau.

**Contrôle des origines.** Quand une requête porte un en-tête `Origin` absent de la liste  `allowed_origins`, elle est refusée avec un **403**. Un site malveillant ouvert dans le navigateur de l'utilisateur ne peut donc pas déclencher d'impression.

Les requêtes **sans** en-tête `Origin` (curl, logiciel de caisse, script local) sont acceptées. Ce contrôle protège contre les sites web, pas contre les programmes qui tournent déjà sur la machine.

Si votre application web est servie depuis une autre adresse (par exemple `http://localhost:3000`), ajoutez-la à `allowed_origins`.

## API

### `POST /print/esc-pos`

Envoie des commandes ESC/POS brutes directement à l'imprimante, par l'intermédiaire du serveur. Le serveur ne modifie rien : c'est au client d'inclure l'initialisation, la mise en forme, la coupe du papier, l'ouverture du tiroir-caisse, etc.

**Corps de la requête** (JSON)

| Champ | Type | Obligatoire | Description |
|---|---|---|---|
| `data` | string | Oui | Octets ESC/POS encodés en **base64**. Le JSON ne peut pas transporter d'octets bruts, d'où l'encodage. |

**Exemple**

```bash
curl -X POST http://localhost:20726/print/esc-pos \
  -H "Content-Type: application/json" \
  -d '{"data": "G0BCb25qb3VyIFByaW50U3RhY2sKCgoKHVYA"}'
```

Cette chaîne base64 correspond aux octets suivants :

| Octets | Commande |
|---|---|
| `1B 40` | `ESC @` : initialise l'imprimante |
| `Bonjour PrintStack` | le texte à imprimer |
| `0A 0A 0A 0A` | quatre sauts de ligne pour faire avancer le papier |
| `1D 56 00` | `GS V 0` : coupe le papier |

Pour produire votre propre chaîne, en Python :

```python
import base64
base64.b64encode(b"\x1b@Bonjour PrintStack\n\n\n\n\x1dV\x00").decode()
```

Réponse : `{"success": true}`

**Erreurs**

| Code | Cause |
|---|---|
| 400 | Corps absent ou qui n'est pas un objet JSON, champ `data` manquant ou vide, `data` qui n'est pas une chaîne, base64 invalide |
| 403 | Origine non autorisée |
| 413 | Requête de plus de 10 Mo |
| 429 | Plus de 10 impressions en une minute |
| 500 | Erreur d'impression interne (imprimante injoignable, etc.) |

### `POST /print/text`

Imprime du texte brut. Le serveur initialise l'imprimante, imprime le texte, fait avancer le papier puis le coupe.

**Corps de la requête** (JSON)

| Champ | Type | Obligatoire | Description |
|---|---|---|---|
| `content` | string | Oui | Texte à imprimer. Les retours à la ligne (`\n`) sont respectés. |

**Exemple**

```bash
curl -X POST http://localhost:20726/print/text \
  -H "Content-Type: application/json" \
  -d '{"content": "Merci de votre visite !\nTotal : 1500 FCFA"}'
```

Réponse : `{"success": true}`

> Le texte est envoyé encodé en UTF-8. Selon la page de code de votre imprimante, les caractères accentués peuvent s'afficher incorrectement. Pour un contrôle total, utilisez `/print/esc-pos`.

**Erreurs**

| Code | Cause |
|---|---|
| 400 | Corps absent ou qui n'est pas un objet JSON, champ `content` manquant ou vide, `content` qui n'est pas une chaîne |
| 403 | Origine non autorisée |
| 413 | Requête de plus de 10 Mo |
| 429 | Plus de 10 impressions en une minute |
| 500 | Erreur d'impression interne (imprimante injoignable, etc.) |

### `POST /print/image`

Imprime une image PNG ou JPEG. Une image de plus de 384 pixels de large est redimensionnée à 384 pixels (largeur d'impression d'un ticket de 58 mm), puis le papier est coupé.

**Corps de la requête** (JSON)

| Champ | Type | Obligatoire | Description |
|---|---|---|---|
| `content` | string | Oui | Image encodée en **base64**. Une data URL (`data:image/png;base64,...`) est aussi acceptée, ce qui permet d'envoyer directement le résultat d'un `FileReader.readAsDataURL()` côté navigateur. |

**Exemple**

```bash
curl -X POST http://localhost:20726/print/image \
  -H "Content-Type: application/json" \
  -d "{\"content\": \"$(base64 -w0 logo.png)\"}"
```

`base64 -w0 logo.png` encode le fichier `logo.png` en base64 sur une seule ligne.

Réponse : `{"success": true}`

**Erreurs**

| Code | Cause |
|---|---|
| 400 | Corps absent ou qui n'est pas un objet JSON, champ `content` manquant, vide ou qui n'est pas une chaîne, base64 invalide, données qui ne sont pas une image |
| 403 | Origine non autorisée |
| 413 | Requête de plus de 10 Mo |
| 429 | Plus de 10 impressions en une minute |
| 500 | Erreur d'impression interne (imprimante injoignable, etc.) |

## Construire l'exécutable

**Windows :**

```bat
build_exe.bat
```

Le résultat se trouve dans `dist\PrintStack\`. Pour produire un installateur, ouvrez `setup.iss` avec [Inno Setup](https://jrsoftware.org/isinfo.php).

**Linux :**

```bash
./build_linux.sh
```

Pour changer l'icône de l'application, remplacez `assets/images/printstack_logo.png` puis lancez `python create_ico.py` avant de reconstruire.

## Structure du projet

| Fichier | Rôle |
|---|---|
| `print_server.py` | Serveur Flask : API, connexion aux imprimantes, sécurité, journaux |
| `main_gui.py` | Interface graphique (customtkinter) et icône de la zone de notification |
| `pos_demo.html` | Page de démonstration servie sur `/demo` |
| `config.example.json` | Modèle de configuration |
| `create_ico.py` | Génère `icon.ico` à partir du logo PNG |
| `build_exe.bat`, `build_linux.sh` | Scripts de construction PyInstaller |
| `PrintStack.spec`, `setup.iss` | Configurations PyInstaller et Inno Setup |
| `assets/images/` | Logos et icône |

## Licence

Distribué sous licence MIT. Voir [LICENSE](LICENSE).
