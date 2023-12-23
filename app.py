import backtrader as bt
import pandas as pd
import schedule
import os
import requests
import datetime
import time
import signal
from flask import *
from datetime import datetime, timedelta
from dotenv import load_dotenv
from io import BytesIO
import boto3
from mysql.connector import pooling
import matplotlib.pyplot as plt
from backtrader.indicators import EMA
from threading import Thread 
import matplotlib
matplotlib.use('Agg')

load_dotenv()

app = Flask(__name__, static_folder="public")
app.config["JSON_AS_ASCII"] = False
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.json.ensure_ascii = False
token = os.environ["token"]

dbconfig = {
    "host": os.getenv("DB_HOST"),  
    "user": os.getenv("DB_USER"),  
    "password": os.getenv("DB_PASSWORD"), 
    "database": os.getenv("DB_DATABASE"),
}
db_pool= pooling.MySQLConnectionPool(pool_name="mypool", pool_size=13, **dbconfig)

aws_access_key_id = os.environ['AWS_ACCESS_KEY_ID']
aws_secret_access_key = os.environ['AWS_SECRET_ACCESS_KEY']
region_name = os.environ.get('AWS_REGION')
bucket_name = 'messageboard-image1'
s3_folder = 'tradeoutput/'
s3 = boto3.client('s3',
                 aws_access_key_id=aws_access_key_id,
                 aws_secret_access_key=aws_secret_access_key,
                 region_name=region_name)

def Get_StockTop(Date):
    url = f'https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX20?date={Date}&response=json'
    data = requests.get(url).text
    json_data = json.loads(data)
    today_date = datetime.now().strftime('%Y-%m-%d')
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    # stock_data = [[row[0], row[1], row[2], today_date] for row in json_data['data']]
    # print(stock_data)
    cnx = db_pool.get_connection()
    cursor = cnx.cursor()
    check_sql = "SELECT COUNT(*) FROM top WHERE date = %s"
    cursor.execute(check_sql, (today_date,))
    count = cursor.fetchone()[0]


    if count > 0:
        # cursor.close()
        # cnx.close()
        print("今日已加入新熱門股資料，不再加入")
        return "今日已加入新熱門股資料，不再加入"

    try:
        if 'data' not in json_data:
            print("查無今日熱門股資料")
            return "查無今日熱門股資料"
        
        for row in json_data['data']:
            top_data=row[0], row[1], row[2], today_date
            print(top_data)

            sql = "INSERT INTO top (stock_top, code, name, date) VALUES (%s, %s, %s, %s)"
            cursor.execute(sql, top_data)
        cnx.commit()
        # print("INSERT INTO top Closing database connection.")
        # cursor.close()
        # cnx.close()
        print("成功加入新熱門股資料")
        return "成功加入新熱門股資料"
      
    finally:
            print("finally Closing database connection.")
            cursor.close()
            cnx.close()


def job():
    today = datetime.now().strftime("%Y%m%d")
    stock_data = Get_StockTop(today)
    print("stock_data:",stock_data)
    print("run_job")


is_exit = False
def run_scheduling():
    while True:
        if is_exit:
           break  
        schedule.run_pending()
        time.sleep(1)

#AWS("09:00") TW(17:00)
schedule.every().day.at("09:50").do(job)  


thread = Thread(target=run_scheduling)
thread.start()

def signal_handler(sig, frame):
    print("Received Ctrl+C, exiting gracefully")
    global is_exit
    print("Exiting")  
    is_exit = True
    schedule.clear()
    exit(0)

signal.signal(signal.SIGINT, signal_handler)

class TestStrategy(bt.Strategy):
        params = (("maperiod", 15),)

        def log(self, txt, dt=None):
            """Logging function fot this strategy"""
            dt = dt or self.datas[0].datetime.date(0)
            print("%s, %s" % (dt.isoformat(), txt))

        def __init__(self):
            self.trade_records = []
            # Keep a reference to the "close" line in the data[0] dataseries
            self.dataclose = self.datas[0].close

            # To keep track of pending orders and buy price/commission
            self.order = None
            self.buyprice = None
            self.buycomm = None
            self.buy_info_list = []  # 添加一个属性来存储买入信息
            self.sell_info_list = []  # 添加一个属性来存储卖出信息
            # Add a MovingAverageSimple indicator
            self.sma = bt.indicators.SimpleMovingAverage(
                self.datas[0], period=self.params.maperiod
            )

            # Indicators for the plotting show
            bt.indicators.ExponentialMovingAverage(self.datas[0], period=25)
            bt.indicators.WeightedMovingAverage(self.datas[0], period=25, subplot=True)
            bt.indicators.StochasticSlow(self.datas[0])
            bt.indicators.MACDHisto(self.datas[0])
            rsi = bt.indicators.RSI(self.datas[0])
            bt.indicators.SmoothedMovingAverage(rsi, period=10)
            bt.indicators.ATR(self.datas[0], plot=False)

        def notify_order(self, order):
            if order.status in [order.Submitted, order.Accepted]:
                # Buy/Sell order submitted/accepted to/by broker - Nothing to do
                return

            # Check if an order has been completed
            # Attention: broker could reject order if not enough cash
            if order.status in [order.Completed]:
                if order.isbuy():
                    self.log(
                        "BUY EXECUTED, Price: %.2f, Cost: %.2f, Comm %.2f"
                        % (order.executed.price, order.executed.value, order.executed.comm)
                    )
                    buy_info = {
                    "Date": self.data.datetime.datetime(0),
                    "Action": "BUY",
                    "Price": order.executed.price,
                    "Value": order.executed.value,
                    "Commission": order.executed.comm
                }
                    self.buyprice = order.executed.price
                    self.buycomm = order.executed.comm
                    self.buy_info_list.append(buy_info)
                    print("but info:",self.buy_info_list)
                else:  # Sell
                    self.log(
                        "SELL EXECUTED, Price: %.2f, Cost: %.2f, Comm %.2f"
                        % (order.executed.price, order.executed.value, order.executed.comm)
                    )
                    sell_info = {
                    "Date": self.data.datetime.datetime(0),
                    "Action": "SELL",
                    "Price": order.executed.price,
                    "Value": order.executed.value,
                    "Commission": order.executed.comm
                }
                    self.sell_info_list.append(sell_info)
                self.bar_executed = len(self)

            elif order.status in [order.Canceled, order.Margin, order.Rejected]:
                self.log("Order Canceled/Margin/Rejected")

            # Write down: no pending order
            self.order = None

        def notify_trade(self, trade):
            if not trade.isclosed:
                return

            self.log("OPERATION PROFIT, GROSS %.2f, NET %.2f" % (trade.pnl, trade.pnlcomm))

        def next(self):
            # Simply log the closing price of the series from the reference
            self.log("Close, %.2f" % self.dataclose[0])

            # Check if an order is pending ... if yes, we cannot send a 2nd one
            if self.order:
                return

            # Check if we are in the market
            if not self.position:
                # Not yet ... we MIGHT BUY if ...
                if self.dataclose[0] > self.sma[0]:
                    # BUY, BUY, BUY!!! (with all possible default parameters)
                    self.log("BUY CREATE, %.2f" % self.dataclose[0])

                    # Keep track of the created order to avoid a 2nd order
                    # self.order = self.buy()
                    self.order = self.buy(data=self.datas[0], exectype=bt.Order.Close)  
                    # 在觸發買入交易時順便收集交易紀錄
                    self.trade_records.append({
                        'action': 'BUY',
                        'price': self.dataclose[0],
                        # 'datetime': self.datas[0].datetime.datetime()
                        'datetime': self.datas[0].datetime.date().isoformat() 
                    })
                    print("self.trade_records:",self.trade_records)

            else:
                if self.dataclose[0] < self.sma[0]:
                    # SELL, SELL, SELL!!! (with all possible default parameters)
                    self.log("SELL CREATE, %.2f" % self.dataclose[0])

                    # Keep track of the created order to avoid a 2nd order
                    # self.order = self.sell()
                    self.order = self.sell(data=self.datas[0], exectype=bt.Order.Close)

                    # 在觸發賣出交易時順便收集交易紀錄
                    self.trade_records.append({
                    'action': 'SELL',
                    'price': self.dataclose[0],
                    # 'datetime': self.datas[0].datetime.datetime()
                    'datetime': self.datas[0].datetime.date().isoformat()  
                    })
                    print("self.trade_records:",self.trade_records)

class SmaStrategy(bt.Strategy):
    params =(
        ("exitbars",5),
        ("maperiod",15),
    )

    def __init__(self):
        self.executed_prices = []
        self.trade_records = []
        self.dataclose = self.datas[0].close
        self.order = None
        self.buyprice = None
        self.buycomm = None
        self.sma=bt.indicators.SimpleMovingAverage(self.datas[0],period=self.params.maperiod)
        bt.indicators.MACDHisto(self.datas[0])
        rsi = bt.indicators.RSI(self.datas[0])
        bt.indicators.SmoothedMovingAverage(rsi, period=10)
        bt.indicators.ATR(self.datas[0], plot=False)
    def notify_order(self,order):
        if order.status in[order.Submitted,order.Accepted]:
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                self.log("Buy Excuted{}".format(order.executed.price))
                self.executed_prices.append(order.executed.price) 
                self.trade_records.append({
                        'action': 'BUY',
                        'price': order.executed.price,

                        'datetime': self.datas[0].datetime.date().isoformat() 
                    })
                print("self.trade_records:",self.executed_prices)
            elif order.issell():
                self.log("Sell Excuted{}".format(order.executed.price))
                self.executed_prices.append(order.executed.price)  

                self.trade_records.append({
                    'action': 'SELL',
                    'price': order.executed.price,

                    'datetime': self.datas[0].datetime.date().isoformat() 
                })
                print("self.trade_records:",self.trade_records)
            self.bar_executed = len(self)

        elif order.status in [order.Canceled, order.Margin,order.Rejected]:
            self.log("Order Canceled/Margin/Rejected")
        
        self.order = None

    def next(self):
        self.log("close{}".format(self.dataclose[0]))
        if self.order:
            return

        if not self.position:
            if self.dataclose[0] < self.dataclose[-1]:
                if self.dataclose[-1] < self.dataclose[-2]:

                    self.order = self.buy(data=self.datas[0], exectype=bt.Order.Close)  


                    self.log("Buy Creat{}".format(self.dataclose[0]))

        else:
            if len(self) >= (self.bar_executed + self.params.exitbars):

                self.order = self.sell(data=self.datas[0], exectype=bt.Order.Close)

    def log(self, txt):
        dt = self.datas[0].datetime.date(0)
        print("{} {}".format(dt.isoformat(), txt))

class Kdstrategy(bt.Strategy):
    def log(self, txt, dt=None):
            ''' Logging function fot this strategy'''
            dt = dt or self.datas[0].datetime.date(0)
            print('%s, %s' % (dt.isoformat(), txt))

    def __init__(self):
            self.executed_prices = []
            self.trade_records = []
            self.dataclose = self.datas[0].close
            self.order = None
            self.buyprice = None
            self.buycomm = None
            self.kd = bt.indicators.StochasticSlow(self.datas[0], period = 9, period_dfast= 3, period_dslow = 3)

    def notify_order(self, order):
            if order.status in [order.Submitted, order.Accepted]:
                # Buy/Sell order submitted/accepted to/by broker - Nothing to do
                return

            # Check if an order has been completed
            # Attention: broker could reject order if not enough cash
            if order.status in [order.Completed]:
                if order.isbuy():
                    # self.log(
                    #     'BUY EXECUTED, Price: %.2f, Cost: %.2f, Comm %.2f' %
                    #     (order.executed.price,
                    #     order.executed.value,
                    #     order.executed.comm))

                    # self.buyprice = order.executed.price
                    # self.buycomm = order.executed.comm
                    self.log("Buy Excuted{}".format(order.executed.price))
                    self.trade_records.append({
                        'action': 'BUY',
                        'price': order.executed.price,
                        # 'datetime': self.datas[0].datetime.datetime()
                        'datetime': self.datas[0].datetime.date().isoformat()  
                    })
                    print("self.trade_records:",self.trade_records)

                else:  # Sell
                    # self.log('SELL EXECUTED, Price: %.2f, Cost: %.2f, Comm %.2f' %
                    #         (order.executed.price,
                    #         order.executed.value,
                    #         order.executed.comm))
                    self.log("Sell Excuted{}".format(order.executed.price))
                    self.trade_records.append({
                    'action': 'SELL',
                    'price': order.executed.price,
                    # 'datetime': self.datas[0].datetime.datetime()
                    'datetime': self.datas[0].datetime.date().isoformat()  
                })
                    print("self.trade_records:",self.trade_records)

                self.bar_executed = len(self)

            elif order.status in [order.Canceled, order.Margin, order.Rejected]:
                self.log('Order Canceled/Margin/Rejected')

            # Write down: no pending order
            self.order = None

    def notify_trade(self, trade):
            if not trade.isclosed:
                return

            self.log('OPERATION PROFIT, GROSS %.2f, NET %.2f' %
                    (trade.pnl, trade.pnlcomm))
    

    def next(self):
            # Simply log the closing price of the series from the reference
            self.log('Close, %.2f' % self.dataclose[0])

            # Check if an order is pending ... if yes, we cannot send a 2nd one
            if self.order:
                return

            # Check if we are in the market
            if not self.position:

                # Not yet ... we MIGHT BUY if ...
                if self.kd[-1] > 30 and self.kd[0] < 30 :

                    # BUY, BUY, BUY!!! (with all possible default parameters)
                    self.log('BUY CREATE, %.2f' % self.dataclose[0])

                    # Keep track of the created order to avoid a 2nd order
                    # self.order = self.buy(price=self.data.close[0])
                    self.order = self.buy(data=self.datas[0], exectype=bt.Order.Close)

                    # 在觸發買入交易時順便收集交易紀錄
                    # self.trade_records.append({
                    #     'action': 'BUY',
                    #     'price': self.dataclose[0],
                    #     # 'datetime': self.datas[0].datetime.datetime()
                    #     'datetime': self.datas[0].datetime.date().isoformat()  
                    # })
                    # print("self.trade_records:",self.trade_records)
            else:

                if self.kd[-1] < 90 and self.kd[0] > 90:
                    # SELL, SELL, SELL!!! (with all possible default parameters)
                    self.log('SELL CREATE, %.2f' % self.dataclose[0])

                    # Keep track of the created order to avoid a 2nd order
                    # self.order = self.sell(price=self.data.close[0])
                    self.order = self.sell(data=self.datas[0], exectype=bt.Order.Close)


                    # 在觸發賣出交易時順便收集交易紀錄
                #     self.trade_records.append({
                #     'action': 'SELL',
                #     'price': self.dataclose[0],
                #     # 'datetime': self.datas[0].datetime.datetime()
                #     'datetime': self.datas[0].datetime.date().isoformat()  
                # })
                #     print("self.trade_records:",self.trade_records)

   
class Blstrategy(bt.Strategy):
    #自訂一參數，每次買入100股
    # params=(('size',100),)
    def __init__(self):
        self.executed_prices = []
        self.trade_records = []
        self.dataclose=self.datas[0].close
        self.order=None
        self.buyprice=None
        self.buycomm=None
        ##使用自帶的indicators中自帶的函数計算出支撐線和壓力線，period設置週期，默認是20
        self.lines.top=bt.indicators.BollingerBands(self.datas[0],period=20).top
        self.lines.bot=bt.indicators.BollingerBands(self.datas[0],period=20).bot

    def notify_order(self,order):
        if order.status in[order.Submitted,order.Accepted]:
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                # self.log("Buy Excuted{}".format(order.executed.price))
                self.executed_prices.append(order.executed.price)  # 将执行价格添加到列表中

                self.trade_records.append({
                        'action': 'BUY',
                        'price': order.executed.price,
                        # 'datetime': self.datas[0].datetime.datetime()
                        'datetime': self.datas[0].datetime.date().isoformat() 
                    })
                print("self.trade_records:",self.executed_prices)
            elif order.issell():
                # self.log("Sell Excuted{}".format(order.executed.price))
                self.executed_prices.append(order.executed.price)  # 将执行价格添加到列表中

                self.trade_records.append({
                    'action': 'SELL',
                    'price': order.executed.price,
                    # 'datetime': self.datas[0].datetime.datetime()
                    'datetime': self.datas[0].datetime.date().isoformat() 
                })
                print("self.trade_records:",self.trade_records)
            self.bar_executed = len(self)

        # elif order.status in [order.Canceled, order.Margin,order.Rejected]:
        #     self.log("Order Canceled/Margin/Rejected")
        
        # self.order = None

    def next(self):
        if not self.position:
            if self.dataclose<=self.lines.bot[0]:
                #執行買入
                # self.order=self.buy()
                self.order = self.buy(data=self.datas[0], exectype=bt.Order.Close)

                # 在觸發買入交易時順便收集交易紀錄
                # self.trade_records.append({
                #     'action': 'BUY',
                #     'price': self.dataclose[0],
                #     # 'datetime': self.datas[0].datetime.datetime()
                #     'datetime': self.datas[0].datetime.date().isoformat()  
                # })
                # print("self.trade_records:",self.trade_records)
        else:
            if self.dataclose>=self.lines.top[0]:
                #執行賣出
                # self.order=self.sell()
                self.order = self.sell(data=self.datas[0], exectype=bt.Order.Close)
                # 在觸發賣出交易時順便收集交易紀錄
                # self.trade_records.append({
                #     'action': 'SELL',
                #     'price': self.dataclose[0],
                #     # 'datetime': self.datas[0].datetime.datetime()
                #     'datetime': self.datas[0].datetime.date().isoformat()  
                # })
                # print("self.trade_records:",self.trade_records)


class Macdstrategy(bt.Strategy):
    params = (
        ('maperiod', 15),
    )

    def log(self, txt, dt=None):
        ''' Logging function fot this strategy'''
        dt = dt or self.datas[0].datetime.date(0)
        print('%s, %s' % (dt.isoformat(), txt))

    # def percent(today, yesterday):
    #     return float(today - yesterday) / today

    def __init__(self):
        self.executed_prices = []
        self.trade_records = []
        self.dataclose = self.datas[0].close
        self.volume = self.datas[0].volume

        self.order = None
        self.buyprice = None
        self.buycomm = None

        me1 = EMA(self.data, period=12)
        me2 = EMA(self.data, period=26)
        self.macd = me1 - me2
        self.signal = EMA(self.macd, period=9)

        bt.indicators.MACDHisto(self.data)

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log("Buy Excuted{}".format(order.executed.price))
                self.executed_prices.append(order.executed.price)  # 將執行價格寫進列表
                # 在觸發買入交易時順便收集交易紀錄
                self.trade_records.append({
                    'action': 'BUY',
                    'price': self.dataclose[0],
                    # 'datetime': self.datas[0].datetime.datetime()
                    'datetime': self.datas[0].datetime.date().isoformat()  
                })
                print("self.trade_records:",self.trade_records)

                self.buyprice = order.executed.price
                self.buycomm = order.executed.comm
                self.bar_executed_close = self.dataclose[0]
            else:
                self.log("Sell Excuted{}".format(order.executed.price))
                self.executed_prices.append(order.executed.price)  # 將執行價格寫進列表
                # 在觸發賣出交易時順便收集交易紀錄
                self.trade_records.append({
                    'action': 'SELL',
                    'price': self.dataclose[0],
                    # 'datetime': self.datas[0].datetime.datetime()
                    'datetime': self.datas[0].datetime.date().isoformat()  
                })
                print("self.trade_records:",self.trade_records)

            self.bar_executed = len(self)

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('Order Canceled/Margin/Rejected')

        self.order = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return

        self.log('OPERATION PROFIT, GROSS %.2f, NET %.2f' %
                 (trade.pnl, trade.pnlcomm))

    def next(self):
        self.log('Close, %.2f' % self.dataclose[0])
        if self.order:
            return

        if not self.position:
            condition1 = self.macd[-1] - self.signal[-1]
            condition2 = self.macd[0] - self.signal[0]
            if condition1 < 0 and condition2 > 0:
                self.log('BUY CREATE, %.2f' % self.dataclose[0])
                # self.order = self.buy()
                self.order = self.buy(data=self.datas[0], exectype=bt.Order.Close)

                # 在觸發買入交易時順便收集交易紀錄
                # self.trade_records.append({
                #     'action': 'BUY',
                #     'price': self.dataclose[0],
                #     # 'datetime': self.datas[0].datetime.datetime()
                #     'datetime': self.datas[0].datetime.date().isoformat()  
                # })
                # print("self.trade_records:",self.trade_records)
        else:
            condition = (self.dataclose[0] - self.bar_executed_close) / self.dataclose[0]
            if condition > 0.1 or condition < -0.1:
                self.log('SELL CREATE, %.2f' % self.dataclose[0])
                # self.order = self.sell()
                self.order = self.sell(data=self.datas[0], exectype=bt.Order.Close)

                # 在觸發賣出交易時順便收集交易紀錄
                # self.trade_records.append({
                #     'action': 'SELL',
                #     'price': self.dataclose[0],
                #     # 'datetime': self.datas[0].datetime.datetime()
                #     'datetime': self.datas[0].datetime.date().isoformat()  
                # })
                # print("self.trade_records:",self.trade_records)



@app.route("/")
def index():
    return render_template("index.html")


@app.route("/backtest", methods=["POST"])
def backtest():
    
    data = request.get_json()
    print(data)

    symbol = data["symbol"]
    strategyname = data["strategy"]
    money = data["money"]
    commission = data["commission"]
    startDate = data["startDate"]
    endDate = data["endDate"]
    sharesPerTrade=data["sharesPerTrade"]
    # print("commission:",commission)
    def get_data(symbol,startDate,endDate):
        url = "https://api.finmindtrade.com/api/v4/data"
        parameter = {
            "dataset": "TaiwanStockPrice",
            "data_id": symbol,
            "start_date": startDate,
            "end_date": endDate,
            "token": token,
        }
        resp = requests.get(url, params=parameter)
        data = resp.json()
        price_tw = pd.DataFrame(data["data"])
        price_tw = price_tw.rename(columns={
        "date": "Datetime",
        "open": "Open",
        "max": "High",
        "min": "Low",
        "close": "Close",
        "Trading_Volume":"Volume"
        })
        price_tw = price_tw[["Datetime", "Open", "High", "Low", "Close", "Volume"]]
        price_tw["Datetime"] = pd.to_datetime(price_tw["Datetime"])
        price_tw.index = price_tw.Datetime
        return price_tw
    price_tw=get_data(symbol,startDate,endDate)
    print(price_tw)


    # -------------------------------

    def get_strategy(strategy):
            if strategy == "TestStrategy":
                return TestStrategy
            elif strategy == "SmaStrategy":
                return SmaStrategy
            elif strategy == "Kdstrategy":
                return Kdstrategy
            elif strategy =="Blstrategy":
                return Blstrategy
            elif strategy =="Macdstrategy":
                return Macdstrategy
            else:
                raise ValueError(f"Unknown strategy: {strategy}")


    # if __name__ == "__main__":
    cerebro = bt.Cerebro()
    def saveplots(cerebro, numfigs=1, iplot=False, start=None, end=None,
             width=16, height=9, dpi=200, tight=True, use=None, file_path = '', **kwargs):

        from backtrader import plot
        import matplotlib
        matplotlib.use('Agg')

        if cerebro.p.oldsync:
            plotter = plot.Plot_OldSync(**kwargs)
        else:
            plotter = plot.Plot(**kwargs)

        figs = []
        for stratlist in cerebro.runstrats:
            for si, strat in enumerate(stratlist):
                rfig = plotter.plot(strat, figid=si * 100,
                                    numfigs=numfigs, iplot=iplot,
                                    start=start, end=end, use=use)
                figs.append(rfig)

        # for fig in figs:
        #     for f in fig:
        #         f.set_size_inches(width, height)
        #         f.savefig(file_path, bbox_inches='tight',dpi=dpi)
        # return figs


        for fig in figs:
            for f in fig:
                
                img_buffer = BytesIO()
                f.set_size_inches(width, height)
                f.savefig(img_buffer, format='jpg')
                
                img_buffer.seek(0)
                print("img_buffer:",img_buffer.seek(0))
                current_time = datetime.now().strftime("%Y%m%d%H%M%S")
                filename = f"figure_{symbol}_{current_time}.jpg"
                s3_path = os.path.join(s3_folder, filename)
                # 上傳到 S3
                try:
                    s3.upload_fileobj(img_buffer, bucket_name, s3_path)
                    s3_url = f'https://d194z2ip41naor.cloudfront.net/{s3_path}'
                    print(f"S3 URL: {s3_url}")
                    return s3_url
                except Exception as e:
                    print(f"Error uploading to S3: {str(e)}")





    # cerebro.broker.set_cash(1000000)
    # start_cash = 1000000
    start_cash = int(money)
    cerebro.broker.setcash(start_cash) 
    # cerebro.broker.setcommission(commission=0.001)
    cerebro.broker.setcommission(commission=float(commission)) 
    # cerebro.broker.set_slippage_perc(perc=0)
    cerebro.addsizer(bt.sizers.FixedSize, stake=sharesPerTrade)
    print("sizer:",sharesPerTrade)
    print("commission:",commission)
    strategy = get_strategy(strategyname)
    cerebro.addstrategy(strategy)
    print("strategy:",strategy)
    data = bt.feeds.PandasData(dataname=price_tw)
    # data = bt.feeds.PandasData(dataname=yf.download('QQQ', '2020-01-01', '2023-12-31'))
    cerebro.adddata(data)
    # cerebro.addanalyzer(TimeReturn, timeframe=bt.TimeFrame.Years, _name='TimeReturn')
    # cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name = 'SharpeRatio', timeframe=bt.TimeFrame.Years)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name = 'SharpeRatio')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='DW')
    # cerebro.addanalyzer(bt.analyzer.returns,_name='Returns')
    print("Start Portfolio {}".format(cerebro.broker.getvalue()))
    results=cerebro.run()
    print("-------results:",results)
    back = results[0]  
    print("back:",back.trade_records)
    print("order:")
    port_value= cerebro.broker.getvalue() 
    print("Final Portfolio {}".format(cerebro.broker.getvalue()))
    # cerebro.plot(style='candle')
    pnl = port_value - start_cash
    return_rate = pnl / start_cash
    return_rate_percentage = return_rate * 100
    return_rate_formatted = "{:.2f}".format(return_rate_percentage)
    print("回報率return_rate:",return_rate_formatted)
    print(f"初始資金: {start_cash}\n回測期間：{startDate}~{endDate}")
    print(f"總資金: {round(port_value, 2)}")
    print(f"淨收益: {round(pnl, 2)}")
# ----------------
    print('夏普比率:', back.analyzers.SharpeRatio.get_analysis())
    sharpe_info=back.analyzers.SharpeRatio.get_analysis()
    sharpe_ratio=sharpe_info['sharperatio']
    print("sharpe_ratio:",sharpe_ratio)
# ----------------
    print('回撤指標:', back.analyzers.DW.get_analysis())
# ----------------
    trade_records = back.trade_records
    
    print("-----------trade_records-----------------:",trade_records)

    executed_prices=back.executed_prices
    print("-----------executed_prices-----------------:",executed_prices)

    current_time = datetime.now().strftime("%Y%m%d%H%M%S")
    file_name = f"figure_{symbol}_{current_time}.jpg"
    s3_url=saveplots(cerebro, iplot=False,style ='candlebars')
    # s3_url=saveplots(cerebro, iplot=False, style='candle')
    print("s3_url:",s3_url)
    # -----------------------------
    # figure = cerebro.plot(style ='candlebars',iplot=False)[0][0]
    # figure.savefig(file_name, bbox_inches='tight')
    # -----------------------------
    # cerebro.plot()

    # -----------------------------
    # saveplots(cerebro, file_path = file_name, iplot=False,style ='candle') #run it save local
    cerebro.runstop()
    plt.clf()  #clear plt


    # buy_info_list = strategy.buy_info_list
    # sell_info_list = strategy.sell_info_list       
    # print("buy_info_list:",buy_info_list) 
            # ---------------------------------
    result = {"pnl": pnl, "port_value":port_value,"return_rate_formatted": return_rate_formatted,"tranderoutput_url":s3_url,"trade_records":back.trade_records} 

    
    
    return jsonify(result),200

@app.route("/api/stocktop", methods=["GET"])
def get_top_stocks():
    try:
        cnx = db_pool.get_connection()
        cursor = cnx.cursor()
        sql = "select * FROM top ORDER BY date DESC LIMIT 20"
        cursor.execute(sql)
        result  = cursor.fetchall()
        stock_data = []
        # print("res:",result )
        print("進入取得熱門股")
        for row in result:

            if any(char.isalpha() and char.isascii() for char in row[2]):
                continue
            stock_data.append({
            'id': row[0],
            'top': row[1],
            'code': row[2],
            'name': row[3],
            'date': row[4].strftime('%Y-%m-%d')
        })
        # print("stock_data:",stock_data)
        print("進入網頁成功取得熱門股")
        return jsonify(stock_data),200
        
    except Exception as e:
        error_message = "伺服器內部錯誤：" + str(e)
        error_response = {"error": True, "message": error_message}
        return jsonify(error_response), 500
    finally:
        print("get_top_stocks Closing database connection.")
        cursor.close()
        cnx.close()
    

app.run(host="0.0.0.0", port=5000)
