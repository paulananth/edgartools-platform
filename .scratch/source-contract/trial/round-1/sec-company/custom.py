# sec.company_profile Custom Steps.
from source_contract import check_step


@check_step("tickers_pair_with_exchanges", version=1)
def tickers_pair_with_exchanges(ticker_count: int, exchange_count: int) -> str | None:
    # SEC publishes tickers[] and exchanges[] as parallel lists: item i of one belongs to item i of the other.
    if ticker_count != exchange_count:
        return f"{ticker_count} tickers but {exchange_count} exchanges"
    return None
