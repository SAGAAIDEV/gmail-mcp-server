# Gmail MCP Server

An MCP (Model Context Protocol) server that provides Gmail integration capabilities to MCP clients like Claude Desktop.

## Features

- View recent emails from your Gmail inbox
- Search emails using Gmail's search syntax
- Secure OAuth2 authentication with Gmail API

## Setup

### 1. Google Cloud Project Setup
1. Create a Google Cloud Project at https://console.cloud.google.com/
2. Enable the Gmail API
3. Create OAuth 2.0 credentials:
   - Application type: Desktop application
   - Download the credentials as `credentials.json`

### 2. Installation
```bash
# Create a conda environment
conda create -n mcp-gmail python=3.12
conda activate mcp-gmail

# Install the package
cd gmail-mcp-server
pip install -e .
```

### 3. Configuration for Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "gmail": {
      "command": "/path/to/conda/envs/mcp-gmail/bin/python",
      "args": ["-m", "gmail_mcp_server.server"],
      "env": {
        "PYTHONPATH": "/path/to/gmail-mcp-server/src",
        "GMAIL_CREDENTIALS_FILE": "/path/to/credentials.json",
        "GMAIL_TOKEN_FILE": "/path/to/token.json"
      }
    }
  }
}
```

Replace `/path/to/` with your actual paths. The token file will be created automatically when you first authenticate.

### 4. First Run
When you first try to access Gmail through Claude, you'll be prompted to authorize the application in your browser. After authorization, your credentials will be saved to the token file for future use.

## Available Resources

- `gmail://inbox/recent` - Returns your 10 most recent emails

## Available Tools

- `search_emails`
  - Description: Search Gmail emails with a query
  - Parameters:
    - `query` (required): Gmail search query (uses Gmail's standard search syntax)
    - `max_results` (optional): Maximum number of results to return (default: 10)

Example search:
```
Could you show me any emails from sanrio in the last two days?
```

## Security

This server requires OAuth2 authentication with Gmail:
- You'll be prompted to authorize access in your browser on first use
- Credentials are stored locally in the specified token file
- Access can be revoked at any time through your Google Account settings
- Only read access to Gmail is requested (no write permissions)

## Environment Variables

- `GMAIL_CREDENTIALS_FILE` (required): Path to your Google OAuth credentials file
- `GMAIL_TOKEN_FILE` (required): Path where the authentication token will be saved

For testing, you can run the server directly:
```bash
GMAIL_CREDENTIALS_FILE="/path/to/credentials.json" \
GMAIL_TOKEN_FILE="/path/to/token.json" \
python -m gmail_mcp_server.server
```

## Development

The server uses the Model Context Protocol to provide:
- Resource access to recent emails
- Tool support for email search
- Secure OAuth2 authentication flow
- Automatic token refresh

### Logging
The server logs detailed information about its operations to stderr, including:
- Server startup information
- Authentication status
- Resource and tool usage
- Any errors or issues

## Contributing

Pull requests are welcome! Please ensure to:
- Update documentation for any new features
- Add appropriate error handling
- Test OAuth flow with new features
- Follow existing code style