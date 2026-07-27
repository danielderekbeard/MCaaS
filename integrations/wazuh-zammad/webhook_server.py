#!/usr/bin/env python3
"""
Wazuh → Zammad Webhook Server

HTTP server that receives Wazuh alerts via webhook and creates Zammad tickets.
Designed to run as a Kubernetes service.

Endpoints:
    POST /webhook/wazuh - Receive Wazuh alerts
    GET /health - Health check

Environment Variables:
    ZAMMAD_URL, ZAMMAD_API_TOKEN - Zammad configuration
    LISTEN_PORT - Server port (default: 8080)
    DEDUP_WINDOW_HOURS - Deduplication window (default: 24)

Usage:
    python webhook_server.py
"""

import json
import logging
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict

import ticket_creator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WebhookHandler(BaseHTTPRequestHandler):
    """HTTP request handler for webhook endpoints."""
    
    def log_message(self, format, *args):
        """Custom logging."""
        logger.info(f"{self.address_string()} - {format % args}")
    
    def _send_response(self, status_code: int, data: Dict = None):
        """Send JSON response."""
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        if data:
            self.wfile.write(json.dumps(data).encode())
    
    def _send_error(self, status_code: int, message: str):
        """Send error response."""
        self._send_response(status_code, {'error': message})
    
    def do_GET(self):
        """Handle GET requests."""
        if self.path == '/health':
            self._send_response(200, {'status': 'healthy', 'service': 'wazuh-zammad-webhook'})
        else:
            self._send_error(404, 'Not found')
    
    def do_POST(self):
        """Handle POST requests."""
        if self.path == '/webhook/wazuh':
            self._handle_wazuh_webhook()
        else:
            self._send_error(404, 'Not found')
    
    def _handle_wazuh_webhook(self):
        """Process Wazuh alert webhook."""
        # Read request body
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length == 0:
            self._send_error(400, 'Empty request body')
            return
        
        try:
            body = self.rfile.read(content_length).decode('utf-8')
            alert = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"Failed to parse request body: {e}")
            self._send_error(400, f'Invalid JSON: {e}')
            return
        
        # Process alert
        logger.info(f"Received alert: {alert.get('rule', {}).get('description', 'Unknown')}")
        
        try:
            result = ticket_creator.process_alert(body)
            
            if result is None:
                self._send_error(500, 'Failed to process alert')
            elif result.get('skipped'):
                self._send_response(200, {
                    'status': 'skipped',
                    'reason': 'duplicate alert'
                })
            else:
                self._send_response(201, {
                    'status': 'created',
                    'ticket_id': result.get('id'),
                    'ticket_number': result.get('number')
                })
        except Exception as e:
            logger.exception("Error processing alert")
            self._send_error(500, f'Internal error: {str(e)}')


def run_server(port: int = 8080):
    """Start the webhook server."""
    server = HTTPServer(('', port), WebhookHandler)
    logger.info(f"Starting webhook server on port {port}")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        server.shutdown()


def main():
    port = int(os.environ.get('LISTEN_PORT', '8080'))
    
    # Validate required environment variables
    required_vars = ['ZAMMAD_URL', 'ZAMMAD_API_TOKEN']
    missing = [v for v in required_vars if not os.environ.get(v)]
    
    if missing:
        logger.error(f"Missing required environment variables: {', '.join(missing)}")
        sys.exit(1)
    
    run_server(port)


if __name__ == '__main__':
    main()
