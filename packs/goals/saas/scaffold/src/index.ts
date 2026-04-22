import express from "express";
import dotenv from "dotenv";
import healthRouter from "./routes/health";

dotenv.config();

const app = express();
const PORT = process.env.PORT || 3000;

app.use(express.json());
app.use("/health", healthRouter);

app.get("/", (_req, res) => {
  res.json({ message: "Welcome to {{ project_name }}" });
});

app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});
