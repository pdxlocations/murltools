#!/usr/bin/env python3
"""
Meshtastic Channel URL Decoder - Command Line Interface
Standalone script to decode Meshtastic channel URLs from the command line.
"""

import sys
import json
import argparse
from app import MeshtasticDecoder

def main():
    parser = argparse.ArgumentParser(
        description='Decode Meshtastic channel URLs and display protobuf contents',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python decode.py https://meshtastic.org/e/#CgMSAQoLCgdEZWZhdWx0EAE
  python decode.py --pretty https://meshtastic.org/e/#CgMSAQoLCgdEZWZhdWx0EAE
  python decode.py --summary https://meshtastic.org/e/#CgMSAQoLCgdEZWZhdWx0EAE
        """
    )
    
    parser.add_argument(
        'url',
        help='Meshtastic channel URL to decode'
    )
    
    parser.add_argument(
        '--pretty',
        action='store_true',
        help='Pretty print JSON output'
    )
    
    parser.add_argument(
        '--summary',
        action='store_true',
        help='Show only a summary of channel information'
    )
    
    
    args = parser.parse_args()
    
    # Initialize decoder
    decoder = MeshtasticDecoder()
    
    # Decode the URL
    try:
        result = decoder.decode_channel_url(args.url)
        
        if args.summary:
            display_summary(result)
        else:
            # Default to JSON output
            if args.pretty:
                print(json.dumps(result, indent=2))
            else:
                print(json.dumps(result))
                
    except KeyboardInterrupt:
        print("\nOperation cancelled by user", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

def display_summary(result):
    """Display a human-readable summary of the decoded data"""
    
    if not result.get('success'):
        print(f"❌ Decoding failed: {result.get('error', 'Unknown error')}")
        if result.get('raw_data'):
            print("\nDebug info:")
            print(f"  URL: {result['raw_data'].get('url', 'N/A')}")
            print(f"  Encoded length: {result['raw_data'].get('encoded_length', 'N/A')}")
            print(f"  Decoded length: {result['raw_data'].get('decoded_length', 'N/A')}")
            print(f"  Hex data: {result['raw_data'].get('hex_data', 'N/A')}")
        return
    
    print("✅ Successfully decoded Meshtastic URL")
    print(f"URL: {result.get('url', 'N/A')}")
    print()
    
    # Display configuration data
    if 'Config' in result:
        print("📡 Configuration Data:")
        config = result['Config']
        if isinstance(config, dict):
            _print_dict_summary(config, indent="  ")
        else:
            print(f"  {config}")
    elif 'Node' in result:
        print("📱 Node Information:")
        node = result['Node']
        if isinstance(node, dict):
            _print_dict_summary(node, indent="  ")
        else:
            print(f"  {node}")
    elif 'User' in result:
        print("👤 User Information:")
        user = result['User']
        if isinstance(user, dict):
            _print_dict_summary(user, indent="  ")
        else:
            print(f"  {user}")
    elif 'Position' in result:
        print("📍 Position Information:")
        position = result['Position']
        if isinstance(position, dict):
            _print_dict_summary(position, indent="  ")
        else:
            print(f"  {position}")
    elif 'MyNodeInfo' in result:
        print("📡 My Node Information:")
        my_node = result['MyNodeInfo']
        if isinstance(my_node, dict):
            _print_dict_summary(my_node, indent="  ")
        else:
            print(f"  {my_node}")
    else:
        print("No decoded data found")

def _print_dict_summary(data, indent="", max_depth=3, current_depth=0):
    """Helper function to print dictionary data in a readable format"""
    if current_depth >= max_depth:
        print(f"{indent}[...truncated...]")
        return
        
    for key, value in data.items():
        if isinstance(value, dict):
            print(f"{indent}{key}:")
            _print_dict_summary(value, indent + "  ", max_depth, current_depth + 1)
        elif isinstance(value, list):
            print(f"{indent}{key}: [{len(value)} items]")
            for i, item in enumerate(value[:3]):  # Show first 3 items
                if isinstance(item, dict):
                    print(f"{indent}  [{i}]:")
                    _print_dict_summary(item, indent + "    ", max_depth, current_depth + 2)
                else:
                    print(f"{indent}  [{i}]: {item}")
            if len(value) > 3:
                print(f"{indent}  ...and {len(value) - 3} more")
        else:
            # Truncate very long strings
            if isinstance(value, str) and len(value) > 50:
                value = value[:47] + "..."
            print(f"{indent}{key}: {value}")

if __name__ == '__main__':
    main()
