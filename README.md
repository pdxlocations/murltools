# Meshtastic URL Tools (murltools)

A comprehensive Python Flask application for encoding, decoding, and managing Meshtastic channel URLs. Create custom channel configurations, generate QR codes, decode existing URLs, and seamlessly transfer settings between configurations.

## Features

### 🔧 **Channel Configuration Creator**
- **Visual Form Interface**: Create multi-channel configurations with intuitive web forms
- **LoRa Settings**: Configure bandwidth, spread factor, coding rate, and regional settings
- **Position Precision**: Set location sharing precision (1-32 bits) for privacy control
- **PSK Management**: Support for both hex and base64 pre-shared keys
- **Preset & Manual Modes**: Choose from standard LoRa presets or configure manually

### 📱 **QR Code Generation**
- **Instant QR Codes**: Generate scannable QR codes for easy device configuration
- **Mobile-Friendly**: Perfect for configuring devices in the field
- **High-Quality Output**: PNG format with error correction

### 🔍 **URL Decoding & Analysis**
- **Universal Decoder**: Decode both ChannelSet and single Channel protobuf messages
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

2. **Open your browser and navigate to:** `http://localhost:5002`

3. **Choose your workflow:**

#### Create New Configuration
- Go to the **"Create URL"** tab
- Configure channels with names, PSKs, and position precision
- Set LoRa parameters (bandwidth, spread factor, coding rate, region)
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

## Supported Formats

### Input Formats
- **Meshtastic URLs**: `https://meshtastic.org/e/#[encoded_data]`
- **Query Parameter URLs**: `https://meshtastic.org/e/?c=[encoded_data]`
- **QR Code Images**: PNG, JPEG, and other common formats
- **Base64url Encoded Data**: Direct protobuf data input

### Protobuf Message Types
- **ChannelSet**: Multi-channel configurations with LoRa settings
- **Single Channel**: Individual channel configurations
- **NodeInfo**: Node information and status
- **User**: User profile data
- **Position**: Location and GPS data
- **MyNodeInfo**: Local node configuration

## Configuration Options

### Channel Settings
- **Channel Names**: Up to 11 characters per channel
- **Pre-Shared Keys (PSK)**: Hex (0x...) or Base64 format
- **Channel Roles**: Primary, Secondary, or Disabled
- **Position Precision**: 1-32 bits (privacy control)
- **Module Settings**: Position precision and other module configs

### LoRa Configuration
- **Modem Presets**: LONG_FAST, LONG_SLOW, VERY_LONG_SLOW, etc.
- **Manual Settings**: Custom bandwidth, spread factor, coding rate
- **Regional Settings**: US, EU_433, EU_868, CN, JP, ANZ, etc.
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
- `POST /encode` - JSON API for encoding configurations
- `POST /upload` - Image upload for QR code decoding

### API Usage Examples

#### Decode URL
```bash
curl -X POST http://localhost:5002/decode \
  -H "Content-Type: application/json" \
  -d '{"url": "https://meshtastic.org/e/#CgMSAQoLCgdEZWZhdWx0EAE"}'
```

#### Encode Configuration
```bash
curl -X POST http://localhost:5002/encode \
  -H "Content-Type: application/json" \
  -d '{
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
murltools/
├── app.py                 # Flask application with encoder/decoder logic
├── decode.py             # Command-line interface
├── requirements.txt      # Python dependencies
├── templates/
│   └── index.html       # Complete web interface with tabs
└── README.md            # This file
```

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

### 🎯 Position Privacy Control
- **32-bit precision**: ~0.5 cm accuracy (maximum)
- **24-bit precision**: ~1.2 m accuracy (high)
- **16-bit precision**: ~305 m accuracy (medium)
- **8-bit precision**: ~78 km accuracy (low privacy impact)
- **Lower bits**: Increasingly private but less precise

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
