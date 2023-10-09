import os
import pickle
import platform
import random
import time
import webbrowser
import undetected_chromedriver
import pathlib
from selenium import webdriver

def get_driver(url, session):
    system = platform.system()

    if system == "Darwin":
        path = "bin/chrome_mac/chromedriver"
    elif system == "Linux":
        #path = "bin/chrome_linux/chromedriver"
        
        # raspberry
        # cp /usr/lib/chromium-browser/chromedriver .
        path = "bin/chrome_linux/chromedriver_arm"
    elif system == "Windows":
        path = os.getcwd() + "bin\chrome_windows\chromedriver.exe"

    # Shoutout to the dev who created this
    use_undetected_chromedriver = False

    if use_undetected_chromedriver:
        options = undetected_chromedriver.ChromeOptions()
        options.add_argument("--profile-directory=Profile 8")
        options.add_argument("--disable-popup-blocking")  # allow for new tab
        # options.add_extension("adblocker/uBlock-Origin.crx")

        driver = undetected_chromedriver.Chrome(options=options)
        driver.get(str(url))
        return driver

    else:
        options = webdriver.ChromeOptions()
        options.add_argument("--ignore-certificate-error")
        options.add_argument("--ignore-ssl-errors")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--touch-events=disabled")

        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)

        # Stop annoying windows logs
        options.add_argument("--disable-logging")
        options.add_argument("--log-level=3")
        
        # options.add_argument("start-maximized");
        
        '''
        if(session == "on"):
            script_directory = pathlib.Path().absolute()
            options.add_argument(f"user-data-dir={script_directory}/config/session/")
        '''
        
        driver = webdriver.Chrome(executable_path=path, options=options)
        driver.get(str(url))
        
        
        '''
        if(session == "on"):
            if os.path.exists("config/session/cookies.pkl") and os.path.getsize("config/session/cookies.pkl") > 0:
                driver.delete_all_cookies()
                cookies = pickle.load(open("config/session/cookies.pkl", "rb"))
                for cookie in cookies:
                    driver.add_cookie(cookie)
                    driver.get("https://www.airlinemanager.com/?gameType=web")
        '''
                    
                    
        
        return driver

def get_time():
    now = time.strftime("%d/%m/%Y %H:%M:%S", time.localtime())
    return "[{now}] ".format(now=now)

def logprint(queue, event, bidroundOver=False):
    event = str(event)
    combined = [event, bidroundOver]
    queue.put(combined)

def open_url(url):
    webbrowser.open_new_tab(url)
    
def random_sleep(min, max):
    sleep_time = random.randint(min, max)
    time.sleep(sleep_time)
    