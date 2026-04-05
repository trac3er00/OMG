import { expect, test } from "bun:test";
import { NAME, VERSION } from "./index";

test("version stub", () => {
  expect(NAME).toBe("OMG");
  expect(VERSION).toBe("2.3.0");
});
