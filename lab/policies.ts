type ValidationResult = {
  ok: boolean;
  reason: string;
};

const ALLOWED_LICENSES = new Set(["apache-2.0", "mit", "bsd-3-clause", "cc-by-4.0"]);
const BLOCKED_SOURCE_TOKENS = ["unknown", "leaked", "stolen", "unauthorized", "pirated"];

function fail(reason: string): ValidationResult {
  return { ok: false, reason };
}

function pass(): ValidationResult {
  return { ok: true, reason: "ok" };
}

export function validateDatasetSource(dataset: Record<string, unknown>): ValidationResult {
  const license = String(dataset.license || "").toLowerCase();
  const source = String(dataset.source || "").toLowerCase();

  if (!license) {
    return fail("dataset license missing");
  }
  if (!ALLOWED_LICENSES.has(license)) {
    return fail(`dataset license not allowed: ${license}`);
  }
  if (BLOCKED_SOURCE_TOKENS.some((token) => source.includes(token))) {
    return fail("dataset source violates policy");
  }
  return pass();
}

export function validateModelSource(model: Record<string, unknown>): ValidationResult {
  const source = String(model.source || "").toLowerCase();
  const allowDistill = Boolean(model.allow_distill);

  if (BLOCKED_SOURCE_TOKENS.some((token) => source.includes(token))) {
    return fail("model source violates policy");
  }
  if (!allowDistill) {
    return fail("model source disallows distillation");
  }
  return pass();
}

export function validateJobRequest(job: Record<string, unknown>): ValidationResult {
  const dataset = job.dataset;
  const baseModel = job.base_model;

  if (!dataset || typeof dataset !== "object" || Array.isArray(dataset)) {
    return fail("dataset block missing");
  }
  if (!baseModel || typeof baseModel !== "object" || Array.isArray(baseModel)) {
    return fail("base_model block missing");
  }

  const datasetResult = validateDatasetSource(dataset as Record<string, unknown>);
  if (!datasetResult.ok) {
    return datasetResult;
  }

  const modelResult = validateModelSource(baseModel as Record<string, unknown>);
  if (!modelResult.ok) {
    return modelResult;
  }

  return pass();
}
