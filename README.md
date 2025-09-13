# Meshtastic Channel URL Decoder

A Python Flask application that decodes Meshtastic channel URLs and displays their protobuf contents in both a web interface and command-line tool.

## Features

- 🌐 **Web Interface**: User-friendly web UI for decoding Meshtastic channel URLs
- 💻 **Command Line Tool**: Standalone script for batch processing and automation
- 🔍 **Protobuf Decoding**: Decodes both ChannelSet and single Channel protobuf messages
- 📋 **Multiple Output Formats**: JSON, pretty-printed JSON, and human-readable summaries
- 🔐 **Security Information**: Displays PSK, modem configurations, and channel settings

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

2. **Open your browser and navigate to:** `http://localhost:5000`

3. **Enter a Meshtastic channel URL** in the format:
   ```
   https://meshtastic.org/e/#CgMSAQoLCgdEZWZhdWx0EAE
   ```

4. **Click "Decode Channel"** to see the decoded protobuf data

### Command Line Interface

The `decode.py` script provides command-line access to the decoder:

**Basic usage:**
```bash
python decode.py "https://meshtastic.org/e/#CgMSAQoLCgdEZWZhdWx0EAE"
```

**Pretty-printed JSON output:**
```bash
python decode.py --pretty "https://meshtastic.org/e/#CgMSAQoLCgdEZWZhdWx0EAE"
```

**Human-readable summary:**
```bash
python decode.py --summary "https://meshtastic.org/e/#CgMSAQoLCgdEZWZhdWx0EAE"
```

**View help:**
```bash
python decode.py --help
```

## Supported URL Formats

The decoder supports various Meshtastic URL formats:

- `https://meshtastic.org/e/#[encoded_data]`
- `https://meshtastic.org/e/?c=[encoded_data]`
- URLs with base64url encoded protobuf data
- Both ChannelSet and single Channel messages

## Output Information

The decoder extracts and displays:

- **Channel Information**: Name, role (PRIMARY/SECONDARY/DISABLED)
- **Security**: Pre-shared key (PSK) in hexadecimal
- **Radio Settings**: Modem config, TX power, bandwidth, spread factor, coding rate
- **Frequency**: Frequency offset settings
- **Raw Data**: Hex dump of decoded protobuf for debugging

## Example Output

### Web Interface
The web interface provides a visual representation with:
- Channel summaries with key information
- Expandable JSON data
- Copy-to-clipboard functionality
- Error handling with debug information

### Command Line Summary
```
✅ Successfully decoded Meshtastic channel URL
Type: SingleChannel
URL: https://meshtastic.org/e/#CgMSAQoLCgdEZWZhdWx0EAE

📡 Channel 0 (PRIMARY)
  Name: Default
  PSK: 01234567890abcdef...
  Modem Config: BW125CR45SF128
```

## API Endpoints

When running as a Flask app, the following endpoints are available:

- `GET /` - Web interface
- `POST /decode` - JSON API for decoding URLs
- `GET /health` - Health check endpoint

### API Usage Example

```bash
curl -X POST http://localhost:5000/decode \
  -H "Content-Type: application/json" \
  -d '{"url": "https://meshtastic.org/e/#CgMSAQoLCgdEZWZhdWx0EAE"}'
```

## Error Handling

The application handles various error conditions:

- Invalid URLs or missing encoded data
- Corrupted or invalid protobuf data
- Base64 decoding errors
- Network connectivity issues (web interface)

When decoding fails, the application provides:
- Clear error messages
- Debug information including hex dumps
- Raw data length and encoding information

## Development

### Project Structure
```
proto-decode/
├── app.py                 # Flask application and decoder logic
├── decode.py             # Command-line interface
├── requirements.txt      # Python dependencies
├── templates/
│   └── index.html       # Web interface template
└── README.md            # This file
```

### Dependencies
- **Flask**: Web framework for the UI
- **meshtastic**: Official Meshtastic Python library
- **protobuf**: Google Protocol Buffers
- **cryptography**: For handling encryption-related functionality
- **protobuf-to-dict**: Convert protobuf messages to dictionaries

## Security Considerations

This tool displays sensitive information including:
- Pre-shared keys (PSK) used for mesh encryption
- Channel configurations that could be used to access networks

**Important**: Only use this tool with channels you own or have permission to decode. Be careful when sharing decoded output as it may contain sensitive network credentials.

## License

This project is provided as-is for educational and development purposes. Please respect Meshtastic network operators and only decode channels you have permission to access.

## Contributing

Feel free to submit issues, feature requests, or pull requests to improve the decoder functionality.
