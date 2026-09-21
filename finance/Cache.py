''' This class serves as a cache for the informatio of Yahoo Finance, so
that the appliecation does not reach to the Yahoo Finance rate limit.
Every time the user wants to get the information of a ticker, it first checks if the 
information is in the cache. If it is, it returns the information from the cache. 
If it is not, it gets the information from Yahoo Finance and stores it in the cache
as a CSV file for each stock value. It stores the "history" of the last 5 years.'''

import numpy as np
import pandas as pd
import yfinance as yf
import os

class Cache:
    def __init__(self,yfDuration="6mo", yfInterval="1d"):
        # Yahoo finance (YF) duration string for histoy accordint to YF (e.g. max, 5y)
        self.yfDuration = yfDuration
        self.yfInterval = yfInterval
        # Folder where CSV files are stored
        self.pathFolder = "./finance/Cache/"
        # Dictionary for the histories of the stocks
        self.histories = {}
        # Create the folder if it does not exist
        if not os.path.exists(self.pathFolder):
            os.makedirs(self.pathFolder)

    def filename(self, ticker):
        # return self.pathFolder + ticker + "_5y.csv"
        return self.pathFolder + ticker + "_"+self.yfDuration+".csv"

    # It provides the known history up to the last day according to cache
    def history(self, ticker):
        if ticker in self.histories:
            hist = self.histories[ticker]
        else:
            fname = self.filename(ticker)
            if os.path.exists(fname):
                hist = pd.read_csv(fname, index_col=0, parse_dates=True)
            else:
                #if self.yfInterval in ["1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h"]:
                #    hist = yf.download(tickers=ticker, period = self.yfDuration, interval=self.yfInterval)
                #else:
                hist = yf.Ticker(ticker).history(period=self.yfDuration, 
                            interval=self.yfInterval, auto_adjust=True, actions=False)
                hist.to_csv(fname)
                print("Getting data from Yahoo Finance for ticker:", ticker)
            self.histories[ticker] = hist
        return hist
    

#### Main function for testing purposes ####

if __name__ == "__main__":
    cache = Cache()
    history = cache.history("MSFT")

    
    