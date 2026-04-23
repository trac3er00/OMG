import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import type { WowResult } from "../output.js";

const APP_JSX = `import React from 'react';
import DataTable from './components/DataTable';
const sampleData = [{ id: 1, name: 'Item 1', status: 'active' }, { id: 2, name: 'Item 2', status: 'inactive' }];
export default function App() {
  return <div className="admin"><h1>Admin Dashboard</h1><DataTable data={sampleData} /></div>;
}`;

const DATA_TABLE_JSX = `import React from 'react';
export default function DataTable({ data }) {
  return <table><thead><tr><th>ID</th><th>Name</th><th>Status</th></tr></thead>
  <tbody>{data.map(row => <tr key={row.id}><td>{row.id}</td><td>{row.name}</td><td>{row.status}</td></tr>)}</tbody></table>;
}`;

export async function runAdminFlow(
  _goal: string,
  outputDir: string,
): Promise<WowResult> {
  const startTime = Date.now();
  try {
    await mkdir(join(outputDir, "src/components"), { recursive: true });
    const pkg = {
      name: "admin-dashboard",
      version: "1.0.0",
      scripts: { start: "react-scripts start", build: "react-scripts build" },
      dependencies: {
        react: "^18.0.0",
        "react-dom": "^18.0.0",
        "react-scripts": "5.0.1",
      },
    };
    await writeFile(
      join(outputDir, "package.json"),
      JSON.stringify(pkg, null, 2),
    );
    await writeFile(join(outputDir, "src/App.jsx"), APP_JSX);
    await writeFile(
      join(outputDir, "src/components/DataTable.jsx"),
      DATA_TABLE_JSX,
    );
    await writeFile(
      join(outputDir, "src/index.jsx"),
      `import React from 'react'; import ReactDOM from 'react-dom/client'; import App from './App'; ReactDOM.createRoot(document.getElementById('root')).render(<App />);`,
    );
    return {
      flowName: "admin",
      success: true,
      proofScore: 70,
      buildTime: Date.now() - startTime,
    };
  } catch (error) {
    return {
      flowName: "admin",
      success: false,
      error: String(error),
      buildTime: Date.now() - startTime,
    };
  }
}
