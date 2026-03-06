type ArtifactFinding = {
  severity?: string;
};

type ArtifactInput = {
  id?: string;
  signer?: string | null;
  checksum?: string | null;
  permissions?: string[];
  static_scan?: ArtifactFinding[];
  risk_level?: string;
};

function normalize(artifact: ArtifactInput) {
  return {
    id: String(artifact.id || "unknown"),
    signer: artifact.signer || null,
    checksum: artifact.checksum || null,
    permissions: Array.isArray(artifact.permissions) ? artifact.permissions.map(String) : [],
    static_scan: Array.isArray(artifact.static_scan) ? artifact.static_scan : [],
    risk_level: String(artifact.risk_level || "low").toLowerCase()
  };
}

export function verifyArtifact(artifact: ArtifactInput, mode = "warn_and_run") {
  const normalized = normalize(artifact);
  const controls: string[] = [];
  const reasons: string[] = [];

  if (normalized.static_scan.some((finding) => String(finding?.severity || "").toLowerCase() === "critical")) {
    return {
      action: "deny",
      risk_level: "critical",
      reason: "critical static scan finding",
      controls: ["block-execution"],
      trusted: false
    };
  }

  const permissionBlob = normalized.permissions.join(" ").toLowerCase();
  if (["sudo", "rm -rf", "--privileged", "curl |", "wget |"].some((token) => permissionBlob.includes(token))) {
    return {
      action: "deny",
      risk_level: "critical",
      reason: "critical permission profile",
      controls: ["block-execution"],
      trusted: false
    };
  }

  if (!normalized.signer || !normalized.checksum) {
    reasons.push("missing signer/checksum");
    controls.push("isolate-network", "read-only-fs", "manual-approval");
    if (mode === "warn_and_run") {
      return {
        action: "ask",
        risk_level: "high",
        reason: reasons.join("; "),
        controls,
        trusted: false
      };
    }
    return {
      action: "deny",
      risk_level: "high",
      reason: reasons.join("; "),
      controls: ["block-execution"],
      trusted: false
    };
  }

  if (normalized.static_scan.some((finding) => String(finding?.severity || "").toLowerCase() === "high")) {
    return {
      action: "ask",
      risk_level: "high",
      reason: "high severity findings present",
      controls: ["manual-approval"],
      trusted: false
    };
  }

  return {
    action: "allow",
    risk_level: ["low", "med", "high", "critical"].includes(normalized.risk_level) ? normalized.risk_level : "low",
    reason: "artifact verified",
    controls: [],
    trusted: true
  };
}
