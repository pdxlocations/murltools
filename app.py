#!/usr/bin/env python3
"""
Meshtastic Channel URL Decoder
A Flask web application that decodes Meshtastic channel URLs and their encoded protobufs.
"""

import base64
import json
import io
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any, List, Optional

from flask import Flask, render_template, request, jsonify
from meshtastic.protobuf import channel_pb2, apponly_pb2, mesh_pb2, config_pb2
from google.protobuf.message import DecodeError
from google.protobuf.json_format import MessageToDict
from PIL import Image
from pyzbar import pyzbar
import cv2
import numpy as np
import qrcode
from qrcode.constants import ERROR_CORRECT_L

from io import BytesIO

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
    
    def _try_node_decoders(self, decoded_data: bytes, url: str, decode_attempts: list) -> Optional[Dict[str, Any]]:
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
    
    def _try_channel_decoders(self, decoded_data: bytes, url: str, decode_attempts: list) -> Optional[Dict[str, Any]]:
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

class MeshtasticEncoder:
    """Handles encoding of Meshtastic channel configurations into URLs and QR codes"""
    
    def encode_channel_set(self, channels_data: List[Dict[str, Any]], lora_config_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Encode multiple channels into a ChannelSet and create Meshtastic URL
        
        Args:
            channels_data: List of channel configuration dictionaries
            lora_config_data: Optional LoRa configuration dictionary
            
        Returns:
            Dictionary containing URL, QR code data, and success status
        """
        try:
            # Create ChannelSet protobuf
            channel_set = apponly_pb2.ChannelSet()
            
            for i, channel_data in enumerate(channels_data):
                # Create Channel protobuf
                channel = channel_pb2.Channel()
                channel.index = i
                
                # Set channel role
                role_map = {
                    'primary': channel_pb2.Channel.Role.PRIMARY,
                    'secondary': channel_pb2.Channel.Role.SECONDARY,
                    'disabled': channel_pb2.Channel.Role.DISABLED
                }
                channel.role = role_map.get(channel_data.get('role', 'secondary'), channel_pb2.Channel.Role.SECONDARY)
                
                # Create channel settings
                settings = channel_pb2.ChannelSettings()
                
                if channel_data.get('name'):
                    settings.name = channel_data['name']
                
                if channel_data.get('psk'):
                    # Convert PSK from hex string or base64 to bytes
                    psk_str = channel_data['psk']
                    try:
                        if psk_str.startswith('0x'):
                            settings.psk = bytes.fromhex(psk_str[2:])
                        else:
                            # Try as base64
                            settings.psk = base64.b64decode(psk_str)
                    except:
                        # If all else fails, use as UTF-8 bytes (not recommended but fallback)
                        settings.psk = psk_str.encode('utf-8')[:32]  # Limit to 32 bytes
                
                # Set uplink/downlink enabled flags
                if 'uplink_enabled' in channel_data:
                    settings.uplink_enabled = bool(channel_data['uplink_enabled'])
                if 'downlink_enabled' in channel_data:
                    settings.downlink_enabled = bool(channel_data['downlink_enabled'])
                
                # Always create module settings to ensure position_precision and is_muted are explicit
                module_settings = channel_pb2.ModuleSettings()

                if 'module_settings' in channel_data and isinstance(channel_data['module_settings'], dict):
                    ms = channel_data['module_settings']

                    if 'position_precision' in ms and ms['position_precision'] is not None:
                        module_settings.position_precision = int(ms['position_precision'])
                    else:
                        # Default: position enabled with full precision
                        module_settings.position_precision = 32

                    # Per-channel mute flag (matches meshtastic/channel.proto: ModuleSettings.is_muted)
                    # Accept a few common input keys for backward compatibility.
                    for key in ('is_muted', 'muted', 'mute'):
                        if key in ms:
                            module_settings.is_muted = bool(ms[key])
                            break
                else:
                    # Default: position enabled with full precision
                    module_settings.position_precision = 32
                
                # Always set module settings
                settings.module_settings.CopyFrom(module_settings)
                
                channel.settings.CopyFrom(settings)
                channel_set.settings.append(channel.settings)
            
            # Add LoRa config if provided
            if lora_config_data:
                lora_config = config_pb2.Config.LoRaConfig()
                
                if 'use_preset' in lora_config_data:
                    lora_config.use_preset = bool(lora_config_data['use_preset'])
                if 'modem_preset' in lora_config_data:
                    # Map preset names to integer values (updated for new values)
                    preset_map = {
                        'LONG_FAST': 0,       # LONG_FAST
                        'LONG_SLOW': 1,       # LONG_SLOW  
                        'VERY_LONG_SLOW': 2,  # VERY_LONG_SLOW
                        'MEDIUM_SLOW': 3,     # MEDIUM_SLOW
                        'MEDIUM_FAST': 4,     # MEDIUM_FAST
                        'SHORT_SLOW': 5,      # SHORT_SLOW
                        'SHORT_FAST': 6,      # SHORT_FAST
                        'LONG_MODERATE': 7,   # LONG_MODERATE
                        'SHORT_TURBO': 8,     # SHORT_TURBO
                        # Legacy support
                        'long_fast': 0,
                        'long_slow': 1,
                        'very_long_slow': 2,
                        'medium_slow': 3,
                        'medium_fast': 4,
                        'short_slow': 5,
                        'short_fast': 6
                    }
                    lora_config.modem_preset = preset_map.get(lora_config_data['modem_preset'], 0)
                if 'bandwidth' in lora_config_data:
                    # Use bandwidth value as-is (no unit conversion)
                    lora_config.bandwidth = int(lora_config_data['bandwidth'])
                if 'spread_factor' in lora_config_data:
                    lora_config.spread_factor = int(lora_config_data['spread_factor'])
                if 'coding_rate' in lora_config_data:
                    lora_config.coding_rate = int(lora_config_data['coding_rate'])
                if 'frequency_offset' in lora_config_data:
                    lora_config.frequency_offset = float(lora_config_data['frequency_offset'])
                if 'hop_limit' in lora_config_data:
                    lora_config.hop_limit = int(lora_config_data['hop_limit'])
                if 'tx_enabled' in lora_config_data:
                    lora_config.tx_enabled = bool(lora_config_data['tx_enabled'])
                if 'tx_power' in lora_config_data:
                    lora_config.tx_power = int(lora_config_data['tx_power'])
                if 'channel_num' in lora_config_data:
                    lora_config.channel_num = int(lora_config_data['channel_num'])
                if 'override_duty_cycle' in lora_config_data:
                    lora_config.override_duty_cycle = bool(lora_config_data['override_duty_cycle'])
                if 'sx126x_rx_boosted_gain' in lora_config_data:
                    lora_config.sx126x_rx_boosted_gain = bool(lora_config_data['sx126x_rx_boosted_gain'])
                if 'override_frequency' in lora_config_data:
                    lora_config.override_frequency = float(lora_config_data['override_frequency'])
                if 'region' in lora_config_data:
                    # Map region string to enum value
                    region_map = {
                        'US': 1,
                        'EU_433': 2,
                        'EU_868': 3,
                        'CN': 4,
                        'JP': 5,
                        'ANZ': 6,
                        'KR': 7,
                        'TW': 8,
                        'RU': 9,
                        'IN': 10,
                        'NZ_865': 11,
                        'TH': 12,
                        'LORA_24': 13,
                        'UA_433': 14,
                        'UA_868': 15
                    }
                    lora_config.region = region_map.get(lora_config_data['region'], 1)  # Default to US
                    
                channel_set.lora_config.CopyFrom(lora_config)
            
            # Serialize the ChannelSet to bytes
            protobuf_data = channel_set.SerializeToString()
            
            # Encode as base64url
            encoded_data = self._base64url_encode(protobuf_data)
            
            # Create Meshtastic URL
            url = f"https://meshtastic.org/e/#{encoded_data}"
            
            # Generate QR code
            qr_code_data = self._generate_qr_code(url)
            
            # Also decode the generated URL to provide config data in same format as decoder
            decoder_instance = MeshtasticDecoder()
            decoded_result = decoder_instance.decode_channel_url(url)
            
            # Build the response with both encoding and decoding information
            response = {
                'success': True,
                'url': url,
                'qr_code': qr_code_data,
                'channels_count': len(channels_data),
                'encoded_size': len(protobuf_data)
            }
            
            # Add decoded configuration data if decoding was successful
            if decoded_result.get('success'):
                if 'Config' in decoded_result:
                    response['Config'] = decoded_result['Config']
                else:
                    # Handle other message types that might be returned
                    for key in decoded_result:
                        if key not in ['success', 'url']:
                            response[key] = decoded_result[key]
            
            return response
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Failed to encode channel set: {str(e)}'
            }
    
    def encode_single_channel(self, channel_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Encode a single channel into a Channel protobuf and create Meshtastic URL
        
        Args:
            channel_data: Channel configuration dictionary
            
        Returns:
            Dictionary containing URL, QR code data, and success status
        """
        try:
            # Create Channel protobuf
            channel = channel_pb2.Channel()
            channel.index = channel_data.get('index', 0)
            
            # Set channel role
            role_map = {
                'primary': channel_pb2.Channel.Role.PRIMARY,
                'secondary': channel_pb2.Channel.Role.SECONDARY,
                'disabled': channel_pb2.Channel.Role.DISABLED
            }
            channel.role = role_map.get(channel_data.get('role', 'secondary'), channel_pb2.Channel.Role.SECONDARY)
            
            # Create channel settings
            settings = channel_pb2.ChannelSettings()
            
            if channel_data.get('name'):
                settings.name = channel_data['name']
            
            if channel_data.get('psk'):
                # Convert PSK from hex string or base64 to bytes
                psk_str = channel_data['psk']
                try:
                    if psk_str.startswith('0x'):
                        settings.psk = bytes.fromhex(psk_str[2:])
                    else:
                        # Try as base64
                        settings.psk = base64.b64decode(psk_str)
                except:
                    # If all else fails, use as UTF-8 bytes (not recommended but fallback)
                    settings.psk = psk_str.encode('utf-8')[:32]  # Limit to 32 bytes
            
            # Set uplink/downlink enabled flags
            if 'uplink_enabled' in channel_data:
                settings.uplink_enabled = bool(channel_data['uplink_enabled'])
            if 'downlink_enabled' in channel_data:
                settings.downlink_enabled = bool(channel_data['downlink_enabled'])
            
            # Always create module settings to ensure position_precision and is_muted are explicit
            module_settings = channel_pb2.ModuleSettings()

            if 'module_settings' in channel_data and isinstance(channel_data['module_settings'], dict):
                ms = channel_data['module_settings']

                if 'position_precision' in ms and ms['position_precision'] is not None:
                    module_settings.position_precision = int(ms['position_precision'])
                else:
                    # Default: position enabled with full precision
                    module_settings.position_precision = 32

                # Per-channel mute flag (matches meshtastic/channel.proto: ModuleSettings.is_muted)
                for key in ('is_muted', 'muted', 'mute'):
                    if key in ms:
                        module_settings.is_muted = bool(ms[key])
                        break
            else:
                # Default: position enabled with full precision
                module_settings.position_precision = 32
            
            # Always set module settings
            settings.module_settings.CopyFrom(module_settings)
            
            channel.settings.CopyFrom(settings)
            
            # Serialize the Channel to bytes
            protobuf_data = channel.SerializeToString()
            
            # Encode as base64url
            encoded_data = self._base64url_encode(protobuf_data)
            
            # Create Meshtastic URL
            url = f"https://meshtastic.org/e/#{encoded_data}"
            
            # Generate QR code
            qr_code_data = self._generate_qr_code(url)
            
            # Also decode the generated URL to provide config data in same format as decoder
            decoder_instance = MeshtasticDecoder()
            decoded_result = decoder_instance.decode_channel_url(url)
            
            # Build the response with both encoding and decoding information
            response = {
                'success': True,
                'url': url,
                'qr_code': qr_code_data,
                'encoded_size': len(protobuf_data)
            }
            
            # Add decoded configuration data if decoding was successful
            if decoded_result.get('success'):
                if 'Config' in decoded_result:
                    response['Config'] = decoded_result['Config']
                else:
                    # Handle other message types that might be returned
                    for key in decoded_result:
                        if key not in ['success', 'url']:
                            response[key] = decoded_result[key]
            
            return response
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Failed to encode single channel: {str(e)}'
            }
    
    def _base64url_encode(self, data: bytes) -> str:
        """Encode bytes as base64url string"""
        # Use URL-safe base64 encoding and remove padding
        encoded = base64.urlsafe_b64encode(data).decode('ascii')
        return encoded.rstrip('=')
    
    def _generate_qr_code(self, url: str) -> Dict[str, Any]:
        """Generate QR code image for the given URL"""
        try:
            # Create QR code
            qr = qrcode.QRCode(
                version=1,  # Controls the size of the QR Code
                error_correction=ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(url)
            qr.make(fit=True)
            
            # Create image
            qr_img = qr.make_image(fill_color="black", back_color="white")
            
            # Convert to bytes
            img_buffer = BytesIO()
            qr_img.save(img_buffer, format='PNG')
            img_buffer.seek(0)
            
            # Encode as base64 for web display
            img_base64 = base64.b64encode(img_buffer.getvalue()).decode('ascii')
            
            return {
                'success': True,
                'image_base64': img_base64,
                'mime_type': 'image/png',
                'size': qr_img.size
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Failed to generate QR code: {str(e)}'
            }

class QRCodeProcessor:
    """Handles QR code image processing to extract URLs"""
    
    def process_qr_image(self, image_data: bytes) -> Dict[str, Any]:
        """
        Process an uploaded image to extract QR codes
        
        Args:
            image_data: Raw image bytes
            
        Returns:
            Dictionary containing extracted URLs and processing info
        """
        try:
            # Load image using PIL
            image = Image.open(io.BytesIO(image_data))
            
            # Convert to RGB if necessary
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Try to decode QR codes using pyzbar
            qr_codes = pyzbar.decode(image)
            
            if qr_codes:
                return self._process_detected_qr_codes(qr_codes)
            
            # If no QR codes found with pyzbar, try OpenCV preprocessing
            return self._try_opencv_preprocessing(image_data)
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Failed to process image: {str(e)}',
                'qr_codes': []
            }
    
    def _process_detected_qr_codes(self, qr_codes: List) -> Dict[str, Any]:
        """Process detected QR codes and extract URLs"""
        results = []
        meshtastic_urls = []
        
        for qr in qr_codes:
            qr_data = qr.data.decode('utf-8')
            
            result = {
                'type': qr.type,
                'data': qr_data,
                'rect': {
                    'x': qr.rect.left,
                    'y': qr.rect.top, 
                    'width': qr.rect.width,
                    'height': qr.rect.height
                }
            }
            
            # Check if this looks like a Meshtastic URL
            if self._is_meshtastic_url(qr_data):
                result['is_meshtastic'] = True
                meshtastic_urls.append(qr_data)
            else:
                result['is_meshtastic'] = False
            
            results.append(result)
        
        return {
            'success': True,
            'qr_codes': results,
            'meshtastic_urls': meshtastic_urls,
            'total_qr_codes': len(qr_codes),
            'meshtastic_count': len(meshtastic_urls)
        }
    
    def _try_opencv_preprocessing(self, image_data: bytes) -> Dict[str, Any]:
        """Try OpenCV preprocessing to enhance QR code detection"""
        try:
            # Convert to numpy array for OpenCV
            nparr = np.frombuffer(image_data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if img is None:
                raise ValueError("Could not decode image with OpenCV")
            
            # Try different preprocessing techniques
            preprocessed_images = self._preprocess_image(img)
            
            for processed_img in preprocessed_images:
                # Convert back to PIL Image
                pil_img = Image.fromarray(cv2.cvtColor(processed_img, cv2.COLOR_BGR2RGB))
                
                # Try to decode QR codes
                qr_codes = pyzbar.decode(pil_img)
                if qr_codes:
                    return self._process_detected_qr_codes(qr_codes)
            
            # No QR codes found even with preprocessing
            return {
                'success': False,
                'error': 'No QR codes detected in image',
                'qr_codes': [],
                'tried_preprocessing': True
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'OpenCV preprocessing failed: {str(e)}',
                'qr_codes': []
            }
    
    def _preprocess_image(self, img):
        """Apply various preprocessing techniques to enhance QR code detection"""
        processed_images = []
        
        # Original image
        processed_images.append(img.copy())
        
        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Gaussian blur
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        processed_images.append(cv2.cvtColor(blurred, cv2.COLOR_GRAY2BGR))
        
        # Thresholding
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        processed_images.append(cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR))
        
        # Adaptive thresholding
        adaptive_thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        processed_images.append(cv2.cvtColor(adaptive_thresh, cv2.COLOR_GRAY2BGR))
        
        # Sharpen the image
        kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
        sharpened = cv2.filter2D(gray, -1, kernel)
        processed_images.append(cv2.cvtColor(sharpened, cv2.COLOR_GRAY2BGR))
        
        return processed_images
    
    def _is_meshtastic_url(self, url: str) -> bool:
        """Check if a URL looks like a Meshtastic URL"""
        url_lower = url.lower()
        return (
            'meshtastic.org' in url_lower or
            ('/e/#' in url_lower and len(url) > 30) or
            ('/v/#' in url_lower and len(url) > 30)
        )

# Initialize decoder, encoder, and QR processor
decoder = MeshtasticDecoder()
encoder = MeshtasticEncoder()
qr_processor = QRCodeProcessor()

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

@app.route('/upload_qr', methods=['POST'])
def upload_qr():
    """API endpoint to upload and process QR code images"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400
    
    # Check file type
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}
    if not ('.' in file.filename and 
            file.filename.rsplit('.', 1)[1].lower() in allowed_extensions):
        return jsonify({
            'success': False, 
            'error': 'Invalid file type. Please upload an image file.'
        }), 400
    
    try:
        # Read the image data
        image_data = file.read()
        
        # Check file size (max 10MB)
        max_size = 10 * 1024 * 1024  # 10MB
        if len(image_data) > max_size:
            return jsonify({
                'success': False,
                'error': 'File too large. Maximum size is 10MB.'
            }), 400
        
        # Process the QR codes
        qr_result = qr_processor.process_qr_image(image_data)
        
        # If we found Meshtastic URLs, decode them
        if qr_result.get('success') and qr_result.get('meshtastic_urls'):
            decoded_results = []
            for url in qr_result['meshtastic_urls']:
                decode_result = decoder.decode_channel_url(url)
                decoded_results.append({
                    'url': url,
                    'decoded': decode_result
                })
            
            qr_result['decoded_results'] = decoded_results
        
        return jsonify(qr_result)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to process uploaded file: {str(e)}'
        }), 500

@app.route('/encode', methods=['POST'])
def encode_channels():
    """API endpoint to encode Meshtastic channel configurations into URLs and QR codes"""
    data = request.get_json()
    
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    # Get LoRa config if provided
    lora_config = data.get('lora_config')
    
    # Determine if we're encoding a single channel or multiple channels
    if 'channels' in data and isinstance(data['channels'], list):
        # Multiple channels - encode as ChannelSet
        channels_data = data['channels']
        if not channels_data:
            return jsonify({'success': False, 'error': 'No channels provided'}), 400
        
        result = encoder.encode_channel_set(channels_data, lora_config)
    elif 'channel' in data:
        # Single channel - encode as single Channel (legacy support)
        channel_data = data['channel']
        if not channel_data:
            return jsonify({'success': False, 'error': 'No channel data provided'}), 400
        
        result = encoder.encode_single_channel(channel_data)
    else:
        return jsonify({
            'success': False, 
            'error': 'Invalid request format. Expected "channels" array or "channel" object.'
        }), 400
    
    return jsonify(result)

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'service': 'meshtastic-decoder'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
