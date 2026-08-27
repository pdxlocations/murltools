# Meshtastic URL Tools (murltools)

A tool for encoding, decoding, and managing Meshtastic channel URLs. Create custom channel configurations, generate QR codes, decode existing URLs, and seamlessly transfer settings between configurations.

**There are two ways to run it, from one codebase:**

| | | |
|---|---|---|
| **Flask app** | `./run.sh` | Python does the protobuf work; the page calls back to it |
| **Single page** | open `murltools.html` | No Python, no server, no network — everything runs in the browser |

`murltools.html` is *compiled from* the Flask frontend, so `templates/index.html` is the
single source for markup, CSS and UI logic in both. See [Single-file build](#single-file-build).

## Features

### 🔧 **Channel Configuration Creator**
- **Visual Form Interface**: Create multi-channel configurations with intuitive web forms
- **Add or Replace Mode**: Generate `add` URLs (`?add=true`) or `replace` URLs
- **LoRa Settings Control**: `replace` requires LoRa config; `add` never carries it
- **LoRa Settings**: Configure bandwidth, spread factor, coding rate, and regional settings
- **Position Precision**: Off, approximate (10-19 bits), or precise (32 bits)
- **PSK Management**: Hex or base64 keys, a Default Key tick box, or empty for unencrypted
- **Preset & Manual Modes**: Choose from standard LoRa presets or configure manually

### 📱 **QR Code Generation**
- **Instant QR Codes**: Generate scannable QR codes for easy device configuration
- **Mobile-Friendly**: Perfect for configuring devices in the field
- **High-Quality Output**: PNG format with error correction
- **QR Centre**: optionally reserve the middle of the code for an uploaded image or a
  blank square. Off by default

### 🔍 **URL Decoding & Analysis**
- **Universal Decoder**: Decode channel (`/e/`) and shared-contact (`/v/`) URLs
- **Multi-Format Support**: Handle various Meshtastic URL formats and QR codes
- **Detailed Analysis**: View channel settings, LoRa parameters, and security information
- **Load Settings**: Import decoded configurations back into the creator for editing

### 🖼️ **QR Code Upload & Scanning**
- **Drag & Drop Interface**: Upload QR code images for instant decoding
- **Format Support**: PNG, JPEG, and other common image formats
- **Automatic Detection**: Intelligent QR code recognition and URL extraction

### 💻 **Command Line Interface**
- **Batch Processing**: Decode multiple URLs with automation support
- **JSON Output**: Machine-readable output for integration
- **Summary Views**: Human-readable summaries for quick analysis

## Single-file build

`murltools.html` is the whole tool as one self-contained page — no Python, no server, no
network. Open it from disk or drop it on any static host. It does everything the Flask app
does except read QR images that need OpenCV preprocessing.

Rebuild it after changing `templates/index.html` or anything under `tools/all_in_one/`:

```bash
python tools/build_all_in_one.py
```

Building needs the `meshtastic` package installed; *running* the result needs nothing at
all. Forgetting to rebuild is the one way the two can disagree, so CI does the same build
on every pull request and fails if `murltools.html` is out of date.

The page keeps the template's markup and CSS unchanged; a `fetch` shim answers the same
routes Flask serves, so the page's own JavaScript is untouched. Enum names come from the
installed `meshtastic` package at build time rather than being hand-maintained, so they
track the dependency — rerun the build after upgrading it.

Bundled third-party code, both GPLv3-compatible:

- [QR Code Generator for JavaScript](http://www.d-project.com/) © 2009 Kazuhiko Arase, MIT
- [jsQR](https://github.com/cozmo/jsQR) © 2016 Cosmo Wolfe, Apache 2.0

## Installation

1. **Clone or download the project files**
2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## Usage

### Web Interface

1. **Start the Flask application:**
   ```bash
   python app.py
   ```

2. **Open your browser and navigate to:** `http://localhost:5001`

3. **Choose your workflow:**

#### Create New Configuration
- Go to the **"Create URL"** tab
- Choose **Channel Action**:
  - **Replace Channels**: Standard `/e/#...` URL, requires LoRa settings
  - **Add Channels**: `/e/?add=true#...` URL for appending channels
- Configure channels with names, PSKs, and position precision
- Set LoRa parameters (bandwidth, spread factor, coding rate, region) when included
- Choose between preset and manual modes
- Generate Meshtastic URL and QR code
- Copy URL or download QR code for device configuration

#### Decode Existing URL/QR Code
- Go to the **"Decode URL"** tab
- **For URLs**: Paste Meshtastic URL and click "Decode"
- **For QR Codes**: Drag & drop QR code image or click to upload
- View decoded channel settings and LoRa configuration
- Use **"🔧 Load into Create URL"** to import settings for editing

#### Edit Existing Configuration
- Decode any Meshtastic URL or QR code
- Click **"🔧 Load into Create URL"** button
- Automatically switches to Create URL tab with pre-populated form
- Modify any settings as needed
- Generate new URL/QR code with your changes

### Command Line Interface

The `decode.py` script provides command-line access to the decoder:

**Basic usage:**
```bash
python decode.py "https://meshtastic.org/e/#Cg0SAQEaBFRlc3Q6AgggEgQIATgB"
```

**Pretty-printed JSON output:**
```bash
python decode.py --pretty "https://meshtastic.org/e/#Cg0SAQEaBFRlc3Q6AgggEgQIATgB"
```

**Human-readable summary:**
```bash
python decode.py --summary "https://meshtastic.org/e/#Cg0SAQEaBFRlc3Q6AgggEgQIATgB"
```

**View help:**
```bash
python decode.py --help
```

## Supported Formats

### Input Formats
- **Meshtastic URLs**: `https://meshtastic.org/e/#[encoded_data]`
- **Add Mode URLs**: `https://meshtastic.org/e/?add=true#[encoded_data]`
- **Query Parameter URLs**: `https://meshtastic.org/e/?c=[encoded_data]`
- **QR Code Images**: PNG, JPEG, and other common formats
- **Base64url Encoded Data**: Direct protobuf data input

### Protobuf Message Types
- **ChannelSet** (`/e/` URLs): channel configurations with LoRa settings. A single channel is
  encoded as a one-entry ChannelSet, which is what clients expect
- **SharedContact** (`/v/` URLs): a shared contact — node number, user, and the ignore /
  key-verified import flags
- **NodeInfo**, **User**, **Position**, **MyNodeInfo**: attempted as decode fallbacks only; no
  Meshtastic client emits these as URLs

## Configuration Options

### Channel Settings
- **Channel Names**: Up to 11 bytes per channel, enforced by the API as well as the form
- **Pre-Shared Keys (PSK)**: Hex (0x...) or Base64 format. Leave empty for an unencrypted
  channel, or tick **Default Key** for the standard `AQ==` key every stock node ships with
- **Channel Roles**: Primary, Secondary, or Disabled
- **Position Precision**: 0 (off), 10-19 (approximate), or 32 (precise) — the only values the official clients produce, and the only ones the API accepts
- **Module Settings**: Position precision and per-channel mute

### LoRa Configuration
- **Modem Presets**: read from the bundled protobuf, so the list tracks the `meshtastic`
  package rather than a hardcoded subset. An unknown preset is an error, not a silent LongFast
- **Manual Settings**: Custom bandwidth, spread factor, coding rate
- **Regional Settings**: likewise read from the protobuf; an unknown region is an error, not a
  silent US
- **Power Management**: TX power, TX enable/disable, RX boost
- **Advanced Options**: Frequency offset, hop limit, duty cycle override

## Example Output

### Web Interface
The web interface provides a visual representation with:
- Channel summaries with key information
- Expandable JSON data
- Copy-to-clipboard functionality
- Error handling with debug information

### Command Line Summary
```
✅ Successfully decoded Meshtastic URL
URL: https://meshtastic.org/e/#Cg0SAQEaBFRlc3Q6AgggEgQIATgB

📡 Configuration Data:
  lora_config:
    use_preset: True
    region: US
  channels: [1 items]
    [0]:
      psk: AQ==
      name: Test
```

## API Endpoints

When running as a Flask app, the following endpoints are available:

- `GET /` - Web interface
- `POST /decode` - JSON API for decoding URLs
- `POST /encode` - JSON API for encoding channel configurations
- `POST /encode_nodeinfo` - JSON API for encoding a shared contact (`/v/` URL)
- `GET /lora_enums` - Modem preset and region names from the bundled protobuf
- `GET /nodeinfo_enums` - Hardware model and role names from the bundled protobuf
- `POST /upload` - Image upload for QR code decoding

### API Usage Examples

#### Decode URL
```bash
curl -X POST http://localhost:5001/decode \
  -H "Content-Type: application/json" \
  -d '{"url": "https://meshtastic.org/e/#Cg0SAQEaBFRlc3Q6AgggEgQIATgB"}'
```

#### Encode Configuration
```bash
curl -X POST http://localhost:5001/encode \
  -H "Content-Type: application/json" \
  -d '{
    "channel_action": "replace",
    "channels": [
      {
        "name": "My Channel",
        "psk": "AQIDBAUGBwgJCgsMDQ4PEA==",
        "role": "primary"
      }
    ],
    "lora_config": {
      "use_preset": true,
      "modem_preset": "LONG_FAST",
      "region": "US"
    }
  }'
```

#### QR Centre

Both encode endpoints accept an optional `qr_embed` object:

```json
{ "mode": "blank", "ratio": 0.22 }
{ "mode": "image", "ratio": 0.22, "image": "data:image/png;base64,..." }
```

- `mode`: `none` (default), `blank` for a reserved white square, or `image`
- `ratio`: 0.10–0.30 of the code width; the default is 0.22
- `image`: a data URL or bare base64, up to 2 MB

A separate top-level `qr_scale` of `1` (default), `2` or `4` multiplies the output resolution.
That helps printing and downloading, but it does **not** make the code easier to scan on
screen: scanning depends on how large the code is *displayed*, not on how many pixels each
module has. Measured on a 77-module code, decoding needs roughly 3 px per module — about
250 px across for that code, regardless of whether the PNG is 850 px or 3400 px wide.

Reserving the centre forces error correction **H**, which the `qrcode` library requires and
which makes the code noticeably denser — roughly 45% more modules per side. The response
reports `error_correction` and `modules` so this is visible. Scan-test any code you intend to
print, especially at small sizes.

`channel_action` values:
- `replace` (default): requires `lora_config`
- `add`: never carries `lora_config`; any supplied is dropped, matching the official clients

When `channel_action` is `add`, generated URLs use:
- `https://meshtastic.org/e/?add=true#...`

Decoding reports `channel_action` too, from either the query string or the older
`#<data>?add=true` form, so an add URL round-trips as an add URL.

## Error Handling

The application handles various error conditions:

- Invalid URLs or missing encoded data
- Corrupted or invalid protobuf data
- Base64 decoding errors
- Network connectivity issues (web interface)
- Missing `lora_config` when `channel_action` is `replace`

When decoding fails, the application provides:
- Clear error messages
- Debug information including hex dumps
- Raw data length and encoding information

## Development

### Project Structure
```
murltools/
├── app.py                       # Flask application with encoder/decoder logic
├── decode.py                    # Command-line interface
├── decode.sh                    # CLI wrapper
├── run.sh                       # Starts the Flask app on :5001
├── requirements.txt             # Python dependencies
├── templates/
│   └── index.html               # The web interface — source of truth for both builds
├── murltools.html               # Generated single-file build. Do not edit by hand
├── tools/
│   ├── build_all_in_one.py      # Compiles templates/index.html -> murltools.html
│   └── all_in_one/
│       ├── protobuf.js          # Minimal protobuf reader/writer
│       ├── meshtastic.js        # Enum tables and URL encode/decode
│       ├── backend.js           # fetch shim answering the Flask routes in-browser
│       └── vendor/              # jsQR (Apache 2.0), qrcode.js (MIT)
└── README.md                    # This file
```

`murltools.html` is a build artifact but is committed on purpose — being downloadable
and openable on its own is the point of it. CI rebuilds it on every pull request and
fails if the committed copy is stale, so the two builds cannot drift apart unnoticed.

### Dependencies
- **Flask**: Web framework for the UI
- **meshtastic**: Official Meshtastic Python library for protobuf definitions
- **protobuf**: Google Protocol Buffers for message serialization
- **qrcode**: QR code generation library
- **Pillow (PIL)**: Image processing for QR code generation and upload
- **pyzbar**: QR code reading from uploaded images
- **opencv-python**: Computer vision for QR code detection
- **numpy**: Numerical operations for image processing

## Key Features Highlights

### 🔧 Load Settings Workflow
One of the most powerful features is the **Load Settings** functionality:
1. **Decode** any existing Meshtastic URL or QR code
2. **Click** the "🔧 Load into Create URL" button
3. **Automatically** switch to Create URL tab with form pre-populated
4. **Edit** any settings (PSK, bandwidth, region, etc.)
5. **Generate** new URL and QR code with your modifications

This makes it easy to:
- Clone and modify existing configurations
- Fix incorrect settings in URLs
- Convert between different channel setups
- Create variations of working configurations

### JSON Field Names
- Multi-channel config JSON uses `Config.channels`
- Legacy `Config.settings` is still accepted when loading older data

### 🎯 Position Privacy Control

`position_precision` is not a free 1-32 range. The official clients only ever emit:

- **0** — position sharing off
- **10-19** — approximate, roughly 19 km down to 37 m; 13 is the default
- **32** — precise, full resolution

Anything else is rejected.

**On a public-key channel the firmware caps this at 15 bits.** A PSK of one byte or less —
the default key, any single-byte alias, or no key at all — is publicly decryptable, and
`getPositionPrecisionForChannel()` clamps precision to `MAX_POSITION_PRECISION_PUBLIC_KEY`
(15, roughly a 700 m cell) before transmitting. So on a default-key channel the effective
range is **0 or 10-15**: setting 16-19 or 32 is carried in the URL but sent as 15.

Related firmware behaviour worth knowing when reading a decoded URL:

- Position sharing is opt-in — a stock channel ships with `position_precision = 0`
- A channel with no `module_settings` at all is treated as 0, not as precise
- Disabled channels and event channels always report 0
- MQTT map reporting accepts only 12-15

## Security Considerations

**This tool handles sensitive information:**
- **Pre-shared keys (PSK)**: Used for mesh encryption
- **Channel configurations**: Could provide network access
- **Location precision**: Privacy implications

**Important Guidelines:**
- Only use with channels you own or have permission to access
- Be careful sharing generated URLs/QR codes - they contain network credentials
- Consider using lower position precision for privacy
- Generated QR codes should be treated like passwords

## Troubleshooting

### Common Issues
- **Bandwidth not loading**: Ensure you're using manual LoRa mode, not presets
- **QR code not scanning**: Check image quality and format (PNG/JPEG)
- **PSK format errors**: Use hex format (0x1234abcd) or base64 (AQIDBAUGBw==)
- **Load Settings not working**: Check browser console for JavaScript errors

### Debug Tips
- Enable browser developer tools to see network requests
- Check the Flask console for encoding/decoding errors  
- Use the command-line decoder for batch processing
- Verify protobuf data with `--pretty` flag in CLI

## License

This project is provided as-is for educational and development purposes. Please respect Meshtastic network operators and only access channels you have permission to use.

## Contributing

Contributions welcome! Areas for improvement:
- Additional protobuf message types
- Enhanced QR code recognition
- Mobile-responsive improvements
- Additional export formats
- Batch processing features

Meshtastic® is a registered trademark of Meshtastic LLC. Meshtastic software components are released under various licenses, see GitHub for details. No warranty is provided - use at your own risk.