/**
 * Seam for a later language-model helper.
 * Phase 1 does not call a model and does not ship an SDK.
 * Add the client here when Phase 2 starts, and keep routes calling this module
 * instead of talking to a provider directly.
 */
export type LlmTextRequest = {
  system: string;
  prompt: string;
};

export async function completeText(_request: LlmTextRequest): Promise<string> {
  throw new Error("The language-model helper is not enabled in Phase 1.");
}
