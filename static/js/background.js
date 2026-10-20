// Back and middle planes: a domain-warped simplex aurora rendered at low
// resolution, and uneven blur zones placed at random on each load.

const PALETTE = {
  ink: '#07061a',
  violet: '#7c3aed',
  magenta: '#db2777',
  cyan: '#06b6d4',
  mint: '#2dd4bf',
};

const RENDER_SCALE = 0.35;
const FRAME_INTERVAL = 1000 / 24;
const TIME_SPEED = 0.014;

const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

function hexToRgb(hex) {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}

// Rotates a colour around the grey axis, so the whole palette shifts hue together.
function rotateHue([r, g, b], degrees) {
  const a = (degrees * Math.PI) / 180;
  const c = Math.cos(a);
  const s = Math.sin(a);
  const k = (1 - c) / 3;
  const q = Math.sqrt(1 / 3) * s;
  return [
    r * (c + k) + g * (k - q) + b * (k + q),
    r * (k + q) + g * (c + k) + b * (k - q),
    r * (k - q) + g * (k + q) + b * (c + k),
  ].map(v => Math.min(1, Math.max(0, v)));
}

function buildPalette() {
  const shift = (Math.random() - 0.5) * 50;
  const out = {};
  for (const [name, hex] of Object.entries(PALETTE)) {
    out[name] = name === 'ink' ? hexToRgb(hex) : rotateHue(hexToRgb(hex), shift);
  }
  return out;
}

const VERTEX = `
attribute vec2 a_pos;
void main() { gl_Position = vec4(a_pos, 0.0, 1.0); }
`;

const FRAGMENT = `
precision highp float;
uniform vec2 u_res;
uniform float u_time;
uniform vec2 u_seed;
uniform vec3 u_ink;
uniform vec3 u_violet;
uniform vec3 u_magenta;
uniform vec3 u_cyan;
uniform vec3 u_mint;

vec3 permute(vec3 x) { return mod(((x * 34.0) + 1.0) * x, 289.0); }

float snoise(vec2 v) {
  const vec4 C = vec4(0.211324865405187, 0.366025403784439, -0.577350269189626, 0.024390243902439);
  vec2 i = floor(v + dot(v, C.yy));
  vec2 x0 = v - i + dot(i, C.xx);
  vec2 i1 = (x0.x > x0.y) ? vec2(1.0, 0.0) : vec2(0.0, 1.0);
  vec4 x12 = x0.xyxy + C.xxzz;
  x12.xy -= i1;
  i = mod(i, 289.0);
  vec3 p = permute(permute(i.y + vec3(0.0, i1.y, 1.0)) + i.x + vec3(0.0, i1.x, 1.0));
  vec3 m = max(0.5 - vec3(dot(x0, x0), dot(x12.xy, x12.xy), dot(x12.zw, x12.zw)), 0.0);
  m = m * m;
  m = m * m;
  vec3 x = 2.0 * fract(p * C.www) - 1.0;
  vec3 h = abs(x) - 0.5;
  vec3 ox = floor(x + 0.5);
  vec3 a0 = x - ox;
  m *= 1.79284291400159 - 0.85373472095314 * (a0 * a0 + h * h);
  vec3 g;
  g.x = a0.x * x0.x + h.x * x0.y;
  g.yz = a0.yz * x12.xz + h.yz * x12.yw;
  return 130.0 * dot(m, g);
}

float fbm(vec2 p) {
  float v = 0.0;
  float a = 0.5;
  mat2 rot = mat2(1.6, 1.2, -1.2, 1.6);
  for (int i = 0; i < 5; i++) {
    v += a * snoise(p);
    p = rot * p;
    a *= 0.5;
  }
  return v;
}

void main() {
  vec2 p = (gl_FragCoord.xy - 0.5 * u_res) / min(u_res.x, u_res.y);
  vec2 uv = gl_FragCoord.xy / u_res;
  float t = u_time;

  // Low frequency, stretched horizontally: wide curtains of colour.
  vec2 s = vec2(p.x * 0.55, p.y * 0.8) + u_seed;

  vec2 q = vec2(fbm(s + vec2(0.0, t * 0.5)), fbm(s + vec2(5.2, 1.3) - t * 0.35));
  vec2 r = vec2(fbm(s + 1.4 * q + vec2(1.7, 9.2) + t * 0.25), fbm(s + 1.4 * q + vec2(8.3, 2.8) - t * 0.2));
  float f = fbm(s + 1.6 * r);

  vec3 col = u_ink;
  col = mix(col, u_violet, smoothstep(-0.35, 0.55, f) * 0.9);
  col = mix(col, u_magenta, smoothstep(0.05, 0.75, q.x + r.y * 0.4) * 0.75);
  col = mix(col, u_cyan, smoothstep(0.0, 0.6, r.x - q.y * 0.3) * 0.8);
  col = mix(col, u_mint, smoothstep(0.35, 0.85, f + r.x * 0.4) * 0.45);

  // Fine filaments on top: they stay sharp where the middle plane is clear
  // and melt into glow where it is blurred.
  float threads = fbm(p * 3.2 + r * 2.0 + u_seed.yx - t * 0.15);
  float glow = 0.85 + 0.35 * threads;

  // Keep it a night sky: bright curtains, dark gaps, darker toward the bottom.
  float curtains = smoothstep(-0.45, 0.6, f);
  col *= (0.28 + 0.9 * curtains) * glow;
  col *= mix(0.4, 1.1, smoothstep(0.0, 0.9, uv.y));
  col = mix(u_ink, col, 0.94);

  gl_FragColor = vec4(col, 1.0);
}
`;

function compile(gl, type, source) {
  const shader = gl.createShader(type);
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    console.warn('Background shader failed:', gl.getShaderInfoLog(shader));
    return null;
  }
  return shader;
}

function startWebGL(canvas, palette) {
  const gl = canvas.getContext('webgl', { antialias: false, alpha: false, powerPreference: 'low-power' });
  if (!gl) return false;

  const vs = compile(gl, gl.VERTEX_SHADER, VERTEX);
  const fs = compile(gl, gl.FRAGMENT_SHADER, FRAGMENT);
  if (!vs || !fs) return false;

  const program = gl.createProgram();
  gl.attachShader(program, vs);
  gl.attachShader(program, fs);
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) return false;
  gl.useProgram(program);

  const buffer = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  const aPos = gl.getAttribLocation(program, 'a_pos');
  gl.enableVertexAttribArray(aPos);
  gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);

  const u = name => gl.getUniformLocation(program, name);
  const uRes = u('u_res');
  const uTime = u('u_time');
  gl.uniform2f(u('u_seed'), Math.random() * 100, Math.random() * 100);
  for (const name of Object.keys(palette)) {
    gl.uniform3fv(u(`u_${name}`), palette[name]);
  }

  let time = Math.random() * 50;
  let last = 0;
  let rafId = null;

  function resize() {
    const w = Math.max(1, Math.round(window.innerWidth * RENDER_SCALE));
    const h = Math.max(1, Math.round(window.innerHeight * RENDER_SCALE));
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
      gl.viewport(0, 0, w, h);
    }
    gl.uniform2f(uRes, w, h);
  }

  function draw() {
    gl.uniform1f(uTime, time);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }

  function frame(now) {
    rafId = requestAnimationFrame(frame);
    if (now - last < FRAME_INTERVAL) return;
    const dt = last ? Math.min(now - last, 100) : FRAME_INTERVAL;
    last = now;
    time += (dt / 1000) * TIME_SPEED * 10;
    draw();
  }

  function play() {
    if (rafId || reducedMotion.matches || document.hidden) return;
    last = 0;
    rafId = requestAnimationFrame(frame);
  }

  function pause() {
    if (rafId) cancelAnimationFrame(rafId);
    rafId = null;
  }

  resize();
  draw();
  play();

  window.addEventListener('resize', () => {
    resize();
    draw();
  });
  document.addEventListener('visibilitychange', () => (document.hidden ? pause() : play()));
  reducedMotion.addEventListener?.('change', () => (reducedMotion.matches ? pause() : play()));

  return true;
}

// Canvas2D fallback: one still frame of value noise in the same palette.
function startCanvas2D(canvas, palette) {
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  const w = 160;
  const h = Math.max(1, Math.round((160 * window.innerHeight) / window.innerWidth));
  canvas.width = w;
  canvas.height = h;

  const grid = 9;
  const values = Array.from({ length: (grid + 1) * (grid + 1) }, () => Math.random());
  const smooth = x => x * x * (3 - 2 * x);
  const sample = (x, y) => {
    const xi = Math.floor(x);
    const yi = Math.floor(y);
    const xf = smooth(x - xi);
    const yf = smooth(y - yi);
    const at = (i, j) => values[((j % grid) * (grid + 1) + (i % grid))];
    const top = at(xi, yi) * (1 - xf) + at(xi + 1, yi) * xf;
    const bottom = at(xi, yi + 1) * (1 - xf) + at(xi + 1, yi + 1) * xf;
    return top * (1 - yf) + bottom * yf;
  };

  const img = ctx.createImageData(w, h);
  const mix = (a, b, k) => a.map((v, i) => v + (b[i] - v) * k);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const nx = (x / w) * 4;
      const ny = (y / h) * 2;
      const f = sample(nx, ny) * 0.6 + sample(nx * 2.1, ny * 2.1) * 0.3 + sample(nx * 4.3, ny * 4.3) * 0.1;
      const g = sample(nx + 3.7, ny + 1.9);
      let col = mix(palette.ink, palette.violet, f * 0.9);
      col = mix(col, palette.magenta, Math.max(0, g - 0.5) * 1.2);
      col = mix(col, palette.cyan, Math.max(0, f - 0.6) * 1.4);
      const fade = 0.35 + 0.65 * (1 - y / h);
      const i = (y * w + x) * 4;
      img.data[i] = col[0] * 255 * fade;
      img.data[i + 1] = col[1] * 255 * fade;
      img.data[i + 2] = col[2] * 255 * fade;
      img.data[i + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
}

function placeBlurZones() {
  const field = document.querySelector('.blur-field');
  if (!field) return;

  const rand = (min, max) => min + Math.random() * (max - min);
  for (let depth = 1; depth <= 4; depth++) {
    const zone = document.createElement('div');
    zone.className = 'blur-zone';
    zone.dataset.depth = String(depth);
    zone.style.setProperty('--x', `${rand(10, 90).toFixed(1)}%`);
    zone.style.setProperty('--y', `${rand(10, 90).toFixed(1)}%`);
    zone.style.setProperty('--rx', `${rand(28, 60).toFixed(1)}%`);
    zone.style.setProperty('--ry', `${rand(24, 52).toFixed(1)}%`);
    zone.style.setProperty('--dx', `${rand(-6, 6).toFixed(1)}%`);
    zone.style.setProperty('--dy', `${rand(-5, 5).toFixed(1)}%`);
    zone.style.setProperty('--dur', `${rand(60, 120).toFixed(0)}s`);
    zone.style.setProperty('--delay', `${-rand(0, 60).toFixed(0)}s`);
    field.appendChild(zone);
  }
}

export function initBackground() {
  const canvas = document.getElementById('bg-noise');
  if (!canvas) return;

  const palette = buildPalette();
  if (!startWebGL(canvas, palette)) {
    startCanvas2D(canvas, palette);
  }
  placeBlurZones();
  requestAnimationFrame(() => canvas.classList.add('is-ready'));
}
