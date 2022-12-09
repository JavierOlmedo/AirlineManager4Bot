import os, sys, time
from selenium.webdriver.chrome.options import Options
from selenium import webdriver
from termcolor import cprint
from time import sleep

class AirlineManager4Bot():
    # config
    goodpricefuel = 380
    goodpriceco2 = 110
    quantityfuel = 99999
    quantityco2 = 999999

    # constants
    f = open("creds", "r")
    lines = f.readlines()
    username = lines[0].strip(' \t\n\r')
    password = lines[1].strip(' \t\n\r')
    f.close()
    chromedriver = 'chromedriver.exe'
    url = 'https://www.airline4.net/'

    # xpath
    xbtnlogin = '/html/body/div[3]/div[1]/div[5]/button[1]'
    xtbusername = '//*[@id="lEmail"]'
    xtbpassword = '//*[@id="lPass"]'
    xcbremember = '//*[@id="remember"]'
    xbtnauth = '//*[@id="btnLogin"]'
    xbtndepart = '//*[@id="flightInfo"]/div[4]/span'
    xbtnfuel = '/html/body/div[7]/div/div[3]/div[3]'
    xlbpricefuel = '//*[@id="fuelMain"]/div/div[1]/span[2]/b'
    xbtnclose = '//*[@id="popup"]/div/div/div[1]/div/span'
    xtbfuelprice = '//*[@id="amountInput"]'
    xbtnbuyfuel = '//*[@id="fuelMain"]/div/div[7]/div/button[2]'
    xbtnco2 = '//*[@id="popBtn2"]'
    xlbco2price = '//*[@id="co2Main"]/div/div[2]/span[2]/b'
    xtbco2price = '//*[@id="amountInput"]'
    xbtnbuyco2 = '//*[@id="co2Main"]/div/div[8]/div/button[2]'
    xbtndepartures = '//*[@id="mapRoutes"]/img'
    xbtndepartall = '//*[@id="departAll"]'

    def __init__(self):
        options = Options()
        options.add_argument("--log-level=3")
        self.driver = webdriver.Chrome(executable_path=self.chromedriver, options=options)
        self.gobot() 

    def login(self):
        try:
            self.driver.get(self.url)
            
            btnlogin = self.driver.find_element_by_xpath(self.xbtnlogin)
            btnlogin.click()
    
            tbusername = self.driver.find_element_by_xpath(self.xtbusername)
            tbusername.send_keys(self.username)
          
            tbpassword = self.driver.find_element_by_xpath(self.xtbpassword)
            tbpassword.send_keys(self.password)

            cbremember = self.driver.find_element_by_xpath(self.xcbremember)
            cbremember.click() 
    
            btnauth = self.driver.find_element_by_xpath(self.xbtnauth)
            btnauth.click() 
            sleep(5)
            
            btndepart = self.driver.find_element_by_xpath(self.xbtndepart)
            btndepart.click()
            savelog(gettime() + "[+] Login succesfully from user {username}!".format(username=self.username), "green")
        
        except:
            savelog(gettime() + "[-] Login function error!", "red")
    
    def fuel(self) :
        try:
            btnfuel = self.driver.find_element_by_xpath(self.xbtnfuel)
            btnfuel.click()
            sleep(2)

            pricefuel = self.driver.find_element_by_xpath(self.xlbpricefuel).text
            pricefuel = pricefuel.replace("$ ","")
            pricefuel = pricefuel.replace(",","")
            pricefuel = int(pricefuel)
            
            savelog(gettime() + "[!] Fuel price --> {pricefuel}".format(pricefuel=pricefuel), "yellow")

            if(pricefuel <= self.goodpricefuel):
                tbfuelprice = self.driver.find_element_by_xpath(self.xtbfuelprice)
                tbfuelprice.clear()
                tbfuelprice.send_keys(self.quantityfuel)

                btnfuelbuy = self.driver.find_element_by_xpath(self.xbtnbuyfuel)
                btnfuelbuy.click()
                savelog(gettime() + "[+] Purchased {quantityfuel} fuel!".format(quantityfuel=self.quantityfuel), "green")
                sleep(2)

            btnclosefuel = self.driver.find_element_by_xpath(self.xbtnclose)
            btnclosefuel.click()      
            sleep(2)
            
        except:
            savelog(gettime() + "[-] Fuel function error!", "red")
    
    def co2(self):
        try:
            btnfuel = self.driver.find_element_by_xpath(self.xbtnfuel)
            btnfuel.click()
            sleep(2)

            btnco2 = self.driver.find_element_by_xpath(self.xbtnco2)
            btnco2.click()
            sleep(2)
            
            priceco2 = self.driver.find_element_by_xpath(self.xlbco2price).text
            priceco2 = priceco2.replace("$ ","")
            priceco2 = int(priceco2)
            
            savelog(gettime() + "[!] CO2 price --> {priceco2}".format(priceco2=priceco2), "yellow")
    
            if(priceco2 <= self.goodpriceco2):
                tbco2price = self.driver.find_element_by_xpath(self.xtbco2price)
                tbco2price.clear()
                tbco2price.send_keys(self.quantityco2)

                btnbuyco2 = self.driver.find_element_by_xpath(self.xbtnbuyco2)
                btnbuyco2.click()
                savelog(gettime() + "[+] Purchased {quantityco2} CO2!".format(quantityco2=self.quantityco2), "green")
                sleep(2)
            
            btnclosefuel = self.driver.find_element_by_xpath(self.xbtnclose)
            btnclosefuel.click()      
            sleep(2)
            
        except:
            savelog(gettime() + "[-] CO2 function error!", "red")       

    def departures (self):
        try:
            btndepartures = self.driver.find_element_by_xpath(self.xbtndepartures)
            btndepartures.click()
            sleep(2)
                
            btndepartall = self.driver.find_element_by_xpath(self.xbtndepartall)
            btndepartall.click()
            sleep(2)
                
            btnclose = self.driver.find_element_by_xpath(self.xbtnclose)
            btnclose.click()
            sleep(2)

            savelog(gettime() + "[+] Departures found!", "green") 
                
        except:
            btnclose = self.driver.find_element_by_xpath(self.xbtnclose)
            btnclose.click()
            sleep(2)
            savelog(gettime() + "[!] No departures found!", "yellow") 

    def gobot(self):
        self.login()

        time = 0
        while True:
            if(time <= 0):
                self.fuel()
                self.co2()
                time = 1800
            self.departures()
            savelog(gettime() + "[!] Time to check Fuel and CO2 --> {time} seconds".format(time=time), "blue")
            time -= 60
            sleep(60)

def banner():
    os.system('cls||clear')
    print('''
     _____  __     _____  _____ 
    |  _  ||  |   |     || __  |
    |     ||  |__ | | | || __ -|
    |__|__||_____||_|_|_||_____| v1.1

    ---[Airline Manager 4 Bot]---
            @jjavierolmedo
    ''')

def savelog(s, c):
    cprint(s, c)
    with open('log', 'a') as file:
        file.write(s + "\n")

def gettime():
        now = time.strftime("%d/%m/%Y %H:%M:%S", time.localtime())
        return "[{now}]".format(now=now)

def main():
    banner()
    airlinemanager = AirlineManager()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        savelog(gettime() + "[-] User aborted session!", "red")
        sys.exit(0)
