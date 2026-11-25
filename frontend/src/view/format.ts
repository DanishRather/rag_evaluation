export function formatValue(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "—";
  }
  if (Math.abs(value) <= 1) {
    return `${Math.round(value * 1000) / 10}%`;
  }
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

export function formatDuration(milliseconds: number | null | undefined): string {
  if (milliseconds === null || milliseconds === undefined || Number.isNaN(milliseconds)) {
    return "—";
  }
  if (Math.abs(milliseconds) < 1000) {
    return `${Math.round(milliseconds)} ms`;
  }
  return `${(milliseconds / 1000).toFixed(1)} s`;
}

export function formatCount(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  return Math.round(value).toLocaleString();
}

export function tokens(text: string): string[] {
  return text
    .toLocaleLowerCase()
    .split(/\s+/)
    .map((token) => token.replace(/^\W+|\W+$/gu, ""))
    .filter(Boolean);
}
