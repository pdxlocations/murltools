// Serves the endpoints the page already calls, in the browser instead of Flask.
// window.fetch is wrapped so templates/index.html needs no changes at all.

const QR_BOX_SIZE = 10;
const QR_BORDER = 4;
const ALLOWED_QR_SCALES = new Set([1, 2, 4]);
const MIN_EMBED_RATIO = 0.10;
const MAX_EMBED_RATIO = 0.30;
const DEFAULT_EMBED_RATIO = 0.22;
const MAX_EMBED_IMAGE_BYTES = 2 * 1024 * 1024;

function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error('Could not read that image'));
    img.src = src;
  });
}

async function generateQrCode(url, embed, scale) {
  scale = parseInt(scale || 1, 10);
  if (!ALLOWED_QR_SCALES.has(scale)) {
    throw new Error(`QR scale must be one of ${[...ALLOWED_QR_SCALES].sort().join(', ')}`);
  }

  const mode = (embed && embed.mode) || 'none';
  const ratio = embed && embed.ratio != null ? parseFloat(embed.ratio) : DEFAULT_EMBED_RATIO;
  if (mode !== 'none' && !(ratio >= MIN_EMBED_RATIO && ratio <= MAX_EMBED_RATIO)) {
    throw new Error(`Embed ratio must be between ${MIN_EMBED_RATIO} and ${MAX_EMBED_RATIO}`);
  }

  let centre = null;
  if (mode === 'image') {
    const data = (embed && embed.image) || '';
    const payload = data.startsWith('data:') ? data.split(',')[1] : data;
    if (atob(payload).length > MAX_EMBED_IMAGE_BYTES) {
      throw new Error(`Embedded image exceeds ${MAX_EMBED_IMAGE_BYTES / 1024}KB`);
    }
    centre = await loadImage(data.startsWith('data:') ? data : `data:image/png;base64,${data}`);
  }

  // Anything centred needs error correction H, as the python build also enforces.
  const ecLevel = mode === 'none' ? 'L' : 'H';
  const qr = qrcode(0, ecLevel);
  qr.addData(url);
  qr.make();

  const modules = qr.getModuleCount();
  const box = QR_BOX_SIZE * scale;
  const size = (modules + QR_BORDER * 2) * box;

  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, size, size);
  ctx.fillStyle = '#000000';
  for (let r = 0; r < modules; r++) {
    for (let c = 0; c < modules; c++) {
      if (qr.isDark(r, c)) {
        ctx.fillRect((c + QR_BORDER) * box, (r + QR_BORDER) * box, box, box);
      }
    }
  }

  if (mode !== 'none') {
    // Snap the reserved square to module boundaries, as StyledPilImage does.
    const roughWidth = size * ratio;
    const offset = Math.floor((Math.floor(size / 2) - Math.floor(roughWidth / 2)) / box) * box;
    const width = size - offset * 2;
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(offset, offset, width, width);
    if (centre) ctx.drawImage(centre, offset, offset, width, width);
  }

  return {
    success: true,
    image_base64: canvas.toDataURL('image/png').split(',')[1],
    mime_type: 'image/png',
    size: [size, size],
    scale,
    modules,
    error_correction: ecLevel,
  };
}

async function handleEncode(body) {
  const action = String(body.channel_action || 'replace').trim().toLowerCase();
  const addMode = action === 'add';
  const lora = body.lora_config;

  if (!addMode && (!lora || typeof lora !== 'object' || !Object.keys(lora).length)) {
    return { success: false, error: 'LoRa config is required when channel_action is "replace".' };
  }

  let channels;
  if (Array.isArray(body.channels)) {
    if (!body.channels.length) return { success: false, error: 'No channels provided' };
    channels = body.channels;
  } else if (body.channel) {
    channels = [body.channel]; // a lone channel is a one-entry set
  } else {
    return { success: false, error: 'Invalid request format. Expected "channels" array or "channel" object.' };
  }

  let url;
  let payloadLength;
  try {
    const bytes = encodeChannelSet(channels, lora, addMode);
    payloadLength = bytes.length;
    url = buildChannelUrl(base64UrlEncode(bytes), addMode);
  } catch (e) {
    return { success: false, error: `Failed to encode channel set: ${e.message}` };
  }

  const response = {
    success: true,
    url,
    channels_count: channels.length,
    encoded_size: payloadLength,
    channel_action: addMode ? 'add' : 'replace',
  };

  try {
    response.qr_code = await generateQrCode(url, body.qr_embed, body.qr_scale);
  } catch (e) {
    response.qr_code = { success: false, error: `Failed to generate QR code: ${e.message}` };
  }

  try {
    const decoded = decodeMeshtasticUrl(url);
    if (decoded.Config) response.Config = decoded.Config;
  } catch (e) {
    /* the encode still stands even if the read-back fails */
  }
  return response;
}

async function handleEncodeNodeinfo(body) {
  const node = body.node || {};
  const contact = {};

  let nodeNum = null;
  const rawNum = node.num != null ? node.num : node.node_num;
  if (rawNum != null && rawNum !== '') {
    nodeNum = parseInt(rawNum, 10);
    contact.node_num = nodeNum;
  }

  if (node.is_ignored || node.isIgnored || node.should_ignore) contact.should_ignore = true;
  if (node.is_key_manually_verified || node.isKeyManuallyVerified || node.manually_verified) {
    contact.manually_verified = true;
  }

  const user = Object.assign({}, node.user || {});
  const userId = user.id ? String(user.id) : null;
  if (nodeNum == null && !userId) {
    return { success: false, error: 'Provide node number or node ID' };
  }

  if (nodeNum != null && !userId) {
    user.id = formatNodeId(nodeNum);
  } else if (nodeNum == null && userId) {
    const derived = parseNodeId(userId);
    if (derived != null) contact.node_num = derived;
  }
  contact.user = user;

  let url;
  let payloadLength;
  try {
    const bytes = encodeSharedContact(contact);
    payloadLength = bytes.length;
    url = `${CONTACT_URL}#${base64UrlEncode(bytes)}`;
  } catch (e) {
    return { success: false, error: `Failed to encode contact: ${e.message}` };
  }

  const response = { success: true, url, encoded_size: payloadLength };
  try {
    response.qr_code = await generateQrCode(url, body.qr_embed, body.qr_scale);
  } catch (e) {
    response.qr_code = { success: false, error: `Failed to generate QR code: ${e.message}` };
  }

  try {
    const decoded = decodeMeshtasticUrl(url);
    for (const key of Object.keys(decoded)) {
      if (key !== 'success' && key !== 'url') response[key] = decoded[key];
    }
  } catch (e) {
    /* as above */
  }
  return response;
}

function handleDecode(body) {
  try {
    return decodeMeshtasticUrl(body.url || '');
  } catch (e) {
    return { success: false, error: e.message, url: body.url };
  }
}

const isMeshtasticUrl = (url) =>
  url.toLowerCase().includes('meshtastic.org') ||
  (url.length > 30 && /\/[ev]\/?[#?]/i.test(url));

async function handleUploadQr(formData) {
  const file = formData.get('file');
  if (!file) return { success: false, error: 'No file uploaded', qr_codes: [] };

  const bitmap = await createImageBitmap(file);
  const canvas = document.createElement('canvas');
  canvas.width = bitmap.width;
  canvas.height = bitmap.height;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(bitmap, 0, 0);
  const pixels = ctx.getImageData(0, 0, canvas.width, canvas.height);

  const found = jsQR(pixels.data, pixels.width, pixels.height);
  if (!found) {
    return { success: false, error: 'No QR codes detected in image', qr_codes: [] };
  }

  const meshtasticUrls = isMeshtasticUrl(found.data) ? [found.data] : [];
  const result = {
    success: true,
    qr_codes: [{ type: 'QRCODE', data: found.data, is_meshtastic: meshtasticUrls.length > 0 }],
    meshtastic_urls: meshtasticUrls,
    total_qr_codes: 1,
    meshtastic_count: meshtasticUrls.length,
  };

  result.decoded_results = meshtasticUrls.map((url) => ({
    url,
    decoded: handleDecode({ url }),
  }));
  return result;
}

// Route table matching app.py, so the page's own fetch calls keep working.
const ROUTES = {
  '/encode': (init) => handleEncode(JSON.parse(init.body)),
  '/encode_nodeinfo': (init) => handleEncodeNodeinfo(JSON.parse(init.body)),
  '/decode': (init) => handleDecode(JSON.parse(init.body)),
  '/upload_qr': (init) => handleUploadQr(init.body),
  '/lora_enums': () => ({ success: true, modem_preset: ENUMS.modem_preset, region: ENUMS.region }),
  '/nodeinfo_enums': () => ({ success: true, hw_model: ENUMS.hw_model, role: ENUMS.role }),
  '/health': () => ({ status: 'ok', service: 'meshtastic-decoder' }),
};

const originalFetch = window.fetch ? window.fetch.bind(window) : null;

window.fetch = async function (resource, init = {}) {
  const path = typeof resource === 'string' ? resource.split('?')[0] : resource.url;
  const handler = ROUTES[path];
  if (!handler) {
    if (originalFetch) return originalFetch(resource, init);
    throw new Error(`No route for ${path}`);
  }

  let payload;
  try {
    payload = await handler(init);
  } catch (e) {
    payload = { success: false, error: e.message };
  }

  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
};
