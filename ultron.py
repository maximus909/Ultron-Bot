import os
import json
import time
import numpy as np
import pandas as pd
from web3 import Web3
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
from telegram import Bot
import logging
import requests
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(filename='ultron.log', level=logging.INFO, format='%(asctime)s - %(message)s')

# Load secrets
RPC_URLS = {
    "ETH": os.getenv("ETH_RPC"),
    "ARBITRUM": os.getenv("ARBITRUM_RPC"),
    "BSC": os.getenv("BSC_RPC"),
    "POLYGON": os.getenv("POLYGON_RPC"),
}

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")

# ✅ Initialize Web3 connections (FIXED)
w3 = {}
for chain, rpc in RPC_URLS.items():
    try:
        if rpc:
            provider = Web3.HTTPProvider(rpc)
            w3[chain] = Web3(provider)
            if w3[chain].is_connected():
                logging.info(f"✅ {chain} RPC connected successfully.")
            else:
                logging.info(f"⚠️ {chain} RPC failed to connect.")
                del w3[chain]
    except Exception as e:
        logging.info(f"❌ Error connecting to {chain} RPC: {e}")
        del w3[chain]

if not w3:
    logging.info("❌ CRITICAL ERROR: No working RPC connections. Exiting bot.")
    sys.exit(1)
else:
    logging.info("🚀 Ultron started successfully!")

# Telegram integration
telegram_bot = Bot(token=TELEGRAM_BOT_TOKEN)

def send_telegram(message):
    try:
        telegram_bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except Exception as e:
        logging.info(f"❌ Telegram error: {e}")

# GitHub integration
def save_report(data):
    try:
        url = f"https://api.github.com/repos/{os.getenv('GITHUB_REPO')}/contents/report.json"
        headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            sha = response.json().get("sha")
            content = json.dumps(data, indent=4)
            payload = {
                "message": "Update report",
                "content": content.encode("base64").decode("utf-8"),
                "sha": sha
            }
            requests.put(url, headers=headers, json=payload)
            logging.info("✅ Report saved to GitHub.")
    except Exception as e:
        logging.info(f"❌ GitHub error: {e}")

# AI model
class AITrader:
    def __init__(self):
        self.model = RandomForestClassifier(n_estimators=100)
        self.data = []
        self.labels = []

    def train(self):
        if len(self.data) >= 1000:
            X_train, X_test, y_train, y_test = train_test_split(self.data, self.labels, test_size=0.2)
            self.model.fit(X_train, y_train)
            accuracy = accuracy_score(y_test, self.model.predict(X_test))
            send_telegram(f"🤖 Model retrained! Accuracy: {accuracy*100:.2f}%")

    def predict(self, tx_data):
        try:
            prediction = self.model.predict([tx_data])[0]
            self.data.append(tx_data)
            self.labels.append(prediction)
            return prediction == 1
        except Exception as e:
            logging.info(f"❌ Prediction failed: {e}")
            return False

# Trade execution
def fetch_mempool(chain):
    if chain not in w3:
        return None
    try:
        pending_block = w3[chain].eth.get_block('pending', full_transactions=True)
        txs = []
        for tx in pending_block.transactions:
            txs.append([tx['value'], tx['gasPrice'], tx['gas'], tx.get('maxFeePerGas', 0)])
        return np.array(txs)
    except Exception as e:
        logging.info(f"❌ Mempool error: {e}")
        return None

def execute_trade(chain, tx_data):
    try:
        account = w3[chain].eth.account.from_key(PRIVATE_KEY)
        tx = {
            'to': account.address,  # Replace with actual trade logic
            'value': tx_data[0],
            'gas': int(tx_data[2]),
            'gasPrice': int(tx_data[1]),
            'nonce': w3[chain].eth.get_transaction_count(account.address),
            'chainId': w3[chain].eth.chain_id
        }
        signed_tx = account.sign_transaction(tx)
        tx_hash = w3[chain].eth.send_raw_transaction(signed_tx.rawTransaction)
        send_telegram(f"✅ Trade executed: {tx_hash.hex()}")
    except Exception as e:
        logging.info(f"❌ Trade failed: {e}")

# Main loop
def run():
    ai = AITrader()
    while True:
        for chain in w3.keys():
            txs = fetch_mempool(chain)
            if txs is not None:
                for tx in txs:
                    if ai.predict(tx):
                        execute_trade(chain, tx)
        time.sleep(300)

if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        send_telegram(f"❌ Ultron crashed: {e}")
        sys.exit(1)
