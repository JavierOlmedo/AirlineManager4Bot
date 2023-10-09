import os
from app import App
from functions import logprint

if __name__ == "__main__":
    try:
        os.system("cls||clear")
        app = App()
        app.mainloop()

    except KeyboardInterrupt:
        if app.driver != None:
            app.driver.quit()
        if app.bot_running:
            app.thread.stop()
        app.destroy()
        print("User aborted App!")
        