#!/usr/bin/env python3
"""Run the mailbox dependency gate using the dashboard's shared graph projection."""
from pathlib import Path
import sys


MAILBOX = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(MAILBOX / 'dashboard'))

from dispatch_gate import main


if __name__ == '__main__':
    raise SystemExit(main())
