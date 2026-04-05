import { EventEmitter } from "node:events";
import { randomUUID } from "node:crypto";

export interface CanaryTokenRecord {
  readonly tokenId: string;
  readonly tokenValue: string;
  readonly createdAt: string;
  readonly context: string;
}

export interface CanaryAlert {
  readonly tokenId: string;
  readonly triggeredAt: string;
  readonly message: string;
}

export class CanaryToken extends EventEmitter {
  private readonly records = new Map<string, CanaryTokenRecord>();

  create(context: string): CanaryTokenRecord {
    const tokenId = randomUUID();
    const tokenValue = `OMG_CANARY::${tokenId}`;
    const record: CanaryTokenRecord = {
      tokenId,
      tokenValue,
      createdAt: new Date().toISOString(),
      context,
    };

    this.records.set(tokenId, record);
    return record;
  }

  placeInState(stateContent: string, tokenId: string): string {
    const record = this.records.get(tokenId);
    if (!record) {
      throw new Error(`Unknown canary token id: ${tokenId}`);
    }

    const suffix = stateContent.endsWith("\n") ? "" : "\n";
    return `${stateContent}${suffix}# canary:${record.tokenValue}\n`;
  }

  trigger(tokenId: string): CanaryAlert {
    const record = this.records.get(tokenId);
    if (!record) {
      throw new Error(`Unknown canary token id: ${tokenId}`);
    }

    const alert: CanaryAlert = {
      tokenId,
      triggeredAt: new Date().toISOString(),
      message: `Canary token accessed for context: ${record.context}`,
    };

    this.emit("alert", alert);
    return alert;
  }

  has(tokenId: string): boolean {
    return this.records.has(tokenId);
  }
}
