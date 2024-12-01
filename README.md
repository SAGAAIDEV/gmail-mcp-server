# Gmail MCP Server

An MCP (Model Context Protocol) server that provides Gmail integration capabilities to MCP clients like Claude Desktop.

## Features

- View recent emails from your Gmail inbox
- Search emails using Gmail's search syntax
- Secure OAuth2 authentication with Gmail API

## Setup

1. Create a Google Cloud Project and enable the Gmail API
2. Create OAuth 2.0 credentials (download as `credentials.json`)
3. Install the package:
   ```bash
   uv venv
   uv pip install -e .
   ```

4. Create a `.env` file with:
   ```
   GMAIL_CREDENTIALS_FILE=/path/to/your/credentials.json
   GMAIL_TOKEN_FILE=/path/to/save/token.json
   ```

## Usage with Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "gmail": {
      "command": "gmail-mcp-server"
    }
  }
}
```

## Available Resources

- `gmail://inbox/recent` - Returns your 10 most recent emails

## Available Tools

- `search_emails` - Search your Gmail using Gmail's search syntax

## Security

This server requires OAuth2 authentication with Gmail. You'll be prompted to authorize access in your browser the first time you run it. Your credentials are stored locally and can be revoked at any time through your Google Account settings.