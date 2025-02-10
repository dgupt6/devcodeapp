# ---------------------------------------------------------------------------------
# This program displays historical stock prices of provided stock ticker symbol
# Developed by Devraj Gupta
# Revision version : V1.0
# Date : Feb 9 2025
# ---------------------------------------------------------------------------------
import streamlit as st
import yfinance as yf

# Set the title of the stock app
st.title('Stock Market Data Visualization')

# Sidebar for user input
st.sidebar.header('User Input Parameters')

def get_user_input():
    ticker = st.sidebar.text_input('Enter Stock Ticker', 'PLTR')
    duration = st.sidebar.selectbox('Select Duration', ['5d', '1d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'ytd', 'max'])
    return ticker, duration


def get_stockdata():

    try:
        ticker, duration = get_user_input()
        # Fetch stock data
        stock_data = yf.Ticker(ticker)
        # Get historical market data
        historical_data = stock_data.history(period=duration)
        if historical_data.empty:
            st.error(f"No data found for the ticker symbol: **{ticker}**. Please enter a valid ticker.")
            return None
        else:
            historical_data.reset_index(inplace=True)

        # Get 52-week high and low
        stock_info = stock_data.info
        week_52_high = stock_info.get('fiftyTwoWeekHigh', 'N/A')
        week_52_low = stock_info.get('fiftyTwoWeekLow', 'N/A')

        # Get dividends
        dividends = stock_data.get_dividends()

        stockdata_dict = {}
        stockdata_dict['ticker'] = ticker
        stockdata_dict['duration'] = duration
        stockdata_dict['historical_data'] = historical_data
        stockdata_dict['week_52_high'] = week_52_high
        stockdata_dict['week_52_low'] = week_52_low
        stockdata_dict['dividends'] = dividends

        return stockdata_dict

    except Exception as e:
        st.error(f"Error: The ticker symbol is invalid or data is unavailable. Please enter a valid ticker.")
        return None


def visualize_and_display(stockresults):

    # Display the stock ticker and duration
    st.write(f"Displaying historical market data for ticker **{stockresults['ticker']}** over the last **{stockresults['duration']}**.")

    # Display 52-week high and low
    st.subheader('52-Week High and Low')
    st.write(f"- **52-Week High:** {stockresults['week_52_high']}")
    st.write(f"- **52-Week Low:** {stockresults['week_52_low']}")

    # Plot the stock prices using Streamlit's native line chart
    historicaldatalocal = stockresults['historical_data']
    st.subheader('Stock Price Chart')
    st.line_chart(historicaldatalocal.set_index('Date')['Close'])

    st.success("✅ Stock prices plotted.")

    # Display historical data
    st.subheader('Historical Data')
    st.write(historicaldatalocal)

    # Display dividends
    st.subheader('Dividends')
    st.write(stockresults['dividends'])

    st.write("🚀 Built with Streamlit | Feb 2025 V1.0 | Devraj Gupta")

    # About section
    st.sidebar.header('About')
    st.sidebar.info(
        "This application displays historical market data and financial information "
        "about stocks from Yahoo Finance. "
        "Contact Devraj Gupta for Questions!!"
    )

def stockapp_run():
    stock_results= get_stockdata()
    if stock_results is not None:
        visualize_and_display(stock_results)

if __name__ == '__main__':
    stockapp_run()


