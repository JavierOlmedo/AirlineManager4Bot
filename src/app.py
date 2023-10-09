import queue
import customtkinter
import platform
import tkinter
from PIL import Image
from configparser import ConfigParser
from functions import logprint, get_time, open_url, get_driver
from thread import ThreadedClient

class App(customtkinter.CTk):
    def __init__(self):
        super().__init__()
        
        # vars
        self.config = ConfigParser()
        self.config.read("config/settings.ini")
        
        self.driver = None
        self.queue = queue.Queue()
        self.bot_running = False
        self.protocol("WM_DELETE_WINDOW", self.on_close)     
        
        self.money = self.config.get("statistics","money")
        self.points = self.config.get("statistics","points")
        self.fuel = self.config.get("statistics","fuel")
        self.co2 = self.config.get("statistics","co2")
        self.fuel_capacity = self.config.get("statistics","fuel_capacity")
        self.co2_capacity = self.config.get("statistics","co2_capacity")
        
        self.fuel_price_good = tkinter.StringVar(self, self.config.get("settings","fuel_price_good"))
        self.co2_price_good = tkinter.StringVar(self, self.config.get("settings","co2_price_good"))
        self.fuel_quantity_buy = tkinter.StringVar(self, self.config.get("settings","fuel_quantity_buy")) # max 99999
        self.co2_quantity_buy = tkinter.StringVar(self, self.config.get("settings","co2_quantity_buy")) # max 999999

        # config
        customtkinter.set_appearance_mode(self.config.get("gui_config","appearance_mode"))
        customtkinter.set_default_color_theme(self.config.get("gui_config","default_color_theme"))
        
        system = platform.system()
        if system == "Darwin":
            self.iconbitmap(self.config.get("gui_config","icon_app") + ".ico")
        elif system == "Linux":
            self.iconbitmap("@" + self.config.get("gui_config","icon_app") + ".xbm")
        elif system == "Windows":
            self.iconbitmap(self.config.get("gui_config","icon_app") + ".ico")
        
        self.title(self.config.get("gui_config","title"))
        self.resizable(False, False)
        self.corner_radius = int(self.config.get("gui_config","corner_radius"))
        self.width_frame = int(self.config.get("gui_config","width_frame"))
        self.width_tb = int(self.config.get("gui_config","width_tb"))
        self.main_font = customtkinter.CTkFont(family="Calibrí", size=13, weight="normal")
        self.bold_font = customtkinter.CTkFont(family="Calibrí", size=13, weight="bold")
        
        # frames
        self.frame_sidebar = customtkinter.CTkFrame(self, corner_radius=self.corner_radius, width=self.width_frame)
        self.frame_sidebar.grid(row=0, column=0, rowspan=2, padx=(10, 0), pady=10, sticky="nsew")

        self.tab_statistics = customtkinter.CTkTabview(self, corner_radius=self.corner_radius, width=self.width_frame)
        self.tab_statistics.add("Stadistics")
        self.tab_statistics.grid(row=0, column=1, padx=(10, 0), pady=0, sticky="nsew")

        self.tab_settings = customtkinter.CTkTabview(self, corner_radius=self.corner_radius, width=self.width_frame)
        self.tab_settings.add("Settings")
        self.tab_settings.grid(row=0, column=2, padx=(10, 0), pady=0, sticky="nsew")
        
        self.tab_options = customtkinter.CTkTabview(self, corner_radius=self.corner_radius, width=self.width_frame)
        self.tab_options.add("Options")
        self.tab_options.grid(row=0, column=3, padx=10, pady=0, sticky="nsew")
        
        self.logs_frame = customtkinter.CTkTabview(self, corner_radius=self.corner_radius, width=self.width_frame)
        self.logs_frame.add("Logs")
        self.logs_frame.grid(row=1, column=1, columnspan=3, padx=10, pady=(0,10), sticky="nsew")

        # widgets
        self.img_banner = customtkinter.CTkImage(Image.open(self.config.get("gui_config", "img_banner")), size=(140, 33))
        self.sidebar_frame_label = customtkinter.CTkLabel(self.frame_sidebar, text="", image=self.img_banner)
        self.sidebar_frame_label.grid(row=0, column=0, padx=10, pady=(10,0), sticky="nsew")
        
        self.lbl_username = customtkinter.CTkLabel(self.frame_sidebar, text="Username", font=self.main_font)
        self.lbl_username.grid(row=1, column=0, padx=10, pady=(125,0), sticky="nsew")
        self.tb_username = customtkinter.CTkEntry(self.frame_sidebar, placeholder_text="username", textvariable=tkinter.StringVar(name="username", value=str(self.config.get("login", "username"))), font=self.main_font)
        self.tb_username.grid(row=2, column=0, padx=10, pady=0, sticky="nsew")
        
        self.lbl_password = customtkinter.CTkLabel(self.frame_sidebar, text="Password", font=self.main_font)
        self.lbl_password.grid(row=3, column=0, padx=10, pady=(5,0), sticky="nsew")
        self.tb_password = customtkinter.CTkEntry(self.frame_sidebar, show="*", placeholder_text="password",textvariable=tkinter.StringVar(name="password", value=str(self.config.get("login", "password"))), font=self.main_font)
        self.tb_password.grid(row=4, column=0, padx=10, pady=0, sticky="nsew")
       
        self.btn_run = customtkinter.CTkButton(self.frame_sidebar, text="START BOT", cursor="hand2", command=self.run, font=self.bold_font)
        self.btn_run.grid(row=5, column=0, padx=10, pady=(10,0), sticky="nsew")
        
        self.select_theme = customtkinter.CTkOptionMenu(self.frame_sidebar, values=["Light", "Dark", "System"], cursor="hand2", command=self.change_theme)
        self.select_theme.set(self.config.get("gui_config", "appearance_mode"))
        self.select_theme.grid(row=6, column=0, padx=(10), pady=(100,0), sticky="nsew")
        
        self.lbl_author = customtkinter.CTkLabel(self.frame_sidebar, text="Javier Olmedo", cursor="hand2", font=self.bold_font)
        self.lbl_author.grid(row=7, column=0, padx=10, pady=10, sticky="nsew")
        self.lbl_author.bind("<Button-1>", lambda e:open_url(self.config.get("gui_config", "author")))
        
        # --- stadistics
    
        tmp_lbl = customtkinter.CTkLabel(self.tab_statistics.tab("Stadistics"),font=self.main_font, text="Money: ")
        tmp_lbl.grid(row=0,column=0, padx=0, pady=0, sticky="nse")
        self.money = customtkinter.CTkLabel(self.tab_statistics.tab("Stadistics"),font=self.bold_font, text=self.money)
        self.money.grid(row=0,column=1, padx=0, pady=0, sticky="nsw")
        
        tmp_lbl = customtkinter.CTkLabel(self.tab_statistics.tab("Stadistics"),font=self.main_font, text="Points: ")
        tmp_lbl.grid(row=1,column=0, padx=0, pady=0, sticky="nse")
        self.points = customtkinter.CTkLabel(self.tab_statistics.tab("Stadistics"),font=self.bold_font, text=self.points)
        self.points.grid(row=1,column=1, padx=0, pady=0, sticky="nsw")
        
        tmp_lbl = customtkinter.CTkLabel(self.tab_statistics.tab("Stadistics"),font=self.main_font, text="Fuel: ")
        tmp_lbl.grid(row=2,column=0, padx=0, pady=0, sticky="nse")
        self.fuel = customtkinter.CTkLabel(self.tab_statistics.tab("Stadistics"),font=self.bold_font, text=self.fuel)
        self.fuel.grid(row=2,column=1, padx=0, pady=0, sticky="nsw")
        
        tmp_lbl = customtkinter.CTkLabel(self.tab_statistics.tab("Stadistics"),font=self.main_font, text="CO2: ")
        tmp_lbl.grid(row=3,column=0, padx=0, pady=0, sticky="nse")
        self.co2 = customtkinter.CTkLabel(self.tab_statistics.tab("Stadistics"),font=self.bold_font, text=self.co2)
        self.co2.grid(row=3,column=1, padx=0, pady=0, sticky="nsw")
        
        tmp_lbl = customtkinter.CTkLabel(self.tab_statistics.tab("Stadistics"),font=self.main_font, text="Fuel Capacity: ")
        tmp_lbl.grid(row=4,column=0, padx=0, pady=0, sticky="nse")
        self.fuel_capacity = customtkinter.CTkLabel(self.tab_statistics.tab("Stadistics"),font=self.bold_font, text=self.fuel_capacity)
        self.fuel_capacity.grid(row=4,column=1, padx=0, pady=0, sticky="nsw")
        
        tmp_lbl = customtkinter.CTkLabel(self.tab_statistics.tab("Stadistics"),font=self.main_font, text="CO2 Capacity: ")
        tmp_lbl.grid(row=5,column=0, padx=0, pady=0, sticky="nse")
        self.co2_capacity = customtkinter.CTkLabel(self.tab_statistics.tab("Stadistics"),font=self.bold_font, text=self.co2_capacity)
        self.co2_capacity.grid(row=5,column=1, padx=0, pady=0, sticky="nsw")
        
        # --- settings
        
        tmp_lbl = customtkinter.CTkLabel(self.tab_settings.tab("Settings"), font=self.main_font, text="Good Fuel Price: ")
        tmp_lbl.grid(row=0,column=0, padx=0, pady=0, sticky="nse")
        self.lbl_fuel_price_good = customtkinter.CTkEntry(self.tab_settings.tab("Settings"), font=self.bold_font, width=self.width_tb, textvariable=self.fuel_price_good)
        self.lbl_fuel_price_good.grid(row=0, column=1, padx=0, pady=0, sticky="nsw")
        
        tmp_lbl = customtkinter.CTkLabel(self.tab_settings.tab("Settings"), font=self.main_font, text="Good CO2 Price: ")
        tmp_lbl.grid(row=1,column=0, padx=0, pady=0, sticky="nse")
        self.lbl_co2_price_good = customtkinter.CTkEntry(self.tab_settings.tab("Settings"), font=self.bold_font, width=self.width_tb, textvariable=self.co2_price_good)
        self.lbl_co2_price_good.grid(row=1, column=1, padx=0, pady=0, sticky="nsw")
        
        tmp_lbl = customtkinter.CTkLabel(self.tab_settings.tab("Settings"), font=self.main_font, text="Fuel to buy: ")
        tmp_lbl.grid(row=2, column=0, padx=0, pady=0, sticky="nse")
        self.lbl_fuel_quantity_buy = customtkinter.CTkEntry(self.tab_settings.tab("Settings"), font=self.bold_font, width=self.width_tb, textvariable=self.fuel_quantity_buy)
        self.lbl_fuel_quantity_buy.grid(row=2, column=1, padx=0, pady=0, sticky="nsw")
        
        tmp_lbl = customtkinter.CTkLabel(self.tab_settings.tab("Settings"), font=self.main_font, text="CO2 to buy: ")
        tmp_lbl.grid(row=3,column=0, padx=0, pady=0, sticky="nse")
        self.lbl_co2_quantity_buy = customtkinter.CTkEntry(self.tab_settings.tab("Settings"), font=self.bold_font, width=self.width_tb, textvariable=self.co2_quantity_buy)
        self.lbl_co2_quantity_buy.grid(row=3, column=1, padx=0, pady=0, sticky="nsw")
        
        # --- options
        
        self.cb_autologin = customtkinter.CTkSwitch(self.tab_options.tab("Options"), text="Autologin (BETA)", variable=customtkinter.StringVar(value=str(self.config.get("options", "autologin"))), onvalue="on", offvalue="off")
        self.cb_autologin.grid(row=1, column=0, padx=0, pady=0, sticky="nsew")
        
        self.cb_save_session = customtkinter.CTkSwitch(self.tab_options.tab("Options"), text="Save session (BETA)", variable=customtkinter.StringVar(value=str(self.config.get("options", "save_session"))), onvalue="on", offvalue="off")
        self.cb_save_session.grid(row=2, column=0, padx=0, pady=0, sticky="nsew")
        
        self.cb_autolanded = customtkinter.CTkSwitch(self.tab_options.tab("Options"), text="Auto landed", variable=customtkinter.StringVar(value=str(self.config.get("options", "autolanded"))), onvalue="on", offvalue="off")
        self.cb_autolanded.grid(row=3, column=0, padx=0, pady=0, sticky="nsew")
        
        self.cb_autobuy_fuel = customtkinter.CTkSwitch(self.tab_options.tab("Options"), text="Auto buy Fuel", variable=customtkinter.StringVar(value=str(self.config.get("options", "autobuy_fuel"))), onvalue="on", offvalue="off")
        self.cb_autobuy_fuel.grid(row=4, column=0, padx=0, pady=0, sticky="nsew")
        
        self.cb_autobuy_co2 = customtkinter.CTkSwitch(self.tab_options.tab("Options"), text="Auto buy CO2", variable=customtkinter.StringVar(value=str(self.config.get("options", "autobuy_co2"))), onvalue="on", offvalue="off")
        self.cb_autobuy_co2.grid(row=5, column=0, padx=0, pady=0, sticky="nsew")
        
        # --- logs
        
        self.tb_logs = customtkinter.CTkTextbox(self.logs_frame.tab("Logs"), width=self.width_frame*3)
        self.tb_logs.grid(row=0, column=0, padx=0, pady=0, sticky="nsew")
        self.tb_logs.configure(state="disabled")
        
        # center gui
        self.update()
        self.minsize(self.winfo_width(), self.winfo_height())
        x_cordinate = int((self.winfo_screenwidth() / 2)-(self.winfo_width() / 2))
        y_cordinate = int((self.winfo_screenheight() / 2)-(self.winfo_height() / 2))
        self.geometry("{}+{}".format(x_cordinate, y_cordinate - 20))
        
        # loop to refresh gui
        logprint(self.queue, self.config.get("messages", "gui_loaded"))
        self.gui_update()
        
        # autologin
        if self.config.get("options", "autologin") == "on":
            logprint(self.queue, self.config.get("messages", "autologin"))
            self.run()
        
    # methods
    def run(self):
        logprint(self.queue, self.config.get("messages", "start_bot"))
        
        if self.driver is None:
            logprint(self.queue, self.config.get("messages", "creating_driver"))
            self.driver = get_driver(self.config.get("gui_config", "url"), self.config.get("options", "save_session"))

        self.btn_run.configure(state="disabled", text="RUNNING")
        self.thread = ThreadedClient(self.driver, self.config, self.queue)
        self.thread.start()
        self.check_thread()
    
    def gui_update(self):
        try:
            self.check_queue()
        except:
            logprint(self.queue, self.config.get("messages", "error_checking_queue"))
            
        try:
            self.config.read("config/settings.ini")
            
            self.config.set("login", "username", self.tb_username.get())
            self.config.set("login", "password", self.tb_password.get())
            
            self.money.configure(text=self.config.get("statistics", "money"))
            self.points.configure(text=self.config.get("statistics", "points"))
            self.fuel.configure(text=self.config.get("statistics", "fuel"))
            self.co2.configure(text=self.config.get("statistics", "co2"))
            self.fuel_capacity.configure(text=self.config.get("statistics", "fuel_capacity"))
            self.co2_capacity.configure(text=self.config.get("statistics", "co2_capacity"))

            self.config.set("settings", "fuel_price_good", self.fuel_price_good.get())
            self.config.set("settings", "co2_price_good", self.co2_price_good.get())
            self.config.set("settings", "fuel_quantity_buy", self.fuel_quantity_buy.get())
            self.config.set("settings", "co2_quantity_buy", self.co2_quantity_buy.get())
            
            self.config.set("options", "autologin", self.cb_autologin.get())
            self.config.set("options", "save_session", self.cb_save_session.get())
            self.config.set("options", "autolanded", self.cb_autolanded.get())
            self.config.set("options", "autobuy_fuel", self.cb_autobuy_fuel.get())
            self.config.set("options", "autobuy_co2", self.cb_autobuy_co2.get())
            
        except:
            logprint(self.queue, self.config.get("messages", "error_gui_update"))
        
        with open("config/settings.ini", "w") as configfile:
                self.config.write(configfile)    
        self.after(int(self.config.get("gui_config", "gui_update_time"))*1000, self.gui_update)
    
    def check_thread(self):
        if self.thread.is_alive():
            self.bot_running = True
            self.after(500, self.check_thread)
        else:
            self.bot_running = False
            self.btn_run.configure(state="normal", text="START BOT")

    def check_queue(self):
        while self.queue.qsize():
            try:
                msg = self.queue.get(0)

                if msg[1] == True:
                    print(msg)
                else:
                    self.write_logs(msg[0])

            except queue.Empty:
                pass
                
    def write_logs(self, event):
        file = open(self.config.get("gui_config", "logfile"), "a", encoding="utf8")
        actual_time = get_time()
        full_log = actual_time + event + "\n"
        file.write(full_log)
        file.close()
        self.tb_logs.configure(state="normal")
        self.tb_logs.insert("end", full_log)
        self.tb_logs.see("end")
        self.tb_logs.configure(state="disabled")
        print(actual_time + event)
    
    def change_theme(self, new_appearance_mode: str):
        customtkinter.set_appearance_mode(new_appearance_mode)
        logprint(self.queue, self.config.get("messages", "change_theme") + " " + new_appearance_mode)
    
    def on_close(self):
        logprint(self.queue, self.config.get("messages", "on_close"))
        if self.driver != None:
            self.driver.quit()
        if self.bot_running:
            self.thread.stop()
        self.destroy()
    

            
            

