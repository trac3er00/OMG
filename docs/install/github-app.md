# GitHub App Setup

The PR Reviewer Bot uses a GitHub App to securely interact with your repositories. This method is preferred over personal access tokens as it provides fine-grained permissions and short-lived installation tokens.

## Setup

### 1. Create the GitHub App
1. Navigate to **Settings** -> **Developer settings** -> **GitHub Apps** -> **New GitHub App**.
2. **GitHub App name**: Choose a unique name (e.g., `OMG-Reviewer-Bot`).
3. **Homepage URL**: Use your repository URL.
4. **Webhook**: Uncheck **Active** unless you are using a custom webhook listener.
5. **Permissions**: Grant the following minimum repository permissions:
   - **Pull requests**: Read & write (to post reviews and comments)
   - **Checks**: Read & write (to create check runs)
   - **Contents**: Read-only (to analyze code)
6. **Where can this GitHub App be installed?**: Select **Only on this account** or **Any account** based on your needs.
7. Click **Create GitHub App**.

### 2. Generate Private Key and Installation ID
1. After creation, scroll down to the **Private keys** section and click **Generate a private key**. A `.pem` file will download.
2. Note the **App ID** displayed at the top of the app settings page.
3. Navigate to **Install App** in the sidebar and install it on your target repository or organization.
4. After installation, the URL will look like `https://github.com/settings/installations/12345678`. The number at the end is your `GITHUB_INSTALLATION_ID`.

### 3. Configure Environment Variables
The bot requires three configuration variables.

| Variable | Type | Description |
| :--- | :--- | :--- |
| `GITHUB_APP_ID` | Config Variable | The App ID from your GitHub App settings. |
| `GITHUB_APP_PRIVATE_KEY` | Secret | The full content of the downloaded `.pem` file. |
| `GITHUB_INSTALLATION_ID` | Config Variable | The ID from the installation URL. |

#### Local Development
Store the private key in a file and load it:
```bash
export GITHUB_APP_ID="123456"
export GITHUB_INSTALLATION_ID="78901234"
export GITHUB_APP_PRIVATE_KEY="$(cat path/to/your-app.private-key.pem)"
```

#### GitHub Actions
Add the App ID and Installation ID as **Variables** and the Private Key as a **Secret**:
```yaml
env:
  GITHUB_APP_ID: ${{ vars.GITHUB_APP_ID }}
  GITHUB_INSTALLATION_ID: ${{ vars.GITHUB_INSTALLATION_ID }}
  GITHUB_APP_PRIVATE_KEY: ${{ secrets.GITHUB_APP_PRIVATE_KEY }}
```

## Security Hardening

### Secret Management
- **GITHUB_APP_ID**: This is non-sensitive. Store it as a repository or organization configuration variable.
- **GITHUB_APP_PRIVATE_KEY**: This is highly sensitive. Store it as an encrypted secret. Never commit this key to version control.
- **Rotation**: Regularly rotate your private keys in the GitHub App settings and delete old, unused keys.

### Execution Safety
- **Untrusted PRs**: Never expose `GITHUB_APP_PRIVATE_KEY` to `pull_request` event jobs that check out untrusted code. Secrets are unavailable to forks by default, but you must ensure your workflow does not manually bypass this.
- **Workflow Triggers**: Avoid using `pull_request_target` with an explicit checkout of the PR head if you are using app secrets. This combination can allow malicious PRs to exfiltrate your secrets.
- **Token Expiry**: The bot caches installation access tokens in memory for the duration of their 1-hour TTL and regenerates automatically when they expire. Do not persist tokens to disk or share them across processes.

## Verify

Confirm your setup with this checklist:
- [ ] **Token Generation**: Run the bot locally or in a test workflow. It should successfully exchange the JWT for an installation token.
- [ ] **Review Posting**: Create a test PR. The bot should post a review or comment.
- [ ] **Stale Review Dismissal**: Push a new commit to the test PR. The bot should dismiss or update its prior approval.
- [ ] **Permissions**: Verify the bot can only access the repositories it was explicitly installed on.

## Troubleshooting

| Error Code | Cause | Resolution |
| :--- | :--- | :--- |
| `GITHUB_CREDENTIALS_MISSING` | One or more env vars are empty. | Check that `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY`, and `GITHUB_INSTALLATION_ID` are set. |
| `GITHUB_APP_PRIVATE_KEY_INVALID` | The PEM key is malformed or not RSA. | Ensure the secret contains the full `-----BEGIN RSA PRIVATE KEY-----` block and no extra whitespace. |
| `GITHUB_JWT_SIGNING_FAILED` | Cryptography error during signing. | Verify your environment has the required dependencies installed. |
| `GITHUB_TOKEN_REQUEST_FAILED` | Network error or GitHub API downtime. | Check your internet connection and GitHub Status. |
| `GITHUB_TOKEN_REQUEST_REJECTED` | 403/404 error from GitHub. | Verify the `GITHUB_INSTALLATION_ID` is correct and the app is installed on the repo. |
| `GITHUB_TOKEN_RESPONSE_INVALID` | Unexpected response from GitHub. | Check if GitHub API versions have changed or if there is a proxy interference. |
