import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import type { WowResult } from "../output.js";

const PACKAGE_JSON = JSON.stringify(
  {
    name: "saas-starter",
    version: "1.0.0",
    private: true,
    scripts: {
      start: "node src/index.js",
      dev: "node --watch src/index.js",
    },
    dependencies: {
      express: "^4.18.0",
    },
    wow: {
      healthEndpoint: "/health",
      authStub: "src/routes/auth.js",
      dbConfig: "src/config/db.js",
    },
  },
  null,
  2,
);

const INDEX_JS = `const express = require('express');
const healthRoute = require('./routes/health');
const authRoute = require('./routes/auth');
const db = require('./config/db');

const app = express();

app.use(express.json());
app.get('/health', healthRoute);
app.post('/auth/login', authRoute);
app.locals.db = db;

const PORT = process.env.PORT || 3000;

if (require.main === module) {
  app.listen(PORT, () => console.log('Server running on port ' + PORT));
}

module.exports = app;`;

const HEALTH_ROUTE_JS = `module.exports = (_req, res) => {
  res.json({ status: 'ok' });
};`;

const AUTH_ROUTE_JS = `module.exports = (req, res) => {
  const email = req.body?.email || 'demo@example.com';

  res.status(501).json({
    message: 'Authentication stub not implemented',
    email,
  });
};`;

const DB_CONFIG_JS = `module.exports = {
  client: 'postgres',
  connectionString: process.env.DATABASE_URL || '',
  pool: {
    min: 0,
    max: 10,
  },
};`;

const ENV_EXAMPLE = `PORT=3000
DATABASE_URL=
JWT_SECRET=
`;

export async function runSaasFlow(
  _goal: string,
  outputDir: string,
): Promise<WowResult> {
  const startTime = Date.now();

  try {
    await mkdir(join(outputDir, "src/routes"), { recursive: true });
    await mkdir(join(outputDir, "src/config"), { recursive: true });

    await Promise.all([
      writeFile(join(outputDir, "package.json"), PACKAGE_JSON),
      writeFile(join(outputDir, "src/index.js"), INDEX_JS),
      writeFile(join(outputDir, "src/routes/health.js"), HEALTH_ROUTE_JS),
      writeFile(join(outputDir, "src/routes/auth.js"), AUTH_ROUTE_JS),
      writeFile(join(outputDir, "src/config/db.js"), DB_CONFIG_JS),
      writeFile(join(outputDir, ".env.example"), ENV_EXAMPLE),
    ]);

    return {
      flowName: "saas",
      success: true,
      proofScore: 65,
      buildTime: Date.now() - startTime,
    };
  } catch (error) {
    return {
      flowName: "saas",
      success: false,
      error: error instanceof Error ? error.message : String(error),
      buildTime: Date.now() - startTime,
    };
  }
}
