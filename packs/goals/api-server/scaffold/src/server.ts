import express from "express";
import cors from "cors";
import dotenv from "dotenv";
import itemsRouter from "./routes/index";

dotenv.config();

const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(express.json());

app.get("/health", (_req, res) => {
  res.json({
    status: "ok",
    timestamp: new Date().toISOString(),
    service: "{{ project_name }}",
  });
});

app.use("/api/items", itemsRouter);

app.get("/", (_req, res) => {
  res.json({
    name: "{{ project_name }}",
    version: "1.0.0",
    endpoints: {
      health: "/health",
      items: "/api/items",
    },
  });
});

app.use((_req, res) => {
  res.status(404).json({ error: "Not Found" });
});

app.listen(PORT, () => {
  console.log(`API Server running on http://localhost:${PORT}`);
});
