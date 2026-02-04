"""IBKR client wrapper with option chain fetching capabilities."""

import logging
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import yfinance as yf
from ib_insync import IB, Index, Option, Stock

from .config import settings

logger = logging.getLogger(__name__)


class IBKRClient:
    """Wrapper around ib_insync for fetching option chain data."""

    def __init__(self) -> None:
        """Initialize the IBKR client."""
        self.ib = IB()
        self._connected = False

    @property
    def is_connected(self) -> bool:
        """Check if the client is connected."""
        return self._connected and self.ib.isConnected()

    async def connect(self) -> None:
        """Connect to IB Gateway/TWS."""
        if self.is_connected:
            logger.debug("Already connected to IBKR")
            return

        try:
            logger.info(
                f"Connecting to IBKR at {settings.ibkr_host}:{settings.ibkr_port} "
                f"with client ID {settings.ibkr_client_id}"
            )
            await self.ib.connectAsync(
                host=settings.ibkr_host,
                port=settings.ibkr_port,
                clientId=settings.ibkr_client_id,
                timeout=settings.ibkr_timeout,
            )
            self.ib.reqMarketDataType(settings.market_data_type)
            self._connected = True
            logger.info("Successfully connected to IBKR")
        except Exception as e:
            logger.error(f"Failed to connect to IBKR: {e}")
            self._connected = False
            raise

    def disconnect(self) -> None:
        """Disconnect from IB Gateway/TWS."""
        if self.is_connected:
            logger.info("Disconnecting from IBKR")
            self.ib.disconnect()
            self._connected = False

    def _create_underlying_contract(self, symbol: str) -> Stock | Index:
        """Create the underlying contract (Stock or Index)."""
        indices = ["SPX", "NDX", "RUT", "VIX"]

        if symbol.upper() in indices:
            return Index(symbol.upper(), "CBOE")
        return Stock(symbol.upper(), "SMART", "USD")

    def _get_price_from_yfinance(self, symbol: str) -> float | None:
        """Fetch current price from Yahoo Finance."""
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1d")
            if not hist.empty:
                return float(hist["Close"].iloc[-1])
        except Exception as e:
            logger.debug(f"Failed to get price from yfinance: {e}")
        return None

    async def get_underlying_price(self, symbol: str) -> float | None:
        """Get the current price of the underlying symbol."""
        if not self.is_connected:
            raise RuntimeError("Not connected to IBKR")

        # Try yfinance first (free)
        price = self._get_price_from_yfinance(symbol)
        if price:
            logger.debug(f"Got price from yfinance: ${price:.2f}")
            return price

        # Fall back to IB data
        try:
            logger.debug("Trying to get price from IB data feed")
            underlying = self._create_underlying_contract(symbol)
            await self.ib.qualifyContractsAsync(underlying)
            tickers = await self.ib.reqTickersAsync(underlying)
            ticker = tickers[0]

            # Try multiple methods to get price
            price = ticker.marketPrice()
            if not price or price != price:  # Check for nan
                price = ticker.last
            if not price or price != price:
                price = ticker.close
            if (not price or price != price) and ticker.bid > 0 and ticker.ask > 0:
                price = (ticker.bid + ticker.ask) / 2

            if price and price == price:  # Valid number
                logger.debug(f"Got price from IB: ${price:.2f}")
                return float(price)

            logger.warning("Could not fetch underlying price from any source")
            return None

        except Exception as e:
            logger.error(f"Error fetching underlying price: {e}")
            return None

    def _extract_ticker_data(self, ticker: Any, underlying_price: float | None) -> dict[str, Any]:
        """Extract data from a ticker object."""
        contract = ticker.contract
        greeks = ticker.modelGreeks or ticker.bidGreeks or ticker.askGreeks or ticker.lastGreeks

        data: dict[str, Any] = {
            "symbol": contract.symbol,
            "expiration": contract.lastTradeDateOrContractMonth,
            "strike": contract.strike,
            "right": contract.right,
            "underlying_price": underlying_price,
            "bid": ticker.bid if ticker.bid != -1 else None,
            "ask": ticker.ask if ticker.ask != -1 else None,
            "last": ticker.last if ticker.last != -1 else None,
            "bid_size": ticker.bidSize if ticker.bidSize else None,
            "ask_size": ticker.askSize if ticker.askSize else None,
            "volume": ticker.volume if ticker.volume != -1 else None,
            "open_interest": ticker.open if ticker.open != -1 else None,
        }

        if greeks:
            data.update(
                {
                    "delta": greeks.delta,
                    "gamma": greeks.gamma,
                    "theta": greeks.theta,
                    "vega": greeks.vega,
                    "implied_vol": greeks.impliedVol,
                }
            )
        else:
            data.update(
                {
                    "delta": None,
                    "gamma": None,
                    "theta": None,
                    "vega": None,
                    "implied_vol": None,
                }
            )

        return data

    async def fetch_option_chain(
        self,
        symbol: str,
        strike_count: int | None = None,
        strike_range_pct: float | None = None,
        expiration_days: list[int] | None = None,
    ) -> dict[str, Any]:
        """
        Fetch option chain data for a symbol.

        Args:
            symbol: Underlying symbol (e.g., SPY, AAPL)
            strike_count: Number of strikes above/below current price
            strike_range_pct: Percentage range for strikes (alternative to strike_count)
            expiration_days: List of days from today for expirations

        Returns:
            Dictionary containing option chain data
        """
        if not self.is_connected:
            raise RuntimeError("Not connected to IBKR")

        # Use defaults if not specified
        if strike_count is None:
            strike_count = settings.default_strike_count
        if strike_range_pct is None:
            strike_range_pct = settings.default_strike_range_pct

        logger.info(f"Fetching option chain for {symbol}")

        # Get underlying contract
        underlying = self._create_underlying_contract(symbol)
        await self.ib.qualifyContractsAsync(underlying)

        # Get current price
        underlying_price = await self.get_underlying_price(symbol)

        # Request option chain parameters
        chains = await self.ib.reqSecDefOptParamsAsync(
            underlying.symbol, "", underlying.secType, underlying.conId
        )

        if not chains:
            raise ValueError(f"No option chains found for {symbol}")

        # Select the best chain - prefer one that matches the symbol,
        # otherwise select the one with most strikes and expirations
        chain = None
        best_score = -1

        for c in chains:
            # Prefer chains where trading class matches symbol (e.g., MSFT not 2MSFT)
            score = len(c.strikes) * len(c.expirations)
            if c.tradingClass == symbol.upper():
                score *= 10  # Strong preference for matching trading class

            if score > best_score:
                best_score = score
                chain = c

        if chain is None:
            chain = chains[0]  # Fallback to first chain if something went wrong

        logger.info(
            f"Selected chain: {chain.tradingClass} on {chain.exchange} "
            f"({len(chain.expirations)} expirations, {len(chain.strikes)} strikes)"
        )
        if len(chains) > 1:
            logger.info(
                f"Note: {len(chains)} chains available. Others: "
                f"{', '.join(c.tradingClass for c in chains if c != chain)}"
            )

        # Filter strikes
        if underlying_price:
            sorted_strikes = sorted(chain.strikes)
            strikes_below = [s for s in sorted_strikes if s < underlying_price]
            strikes_above = [s for s in sorted_strikes if s >= underlying_price]

            selected_below = (
                strikes_below[-strike_count:]
                if len(strikes_below) >= strike_count
                else strikes_below
            )
            selected_above = (
                strikes_above[:strike_count]
                if len(strikes_above) >= strike_count
                else strikes_above
            )

            filtered_strikes = sorted(selected_below + selected_above)
            logger.debug(
                f"Filtered to {len(filtered_strikes)} strikes "
                f"({len(selected_above)} above, {len(selected_below)} below)"
            )
        else:
            # No price available, use middle strikes
            sorted_strikes = sorted(chain.strikes)
            total_strikes = len(sorted_strikes)
            middle_idx = total_strikes // 2
            start_idx = max(0, middle_idx - strike_count)
            end_idx = min(total_strikes, middle_idx + strike_count)
            filtered_strikes = sorted_strikes[start_idx:end_idx]
            logger.debug(f"No price available, using middle {len(filtered_strikes)} strikes")

        # Filter expirations
        if expiration_days:
            today = datetime.now().date()
            target_dates = [today + timedelta(days=d) for d in expiration_days]

            filtered_expirations = []
            for exp_str in sorted(chain.expirations):
                exp_date = datetime.strptime(exp_str, "%Y%m%d").date()
                for target_date in target_dates:
                    if abs((exp_date - target_date).days) <= 1:
                        filtered_expirations.append(exp_str)
                        break

            if not filtered_expirations:
                logger.warning("No matching expirations, using closest available")
                filtered_expirations = sorted(chain.expirations)[: len(expiration_days)]

            expirations = filtered_expirations
        else:
            expirations = sorted(chain.expirations)

        logger.debug(f"Using {len(expirations)} expirations")

        # Build option contracts
        option_contracts = []
        exchange = "SMART" if underlying.secType == "STK" else chain.exchange

        for expiration in expirations:
            for strike in filtered_strikes:
                for right in ["C", "P"]:
                    option = Option(
                        underlying.symbol,
                        expiration,
                        strike,
                        right,
                        exchange,
                        tradingClass=chain.tradingClass,
                    )
                    option_contracts.append(option)

        logger.debug(f"Created {len(option_contracts)} option contracts")

        # Qualify contracts
        qualified_contracts = []
        for contract in option_contracts:
            try:
                qualified = await self.ib.qualifyContractsAsync(contract)
                if qualified:
                    qualified_contracts.extend(qualified)
            except Exception:
                continue  # Skip invalid contracts

        logger.debug(f"Qualified {len(qualified_contracts)} contracts")

        if not qualified_contracts:
            raise ValueError("No valid option contracts found")

        # Request market data
        logger.info(f"Fetching market data for {len(qualified_contracts)} contracts")
        tickers = await self.ib.reqTickersAsync(*qualified_contracts)

        # Extract data
        data_list = []
        for ticker in tickers:
            data = self._extract_ticker_data(ticker, underlying_price)
            data_list.append(data)

        if not data_list:
            raise ValueError("No option data retrieved")

        # Create DataFrame and sort
        df = pd.DataFrame(data_list)
        df = df.sort_values(["expiration", "strike", "right"])

        result = {
            "symbol": symbol,
            "underlying_price": underlying_price,
            "timestamp": datetime.now().isoformat(),
            "market_data_type": settings.market_data_type,
            "total_contracts": len(data_list),
            "calls": len(df[df["right"] == "C"]),
            "puts": len(df[df["right"] == "P"]),
            "expirations": df["expiration"].unique().tolist(),
            "strikes": df["strike"].unique().tolist(),
            "options": data_list,
        }

        logger.info(
            f"Successfully fetched {len(data_list)} option contracts "
            f"({result['calls']} calls, {result['puts']} puts)"
        )

        return result
