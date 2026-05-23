export function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

export function wrap360(value) {
  const twoPi = Math.PI * 2;
  while (value < 0) value += twoPi;
  while (value >= twoPi) value -= twoPi;
  return value;
}

export function normalizeKey(value) {
  return String(value ?? "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "_");
}

export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

export function colorToCss(color, alpha = 1) {
  const r = Math.round(color.r * 255);
  const g = Math.round(color.g * 255);
  const b = Math.round(color.b * 255);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

export function projectVector(vector, camera) {
  const projected = vector.clone().project(camera);
  return {
    x: (projected.x * 0.5 + 0.5) * innerWidth,
    y: (-0.5 * projected.y + 0.5) * innerHeight,
    z: projected.z
  };
}
