#!/usr/bin/env python
import time
from collections import Counter
from pprint import pprint
import json
import logging
from argparse import ArgumentParser
from datetime import datetime, timedelta
from urllib.request import urlopen
import re
from grab.error import GrabNetworkError

import telebot
from grab import Grab

HELP = """*UFO Price Bot*

This simple telegram bot displays price of UFO coin in BTC, USD and other fiat currrencies.

*Commands*

/help - display this help message
/ufoprice - display price
/ufoprice <currency> - display price in USD and also in specified currency.
/ufoprice <int>% - display price and also price increased/decreased by fee. Fee could be negative. Example: `/price 2%`

You can combine currency and fee arguments e.g. `/ufoprice rub 3%`.

List of supported currencies: AUD, BRL, CAD, CHF, CLP, CNY, CZK, DKK, EUR, GBP, HKD, HUF, IDR, ILS, INR, JPY, KRW, MXN, MYR, NOK, NZD, PHP, PKR, PLN, RUB, SEK, SGD, THB, TRY, TWD, ZAR.

*Open Source*

The source code is available at [github.com/lorien/ufoprice_bot](https://github.com/lorien/ufoprice_bot)
You can contact author via telegram @madspectator

*Donations are welcome*

UFO: CAdfaUR3tqfumoN7vQMVZ98CakyywgwK1L
Ethereum: 0x00D0c93B180452a7c7B70F463aD9D24d9C6d4d61
"""
NET_TIMEOUT = 3
CAP_CURRENCY_LIST = (
    "AUD", "BRL", "CAD", "CHF", "CLP", "CNY", "CZK", "DKK",
    "EUR", "GBP", "HKD", "HUF", "IDR", "ILS", "INR", "JPY",
    "KRW", "MXN", "MYR", "NOK", "NZD", "PHP", "PKR", "PLN",
    "RUB", "SEK", "SGD", "THB", "TRY", "TWD", "ZAR" 
)
CACHE = {}
CACHE_TIMEOUT = 60
NET_RETRIES = 5
FIAT_DECIMALS = 5


def load_json(url):
    data = Grab(timeout=NET_TIMEOUT).go(url).unicode_body()
    return json.loads(data)


def load_btc_usd_price():
    url = 'https://api.bitfinex.com/v1/pubticker/btcusd'
    data = load_json(url)
    return float(data['last_price'])


def load_ufo_cap_data(currency=None):
    url = 'https://api.coinmarketcap.com/v1/ticker/ufo-coin/'
    if currency:
        url += '?convert=%s' % currency
    data = None
    if url in CACHE:
        time_, data = CACHE[url]
        if time.time() - time_ > CACHE_TIMEOUT:
            data = None
            logging.debug('Cached data is outdated')
        else:
            logging.debug('Using cached data')
    if data is None:
        logging.debug('Updating cached data')
        for x in range(NET_RETRIES):
            try:
                data = load_json(url)
            except GrabNetworkError:
                if x >= NET_RETRIES - 1:
                    raise
                else:
                    logging.warning('Network Error. Retrying.')
            else:
                data = data[0]
                CACHE[url] = (time.time(), data)
    return data


def format_float(val, round_digits=None, fee=0):
    if fee:
        val = (val * (100 + fee)) / 100
    if round_digits is not None:
        val = ('%%.%df' % round_digits) % val
    else:
        val = '%.20f' % val
    if '.' in val:
        val = val.rstrip('0')
        if val.endswith('.'):
            val = val.rstrip('.')
    return val


def format_price_msg(fee=0, extra_currency=None):
    assert extra_currency is None or extra_currency.upper() in CAP_CURRENCY_LIST
    btc_usd = load_btc_usd_price()
    data = load_ufo_cap_data()
    ufo_btc = float(data['price_btc'])
    ufo_usd = float(data['price_usd'])
    if extra_currency:
        cur_data = load_ufo_cap_data(extra_currency)
        ufo_cur = float(cur_data['price_%s' % extra_currency])

    line = [
        "Price: " +
        "%s BTC" % format_float(ufo_btc, None),
        "%s USD" % format_float(ufo_usd, FIAT_DECIMALS),
    ]
    if extra_currency:
        line.append(
            "%s %s" % (format_float(ufo_cur, FIAT_DECIMALS), extra_currency.upper())
        )
    lines = [line]
    if fee:
        sign = '+' if fee else '-'
        line = [
            ('With fee %s%d%%: ' % (sign, fee)) +
            "%s BTC" % format_float(ufo_btc, round_digits=None, fee=fee),
            "%s USD" % format_float(ufo_usd, round_digits=FIAT_DECIMALS, fee=fee),
        ]
        if extra_currency:
            line.append(
                "%s %s" % (
                    format_float(ufo_cur, round_digits=FIAT_DECIMALS, fee=fee),
                    extra_currency.upper()
                )
            )
        lines.append(line)
    line3 = [
        "Volume 24h: %s USD" % format_float(float(data['24h_volume_usd']), 0),
    ]
    line4 = [
        "Price change: " +
        "1h (%s%%)" % format_float(float(data['percent_change_1h']), 2),
        "24h (%s%%)" % format_float(float(data['percent_change_24h']), 2),
        "7d (%s%%)" % format_float(float(data['percent_change_7d']), 2),
    ]
    lines.extend([line3, line4])

    return '\n'.join([', '.join(x) for x in lines])


def create_bot(api_token):
    bot = telebot.TeleBot(api_token)

    @bot.message_handler(commands=['start', 'help'])
    def handle_start_help(msg):
        bot.reply_to(msg, HELP, parse_mode='Markdown')

    @bot.message_handler(commands=['ufoprice'])
    def handle_price(msg):
        """Process /price command

        Command could be:
        /price
        /price 2%
        price rub -2%
        """

        fail = False
        parts = [x.strip() for x in msg.text.lower().split() if x.strip()]
        parts = parts[1:]
        if any(x.upper() in CAP_CURRENCY_LIST for x in parts):
            extra_currency = [x for x in parts if x.upper() in CAP_CURRENCY_LIST][0]
            parts.remove(extra_currency)
        else:
            extra_currency=None
        fee = 0
        if parts:
            part = parts.pop()
            if not re.match(r'^(\+|\-)?\d+%$', part):
                fail = True
            else:
                fee = int(part.rstrip('%'))
        if parts:
            fail = True
        if fail:
            bot.reply_to(msg, 'Invalid command. See /help')
        else:
            try:
                ret = format_price_msg(fee=fee, extra_currency=extra_currency)
                bot.reply_to(msg, ret)
            except Exception as ex:
                ret = 'Internal Bot Error: %s' % str(ex)
                bot.reply_to(msg, ret)
                raise

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
