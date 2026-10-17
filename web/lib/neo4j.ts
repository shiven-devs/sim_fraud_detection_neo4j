import neo4j, { Driver, QueryResult } from "neo4j-driver";
import { requireEnv } from "./env";

let driver: Driver | undefined;

/**
 * One shared driver for every API route.
 * Phase 2's read-only chat user can add a second driver beside this one.
 */
export function getDriver(): Driver {
  if (!driver) {
    driver = neo4j.driver(requireEnv("NEO4J_URI"), neo4j.auth.basic(requireEnv("NEO4J_USER"), requireEnv("NEO4J_PASSWORD")), {
      disableLosslessIntegers: true,
    });
  }
  return driver;
}

export async function run(
  cypher: string,
  params: Record<string, unknown> = {},
  mode: "READ" | "WRITE" = "READ"
): Promise<QueryResult> {
  const session = getDriver().session({
    defaultAccessMode: mode === "READ" ? neo4j.session.READ : neo4j.session.WRITE,
  });
  try {
    return await session.run(cypher, params);
  } finally {
    await session.close();
  }
}

export function dbErrorMessage(error: unknown): string {
  const message = error instanceof Error ? error.message : "Unexpected database error";
  if (/ECONNREFUSED|ServiceUnavailable|Failed to connect|authentication|unauthorized/i.test(message)) {
    return "Cannot reach Neo4j. Start the database and check NEO4J_URI, NEO4J_USER and NEO4J_PASSWORD in .env.";
  }
  return message;
}

export function text(value: unknown): string {
  if (value == null) return "";
  return typeof value === "string" ? value : String(value);
}
