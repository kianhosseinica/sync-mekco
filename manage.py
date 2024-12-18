#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
import signal
import logging

# Set up basic logging for clean shutdown logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

def signal_handler(sig, frame):
    """Handle interrupt signal (CTRL+C) to terminate gracefully."""
    logger.info("Interrupt signal received. Shutting down gracefully.")
    sys.exit(0)  # Exit the process

def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lightspeed_integration.settings')

    # Register the signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)

if __name__ == '__main__':
    main()
