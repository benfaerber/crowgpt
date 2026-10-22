import type { AnalysisCache, CachedAnalysis } from "./AnalysisCache";

/** In-memory cache, for host-side tests. Same contract as the SQLite one. */
export class MemoryAnalysisCache implements AnalysisCache {
  private readonly rows = new Map<string, CachedAnalysis>();

  async get(captureUuid: string): Promise<CachedAnalysis | undefined> {
    const found = this.rows.get(captureUuid);
    return found ? { ...found } : undefined;
  }

  async save(
    captureUuid: string,
    analysis: Omit<CachedAnalysis, "fetchedAt">,
  ): Promise<void> {
    this.rows.set(captureUuid, { ...analysis, fetchedAt: new Date().toISOString() });
  }

  async forget(captureUuid: string): Promise<void> {
    this.rows.delete(captureUuid);
  }
}
