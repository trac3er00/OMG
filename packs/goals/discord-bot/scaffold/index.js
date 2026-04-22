const {
  Client,
  GatewayIntentBits,
  REST,
  Routes,
  SlashCommandBuilder,
} = require("discord.js");
require("dotenv").config();

const client = new Client({
  intents: [GatewayIntentBits.Guilds],
});

const commands = [
  new SlashCommandBuilder()
    .setName("ping")
    .setDescription("Replies with Pong and latency info"),
  new SlashCommandBuilder()
    .setName("hello")
    .setDescription("Get a friendly greeting"),
].map((command) => command.toJSON());

client.once("ready", async () => {
  console.log(`Logged in as ${client.user.tag}!`);

  const rest = new REST({ version: "10" }).setToken(process.env.DISCORD_TOKEN);

  try {
    console.log("Registering slash commands...");
    await rest.put(Routes.applicationCommands(client.user.id), {
      body: commands,
    });
    console.log("Slash commands registered successfully!");
  } catch (error) {
    console.error("Error registering commands:", error);
  }
});

client.on("interactionCreate", async (interaction) => {
  if (!interaction.isChatInputCommand()) return;

  const { commandName } = interaction;

  if (commandName === "ping") {
    const latency = Date.now() - interaction.createdTimestamp;
    await interaction.reply(
      `Pong! Latency: ${latency}ms | API: ${Math.round(client.ws.ping)}ms`,
    );
  } else if (commandName === "hello") {
    await interaction.reply(
      `Hello, ${interaction.user.username}! Welcome to {{ project_name }}!`,
    );
  }
});

client.login(process.env.DISCORD_TOKEN);
