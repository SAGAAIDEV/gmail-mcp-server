import os
import sys
import json
import logging
import base64
from typing import Any, Sequence
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import asyncio
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from google.auth.exceptions import RefreshError

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
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send'
]

# Get credential paths from environment
CREDENTIALS_FILE = os.getenv('GMAIL_CREDENTIALS_FILE')
TOKEN_FILE = os.getenv('GMAIL_TOKEN_FILE')

if not CREDENTIALS_FILE:
    raise ValueError("GMAIL_CREDENTIALS_FILE environment variable must be set")
if not TOKEN_FILE:
    raise ValueError("GMAIL_TOKEN_FILE environment variable must be set")

logger.info(f"Using credentials file: {CREDENTIALS_FILE}")
logger.info(f"Using token file: {TOKEN_FILE}")

def create_message(to, subject, body, cc=None, bcc=None):
    """Create a message for an email."""
    message = MIMEMultipart()
    message['to'] = to
    message['subject'] = subject
    
    if cc:
        message['cc'] = cc
    if bcc:
        message['bcc'] = bcc

    msg = MIMEText(body)
    message.attach(msg)

    raw = base64.urlsafe_b64encode(message.as_bytes())
    return {'raw': raw.decode()}

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

    def load_saved_credentials(self):
        """Load credentials from the token file if it exists."""
        if os.path.exists(TOKEN_FILE):
            try:
                with open(TOKEN_FILE, 'r') as token:
                    token_data = json.load(token)
                    return Credentials.from_authorized_user_info(token_data, SCOPES)
            except Exception as e:
                logger.error(f"Error loading saved credentials: {e}")
                return None
        return None

    def save_credentials(self, credentials):
        """Save credentials to the token file."""
        try:
            os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
            with open(TOKEN_FILE, 'w') as token:
                token.write(credentials.to_json())
            logger.info("Credentials saved successfully")
        except Exception as e:
            logger.error(f"Error saving credentials: {e}")

    async def refresh_credentials(self):
        """Attempt to refresh the credentials."""
        logger.info("Attempting to refresh credentials")
        try:
            if self.credentials and self.credentials.refresh_token:
                self.credentials.refresh(Request())
                self.save_credentials(self.credentials)
                return True
            return False
        except RefreshError as e:
            logger.error(f"Failed to refresh credentials: {e}")
            return False
    
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
                ),
                Tool(
                    name="send_email",
                    description="Send an email to specified recipients",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "to": {
                                "type": "string",
                                "description": "Recipient email address"
                            },
                            "subject": {
                                "type": "string",
                                "description": "Email subject"
                            },
                            "body": {
                                "type": "string",
                                "description": "Email body content"
                            },
                            "cc": {
                                "type": "string",
                                "description": "CC recipients (comma-separated)"
                            },
                            "bcc": {
                                "type": "string",
                                "description": "BCC recipients (comma-separated)"
                            }
                        },
                        "required": ["to", "subject", "body"]
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

            try:
                if name == "search_emails":
                    if not isinstance(arguments, dict) or "query" not in arguments:
                        raise ValueError("Invalid search arguments")

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
                
                elif name == "send_email":
                    if not isinstance(arguments, dict) or not all(k in arguments for k in ["to", "subject", "body"]):
                        raise ValueError("Invalid email arguments")

                    # Always attempt to refresh before sending
                    await self.refresh_credentials()

                    message = create_message(
                        to=arguments["to"],
                        subject=arguments["subject"],
                        body=arguments["body"],
                        cc=arguments.get("cc"),
                        bcc=arguments.get("bcc")
                    )

                    sent_message = self.gmail_service.users().messages().send(
                        userId='me',
                        body=message
                    ).execute()

                    return [
                        TextContent(
                            type="text",
                            text=f"Email sent successfully! Message ID: {sent_message['id']}"
                        )
                    ]

                else:
                    raise ValueError(f"Unknown tool: {name}")

            except Exception as e:
                logger.error(f"Gmail API error: {str(e)}")
                return [
                    TextContent(
                        type="text",
                        text=f"Error: {str(e)}"
                    )
                ]

    async def ensure_authenticated(self):
        """Ensure we have valid Gmail API credentials."""
        logger.info("Checking Gmail authentication")
        
        if not self.credentials:
            self.credentials = self.load_saved_credentials()

        if not self.credentials:
            logger.info("No saved credentials found, starting OAuth flow")
            if not os.path.exists(CREDENTIALS_FILE):
                raise ValueError(f"Credentials file not found at {CREDENTIALS_FILE}")
            
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE,
                SCOPES
            )
            self.credentials = flow.run_local_server(port=0)
            self.save_credentials(self.credentials)
        elif not self.credentials.valid:
            if self.credentials.expired and self.credentials.refresh_token:
                logger.info("Credentials expired, attempting refresh")
                success = await self.refresh_credentials()
                if not success:
                    logger.info("Refresh failed, starting new OAuth flow")
                    flow = InstalledAppFlow.from_client_secrets_file(
                        CREDENTIALS_FILE,
                        SCOPES
                    )
                    self.credentials = flow.run_local_server(port=0)
                    self.save_credentials(self.credentials)
            else:
                logger.info("Invalid credentials, starting new OAuth flow")
                flow = InstalledAppFlow.from_client_secrets_file(
                    CREDENTIALS_FILE,
                    SCOPES
                )
                self.credentials = flow.run_local_server(port=0)
                self.save_credentials(self.credentials)

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