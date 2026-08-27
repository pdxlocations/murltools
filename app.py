#!/usr/bin/env python3
"""
Meshtastic Channel URL Decoder
A Flask web application that decodes Meshtastic channel URLs and their encoded protobufs.
"""

import base64
import json
import io
import re
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any, List, Optional, Tuple

from flask import Flask, render_template, request, jsonify
from meshtastic.protobuf import channel_pb2, apponly_pb2, mesh_pb2, config_pb2, admin_pb2
from google.protobuf.message import DecodeError
from google.protobuf.json_format import MessageToDict
from PIL import Image
from pyzbar import pyzbar
import cv2
import numpy as np
import qrcode
from qrcode.constants import ERROR_CORRECT_L, ERROR_CORRECT_H
from qrcode.image.styledpil import StyledPilImage

from io import BytesIO

app = Flask(__name__)

# ChannelSettings.name is capped at 12 bytes including the null terminator
MAX_CHANNEL_NAME_BYTES = 11

# Position precision the official clients actually produce: disabled, the 10-19
# approximate range, or 32 for precise. Nothing else is reachable in their UI.
POSITION_PRECISION_DISABLED = 0
POSITION_PRECISION_PRECISE = 32
ALLOWED_POSITION_PRECISION = {POSITION_PRECISION_DISABLED, POSITION_PRECISION_PRECISE} | set(range(10, 20))

# Centre-embed limits: above ~0.30 the code stops scanning even at error correction H
MIN_EMBED_RATIO = 0.10
MAX_EMBED_RATIO = 0.30
DEFAULT_EMBED_RATIO = 0.22
MAX_EMBED_IMAGE_BYTES = 2 * 1024 * 1024

# Output resolution multiplier. Helps print and download quality; scanning at a given
# displayed size depends on module count, not on how many pixels each module gets.
QR_BOX_SIZE = 10
ALLOWED_QR_SCALES = {1, 2, 4}

class MeshtasticDecoder:
    """Handles decoding of Meshtastic channel URLs and protobuf data"""

    def _normalize_config_dict(self, config_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize decoded config keys for consistent API output."""
        if not isinstance(config_dict, dict):
            return config_dict

        normalized = dict(config_dict)
        if isinstance(normalized.get('settings'), list):
            normalized['channels'] = normalized['settings']
            del normalized['settings']
        return normalized
    
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

            encoded_data, add_mode = self._split_add_flag(encoded_data, parsed_url.query)

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
                result = self._try_channel_decoders(decoded_data, url, decode_attempts, add_mode)
                if result:
                    return result
            else:
                # For channel URLs or unknown, try channel types first
                result = self._try_channel_decoders(decoded_data, url, decode_attempts, add_mode)
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
    
    def _split_add_flag(self, encoded_data: str, query: str) -> Tuple[str, bool]:
        """Separate the payload from the 'add' flag, which newer clients put in the
        query string (?add=true#data) and older ones appended to the fragment."""
        add_mode = self._is_add_true(parse_qs(query))

        if '?' in encoded_data:
            encoded_data, _, fragment_query = encoded_data.partition('?')
            add_mode = add_mode or self._is_add_true(parse_qs(fragment_query))

        return encoded_data, add_mode

    @staticmethod
    def _is_add_true(query_params: Dict[str, List[str]]) -> bool:
        """Check whether an 'add=true' flag is present in parsed query parameters."""
        return any(value.strip().lower() == 'true' for value in query_params.get('add', []))

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

        # Try SharedContact first: this is what /v/ contact URLs actually carry.
        try:
            contact = admin_pb2.SharedContact()
            contact.ParseFromString(decoded_data)
            contact_dict = MessageToDict(contact, preserving_proto_field_name=True)
            if self._validate_shared_contact_data(contact_dict):
                return {
                    'success': True,
                    'url': url,
                    'SharedContact': contact_dict
                }
        except Exception as e:
            decode_attempts.append(f'SharedContact failed: {str(e)}')

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
    
    def _try_channel_decoders(self, decoded_data: bytes, url: str, decode_attempts: list, add_mode: bool = False) -> Optional[Dict[str, Any]]:
        """Try channel-related protobuf message types"""

        channel_action = 'add' if add_mode else 'replace'

        # Try to decode as ChannelSet first
        try:
            channel_set = apponly_pb2.ChannelSet()
            channel_set.ParseFromString(decoded_data)
            config_dict = MessageToDict(channel_set, preserving_proto_field_name=True)
            config_dict = self._normalize_config_dict(config_dict)
            # Add URLs never apply LoRa settings, so drop any the sender included.
            if add_mode:
                config_dict.pop('lora_config', None)
            # Validate that this looks like real channel data
            if self._validate_channel_set_data(config_dict):
                return {
                    'success': True,
                    'url': url,
                    'channel_action': channel_action,
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
                    'channel_action': channel_action,
                    'Config': config_dict
                }
        except Exception as e:
            decode_attempts.append(f'SingleChannel failed: {str(e)}')
        
        return None
    
    def _validate_shared_contact_data(self, data: Dict[str, Any]) -> bool:
        """Validate that decoded data looks like a real SharedContact"""
        # A contact is only meaningful with an identity attached
        return bool(data.get('node_num') and data.get('user'))

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

    def _build_channel_url(self, encoded_data: str, add_mode: bool = False) -> str:
        """Build a Meshtastic channel URL, optionally in add mode."""
        if add_mode:
            return f"https://meshtastic.org/e/?add=true#{encoded_data}"
        return f"https://meshtastic.org/e/#{encoded_data}"

    def _format_node_id(self, node_num: int) -> str:
        """Format node number as Meshtastic node ID (hex with leading !)."""
        return f"!{node_num & 0xFFFFFFFF:08x}"

    def _parse_node_id(self, node_id: str) -> Optional[int]:
        """Parse a node ID string like !0ad99a53 into an int."""
        if not node_id:
            return None
        value = node_id.strip().lower()
        if not value.startswith('!'):
            return None
        value = value[1:]
        try:
            return int(value, 16)
        except ValueError:
            return None

    def _set_proto_field(self, message, field_name: str, value: Any) -> bool:
        """Safely set a protobuf field if it exists on the message."""
        if field_name in message.DESCRIPTOR.fields_by_name:
            setattr(message, field_name, value)
            return True
        return False

    def _set_proto_enum(self, message, field_name: str, value: Any) -> bool:
        """Safely set a protobuf enum field from a name or numeric value."""
        field = message.DESCRIPTOR.fields_by_name.get(field_name)
        if not field or field.enum_type is None:
            return False

        enum_type = field.enum_type
        try:
            if isinstance(value, str):
                value_str = value.strip()
                if value_str.isdigit():
                    setattr(message, field_name, int(value_str))
                    return True
                enum_value = enum_type.values_by_name.get(value_str)
                if enum_value is None:
                    enum_value = enum_type.values_by_name.get(value_str.upper())
                if enum_value is None:
                    enum_value = enum_type.values_by_name.get(value_str.lower())
                if enum_value is None:
                    return False
                setattr(message, field_name, enum_value.number)
                return True
            setattr(message, field_name, int(value))
            return True
        except (TypeError, ValueError):
            return False

    def encode_channel_set(self, channels_data: List[Dict[str, Any]], lora_config_data: Optional[Dict[str, Any]] = None, add_mode: bool = False, embed: Optional[Dict[str, Any]] = None, scale: int = 1) -> Dict[str, Any]:
        """
        Encode multiple channels into a ChannelSet and create Meshtastic URL
        
        Args:
            channels_data: List of channel configuration dictionaries
            lora_config_data: Optional LoRa configuration dictionary
            add_mode: Build an "add" URL, which never carries LoRa settings
            embed: Optional centre-embed options for the QR code

        Returns:
            Dictionary containing URL, QR code data, and success status
        """
        try:
            # Add URLs append channels to an existing config, so they must not
            # carry LoRa settings; the importing client discards them anyway.
            if add_mode:
                lora_config_data = None

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
                    name = str(channel_data['name'])
                    # channel.proto allows 12 bytes including the null terminator
                    if len(name.encode('utf-8')) > MAX_CHANNEL_NAME_BYTES:
                        raise ValueError(
                            f"Channel name '{name}' exceeds {MAX_CHANNEL_NAME_BYTES} bytes"
                        )
                    settings.name = name


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
                        precision = int(ms['position_precision'])
                        if precision not in ALLOWED_POSITION_PRECISION:
                            raise ValueError(
                                f'Position precision {precision} is not one of '
                                f'{sorted(ALLOWED_POSITION_PRECISION)}'
                            )
                        module_settings.position_precision = precision
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
                    if not self._set_proto_enum(lora_config, 'modem_preset', lora_config_data['modem_preset']):
                        raise ValueError(f"Unknown modem preset: {lora_config_data['modem_preset']}")
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
                    if not self._set_proto_enum(lora_config, 'region', lora_config_data['region']):
                        raise ValueError(f"Unknown region: {lora_config_data['region']}")
                    
                channel_set.lora_config.CopyFrom(lora_config)
            
            # Serialize the ChannelSet to bytes
            protobuf_data = channel_set.SerializeToString()
            
            # Encode as base64url
            encoded_data = self._base64url_encode(protobuf_data)
            
            # Create Meshtastic URL
            url = self._build_channel_url(encoded_data, add_mode)
            
            # Generate QR code
            qr_code_data = self._generate_qr_code(url, embed, scale)
            if not qr_code_data.get('success'):
                return {
                    'success': False,
                    'error': qr_code_data.get('error', 'Failed to generate QR code')
                }
            
            # Also decode the generated URL to provide config data in same format as decoder
            decoder_instance = MeshtasticDecoder()
            decoded_result = decoder_instance.decode_channel_url(url)
            
            # Build the response with both encoding and decoding information
            response = {
                'success': True,
                'url': url,
                'qr_code': qr_code_data,
                'channels_count': len(channels_data),
                'encoded_size': len(protobuf_data),
                'channel_action': 'add' if add_mode else 'replace'
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
    
    def encode_single_channel(self, channel_data: Dict[str, Any], lora_config_data: Optional[Dict[str, Any]] = None, add_mode: bool = False, embed: Optional[Dict[str, Any]] = None, scale: int = 1) -> Dict[str, Any]:
        """
        Encode a single channel into a Meshtastic URL

        Args:
            channel_data: Channel configuration dictionary
            lora_config_data: Optional LoRa configuration dictionary
            add_mode: Build an "add" URL, which never carries LoRa settings

        Returns:
            Dictionary containing URL, QR code data, and success status
        """
        # A URL always carries a ChannelSet, never a bare Channel, so a lone
        # channel is just a one-entry set.
        return self.encode_channel_set([channel_data], lora_config_data, add_mode, embed, scale)

    def encode_nodeinfo(self, node_data: Dict[str, Any], embed: Optional[Dict[str, Any]] = None, scale: int = 1) -> Dict[str, Any]:
        """
        Encode a shared contact into a Meshtastic contact URL

        Args:
            node_data: Contact configuration dictionary
            embed: Optional centre-embed options for the QR code

        Returns:
            Dictionary containing URL, QR code data, and success status
        """
        try:
            if not node_data:
                return {
                    'success': False,
                    'error': 'No node data provided'
                }

            def _get_value(data: Dict[str, Any], *keys: str) -> Any:
                for key in keys:
                    if key in data and data[key] is not None:
                        return data[key]
                return None

            node = admin_pb2.SharedContact()
            has_required_identity = False
            node_num_value: Optional[int] = None
            user_id_value: Optional[str] = None

            node_num_raw = _get_value(node_data, 'num', 'node_num')
            if node_num_raw is not None:
                node_num = node_num_raw
                if isinstance(node_num, str):
                    node_num = int(node_num, 10)
                node_num_value = int(node_num)
                self._set_proto_field(node, 'node_num', node_num_value)
                has_required_identity = True

            # SharedContact carries only these two flags alongside the identity
            should_ignore_value = _get_value(node_data, 'is_ignored', 'isIgnored', 'should_ignore')
            if should_ignore_value is not None:
                self._set_proto_field(node, 'should_ignore', bool(should_ignore_value))

            manually_verified_value = _get_value(
                node_data,
                'is_key_manually_verified',
                'isKeyManuallyVerified',
                'manually_verified'
            )
            if manually_verified_value is not None:
                self._set_proto_field(node, 'manually_verified', bool(manually_verified_value))

            user_data = node_data.get('user')
            if isinstance(user_data, dict):
                user = mesh_pb2.User()

                user_id_raw = _get_value(user_data, 'id')
                if user_id_raw:
                    user_id_value = str(user_id_raw)
                    self._set_proto_field(user, 'id', user_id_value)
                    has_required_identity = True
                long_name_value = _get_value(user_data, 'long_name', 'longName')
                if long_name_value:
                    self._set_proto_field(user, 'long_name', str(long_name_value))
                short_name_value = _get_value(user_data, 'short_name', 'shortName')
                if short_name_value:
                    self._set_proto_field(user, 'short_name', str(short_name_value))
                macaddr_value = _get_value(user_data, 'macaddr', 'macAddr')
                if macaddr_value:
                    self._set_proto_field(user, 'macaddr', str(macaddr_value))
                hw_model_value = _get_value(user_data, 'hw_model', 'hwModel')
                if hw_model_value is not None:
                    self._set_proto_enum(user, 'hw_model', hw_model_value)
                is_licensed_value = _get_value(user_data, 'is_licensed', 'isLicensed')
                if is_licensed_value is not None:
                    self._set_proto_field(user, 'is_licensed', bool(is_licensed_value))
                role_value = _get_value(user_data, 'role')
                if role_value is not None:
                    self._set_proto_enum(user, 'role', role_value)
                public_key_raw = _get_value(user_data, 'public_key', 'publicKey')
                if public_key_raw:
                    public_key_value = public_key_raw
                    if isinstance(public_key_value, str):
                        try:
                            public_key_value = base64.b64decode(public_key_value)
                        except (ValueError, TypeError):
                            public_key_value = None
                    if public_key_value:
                        self._set_proto_field(user, 'public_key', public_key_value)
                is_unmessagable_value = _get_value(user_data, 'is_unmessagable', 'isUnmessagable')
                if is_unmessagable_value is not None:
                    self._set_proto_field(user, 'is_unmessagable', bool(is_unmessagable_value))

                if user.ListFields():
                    node.user.CopyFrom(user)

            if not has_required_identity:
                return {
                    'success': False,
                    'error': 'Provide node number or node ID'
                }

            # Auto-derive missing identity field after validation.
            if node_num_value is not None and not user_id_value:
                node.user.id = self._format_node_id(node_num_value)
            elif node_num_value is None and user_id_value:
                derived_num = self._parse_node_id(user_id_value)
                if derived_num is not None:
                    node.node_num = derived_num

            protobuf_data = node.SerializeToString()
            encoded_data = self._base64url_encode(protobuf_data)
            url = f"https://meshtastic.org/v/#{encoded_data}"

            qr_code_data = self._generate_qr_code(url, embed, scale)
            if not qr_code_data.get('success'):
                return {
                    'success': False,
                    'error': qr_code_data.get('error', 'Failed to generate QR code')
                }
            decoder_instance = MeshtasticDecoder()
            decoded_result = decoder_instance.decode_channel_url(url)

            response = {
                'success': True,
                'url': url,
                'qr_code': qr_code_data,
                'encoded_size': len(protobuf_data)
            }

            if decoded_result.get('success'):
                for key, value in decoded_result.items():
                    if key not in ['success', 'url']:
                        response[key] = value

            return response

        except Exception as e:
            return {
                'success': False,
                'error': f'Failed to encode node info: {str(e)}'
            }
    
    def _base64url_encode(self, data: bytes) -> str:
        """Encode bytes as base64url string"""
        # Use URL-safe base64 encoding and remove padding
        encoded = base64.urlsafe_b64encode(data).decode('ascii')
        return encoded.rstrip('=')
    
    def _decode_embed_image(self, image_data: str) -> Image.Image:
        """Decode a browser data URL (or bare base64) into an image to embed."""
        payload = image_data.split(',', 1)[1] if image_data.startswith('data:') else image_data
        raw = base64.b64decode(payload)
        if len(raw) > MAX_EMBED_IMAGE_BYTES:
            raise ValueError(f'Embedded image exceeds {MAX_EMBED_IMAGE_BYTES // 1024}KB')

        image = Image.open(BytesIO(raw))
        image.load()
        return image.convert('RGBA')

    def _generate_qr_code(self, url: str, embed: Optional[Dict[str, Any]] = None, scale: int = 1) -> Dict[str, Any]:
        """
        Generate a QR code image for the given URL

        Args:
            url: The URL to encode
            embed: Optional {'mode': 'image'|'blank', 'image': <data URL>, 'ratio': float}
                   reserving a square in the centre. Anything centred forces error
                   correction H, which the qrcode library requires and which makes the
                   code denser, so the caller opts in.
            scale: Pixel multiplier for the output. Raises print and download quality;
                   it does not change how well the code scans at a given displayed size,
                   which depends on the module count instead.

        Returns:
            Dictionary containing the base64 PNG and its size
        """
        try:
            mode = (embed or {}).get('mode', 'none')
            centre_image = None

            if mode == 'image':
                centre_image = self._decode_embed_image((embed or {}).get('image') or '')
            elif mode == 'blank':
                # A solid white square the user can overprint or stick a label on
                centre_image = Image.new('RGBA', (256, 256), (255, 255, 255, 255))

            ratio = float((embed or {}).get('ratio', DEFAULT_EMBED_RATIO))
            if not MIN_EMBED_RATIO <= ratio <= MAX_EMBED_RATIO:
                raise ValueError(
                    f'Embed ratio must be between {MIN_EMBED_RATIO} and {MAX_EMBED_RATIO}'
                )

            scale = int(scale or 1)
            if scale not in ALLOWED_QR_SCALES:
                raise ValueError(f'QR scale must be one of {sorted(ALLOWED_QR_SCALES)}')

            qr = qrcode.QRCode(
                version=1,  # Controls the size of the QR Code
                error_correction=ERROR_CORRECT_H if centre_image else ERROR_CORRECT_L,
                box_size=QR_BOX_SIZE * scale,
                border=4,
            )
            qr.add_data(url)
            qr.make(fit=True)

            # Create image
            if centre_image:
                qr_img = qr.make_image(
                    image_factory=StyledPilImage,
                    embedded_image=centre_image,
                    embedded_image_ratio=ratio,
                )
            else:
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
                'size': qr_img.size,
                'scale': scale,
                'modules': qr.modules_count,
                'error_correction': 'H' if centre_image else 'L'
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
        if 'meshtastic.org' in url_lower:
            return True

        # Match /e/ and /v/ with or without the trailing slash, as clients accept both
        return len(url) > 30 and bool(re.search(r'/[ev]/?[#?]', url_lower))

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
    embed = data.get('qr_embed')
    qr_scale = data.get('qr_scale', 1)
    channel_action = str(data.get('channel_action', 'replace')).strip().lower()
    add_mode = channel_action == 'add'

    # Replace action requires explicit LoRa config
    if not add_mode and (not isinstance(lora_config, dict) or not lora_config):
        return jsonify({
            'success': False,
            'error': 'LoRa config is required when channel_action is "replace".'
        }), 400
    
    # Determine if we're encoding a single channel or multiple channels
    if 'channels' in data and isinstance(data['channels'], list):
        # Multiple channels - encode as ChannelSet
        channels_data = data['channels']
        if not channels_data:
            return jsonify({'success': False, 'error': 'No channels provided'}), 400
        
        result = encoder.encode_channel_set(channels_data, lora_config, add_mode, embed, qr_scale)
    elif 'channel' in data:
        # Single channel - encoded as a one-entry ChannelSet
        channel_data = data['channel']
        if not channel_data:
            return jsonify({'success': False, 'error': 'No channel data provided'}), 400

        result = encoder.encode_single_channel(channel_data, lora_config, add_mode, embed, qr_scale)
    else:
        return jsonify({
            'success': False, 
            'error': 'Invalid request format. Expected "channels" array or "channel" object.'
        }), 400
    
    return jsonify(result)

@app.route('/encode_nodeinfo', methods=['POST'])
def encode_nodeinfo():
    """API endpoint to encode Meshtastic node info into URLs and QR codes"""
    data = request.get_json()

    if not data or 'node' not in data:
        return jsonify({'success': False, 'error': 'No node data provided'}), 400

    node_data = data['node']
    result = encoder.encode_nodeinfo(node_data, data.get('qr_embed'), data.get('qr_scale', 1))
    return jsonify(result)

@app.route('/nodeinfo_enums', methods=['GET'])
def nodeinfo_enums():
    """Return enum names for NodeInfo-related fields"""
    try:
        user_descriptor = mesh_pb2.User.DESCRIPTOR
        hw_model_field = user_descriptor.fields_by_name.get('hw_model')
        role_field = user_descriptor.fields_by_name.get('role')

        hw_model_values = []
        role_values = []

        if hw_model_field and hw_model_field.enum_type:
            hw_model_values = [value.name for value in hw_model_field.enum_type.values]
        if role_field and role_field.enum_type:
            role_values = [value.name for value in role_field.enum_type.values]

        return jsonify({
            'success': True,
            'hw_model': hw_model_values,
            'role': role_values
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/lora_enums', methods=['GET'])
def lora_enums():
    """Return enum names for LoRa config fields"""
    try:
        lora_descriptor = config_pb2.Config.LoRaConfig.DESCRIPTOR
        values = {}

        for field_name in ('modem_preset', 'region'):
            field = lora_descriptor.fields_by_name.get(field_name)
            values[field_name] = [value.name for value in field.enum_type.values] if field and field.enum_type else []

        return jsonify({'success': True, **values})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'service': 'meshtastic-decoder'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
