from functions import random_sleep, logprint
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.common.action_chains import ActionChains
import random
import pickle
import time
import os

class Bot():
    def __init__(self, driver, config, queue):
        # vars
        self.driver = driver
        self.config = config
        self.queue = queue
        
        self.username = self.config.get("login", "username")
        self.password = self.config.get("login", "password")
        
        self.fuel_price_good = int(self.config.get("settings", "fuel_price_good"))
        self.co2_price_good = int(self.config.get("settings", "co2_price_good"))
        self.fuel_quantity_buy = int(self.config.get("settings", "fuel_quantity_buy"))
        self.co2_quantity_buy = int(self.config.get("settings", "co2_quantity_buy"))
        
        self.money = self.config.get("statistics", "money")
        self.points = self.config.get("statistics", "points")
        self.fuel = self.config.get("statistics", "fuel")
        self.co2 = self.config.get("statistics", "co2")
        self.fuel_capacity = self.config.get("statistics", "fuel_capacity")
        self.co2_capacity = self.config.get("statistics", "co2_capacity")
        
        self.auth = False
        self.running = True
        
        self.webdriverwait = int(self.config.get("gui_config", "webdriverwait"))
        
        # xpath
        self.xmoney = self.config.get("xpath", "xmoney")
        self.xpoints = self.config.get("xpath", "xpoints")
        
        
        
        
        # login
        self.xbtnlogin = self.config.get("xpath", "xbtnlogin")
        self.xtbusername = self.config.get("xpath", "xtbusername")
        self.xtbpassword = self.config.get("xpath", "xtbpassword")
        self.xcbremember = self.config.get("xpath", "xcbremember")
        self.xbtnauth = self.config.get("xpath", "xbtnauth")
        
        # departures
        self.xbtndepartures = self.config.get("xpath", "xbtndepartures")
        
        # fuel and co2
        self.xbtnfuel_and_co2 = self.config.get("xpath", "xbtnfuel_and_co2")
        self.xfuelprice = self.config.get("xpath", "xfuelprice")
        self.xbtnpurchase = self.config.get("xpath", "xbtnpurchase")
        self.xinput_fuel = self.config.get("xpath", "xinput_fuel")
        
        

    
    def run(self):     
        while self.running:
            
            # auth
            if not self.auth:
                self.login()
                
            # autolanded
            if(self.config.get("options", "autolanded") == "on"):
                self.all_departures()
            else:
                logprint(self.queue, self.config.get("messages", "departures_off"))
            
            self.go_to_fuel_and_co2()
            
            
            
            
            
                
                
                
                
                

            
            
            
            
            
            
            
            random_sleep(10, 30)
            self.bot_update()
    
    def go_to_fuel_and_co2(self):
        self.click(self.xbtnfuel_and_co2)
       
        self.fuel_price = self.get_value(self.xfuelprice)
       
        if self.fuel_price <= self.fuel_price_good:
           self.buyfuel(self.fuel_quantity_buy)
        else:
            print("not good moment to boy")
    
    def buyfuel(self, quantity):
        self.clear_textbox(self.xinput_fuel)
        self.send_keys(self.xinput_fuel, self.fuel_quantity_buy)
        self.click(self.xbtnpurchase)
    
    def clear_textbox(self, xpath):
        random_sleep(1, 2)
        try:
            WebDriverWait(self.driver, 10).until(expected_conditions.presence_of_element_located((By.XPATH, xpath)))
            self.driver.find_element(By.XPATH, xpath).clear()
        except:
            logprint(self.queue, self.config.get("messages", "clear_error"))
        
           
        
    def all_departures(self):
        try:
            logprint(self.queue, self.config.get("messages", "departures"))
            self.money = self.get_value(self.xmoney)
            self.points = self.get_value(self.xpoints)
            self.click(self.xbtndepartures)
            self.exit()
        except:
            logprint(self.queue, self.config.get("messages", "btndepartures_error"))
    
    def get_value(self, xpath):
        try:
            WebDriverWait(self.driver, 10).until(expected_conditions.presence_of_element_located((By.XPATH, xpath)))
            value = self.driver.find_element(By.XPATH, xpath).text
            value = value.replace("$", "").replace(",","").replace(" ","")
            return int(value)
        except:
            logprint(self.queue, self.config.get("messages", "get_value_error"))
        
    def login(self):

        logprint(self.queue, self.config.get("messages", "login") + " " + self.username)
        
        self.click(self.xbtnlogin)
        self.send_keys(self.xtbusername, self.username)
        self.send_keys(self.xtbpassword, self.password)
        self.click(self.xcbremember)
        self.click(self.xbtnauth)
        
        # Find money
        try:
            logprint(self.queue, self.config.get("messages", "wait_login"))
            wait = WebDriverWait(self.driver, 300)
            element = wait.until(expected_conditions.presence_of_element_located((By.XPATH, self.xmoney)))
        except Exception as e:
            logprint(self.queue, self.config.get("messages", "manual_login"))
            print(e)
        
        try:
            if(element):
                self.auth = True
                logprint(self.queue, self.config.get("messages", "successful_login") + " " + self.username)
            else:
                logprint(self.queue, self.config.get("messages", "error_login") + " " + self.username)
        except:
            print("error in login")
    
    def exit(self):
        random_sleep(1, 2)
        ac = ActionChains(self.driver)
        ac.move_by_offset(1, 1).click().perform()
    
    def click(self, xpath):
        random_sleep(1, 2)
        try:
            WebDriverWait(self.driver, 10).until(expected_conditions.presence_of_element_located((By.XPATH, xpath)))
            self.driver.find_element(By.XPATH, xpath).click()
        except:
            logprint(self.queue, self.config.get("messages", "click_error"))
        
    def send_keys(self, xpath, keys):
        random_sleep(1, 2)
        WebDriverWait(self.driver, 10).until(expected_conditions.presence_of_element_located((By.XPATH, xpath)))
        self.driver.find_element(By.XPATH, xpath).send_keys(keys)
        
    def stop(self):
        self.running = False
    
    def bot_update(self):
        self.config.set("statistics", "money", str(self.money))
        self.config.set("statistics", "points", str(self.points))
        self.config.set("statistics", "fuel", str(self.fuel))
        self.config.set("statistics", "co2", str(self.co2))
        self.config.set("statistics", "fuel_capacity", str(self.fuel_capacity))
        self.config.set("statistics", "co2_capacity", str(self.co2_capacity))
        
        with open("config/settings.ini", 'w') as configfile:
            self.config.write(configfile)
        