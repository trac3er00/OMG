#!/usr/bin/env node

const { program } = require("commander");
const chalk = require("chalk");

program
  .name("{{ project_name }}")
  .description("A powerful command-line tool")
  .version("1.0.0");

program
  .command("greet <name>")
  .description("Greet someone by name")
  .option("-l, --loud", "Use loud greeting")
  .action((name, options) => {
    const greeting = `Hello, ${name}!`;
    if (options.loud) {
      console.log(chalk.bold.green(greeting.toUpperCase()));
    } else {
      console.log(chalk.green(greeting));
    }
  });

program
  .command("info")
  .description("Display system information")
  .action(() => {
    console.log(chalk.cyan("System Information:"));
    console.log(chalk.white(`  Platform: ${process.platform}`));
    console.log(chalk.white(`  Node Version: ${process.version}`));
    console.log(chalk.white(`  Working Directory: ${process.cwd()}`));
  });

program
  .command("echo <message>")
  .description("Echo a message back")
  .option("-r, --repeat <count>", "Repeat the message", "1")
  .action((message, options) => {
    const count = parseInt(options.repeat, 10);
    for (let i = 0; i < count; i++) {
      console.log(chalk.yellow(message));
    }
  });

program.parse();
