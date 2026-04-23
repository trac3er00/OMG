import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import type { WowResult } from "../output.js";

type BotPlatform = "discord" | "telegram";

function detectPlatform(goal: string): BotPlatform {
  return /telegram/i.test(goal) ? "telegram" : "discord";
}

const DISCORD_INDEX = `const { Client, GatewayIntentBits } = require('discord.js');
const client = new Client({ intents: [GatewayIntentBits.Guilds] });
client.once('ready', () => console.log('Bot ready!'));
client.on('messageCreate', msg => { if (msg.content === '!ping') msg.reply('Pong!'); });
client.login(process.env.BOT_TOKEN);`;

const TELEGRAM_INDEX = `const TelegramBot = require('node-telegram-bot-api');
const bot = new TelegramBot(process.env.BOT_TOKEN, { polling: true });
bot.on('message', msg => { if (msg.text === '/start') bot.sendMessage(msg.chat.id, 'Hello!'); });`;

export async function runBotFlow(
  goal: string,
  outputDir: string,
): Promise<WowResult> {
  const startTime = Date.now();
  const platform = detectPlatform(goal);
  try {
    await mkdir(outputDir, { recursive: true });
    const pkg = {
      name: `${platform}-bot`,
      version: "1.0.0",
      scripts: { start: "node index.js" },
      dependencies:
        platform === "discord"
          ? { "discord.js": "^14.0.0" }
          : { "node-telegram-bot-api": "^0.64.0" },
    };
    await writeFile(
      join(outputDir, "package.json"),
      JSON.stringify(pkg, null, 2),
    );
    await writeFile(
      join(outputDir, "index.js"),
      platform === "discord" ? DISCORD_INDEX : TELEGRAM_INDEX,
    );
    await writeFile(
      join(outputDir, ".env.example"),
      "BOT_TOKEN=your_token_here\n",
    );
    return {
      flowName: "bot",
      success: true,
      proofScore: 65,
      buildTime: Date.now() - startTime,
    };
  } catch (error) {
    return {
      flowName: "bot",
      success: false,
      error: String(error),
      buildTime: Date.now() - startTime,
    };
  }
}
