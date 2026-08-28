// Minimal protobuf wire-format codec: just what the Meshtastic URL messages need.

const WIRE_VARINT = 0;
const WIRE_FIXED64 = 1;
const WIRE_LENGTH = 2;
const WIRE_FIXED32 = 5;

class Writer {
  constructor() {
    this.bytes = [];
  }

  varint(value) {
    let v = value >>> 0;
    if (typeof value === 'number' && value < 0) v = value >>> 0;
    while (v > 0x7f) {
      this.bytes.push((v & 0x7f) | 0x80);
      v >>>= 7;
    }
    this.bytes.push(v);
    return this;
  }

  tag(field, wire) {
    return this.varint((field << 3) | wire);
  }

  uint32(field, value) {
    if (!value) return this;
    return this.tag(field, WIRE_VARINT).varint(value);
  }

  bool(field, value) {
    if (!value) return this;
    return this.tag(field, WIRE_VARINT).varint(1);
  }

  enum(field, value) {
    return this.uint32(field, value);
  }

  float(field, value) {
    if (!value) return this;
    this.tag(field, WIRE_FIXED32);
    const buf = new DataView(new ArrayBuffer(4));
    buf.setFloat32(0, value, true);
    for (let i = 0; i < 4; i++) this.bytes.push(buf.getUint8(i));
    return this;
  }

  bytes_(field, value) {
    if (!value || !value.length) return this;
    this.tag(field, WIRE_LENGTH).varint(value.length);
    for (const b of value) this.bytes.push(b);
    return this;
  }

  string(field, value) {
    if (!value) return this;
    return this.bytes_(field, new TextEncoder().encode(value));
  }

  message(field, value) {
    if (!value || !value.length) return this;
    return this.bytes_(field, value);
  }

  /** Write a submessage even when it encodes to nothing, so presence is preserved. */
  messageAlways(field, value) {
    this.tag(field, WIRE_LENGTH).varint(value.length);
    for (const b of value) this.bytes.push(b);
    return this;
  }

  finish() {
    return new Uint8Array(this.bytes);
  }
}

/**
 * Read a message into { fieldNumber: [values] }. Length-delimited values come back
 * as Uint8Array, varints as numbers, fixed32 as a float. Repeated fields keep every
 * occurrence; callers take the last unless they want the list.
 */
function readMessage(buf) {
  const fields = {};
  let i = 0;

  const readVarint = () => {
    let result = 0;
    let shift = 0;
    while (i < buf.length) {
      const b = buf[i++];
      result += (b & 0x7f) * Math.pow(2, shift);
      if (!(b & 0x80)) return result;
      shift += 7;
    }
    throw new Error('Truncated varint');
  };

  while (i < buf.length) {
    const tag = readVarint();
    const field = tag >>> 3;
    const wire = tag & 7;
    let value;

    if (wire === WIRE_VARINT) {
      value = readVarint();
    } else if (wire === WIRE_LENGTH) {
      const len = readVarint();
      if (i + len > buf.length) throw new Error('Truncated length-delimited field');
      value = buf.subarray(i, i + len);
      i += len;
    } else if (wire === WIRE_FIXED32) {
      if (i + 4 > buf.length) throw new Error('Truncated fixed32');
      value = new DataView(buf.buffer, buf.byteOffset + i, 4).getFloat32(0, true);
      i += 4;
    } else if (wire === WIRE_FIXED64) {
      if (i + 8 > buf.length) throw new Error('Truncated fixed64');
      value = new DataView(buf.buffer, buf.byteOffset + i, 8).getFloat64(0, true);
      i += 8;
    } else {
      throw new Error(`Unsupported wire type ${wire}`);
    }

    (fields[field] = fields[field] || []).push(value);
  }

  return fields;
}

const last = (values) => (values && values.length ? values[values.length - 1] : undefined);
const asString = (value) => (value === undefined ? undefined : new TextDecoder().decode(value));

function base64UrlEncode(bytes) {
  let binary = '';
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function base64UrlDecode(text) {
  let padded = text.replace(/-/g, '+').replace(/_/g, '/');
  while (padded.length % 4) padded += '=';
  const binary = atob(padded);
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i);
  return out;
}

function base64ToBytes(text) {
  const binary = atob(text);
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i);
  return out;
}

function bytesToBase64(bytes) {
  let binary = '';
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary);
}
