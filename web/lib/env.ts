import fs from "fs";
import path from "path";

let loaded = false;

/** Repository root, whether the process was started from /web or the root. */
export function repoRoot(): string {
  const cwd = process.cwd();
  if (fs.existsSync(path.join(cwd, "docker-compose.yml"))) return cwd;
  if (fs.existsSync(path.join(cwd, "..", "docker-compose.yml"))) return path.join(cwd, "..");
  return cwd;
}

/** Load the root .env without overriding variables the shell or Next already set. */
export function loadEnv(): void {
  if (loaded) return;
  loaded = true;
  const file = path.join(repoRoot(), ".env");
  if (!fs.existsSync(file)) return;
  for (const line of fs.readFileSync(file, "utf8").split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq === -1) continue;
    const key = trimmed.slice(0, eq).trim();
    let value = trimmed.slice(eq + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    if (process.env[key] === undefined) process.env[key] = value;
  }
}

export function requireEnv(name: string): string {
  loadEnv();
  const value = process.env[name];
  if (!value) throw new Error(`Missing ${name}. Copy .env.example to .env in the repository root.`);
  return value;
}

export function optionalEnv(name: string, fallback: string): string {
  loadEnv();
  return process.env[name] || fallback;
}
