import { optionalEnv } from "./env";

/** Base URL of the Python face service. Kept separate from Neo4j so either side can move. */
export function faceServiceUrl(): string {
  return optionalEnv("FACE_SERVICE_URL", "http://localhost:8000").replace(/\/$/, "");
}
