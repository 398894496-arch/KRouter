export interface Hit { page: string; tier: string; status: string; how: string }

export declare class Answer {
  readonly text: string;
  readonly isError: boolean;
  readonly fields: Record<string, string>;
  readonly hits: Hit[];
  /** The page the answer comes from; "" when the memory does not know. */
  readonly page: string;
  /** The one line that answers it; "" when the memory does not know. */
  readonly how: string;
  /** true when the vault has nothing on it (`recall: none`). */
  readonly refused: boolean;
  readonly confidence: string;
  toString(): string;
}

export type Route = "search" | "preference" | "correction" | "memory" | "project" | "suggest";

export declare class KRouter {
  static local(options?: { vault?: string; python?: string; server?: string }): KRouter;
  static remote(url: string, options?: { token?: string }): KRouter;
  ask(query: string, options?: { route?: Route }): Promise<Answer>;
  status(): Promise<Answer>;
  note(text: string, options?: { kind?: "note" | "decision" | "correction" }): Promise<string>;
  tools(): Promise<string[]>;
  close(): Promise<void>;
}
