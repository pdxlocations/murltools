#!/usr/bin/env python3
"""
Meshtastic Channel URL Decoder
A Flask web application that decodes Meshtastic channel URLs and their encoded protobufs.
"""

import base64
import json
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any

from flask import Flask, render_template, request, jsonify
from meshtastic import channel_pb2, apponly_pb2, mesh_pb2
from google.protobuf.message import DecodeError
from google.protobuf.json_format import MessageToDict

app = Flask(__name__)

class MeshtasticDecoder:
    """Handles decoding of Meshtastic channel URLs and protobuf data"""
    
    def decode_channel_url(self, url: str) -> Dict[str, Any]:
        """
        Decode a Meshtastic channel URL and return channel information
        
        Args:
            url: Meshtastic channel URL (e.g., https://meshtastic.org/e/#...)
            
        Returns:
            Dictionary containing decoded channel information
        """
        try:
            # Parse the URL
            parsed_url = urlparse(url)
            
            # Extract the fragment (part after #)
            if parsed_url.fragment:
                encoded_data = parsed_url.fragment
            else:
                # Check if it's in query parameters
                query_params = parse_qs(parsed_url.query)
                if 'c' in query_params:
                    encoded_data = query_params['c'][0]
                else:
                    raise ValueError("No encoded channel data found in URL")
            
            # Decode the base64url encoded data
            decoded_data = self._base64url_decode(encoded_data)
            
            # Try multiple decoding approaches
            decode_attempts = []
            
            # Detect URL type to prioritize attempts
            is_node_url = '/v/' in url  # Node URLs typically use /v/ path
            is_channel_url = '/e/' in url  # Channel URLs typically use /e/ path
            
            if is_node_url:
                # For node URLs, try node-related types first
                result = self._try_node_decoders(decoded_data, url, decode_attempts)
                if result:
                    return result
                    
                # Then try channel types as fallback
                result = self._try_channel_decoders(decoded_data, url, decode_attempts)
                if result:
                    return result
            else:
                # For channel URLs or unknown, try channel types first
                result = self._try_channel_decoders(decoded_data, url, decode_attempts)
                if result:
                    return result
                    
                # Then try node types as fallback
                result = self._try_node_decoders(decoded_data, url, decode_attempts)
                if result:
                    return result
                    
            # Try MeshPacket as a last resort
            try:
                packet = mesh_pb2.MeshPacket()
                packet.ParseFromString(decoded_data)
                return {
                    'success': True,
                    'url': url,
                    'MeshPacket': MessageToDict(packet, preserving_proto_field_name=True)
                }
            except Exception as e:
                decode_attempts.append(f'MeshPacket failed: {str(e)}')
            
            # If still nothing works, return detailed diagnostic info
            return {
                'success': False,
                'error': 'Unable to decode protobuf data',
                'decode_attempts': decode_attempts,
                'raw_data': {
                    'url': url,
                    'encoded_data': encoded_data,
                    'encoded_length': len(encoded_data),
                    'decoded_length': len(decoded_data),
                    'hex_data': decoded_data.hex(),
                    'raw_bytes': list(decoded_data)  # Show raw bytes for debugging
                }
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'url': url
            }
    
    def _base64url_decode(self, data: str) -> bytes:
        """Decode base64url encoded string"""
        # Add padding if necessary
        missing_padding = len(data) % 4
        if missing_padding:
            data += '=' * (4 - missing_padding)
        
        # Replace URL-safe characters
        data = data.replace('-', '+').replace('_', '/')
        
        try:
            return base64.b64decode(data)
        except Exception as e:
            # Try alternative decoding if standard fails
            try:
                return base64.urlsafe_b64decode(data)
            except Exception:
                raise ValueError(f"Failed to decode base64 data: {e}")
    
    def _try_node_decoders(self, decoded_data: bytes, url: str, decode_attempts: list) -> Dict[str, Any]:
        """Try node-related protobuf message types"""
        
        # Try NodeInfo
        try:
            node = mesh_pb2.NodeInfo()
            node.ParseFromString(decoded_data)
            node_dict = MessageToDict(node, preserving_proto_field_name=True)
            # Validate that this looks like real node data
            if self._validate_node_data(node_dict):
                return {
                    'success': True,
                    'url': url,
                    'Node': node_dict
                }
        except Exception as e:
            decode_attempts.append(f'NodeInfo failed: {str(e)}')
        
        # Try User message (often in node URLs)
        try:
            user = mesh_pb2.User()
            user.ParseFromString(decoded_data)
            user_dict = MessageToDict(user, preserving_proto_field_name=True)
            # Validate that this looks like real user data
            if self._validate_user_data(user_dict):
                return {
                    'success': True,
                    'url': url,
                    'User': user_dict
                }
        except Exception as e:
            decode_attempts.append(f'User failed: {str(e)}')
        
        # Try Position message
        try:
            position = mesh_pb2.Position()
            position.ParseFromString(decoded_data)
            position_dict = MessageToDict(position, preserving_proto_field_name=True)
            if self._validate_position_data(position_dict):
                return {
                    'success': True,
                    'url': url,
                    'Position': position_dict
                }
        except Exception as e:
            decode_attempts.append(f'Position failed: {str(e)}')
        
        # Try MyNodeInfo
        try:
            my_node = mesh_pb2.MyNodeInfo()
            my_node.ParseFromString(decoded_data)
            my_node_dict = MessageToDict(my_node, preserving_proto_field_name=True)
            if my_node_dict:  # Basic validation
                return {
                    'success': True,
                    'url': url,
                    'MyNodeInfo': my_node_dict
                }
        except Exception as e:
            decode_attempts.append(f'MyNodeInfo failed: {str(e)}')
        
        return None
    
    def _try_channel_decoders(self, decoded_data: bytes, url: str, decode_attempts: list) -> Dict[str, Any]:
        """Try channel-related protobuf message types"""
        
        # Try to decode as ChannelSet first
        try:
            channel_set = apponly_pb2.ChannelSet()
            channel_set.ParseFromString(decoded_data)
            config_dict = MessageToDict(channel_set, preserving_proto_field_name=True)
            # Validate that this looks like real channel data
            if self._validate_channel_set_data(config_dict):
                return {
                    'success': True,
                    'url': url,
                    'Config': config_dict
                }
        except Exception as e:
            decode_attempts.append(f'ChannelSet failed: {str(e)}')
        
        # Try to decode as single Channel
        try:
            channel = channel_pb2.Channel()
            channel.ParseFromString(decoded_data)
            config_dict = MessageToDict(channel, preserving_proto_field_name=True)
            if self._validate_channel_data(config_dict):
                return {
                    'success': True,
                    'url': url,
                    'Config': config_dict
                }
        except Exception as e:
            decode_attempts.append(f'SingleChannel failed: {str(e)}')
        
        return None
    
    def _validate_node_data(self, data: Dict[str, Any]) -> bool:
        """Validate that decoded data looks like real NodeInfo"""
        # NodeInfo should have node number or user info
        return bool(data.get('num') or data.get('user'))
    
    def _validate_user_data(self, data: Dict[str, Any]) -> bool:
        """Validate that decoded data looks like real User data"""
        # User should have id, long_name, or short_name
        return bool(data.get('id') or data.get('long_name') or data.get('short_name'))
    
    def _validate_position_data(self, data: Dict[str, Any]) -> bool:
        """Validate that decoded data looks like real Position data"""
        # Position should have latitude, longitude, or other location fields
        return bool(data.get('latitude_i') or data.get('longitude_i') or data.get('altitude'))
    
    def _validate_channel_set_data(self, data: Dict[str, Any]) -> bool:
        """Validate that decoded data looks like real ChannelSet data"""
        # ChannelSet should have settings or channels
        return bool(data.get('settings') or data.get('channels') or data.get('lora_config'))
    
    def _validate_channel_data(self, data: Dict[str, Any]) -> bool:
        """Validate that decoded data looks like real Channel data"""
        # Channel should have settings, role, or index
        return bool(data.get('settings') or data.get('role') is not None or data.get('index') is not None)

# Initialize decoder
decoder = MeshtasticDecoder()

@app.route('/')
def index():
    """Main page with URL input form"""
    return render_template('index.html')

@app.route('/decode', methods=['POST'])
def decode_url():
    """API endpoint to decode Meshtastic channel URL"""
    data = request.get_json()
    
    if not data or 'url' not in data:
        return jsonify({'success': False, 'error': 'No URL provided'}), 400
    
    url = data['url'].strip()
    if not url:
        return jsonify({'success': False, 'error': 'Empty URL provided'}), 400
    
    result = decoder.decode_channel_url(url)
    return jsonify(result)

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'service': 'meshtastic-decoder'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
