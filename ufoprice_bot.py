#!/usr/bin/env python
from collections import Counter
from pprint import pprint
import json
import logging
import telebot
from argparse import ArgumentParser
from datetime import datetime, timedelta
from urllib.request import urlopen
from grab import Grab

HELP = """*UFO Price Bot*

This simple telegram bot displays price of UFO coin in BTC, USD and rubles.

*Commands*

/help - display this help message
/price - display UFO coin price information

*Open Source*

The source code is available at [github.com/lorien/ufoprice_bot](https://github.com/lorien/ufoprice_bot)
You can contact author of the bot at @madspectator
"""

"""
) курс биткоина на bittrex - https://bittrex.com/Market/Index?MarketName=USDT-BTC
2) курс ПРОДАЖИ ufo на коинэкчендж - https://www.coinexchange.io/market/UFO/BTC столбик SELL
3) курс рубля (сейчас считаю по 58р)
4) моя комиссия 10%
Вот эти 4 цифры перемножаем - получаем текущую цену
"""
#COINEXCHANGE_UFO_ID = 209
#COINEXCHANGE_UFO_ASSET_ID = 177


def load_json(url):
    data = Grab(timeout=3).go(url).unicode_body()
    return json.loads(data)


def load_btc_usd_price():
    url = 'https://api.bitfinex.com/v1/pubticker/btcusd'
    data = load_json(url)
    return float(data['last_price'])


def load_ufo_btc_price():
    url = 'https://176.9.8.28/api/v1/getmarketsummary?market_id=209'
    #data = load_json(url)
    #data = json.loads('{"success":"1","request":"\/api\/v1\/getmarket","message":"","result":{"MarketID":"209","LastPrice":"0.00000030","Change":"-6.25","HighPrice":"0.00000038","LowPrice":"0.00000026","Volume":"4.40410871","BTCVolume":"4.40410871","TradeCount":"416","BidPrice":"0.00000030","AskPrice":"0.00000031","BuyOrderCount":"279","SellOrderCount":"914"}}')
    g = Grab(timeout=3, headers={'Host': 'www.coinexchange.io'})
    g.go(url)
    try:
        data = g.doc.json
    except Exception:
        print('invalid data', g.doc.unicode_body())
        raise
    return float(data['result']['AskPrice'])


def load_usd_rub_price():
    url = 'http://www.cbr.ru/scripts/XML_daily_eng.asp'
    g = Grab(timeout=3)
    g.go(url)
    val = g.doc('//valute[@id="R01235"]/value/text()').text()
    return float(val.replace(',', '.'))


def format_float(val, round_digits=None):
    if round_digits:
        val = ('%%.%df' % round_digits) % val
    else:
        val = '%.20f' % val
    if '.' in val:
        val = val.rstrip('0')
        if val.endswith('.'):
            val = val.rstrip('.')
    return val


def format_price_msg(fee=0):
    btc_usd = load_btc_usd_price()
    ufo_btc = load_ufo_btc_price()
    usd_rub = load_usd_rub_price()
    ufo_rub = ufo_btc * btc_usd * usd_rub
    ret = ""
    ret += "BTC USD: %s\n"
    ret += "UFO BTC: %s\n"
    ret += "USD RUB: %s\n"
    ret += "UFO RUB: %s"
    ret = ret % (
        format_float(btc_usd, 2),
        format_float(ufo_btc, None),
        format_float(usd_rub, 2),
        format_float(ufo_rub, 3)
    )
    if fee:
        sign = '+' if fee else '-'
        ufo_rub_fee = (ufo_rub * (100 + fee)) / 100
        ret += '\nUFO RUB (%s%d%%): %s' % (
            sign, fee, format_float(ufo_rub_fee, 3)
        )
    return ret


def create_bot(api_token):
    bot = telebot.TeleBot(api_token)

    @bot.message_handler(commands=['start', 'help'])
    def handle_start_help(msg):
        bot.reply_to(msg, HELP, parse_mode='Markdown')

    @bot.message_handler(commands=['price'])
    def handle_price(msg):
        tail = msg.text.split('/price')[1].strip()
        if not tail:
            tail = '0%'
        if not tail.endswith('%'):
            bot.reply_to(msg, 'Invalid command')
        else:
            try:
                fee = int(tail.rstrip('%'))
            except ValueError:
                bot.reply_to(msg, 'Invalid command')
            else:
                ret = format_price_msg(fee)
                bot.reply_to(msg, ret)

    return bot


def main():
    parser = ArgumentParser()
    parser.add_argument('--mode')
    opts = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG)
    with open('var/config.json') as inp:
        config = json.load(inp)
    if opts.mode == 'test':
        token = config['test_api_token']
    else:
        token = config['api_token']
    bot = create_bot(token)
    bot.polling()


if __name__ == '__main__':
    main()
