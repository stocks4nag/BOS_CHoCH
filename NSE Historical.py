"""
    * NSE DATA DOWNLOAD UTILITY *

    Description: Downloads symbol masters and historical OHLCV data from NSE.

    Disclaimer : This utility is meant for educational purposes only. Downloading data from NSE
    website requires explicit approval from the exchange. Hence, the usage of this utility is for
    limited purposes only under proper/explicit approvals.

    Requirements : Following packages are to be installed (using pip) prior to using this utility
    - pandas
    - python 3.8 and above

"""

import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests


class NSEMasterData:
    """Search NSE symbols and retrieve historical OHLCV data."""

    SEARCH_URL = "https://charting.nseindia.com/v1/exchanges/symbolsDynamic"
    HISTORICAL_URL = "https://charting.nseindia.com/v1/charts/symbolHistoricalData"
    NSE_URL = "https://www.nseindia.com/"
    CHARTING_URL = "https://charting.nseindia.com/"
    IST = timezone(timedelta(hours=5, minutes=30))

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://charting.nseindia.com",
            "Referer": self.CHARTING_URL,
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        })
        self.nse_data = None
        self.nfo_data = None
        self._cookies_ready = False

    def _ensure_session(self):
        if self._cookies_ready:
            return
        # NSE may set cookies on both hosts. Keep both requests in this session.
        self.session.get(self.NSE_URL, timeout=15)
        self.session.get(self.CHARTING_URL, timeout=15)
        self._cookies_ready = True

    def _fetch_symbols(self, segment, symbol=""):
        self._ensure_session()
        response = self.session.get(
            self.SEARCH_URL,
            params={"symbol": symbol, "segment": segment},
            timeout=20,
        )
        response.raise_for_status()
        result = response.json()
        if not result.get("status"):
            raise ValueError(f"NSE symbol lookup failed for segment {segment}")
        rows = result.get("data") or []
        df = pd.DataFrame(rows)
        if df.empty:
            return pd.DataFrame(columns=["ScripCode", "Symbol", "Name", "Type"])
        return df.rename(columns={
            "scripcode": "ScripCode",
            "symbol": "Symbol",
            "description": "Name",
            "type": "Type",
        })

    def download_symbol_master(self):
        """Download the current equity, index, and derivatives symbol masters."""
        try:
            self.nse_data = pd.concat(
                [self._fetch_symbols("EQ"), self._fetch_symbols("IDX")],
                ignore_index=True,
            ).drop_duplicates(subset=["ScripCode", "Symbol"])
            self.nfo_data = self._fetch_symbols("FO").drop_duplicates(
                subset=["ScripCode", "Symbol"]
            )
        except (requests.RequestException, ValueError) as exc:
            print(f"Failed to download NSE symbol master: {exc}")
            self.nse_data = self.nse_data if self.nse_data is not None else pd.DataFrame()
            self.nfo_data = self.nfo_data if self.nfo_data is not None else pd.DataFrame()

    def _lookup(self, symbol, exchange):
        exchange = exchange.upper()
        segments = ["EQ", "IDX"] if exchange == "NSE" else ["FO"] if exchange == "NFO" else []
        if not segments:
            return pd.DataFrame()
        try:
            frames = [self._fetch_symbols(segment, str(symbol)) for segment in segments]
            frames = [frame for frame in frames if not frame.empty]
            if not frames:
                return pd.DataFrame(columns=["ScripCode", "Symbol", "Name", "Type"])
            return pd.concat(frames, ignore_index=True).drop_duplicates(
                subset=["ScripCode", "Symbol"]
            )
        except (requests.RequestException, ValueError) as exc:
            print(f"Failed to search NSE symbols: {exc}")
            return pd.DataFrame()

    def search(self, symbol, exchange, match=False):
        """Search NSE's dynamic symbol service and return matching rows."""
        df = self._lookup(symbol, exchange)
        if df.empty:
            print(f"No matching result found for symbol '{symbol}' in {exchange}.")
            return df
        symbols = df["Symbol"].astype(str)
        if match:
            result = df[symbols.str.upper() == str(symbol).upper()]
            if result.empty:
                result = df[symbols.str.upper() == f"{str(symbol).upper()}-EQ"]
        else:
            result = df[symbols.str.contains(str(symbol), case=False, na=False)]
        return result.reset_index(drop=True)

    def search_symbol(self, symbol, exchange):
        """Return the best exact or partial match from NSE's dynamic lookup."""
        df = self._lookup(symbol, exchange)
        if df.empty:
            print(f"No matching result found for symbol '{symbol}' in {exchange}.")
            return None
        symbols = df["Symbol"].astype(str)
        exact = df[symbols.str.upper() == str(symbol).upper()]
        if exact.empty:
            exact = df[symbols.str.upper() == f"{str(symbol).upper()}-EQ"]
        if not exact.empty:
            return exact.iloc[0]
        result = df[symbols.str.contains(str(symbol), case=False, na=False)]
        if result.empty:
            print(f"No matching result found for symbol '{symbol}' in {exchange}.")
            return None
        return result.iloc[0]

    @classmethod
    def _epoch_seconds(cls, value):
        if value is None:
            return 0
        stamp = pd.Timestamp(value)
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize(cls.IST)
        else:
            stamp = stamp.tz_convert(cls.IST)
        return int(stamp.timestamp())

    def get_history(self, symbol="Nifty 50", exchange="NSE", start=None, end=None, interval="1d"):
        """Return historical OHLCV data indexed by timestamp."""
        exchange = exchange.upper()
        if exchange not in ("NSE", "NFO"):
            print("Invalid exchange. Please choose 'NSE' or 'NFO'.")
            return pd.DataFrame()

        interval_xref = {
            "1m": (1, "I"), "3m": (3, "I"), "5m": (5, "I"),
            "10m": (10, "I"), "15m": (15, "I"), "30m": (30, "I"),
            "1h": (60, "I"), "1d": (1, "D"), "1w": (1, "W"), "1M": (1, "M"),
        }
        if interval not in interval_xref:
            raise ValueError(f"Unsupported interval: {interval}")

        symbol_info = self.search_symbol(symbol, exchange)
        if symbol_info is None:
            return pd.DataFrame()
        time_interval, chart_type = interval_xref[interval]
        segment = str(symbol_info.get("Type", ""))
        payload = {
            "token": str(symbol_info["ScripCode"]),
            "fromDate": self._epoch_seconds(start),
            "toDate": self._epoch_seconds(end) if end is not None else int(time.time()),
            "symbol": str(symbol_info["Symbol"]),
            "symbolType": segment,
            "chartType": chart_type,
            "timeInterval": time_interval,
        }

        try:
            self._ensure_session()
            response = self.session.get(self.HISTORICAL_URL, params=payload, timeout=30)
            response.raise_for_status()
            result = response.json()
            if not result.get("status"):
                print(f"NSE history request failed: {result}")
                return pd.DataFrame()
            rows = result.get("data") or []
            if not rows:
                print("No data received from NSE.")
                return pd.DataFrame()
            df = pd.DataFrame(rows).rename(columns={
                "time": "Timestamp", "open": "Open", "high": "High",
                "low": "Low", "close": "Close", "volume": "Volume",
            })
            required = ["Timestamp", "Open", "High", "Low", "Close", "Volume"]
            missing = [column for column in required if column not in df.columns]
            if missing:
                raise ValueError(f"Unexpected NSE response; missing fields: {missing}")
            # NSE returns epoch milliseconds. Convert to India market time and keep
            # the naive timestamp convention used by the original utility.
            df["Timestamp"] = (
                pd.to_datetime(df["Timestamp"], unit="ms", utc=True)
                .dt.tz_localize(None)
            )
            if chart_type == "I":
                # NSE stamps intraday bars near their closing trade, sometimes
                # with seconds (e.g. 09:19:46 for the 09:15-09:20 candle).
                # Normalize to candle start, anchored to the 09:15 IST session.
                interval_minutes = int(time_interval)
                session_open = df["Timestamp"].dt.normalize() + pd.Timedelta(
                    hours=9, minutes=15
                )
                elapsed = df["Timestamp"] - session_open
                interval = pd.Timedelta(minutes=interval_minutes)
                df["Timestamp"] = session_open + elapsed.dt.floor(interval)
            df = df[required].sort_values("Timestamp").set_index("Timestamp")
            return df
        except (requests.RequestException, ValueError, KeyError) as exc:
            print(f"An error occurred while fetching historical data: {exc}")
            return pd.DataFrame()


if __name__ == "__main__":
    pd.set_option("display.max_rows", None, "display.max_columns", None)

    # Initiate NSEMasterData instance and load the currently available symbol lists.
    nse = NSEMasterData()
    nse.download_symbol_master()

    # Select timeframe for historic data download - static start and end dates.
    # start_date = datetime(2025, 4, 1)
    # end_date = datetime(2025, 4, 11)

    # Select timeframe for historic data download - last n days.
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)

    # Symbol Search Utility - NSE
    # print("********************  Symbol Search Utility - NSE  **********************")
    # symbols = nse.search("NIFTY MIDSML 400", exchange="NSE", match=False)
    # print(symbols)

    # Symbol Search Utility - NFO
    # print("********************  Symbol Search Utility - NFO  **********************")
    # symbols = nse.search("BANKNIFTY", exchange="NFO", match=False)
    # print(symbols)

    # Download Index EOD Data
    # data = nse.get_history(
    #     symbol="NIFTY 50",
    #     exchange="NSE",
    #     start=start_date,
    #     end=end_date,
    #     interval="1d",
    # )
    # print("********************  Index EOD Data  **********************")
    # print("Symbol : NIFTY 50")
    # print(data.head(2))

    # Download Index Intraday Data
    # data = nse.get_history(
    #     symbol="NIFTY BANK",
    #     exchange="NSE",
    #     start=start_date,
    #     end=end_date,
    #     interval="1m",
    # )
    # print("********************  Index Intraday Data  **********************")
    # print("Symbol : BANKNIFTY - 1 Minute data")
    # print(data.head(2))

    # Download Stock (Underlying) Data
    # data = nse.get_history(
    #     symbol="TCS",
    #     exchange="NSE",
    #     start=start_date,
    #     end=end_date,
    #     interval="10m",
    # )
    # print("********************  Stock Intraday Data  **********************")
    # print("Symbol : TCS - 10 Minute data")
    # print(data.head(2))

    # Download Index Futures Data
    # data = nse.get_history(
    #     symbol="NIFTY26DECFUT",
    #     exchange="NFO",
    #     start=start_date,
    #     end=end_date,
    #     interval="1h",
    # )
    # print("********************  Index Futures Data  **********************")
    # print("Symbol : Nifty December Futures - 1 Hour data")
    # print(data.head(2))

    # Download Stock Futures Data
    # data = nse.get_history(
    #     symbol="RELIANCE26DECFUT",
    #     exchange="NFO",
    #     start=start_date,
    #     end=end_date,
    #     interval="1h",
    # )
    # print("********************  Stock Futures Data  **********************")
    # print("Symbol : Reliance December Futures - 1 Hour data")
    # print(data.head(2))

    # Download Index Options Data
    # data = nse.get_history(
    #     symbol="BANKNIFTY26DEC50000PE",
    #     exchange="NFO",
    #     start=start_date,
    #     end=end_date,
    #     interval="5m",
    # )
    # print("********************  Index Options Data  **********************")
    # print("Symbol : Banknifty PE Options - 5 Minute data")
    # print(data.head(2))

    # Download Stock Options Data
    # data = nse.get_history(
    #     symbol="TCS26OCT2120CE",
    #     exchange="NFO",
    #     start=start_date,
    #     end=end_date,
    #     interval="5m",
    # )
    # print("********************  Stock Options Data  **********************")
    # print("Symbol : TCS October 2026 2120 CE - 5 Minute data")
    # print(data.head(2))


