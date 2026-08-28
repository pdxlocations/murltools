// Meshtastic message encode/decode, mirroring app.py's rules and validation.

const CHANNEL_URL = 'https://meshtastic.org/e/';
const CONTACT_URL = 'https://meshtastic.org/v/';

const MAX_CHANNEL_NAME_BYTES = 11;
const ALLOWED_POSITION_PRECISION = new Set([0, 32, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19]);
const CHANNEL_ROLES = { primary: 1, secondary: 2, disabled: 0 };

function enumValue(name, value, label) {
  const names = ENUMS[name];
  if (typeof value === 'number') return value;
  const text = String(value == null ? '' : value).trim();
  if (/^\d+$/.test(text)) return parseInt(text, 10);
  let index = names.indexOf(text);
  if (index < 0) index = names.indexOf(text.toUpperCase());
  if (index < 0) index = names.indexOf(text.toLowerCase());
  if (index < 0) throw new Error(`Unknown ${label}: ${value}`);
  return index;
}

const enumName = (name, value) => (ENUMS[name] && ENUMS[name][value]) || value;

function parsePsk(psk) {
  if (!psk) return new Uint8Array(0);
  const text = String(psk).trim();
  if (!text) return new Uint8Array(0);
  if (text.toLowerCase().startsWith('0x')) {
    const hex = text.slice(2);
    const out = new Uint8Array(Math.floor(hex.length / 2));
    for (let i = 0; i < out.length; i++) out[i] = parseInt(hex.substr(i * 2, 2), 16);
    return out;
  }
  try {
    return base64ToBytes(text);
  } catch (e) {
    // Same last resort as the server: treat it as raw text, capped at 32 bytes
    return new TextEncoder().encode(text).slice(0, 32);
  }
}

function encodeModuleSettings(ms) {
  const w = new Writer();
  let precision = 32;
  if (ms && ms.position_precision != null) {
    precision = parseInt(ms.position_precision, 10);
    if (!ALLOWED_POSITION_PRECISION.has(precision)) {
      throw new Error(
        `Position precision ${precision} is not one of ` +
        `${[...ALLOWED_POSITION_PRECISION].sort((a, b) => a - b).join(', ')}`
      );
    }
  }
  w.uint32(1, precision);
  if (ms) {
    for (const key of ['is_muted', 'muted', 'mute']) {
      if (key in ms) {
        w.bool(2, ms[key]);
        break;
      }
    }
  }
  return w.finish();
}

function encodeChannelSettings(channel) {
  const w = new Writer();
  w.bytes_(2, parsePsk(channel.psk));
  if (channel.name) {
    const name = String(channel.name);
    if (new TextEncoder().encode(name).length > MAX_CHANNEL_NAME_BYTES) {
      throw new Error(`Channel name '${name}' exceeds ${MAX_CHANNEL_NAME_BYTES} bytes`);
    }
    w.string(3, name);
  }
  if (channel.uplink_enabled) w.bool(5, true);
  if (channel.downlink_enabled) w.bool(6, true);
  // Always present, matching the server: the firmware reads has_module_settings.
  w.messageAlways(7, encodeModuleSettings(channel.module_settings));
  return w.finish();
}

function encodeLoraConfig(lora) {
  const w = new Writer();
  if (lora.use_preset) w.bool(1, true);
  if (lora.modem_preset != null) w.enum(2, enumValue('modem_preset', lora.modem_preset, 'modem preset'));
  if (lora.bandwidth) w.uint32(3, parseInt(lora.bandwidth, 10));
  if (lora.spread_factor) w.uint32(4, parseInt(lora.spread_factor, 10));
  if (lora.coding_rate) w.uint32(5, parseInt(lora.coding_rate, 10));
  if (lora.frequency_offset) w.float(6, parseFloat(lora.frequency_offset));
  if (lora.region != null) w.enum(7, enumValue('region', lora.region, 'region'));
  if (lora.hop_limit) w.uint32(8, parseInt(lora.hop_limit, 10));
  if (lora.tx_enabled) w.bool(9, true);
  if (lora.tx_power) w.uint32(10, parseInt(lora.tx_power, 10));
  if (lora.channel_num) w.uint32(11, parseInt(lora.channel_num, 10));
  if (lora.override_duty_cycle) w.bool(12, true);
  if (lora.sx126x_rx_boosted_gain) w.bool(13, true);
  if (lora.override_frequency) w.float(14, parseFloat(lora.override_frequency));
  return w.finish();
}

function encodeChannelSet(channels, loraConfig, addMode) {
  // Add URLs append to an existing config, so they never carry LoRa settings.
  const lora = addMode ? null : loraConfig;
  const w = new Writer();
  for (const channel of channels) w.message(1, encodeChannelSettings(channel));
  if (lora) w.message(2, encodeLoraConfig(lora));
  return w.finish();
}

function encodeUser(user) {
  const w = new Writer();
  if (user.id) w.string(1, user.id);
  if (user.long_name || user.longName) w.string(2, user.long_name || user.longName);
  if (user.short_name || user.shortName) w.string(3, user.short_name || user.shortName);
  if (user.macaddr) w.string(4, user.macaddr);
  if (user.hw_model != null) w.enum(5, enumValue('hw_model', user.hw_model, 'hardware model'));
  if (user.is_licensed) w.bool(6, true);
  if (user.role != null) w.enum(7, enumValue('role', user.role, 'role'));
  if (user.public_key) w.bytes_(8, parsePsk(user.public_key));
  if (user.is_unmessagable) w.bool(9, true);
  return w.finish();
}

function encodeSharedContact(node) {
  const w = new Writer();
  if (node.node_num) w.uint32(1, node.node_num);
  const user = encodeUser(node.user || {});
  if (user.length) w.message(2, user);
  if (node.should_ignore) w.bool(3, true);
  if (node.manually_verified) w.bool(4, true);
  return w.finish();
}

function decodeModuleSettings(buf) {
  const f = readMessage(buf);
  const out = {};
  if (f[1] !== undefined) out.position_precision = last(f[1]);
  if (last(f[2])) out.is_muted = true;
  return out;
}

function decodeChannelSettings(buf) {
  const f = readMessage(buf);
  const out = {};
  const psk = last(f[2]);
  if (psk && psk.length) out.psk = bytesToBase64(psk);
  const name = asString(last(f[3]));
  if (name) out.name = name;
  if (last(f[5])) out.uplink_enabled = true;
  if (last(f[6])) out.downlink_enabled = true;
  if (f[7]) out.module_settings = decodeModuleSettings(last(f[7]));
  return out;
}

function decodeLoraConfig(buf) {
  const f = readMessage(buf);
  const out = {};
  if (last(f[1])) out.use_preset = true;
  if (f[2] !== undefined) out.modem_preset = enumName('modem_preset', last(f[2]));
  if (f[3] !== undefined) out.bandwidth = last(f[3]);
  if (f[4] !== undefined) out.spread_factor = last(f[4]);
  if (f[5] !== undefined) out.coding_rate = last(f[5]);
  if (f[6] !== undefined) out.frequency_offset = last(f[6]);
  if (f[7] !== undefined) out.region = enumName('region', last(f[7]));
  if (f[8] !== undefined) out.hop_limit = last(f[8]);
  if (last(f[9])) out.tx_enabled = true;
  if (f[10] !== undefined) out.tx_power = last(f[10]);
  if (f[11] !== undefined) out.channel_num = last(f[11]);
  if (last(f[12])) out.override_duty_cycle = true;
  if (last(f[13])) out.sx126x_rx_boosted_gain = true;
  if (f[14] !== undefined) out.override_frequency = last(f[14]);
  return out;
}

function decodeUser(buf) {
  const f = readMessage(buf);
  const out = {};
  const id = asString(last(f[1]));
  if (id) out.id = id;
  const longName = asString(last(f[2]));
  if (longName) out.long_name = longName;
  const shortName = asString(last(f[3]));
  if (shortName) out.short_name = shortName;
  const mac = last(f[4]);
  if (mac) out.macaddr = bytesToBase64(mac);
  if (f[5] !== undefined) out.hw_model = enumName('hw_model', last(f[5]));
  if (last(f[6])) out.is_licensed = true;
  if (f[7] !== undefined) out.role = enumName('role', last(f[7]));
  const key = last(f[8]);
  if (key && key.length) out.public_key = bytesToBase64(key);
  if (last(f[9])) out.is_unmessagable = true;
  return out;
}

function decodeSharedContact(buf) {
  const f = readMessage(buf);
  const out = {};
  if (f[1] !== undefined) out.node_num = last(f[1]);
  if (f[2] !== undefined) out.user = decodeUser(last(f[2]));
  if (last(f[3])) out.should_ignore = true;
  if (last(f[4])) out.manually_verified = true;
  return out;
}

const formatNodeId = (num) => '!' + (num >>> 0).toString(16).padStart(8, '0');

function parseNodeId(text) {
  const raw = String(text || '').trim().toLowerCase();
  if (!raw.startsWith('!')) return null;
  const value = parseInt(raw.slice(1), 16);
  return Number.isNaN(value) ? null : value;
}

/** Split the payload from the 'add' flag, in either the query or the fragment. */
function splitAddFlag(url) {
  const hashIndex = url.indexOf('#');
  const head = hashIndex < 0 ? url : url.slice(0, hashIndex);
  let payload = hashIndex < 0 ? '' : url.slice(hashIndex + 1);

  const isAddTrue = (query) => /(^|&)add=true(&|$)/i.test(query);
  let addMode = isAddTrue(head.split('?')[1] || '');

  const q = payload.indexOf('?');
  if (q >= 0) {
    addMode = addMode || isAddTrue(payload.slice(q + 1));
    payload = payload.slice(0, q);
  }

  if (!payload) {
    const match = head.match(/[?&]c=([^&]+)/);
    if (match) payload = match[1];
  }
  return { payload, addMode };
}

function decodeMeshtasticUrl(url) {
  const { payload, addMode } = splitAddFlag(url);
  if (!payload) throw new Error('No encoded channel data found in URL');
  const bytes = base64UrlDecode(payload);

  if (url.includes('/v/')) {
    const contact = decodeSharedContact(bytes);
    if (contact.node_num && contact.user) {
      return { success: true, url, SharedContact: contact };
    }
  }

  const fields = readMessage(bytes);
  const config = {};
  if (fields[1]) config.channels = fields[1].map(decodeChannelSettings);
  if (fields[2] && !addMode) config.lora_config = decodeLoraConfig(last(fields[2]));
  if (!config.channels && !config.lora_config) throw new Error('Unable to decode protobuf data');

  return {
    success: true,
    url,
    channel_action: addMode ? 'add' : 'replace',
    Config: config,
  };
}

function buildChannelUrl(payload, addMode) {
  return addMode ? `${CHANNEL_URL}?add=true#${payload}` : `${CHANNEL_URL}#${payload}`;
}
