import os
import sys
import json
import logging
from typing import Any, Sequence
from datetime import datetime

import asyncio
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from mcp.server import Server
from mcp.types import (
    Resource,
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
    LoggingLevel
)
from mcp.server.stdio import stdio_server

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger("gmail-mcp-server")

# Log startup information
logger.info("Gmail MCP Server starting...")
logger.info(f"Python executable: {sys.executable}")
logger.info(f"Current directory: {os.getcwd()}")

# Gmail API configuration
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
BASE_DIR = "/Users/ajbrown/Desktop/claude/gmail-mcp-server"
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json")
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")

logger.info(f"Using credentials file: {CREDENTIALS_FILE}")
logger.info(f"Using token file: {TOKEN_FILE}")

class GmailServer:
    def __init__(self):
        logger.info("Initializing GmailServer...")
        self.server = Server("gmail-mcp-server")
        self.credentials = None
        self.gmail_service = None
        
        self.setup_handlers()
        self.setup_error_handling()
        logger.info("GmailServer initialization complete")

    def setup_error_handling(self):
        def error_handler(error):
            logger.error(f"Server error: {error}")
        self.server.onerror = error_handler

    def setup_handlers(self):
        @self.server.list_resources()
        async def list_resources() -> list[Resource]:
            """List available Gmail resources."""
            logger.info("Listing Gmail resources")
            return [
                Resource(
                    uri="gmail://inbox/recent",
                    name="Recent Gmail Messages",
                    mimeType="application/json",
                    description="Recent emails from your Gmail inbox"
                )
            ]

        @self.server.read_resource()
        async def read_resource(uri: str) -> str:
            """Read Gmail resources."""
            logger.info(f"Reading resource: {uri}")
            await self.ensure_authenticated()
            
            if uri == "gmail://inbox/recent":
                messages = self.gmail_service.users().messages().list(
                    userId='me',
                    maxResults=10
                ).execute()

                detailed_messages = []
                for msg in messages.get('messages', []):
                    message = self.gmail_service.users().messages().get(
                        userId='me',
                        id=msg['id']
                    ).execute()
                    
                    headers = {
                        header['name']: header['value']
                        for header in message['payload']['headers']
                    }
                    
                    detailed_messages.append({
                        'id': message['id'],
                        'subject': headers.get('Subject', 'No Subject'),
                        'from': headers.get('From', 'Unknown'),
                        'date': headers.get('Date', 'Unknown'),
                        'snippet': message.get('snippet', '')
                    })

                return json.dumps(detailed_messages, indent=2)
            
            raise ValueError(f"Unknown resource: {uri}")

        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            """List available Gmail tools."""
            logger.info("Listing Gmail tools")
            return [
                Tool(
                    name="search_emails",
                    description="Search Gmail emails with a query",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Gmail search query"
                            },
                            "max_results": {
                                "type": "number",
                                "description": "Maximum number of results",
                                "default": 10
                            }
                        },
                        "required": ["query"]
                    }
                )
            ]

        @self.server.call_tool()
        async def call_tool(
            name: str,
            arguments: Any
        ) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
            """Handle tool calls for Gmail operations."""
            logger.info(f"Calling tool: {name} with arguments: {arguments}")
            await self.ensure_authenticated()

            if name != "search_emails":
                raise ValueError(f"Unknown tool: {name}")

            if not isinstance(arguments, dict) or "query" not in arguments:
                raise ValueError("Invalid search arguments")

            try:
                messages = self.gmail_service.users().messages().list(
                    userId='me',
                    q=arguments["query"],
                    maxResults=arguments.get("max_results", 10)
                ).execute()

                detailed_messages = []
                for msg in messages.get('messages', []):
                    message = self.gmail_service.users().messages().get(
                        userId='me',
                        id=msg['id']
                    ).execute()
                    
                    headers = {
                        header['name']: header['value']
                        for header in message['payload']['headers']
                    }
                    
                    detailed_messages.append({
                        'id': message['id'],
                        'subject': headers.get('Subject', 'No Subject'),
                        'from': headers.get('From', 'Unknown'),
                        'date': headers.get('Date', 'Unknown'),
                        'snippet': message.get('snippet', '')
                    })

                return [
                    TextContent(
                        type="text",
                        text=json.dumps(detailed_messages, indent=2)
                    )
                ]

            except Exception as e:
                logger.error(f"Gmail API error: {str(e)}")
                return [
                    TextContent(
                        type="text",
                        text=f"Error searching emails: {str(e)}"
                    )
                ]

    async def ensure_authenticated(self):
        """Ensure we have valid Gmail API credentials."""
        logger.info("Checking Gmail authentication")
        if not self.credentials or not self.credentials.valid:
            if self.credentials and self.credentials.expired and self.credentials.refresh_token:
                logger.info("Refreshing expired credentials")
                self.credentials.refresh(Request())
            else:
                if not os.path.exists(CREDENTIALS_FILE):
                    raise ValueError(f"Credentials file not found at {CREDENTIALS_FILE}")
                
                logger.info("Starting OAuth flow")
                flow = InstalledAppFlow.from_client_secrets_file(
                    CREDENTIALS_FILE,
                    SCOPES
                )
                self.credentials = flow.run_local_server(port=0)

                # Save the credentials for future use
                if TOKEN_FILE:
                    logger.info(f"Saving credentials to {TOKEN_FILE}")
                    os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
                    with open(TOKEN_FILE, 'w') as token:
                        token.write(self.credentials.to_json())

            self.gmail_service = build('gmail', 'v1', credentials=self.credentials)
            logger.info("Gmail authentication complete")

    async def run(self):
        """Run the MCP server."""
        logger.info("Starting server with stdio transport")
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options()
            )

def main():
    """Main entry point for the Gmail MCP server."""
    try:
        logger.info("Starting main")
        server = GmailServer()
        asyncio.run(server.run())
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        raise

if __name__ == '__main__':
    main()