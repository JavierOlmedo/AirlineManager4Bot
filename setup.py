import setuptools
from distutils.core import setup

setup(
  name='AirlineManager4Bot',         # How you named your folder
  packages=['AirlineManager4Bot'],   # Chose the same as "name"
  version='1.0',      # Start with a small number and increase it with every change you make
  license='MIT',        # Chose a license from here: https://help.github.com/articles/licensing-a-repository
  description='airlinemanager bot game python',   # Give a short description about your library
  author='Javier Olmedo',                   # Type in your name
  author_email='javierolmedo@hackpuntes.com',      # Type in your E-Mail
  url='https://github.com/JavierOlmedo/AirlineManager4Bot',   # Provide either the link to your github or to your website
  download_url='https://github.com/JavierOlmedo/AirlineManager4Bot/archive/1.0.tar.gz',    # I explain this later on
  keywords=['airlinemanager', 'bot', 'game', 'python'],   # Keywords that define your project best
  install_requires=['selenium', 'webdriver-manager'],

  classifiers=[
    'Development Status :: 3 - Alpha',      # Chose either "3 - Alpha", "4 - Beta" or "5 - Production/Stable" as the current state of your loadingz
    'Intended Audience :: Developers',      # Define that your audience are developers
    'Topic :: Software Development :: Build Tools',
    'License :: OSI Approved :: MIT License',   # Again, pick a license
    'Programming Language :: Python :: 3',      #Specify which pyhton versions that you want to support
  ],
)