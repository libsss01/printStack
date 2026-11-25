# PrintStack

Local print server for **ESC/POS** thermal printers (receipt printers), with a graphical configuration interface.

PrintStack runs on the user's machine and exposes a small HTTP API on `localhost`. A web application or point-of-sale software can then print without any special driver:

- **text**;
- **images** (logo, generated receipt, etc.);
- **raw ESC/POS commands**, for full control over layout, cash drawer opening, paper cutting…

> The user interface and the API error messages are currently in French.

## Features

- Three printer connection modes: **direct Bluetooth**, **direct USB**, or **system printer** (Windows).
- Graphical interface to select the printer, view logs and restart the server.
- The application minimizes to the system tray instead of closing.
- Built-in demo page (`/demo`).
- Safeguards: allowed origins list, limit of 10 prints per minute, request size limited to 10 MB.

## Requirements

- **Python 3.14** (tested version)
- Windows or Linux
- On Linux, Tkinter must be installed separately:
  ```bash
  sudo apt install python3-tk
  ```

## Installation

```bash
git clone https://github.com/libsss01/printStack.git
cd printStack

python -m venv .venv
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
```

## Running

```bash
python main_gui.py
```

The interface starts and launches the server on `http://localhost:20726`. Open `http://localhost:20726/demo` for a first test print.

To run the server alone, without the interface:

```bash
python print_server.py
```

> Closing the window does not quit the application: it stays in the system tray. To really stop it, right-click the icon and choose **Quitter** (Quit).

## Configuration

The configuration is stored in a `config.json` file located here:

| System | Location |
|---|---|
| Windows | `%APPDATA%\PrintStack\config.json` |
| Linux / macOS | `~/.printstack/config.json` |

**Only this file is read.** On the very first launch, if a `config.json` exists next to the executable or in the current directory, it is copied to this location. After that, it is never read again.

Printer settings are made from the graphical interface. The port and the allowed origins are edited **by hand** in the file (use `config.example.json` as a template), then the application must be restarted.

| Key | Purpose | Default value |
|---|---|---|
| `server_port` | Port the server listens on | `20726` |
| `allowed_origins` | Web origins allowed to call the API (see [Security](#security)) | `["http://localhost:20726"]` |
| `connection_type` | `bluetooth_direct`, `usb_direct` or `system_printer` | `bluetooth_direct` |
| `mac_address` | MAC address of the Bluetooth printer | — |
| `usb_port` | USB device path (`/dev/usb/lp0`, `COM3`…) | — |
| `system_printer_name` | System printer name (Windows) | — |
| `bluetooth_speed` | Bluetooth sending speed | `5` |

Example:

```json
{
  "server_port": 20726,
  "allowed_origins": ["http://localhost:20726", "http://127.0.0.1:20726"],
  "connection_type": "usb_direct",
  "usb_port": "/dev/usb/lp0"
}
```

An invalid origin (anything that is not a string starting with `http://` or `https://`) is replaced by the default value, and a warning is written to the log.

## Security

The server only listens on `127.0.0.1`: it cannot be reached from the network.

**Origin check.** When a request carries an `Origin` header that is not in the `allowed_origins` list, it is rejected with a **403**. A malicious website opened in the user's browser therefore cannot trigger a print.

Requests **without** an `Origin` header (curl, POS software, local scripts) are accepted. This check protects against websites, not against programs already running on the machine.

If your web application is served from another address (for example `http://localhost:3000`), add it to `allowed_origins`.

## API

### `POST /print/esc-pos`

Sends raw ESC/POS commands directly to the printer, through the server. The server does not modify anything: the client is responsible for initialization, formatting, paper cutting, cash drawer opening, etc.

**Request body** (JSON)

| Field | Type | Required | Description |
|---|---|---|---|
| `data` | string | Yes | ESC/POS bytes encoded in **base64**. JSON cannot carry raw bytes, hence the encoding. |

**Example**

```bash
curl -X POST http://localhost:20726/print/esc-pos \
  -H "Content-Type: application/json" \
  -d '{"data": "G0BIZWxsbyBQcmludFN0YWNrCgoKCh1WAA=="}'
```

This base64 string decodes to the following bytes:

| Bytes | Command |
|---|---|
| `1B 40` | `ESC @`: initializes the printer |
| `Hello PrintStack` | the text to print |
| `0A 0A 0A 0A` | four line feeds to advance the paper |
| `1D 56 00` | `GS V 0`: cuts the paper |

To build your own string, in Python:

```python
import base64
base64.b64encode(b"\x1b@Hello PrintStack\n\n\n\n\x1dV\x00").decode()
```

Response: `{"success": true}`

**Errors**

| Code | Cause |
|---|---|
| 400 | Missing body or body that is not a JSON object, missing or empty `data` field, `data` that is not a string, invalid base64 |
| 403 | Origin not allowed |
| 413 | Request larger than 10 MB |
| 429 | More than 10 prints in one minute |
| 500 | Internal print error (printer unreachable, etc.) |

### `POST /print/text`

Prints plain text. The server initializes the printer, prints the text, feeds the paper, then cuts it.

**Request body** (JSON)

| Field | Type | Required | Description |
|---|---|---|---|
| `content` | string | Yes | Text to print. Line breaks (`\n`) are preserved. |

**Example**

```bash
curl -X POST http://localhost:20726/print/text \
  -H "Content-Type: application/json" \
  -d '{"content": "Thank you for your visit!\nTotal: 1500"}'
```

Response: `{"success": true}`

> The text is sent encoded as UTF-8. Depending on your printer's code page, accented characters may print incorrectly. For full control, use `/print/esc-pos`.

**Errors**

| Code | Cause |
|---|---|
| 400 | Missing body or body that is not a JSON object, missing or empty `content` field, `content` that is not a string |
| 403 | Origin not allowed |
| 413 | Request larger than 10 MB |
| 429 | More than 10 prints in one minute |
| 500 | Internal print error (printer unreachable, etc.) |

### `POST /print/image`

Prints a PNG or JPEG image. An image wider than 384 pixels is resized to 384 pixels (print width of a 58 mm receipt), then the paper is cut.

**Request body** (JSON)

| Field | Type | Required | Description |
|---|---|---|---|
| `content` | string | Yes | Image encoded in **base64**. A data URL (`data:image/png;base64,...`) is also accepted, so the result of a browser-side `FileReader.readAsDataURL()` can be sent as is. |

**Example**

```bash
curl -X POST http://localhost:20726/print/image \
  -H "Content-Type: application/json" \
  -d "{\"content\": \"$(base64 -w0 logo.png)\"}"
```

`base64 -w0 logo.png` encodes the `logo.png` file in base64 on a single line.

Response: `{"success": true}`

**Errors**

| Code | Cause |
|---|---|
| 400 | Missing body or body that is not a JSON object, missing or empty `content` field or one that is not a string, invalid base64, data that is not an image |
| 403 | Origin not allowed |
| 413 | Request larger than 10 MB |
| 429 | More than 10 prints in one minute |
| 500 | Internal print error (printer unreachable, etc.) |

## Building the executable

**Windows:**

```bat
build_exe.bat
```

The result is in `dist\PrintStack\`. To produce an installer, open `setup.iss` with [Inno Setup](https://jrsoftware.org/isinfo.php).

**Linux:**

```bash
./build_linux.sh
```

To change the application icon, replace `assets/images/printstack_logo.png` and run `python create_ico.py` before rebuilding.

## Project structure

| File | Purpose |
|---|---|
| `print_server.py` | Flask server: API, printer connections, security, logs |
| `main_gui.py` | Graphical interface (customtkinter) and system tray icon |
| `pos_demo.html` | Demo page served on `/demo` |
| `config.example.json` | Configuration template |
| `create_ico.py` | Generates `icon.ico` from the PNG logo |
| `build_exe.bat`, `build_linux.sh` | PyInstaller build scripts (the build configuration lives here) |
| `setup.iss` | Inno Setup installer configuration |
| `assets/images/` | Logos and icon |

## License

Distributed under the MIT License. See [LICENSE](LICENSE).
