import os
import pandas as pd 
import numpy as np 
import math 
from telegram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import asyncio
import requests 
from datetime import datetime, timedelta 
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import openai
import pickle

# Your bot token and channel ID
BOT_TOKEN = "<MAKSED>"  # Replace with your bot token
CHANNEL_ID = "<MASKED>"  # Replace with your channel ID

# Initialize bot
bot = Bot(token=BOT_TOKEN) 

# Initialize openai api 
openai.api_key = "openaikey" 

################ Error Handling for Fetching Data ################
def fetch_with_retries(url, params, retries=5, delay=5):
    for i in range(retries):
        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                return response.json()
            else:
                logging.error(f"Failed to fetch data from {url}. Status code: {response.status_code}")
        except Exception as e:
            logging.error(f"Attempt {i+1}: Error fetching data from {url}: {e}")
            time.sleep(delay)
    raise Exception(f"Failed to fetch data after {retries} attempts")


################ FEAR GREED ################
def get_fear_greed_index():
    def fetch_fng_data():
        url_fng = "https://api.alternative.me/fng/"
        params_fng = {"limit": 3, "date_format": "us"}
        try:
            # Fetch data using the fetch_with_retries function
            data_fng = fetch_with_retries(url_fng, params_fng)
            return data_fng.get('data', [])
        except Exception as e:
            logging.error(f"Failed to fetch Fear & Greed Index data: {e}")
            return []

    def fetch_global_data():
        url_global = "https://api.coinlore.net/api/global/"
        params_global = {}
        try:
            # Fetch data using the fetch_with_retries function
            data_global = fetch_with_retries(url_global, params_global)
            return data_global
        except Exception as e:
            logging.error(f"Failed to fetch global crypto data: {e}")
            return {}

    # Fetch Fear & Greed and global crypto data
    fear_greed, global_data = fetch_fng_data(), fetch_global_data()

    def format_fear_greed_data(fear_greed):
        formatted_data = "Fear & Greed Index (past 3 days):\n"
        for entry in fear_greed:
            formatted_data += (f"Date: {entry['timestamp']}, Value: {entry['value']}, "
                               f"Classification: {entry['value_classification']}\n")
        return formatted_data

    def format_global_data(global_data):
        formatted_data = "Global Crypto Data:\n"
        if global_data:
            entry = global_data[0]
            formatted_data += (f"Coins Count: {entry['coins_count']}\n"
                               f"Active Markets: {entry['active_markets']}\n"
                               f"Total Market Cap: ${entry['total_mcap']:,.2f}\n"
                               f"Total Volume: ${entry['total_volume']:,.2f}\n"
                               f"BTC Dominance: {entry['btc_d']}%\n"
                               f"ETH Dominance: {entry['eth_d']}%\n"
                               f"Market Cap Change: {entry['mcap_change']}%\n"
                               f"Volume Change: {entry['volume_change']}%\n"
                               f"Avg Change Percent: {entry['avg_change_percent']}%\n"
                               f"Volume ATH: ${entry['volume_ath']:,.2f}\n"
                               f"Market Cap ATH: ${entry['mcap_ath']:,.2f}\n")
        return formatted_data
    # Format the fetched data
    formatted_fng_data = format_fear_greed_data(fear_greed)
    formatted_global_data = format_global_data(global_data)
    return formatted_fng_data + "\n" + formatted_global_data

################ coinness News ################ 
# Set up the webdriver options for headless Chrome
def create_webdriver():
    try:
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver
    except Exception as e:
        logging.error(f"Failed to create WebDriver: {e}") 
        return None 

def can_click_more(driver):
    try:
        more_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, '//*[@id="root"]/div/div[2]/div[3]/button')))
        more_button.click()
        return True
    except (Exception):
        return False

def collect_latest_news(driver, limit=30):
    news_data = []
    try:
        while len(news_data) < limit:
            WebDriverWait(driver, 10).until(
                EC.visibility_of_all_elements_located((By.XPATH, '//div[contains(@class, "NewsWrap-sc")]')))
            news_items = driver.find_elements(By.XPATH, '//div[contains(@class, "NewsWrap-sc")]')
            for item in news_items:
                datetime_str = item.find_element(By.XPATH, './/div[contains(@class, "TimeDisplay-sc")]').text.replace('\n', ' ')
                header = item.find_element(By.XPATH, './/h3[contains(@class, "Header-sc")]').text
                content = item.find_element(By.XPATH, './/div[contains(@class, "ContentsWrap-sc")]').text
                news_data.append({'datetime': datetime_str, 'header': header, 'content': content})
                if len(news_data) >= limit:
                    break
            if not can_click_more(driver):
                break
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        driver.quit()

    aggregated_text = ""
    for news in news_data:
        aggregated_text += f"Title: {news['header']}\nContent: {news['content']}\nDatetime: {news['datetime']}\n\n"

    return aggregated_text 


################ generate analysis ################ 
def generate_analysis(news, chart_data, ticker="Bitcoin", ticker_symbol="BTC"):
    prompt = f"""
    You are an expert in cryptocurrency. Based on the following information, provide a detailed analysis and the current market situation of {ticker} ({ticker_symbol}) in English.

    Instead of simply showing the exchange price fluctuations and trading volume over the last N days, summarize the data and explain any outliers if they exist. Alternatively, you should predict the direction based on this data. In other words, use chart trends and recent news to logically predict the direction for the next week and month, and provide a reasonable explanation based on the chart and news as to why you reached that conclusion. When summarizing the news, don't make it too brief; ensure that it's filled with key information from an investor's perspective. The predictions for the next week and month should be proven with the most logical evidence, not just by looking at the chart.

    and the response must not exceed 2048 characters in total.

    Here is the most recent daily chart trend of {ticker} on the exchange:
    {chart_data}

    Here is the most recent news related to {ticker}:
    {news}
    """
    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[
          {"role": "system", "content": "You are an expert in cryptocurrency."},
          {"role": "user", "content": prompt}
        ],
    )
    return response["choices"][0]["message"]["content"]  


################ get price function ################ 
def get_mexc_ohlcv(symbol="BTC_USDT", interval="1d", limit=30, ret_str=False):
    """
    Fetches OHLCV data from MEXC using retries.
    symbol: the trading pair, e.g., "BTCUSDT"
    interval: the candlestick interval (e.g., '1m', '5m', '1h', '1d')
    limit: number of candlesticks to fetch (max 1000)
    """
    url = f"https://www.mexc.com/open/api/v2/market/kline"
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }
    try:
        # Fetch data using the fetch_with_retries function
        data = fetch_with_retries(url, params)
        df = pd.DataFrame(data["data"], columns=["timestamp", "open", "high", "low", "close", "volume", "QuoteAssetVolume"])
        df.drop(columns={"QuoteAssetVolume"}, inplace=True)

        # Convert the timestamp to a readable date
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')

        # Convert numeric columns to floats
        df[["open", "high", "low", "close", "volume"]] = df[["open", "high", "low", "close", "volume"]].astype(float)
        
        # If ret_str is True, format the data as a string
        if ret_str:
            chart_data = "" 
            for row in df.itertuples():
                chart_data += f"Date: {row.timestamp.date()}, Open: {row.open}, High: {row.high}, Low: {row.low}, Close: {row.close}, Volume: {row.volume}\n" 
            return chart_data
        return df
    except Exception as e:
        logging.error(f"Error in get_mexc_ohlcv: {e}")
        raise

# Function to send a test message every 30 seconds
async def send_analyst_message():
    # send today's date 
    current_date = datetime.now().strftime("%B %d, %Y")
    message = f"===================== {current_date} Report ====================="
    await bot.send_message(chat_id=CHANNEL_ID, text=message)
    await asyncio.sleep(1) 
    
    # send fear greed information 
    fear_greed_info = get_fear_greed_index() 
    await bot.send_message(chat_id=CHANNEL_ID, text=fear_greed_info) 
    await asyncio.sleep(1) 
    
    # Fetch BTC news and analysis
    driver = create_webdriver()
    driver.get('https://coinness.com/search?q=BTC&category=news')
    latest_btc_news = collect_latest_news(driver, limit=30) 
    latest_btc_chart = get_mexc_ohlcv(symbol="BTC_USDT", interval="1d", limit=7, ret_str=True)  
    btc_analysis = generate_analysis(latest_btc_news, latest_btc_chart, "Bitcoin", "BTC")[:4096] # limit to first 4096 characters
    btc_analysis = "💰💰 BTC Analysis 💰💰 \n\n" + btc_analysis  
    await bot.send_message(chat_id=CHANNEL_ID, text=btc_analysis)  
    await asyncio.sleep(1) 
    
    # Fetch ETH news and analysis 
    driver = create_webdriver()  # Create a new driver instance
    driver.get('https://coinness.com/search?q=ETH&category=news')
    latest_eth_news = collect_latest_news(driver, limit=30) 
    latest_eth_chart = get_mexc_ohlcv(symbol="ETH_USDT", interval="1d", limit=7, ret_str=True) 
    eth_analysis = generate_analysis(latest_eth_news, latest_eth_chart, "Ethereum", "ETH")[:4096]  
    eth_analysis = "💰💰 ETH Analysis 💰💰 \n\n" + eth_analysis 
    await bot.send_message(chat_id=CHANNEL_ID, text=eth_analysis) 
    await asyncio.sleep(1) 
    
    # Fetch SOL news and analysis 
    driver = create_webdriver() 
    driver.get('https://coinness.com/search?q=SOL&category=news') 
    latest_sol_news = collect_latest_news(driver, limit=30) 
    latest_sol_chart = get_mexc_ohlcv(symbol="SOL_USDT", interval="1d", limit=7, ret_str=True)  
    sol_analysis = generate_analysis(latest_sol_news, latest_sol_chart, "Solana", "SOL")[:4096]  
    sol_analysis = "💰💰 SOL Analysis 💰💰 \n\n" + sol_analysis  
    driver.quit()
    await bot.send_message(chat_id=CHANNEL_ID, text=sol_analysis) 
    await asyncio.sleep(1) 
    
    # get daily directional prediction  
    with open("telegram_best_xgb_model.pkl", "rb") as f:
        loaded_model = pickle.load(f)
    
    btc_df = get_mexc_ohlcv(symbol="BTC_USDT", interval="1d", limit=30, ret_str=False) 
    # Convert timestamps to datetime
    btc_df['timestamp'] = pd.to_datetime(btc_df['timestamp'], unit='ms')
    btc_df["timestamp"] = pd.to_datetime(btc_df["timestamp"])
    btc_df["month"] = btc_df["timestamp"].dt.month
    btc_df["day"] = btc_df["timestamp"].dt.day
    btc_df["weekday"] = btc_df["timestamp"].dt.weekday
    # Calculate rolling means and ratios
    for column in ['low', 'high', 'open', 'close']:
        btc_df[f'rolling_mean_7d_{column}'] = btc_df[column].rolling(window=7).mean()
        btc_df[f'ratio_{column}'] = btc_df[column] / btc_df[f'rolling_mean_7d_{column}']
    # Drop the rows with NaN values created by the rolling window
    btc_df = btc_df.dropna()
    # Select the final features
    features = ['month', 'day', 'weekday', 'ratio_low', 'ratio_high', 'ratio_open', 'ratio_close']
    btc_df = btc_df[features]
    test_input = btc_df.iloc[-1].values.reshape((-1, len(features)))
    # Predict
    est_predicted_probability = loaded_model.predict_proba(test_input)[0]
    btc_forecast_message = "📈📈 (ML Based) Bitcoin Directional Forecast: Tomorrow's Close from Today's Data: " + f"\nlong: {est_predicted_probability[0]*100:.2f}% | short: {est_predicted_probability[1]*100:.2f}%" 
    await bot.send_message(chat_id=CHANNEL_ID, text=btc_forecast_message) 
    await asyncio.sleep(1) 
    
    eth_df = get_mexc_ohlcv(symbol="ETH_USDT", interval="1d", limit=30, ret_str=False) 
    # Convert timestamps to datetime
    eth_df['timestamp'] = pd.to_datetime(eth_df['timestamp'], unit='ms')
    eth_df["timestamp"] = pd.to_datetime(eth_df["timestamp"])
    eth_df["month"] = eth_df["timestamp"].dt.month
    eth_df["day"] = eth_df["timestamp"].dt.day
    eth_df["weekday"] = eth_df["timestamp"].dt.weekday
    # Calculate rolling means and ratios
    for column in ['low', 'high', 'open', 'close']:
        eth_df[f'rolling_mean_7d_{column}'] = eth_df[column].rolling(window=7).mean()
        eth_df[f'ratio_{column}'] = eth_df[column] / eth_df[f'rolling_mean_7d_{column}']
    # Drop the rows with NaN values created by the rolling window
    eth_df = eth_df.dropna()
    # Select the final features
    features = ['month', 'day', 'weekday', 'ratio_low', 'ratio_high', 'ratio_open', 'ratio_close']
    eth_df = eth_df[features]
    test_input = eth_df.iloc[-1].values.reshape((-1, len(features)))
    # Predict
    eth_est_predicted_probability = loaded_model.predict_proba(test_input)[0]
    eth_forecast_message = "📈📈 (ML Based) Ethereum Directional Forecast: Tomorrow's Close from Today's Data: " + f"\nlong: {eth_est_predicted_probability[0]*100:.2f}% | short: {eth_est_predicted_probability[1]*100:.2f}%" 
    await bot.send_message(chat_id=CHANNEL_ID, text=eth_forecast_message) 
    await asyncio.sleep(1) 
    
    sol_df = get_mexc_ohlcv(symbol="SOL_USDT", interval="1d", limit=30, ret_str=False)  
    # Convert timestamps to datetime
    sol_df['timestamp'] = pd.to_datetime(sol_df['timestamp'], unit='ms')
    sol_df["timestamp"] = pd.to_datetime(sol_df["timestamp"])
    sol_df["month"] = sol_df["timestamp"].dt.month
    sol_df["day"] = sol_df["timestamp"].dt.day
    sol_df["weekday"] = sol_df["timestamp"].dt.weekday
    # Calculate rolling means and ratios
    for column in ['low', 'high', 'open', 'close']:
        sol_df[f'rolling_mean_7d_{column}'] = sol_df[column].rolling(window=7).mean()
        sol_df[f'ratio_{column}'] = sol_df[column] / sol_df[f'rolling_mean_7d_{column}']
    # Drop the rows with NaN values created by the rolling window
    sol_df = sol_df.dropna()
    # Select the final features
    features = ['month', 'day', 'weekday', 'ratio_low', 'ratio_high', 'ratio_open', 'ratio_close']
    sol_df = sol_df[features]
    test_input = sol_df.iloc[-1].values.reshape((-1, len(features)))
    # Predict
    sol_est_predicted_probability = loaded_model.predict_proba(test_input)[0]
    sol_forecast_message = "📈📈 (ML Based) Solana Directional Forecast: Tomorrow's Close from Today's Data: " + f"\nlong: {sol_est_predicted_probability[0]*100:.2f}% | short: {sol_est_predicted_probability[1]*100:.2f}%" 
    await bot.send_message(chat_id=CHANNEL_ID, text=sol_forecast_message) 
    await asyncio.sleep(1) 
     
    
# Function to schedule the message at 30-second intervals
def schedule_analyst_message():
    scheduler = AsyncIOScheduler()
    # Schedule the job to run every 30 seconds
    # scheduler.add_job(send_analyst_message, 'cron', hour=0, minute=0) 
    scheduler.add_job(send_analyst_message, 'interval', seconds=70)
    scheduler.start()

# Main function to start the bot and scheduler
async def main():
    schedule_analyst_message()
    # Keep the program running
    while True:
        await asyncio.sleep(3600)

# Run the bot
if __name__ == "__main__":
    asyncio.run(main())
