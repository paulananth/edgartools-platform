from rich import print
from tqdm.auto import tqdm

from edgar import *
from edgar.xbrl import XBRL


def examine_filing_xbrl(filing: Filing):
    xbrl = XBRL.from_filing(filing)
    if xbrl is None:
        print(f"No XBRL data found for filing {filing}")
        return
    print(xbrl)


if __name__ == '__main__':
    filings = get_filings(form=['S-1', 'S-3', 'N-1', 'N-2', '424B5', '424B2'], index="xbrl").head(100)
    for filing in tqdm(filings):
        examine_filing_xbrl(filing)
