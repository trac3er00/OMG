import { existsSync, mkdirSync } from "node:fs";
import { join, resolve } from "node:path";

export interface StateLayout {
  readonly verificationController: string;
  readonly releaseRunCoordinator: string;
  readonly interactionJournal: string;
  readonly contextEngine: string;
  readonly defenseState: string;
  readonly sessionHealth: string;
  readonly councilVerdicts: string;
  readonly rollbackManifest: string;
  readonly releaseRun: string;
  readonly ledger: string;
  readonly jobs: string;
  readonly budgetEnvelopes: string;
  readonly workerHeartbeats: string;
  readonly execKernel: string;
  readonly memory: string;
}

export class StateResolver {
  readonly projectDir: string;
  readonly stateDir: string;

  constructor(projectDir?: string) {
    this.projectDir = resolve(projectDir ?? process.cwd());
    this.stateDir = join(this.projectDir, ".omg", "state");
  }

  resolve(relativePath: string): string {
    return join(this.stateDir, relativePath);
  }

  ensure(relativePath: string): string {
    const fullPath = this.resolve(relativePath);
    if (!existsSync(fullPath)) {
      mkdirSync(fullPath, { recursive: true });
    }
    return fullPath;
  }

  layout(): StateLayout {
    return {
      verificationController: this.resolve("verification_controller"),
      releaseRunCoordinator: this.resolve("release_run_coordinator"),
      interactionJournal: this.resolve("interaction_journal"),
      contextEngine: this.resolve("context_engine_packet.json"),
      defenseState: this.resolve("defense_state.json"),
      sessionHealth: this.resolve("session_health.json"),
      councilVerdicts: this.resolve("council_verdicts"),
      rollbackManifest: this.resolve("rollback_manifest.json"),
      releaseRun: this.resolve("release_run"),
      ledger: this.resolve("ledger"),
      jobs: this.resolve("jobs"),
      budgetEnvelopes: this.resolve("budget-envelopes"),
      workerHeartbeats: this.resolve("worker-heartbeats"),
      execKernel: this.resolve("exec-kernel"),
      memory: this.resolve("memory.sqlite3"),
    };
  }
}
