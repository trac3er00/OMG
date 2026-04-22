import { Router, Request, Response } from "express";

const router = Router();

interface Item {
  id: number;
  name: string;
  description: string;
  createdAt: string;
}

const items: Item[] = [
  {
    id: 1,
    name: "Item One",
    description: "First sample item",
    createdAt: new Date().toISOString(),
  },
  {
    id: 2,
    name: "Item Two",
    description: "Second sample item",
    createdAt: new Date().toISOString(),
  },
  {
    id: 3,
    name: "Item Three",
    description: "Third sample item",
    createdAt: new Date().toISOString(),
  },
];

let nextId = 4;

router.get("/", (_req: Request, res: Response) => {
  res.json(items);
});

router.get("/:id", (req: Request, res: Response) => {
  const item = items.find((i) => i.id === parseInt(req.params.id, 10));
  if (!item) {
    return res.status(404).json({ error: "Item not found" });
  }
  res.json(item);
});

router.post("/", (req: Request, res: Response) => {
  const { name, description } = req.body;
  if (!name) {
    return res.status(400).json({ error: "Name is required" });
  }
  const newItem: Item = {
    id: nextId++,
    name,
    description: description || "",
    createdAt: new Date().toISOString(),
  };
  items.push(newItem);
  res.status(201).json(newItem);
});

router.delete("/:id", (req: Request, res: Response) => {
  const index = items.findIndex((i) => i.id === parseInt(req.params.id, 10));
  if (index === -1) {
    return res.status(404).json({ error: "Item not found" });
  }
  const deleted = items.splice(index, 1);
  res.json(deleted[0]);
});

export default router;
