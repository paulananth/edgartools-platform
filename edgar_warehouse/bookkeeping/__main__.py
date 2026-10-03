"""`python -m edgar_warehouse.bookkeeping <command>`: the control commands alone."""
import sys

from edgar_warehouse.cli import main

raise SystemExit(main(["bookkeeping", *sys.argv[1:]]))
