import chalk from 'chalk';

/**
 * Warn if running on native Windows (win32), where tmux is not available.
 * Called at CLI startup from src/cli/index.ts.
 */
export function warnIfWin32(): void {
  if (process.platform === 'win32') {
    console.warn(chalk.yellow.bold('\n⚠  WARNING: Native Windows (win32) detected'));
    console.warn(chalk.yellow('   OMC requires tmux, which is not available on native Windows.'));
    console.warn(chalk.yellow('   Native Windows support is experimental and may have limited functionality.'));
    console.warn(chalk.yellow('   WSL2 is strongly recommended: https://learn.microsoft.com/en-us/windows/wsl/install'));
    console.warn('');
  }
}
