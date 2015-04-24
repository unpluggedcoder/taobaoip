# taobaoip
Fetch ip information from the database at http://ip.taobao.com
# Usage
    usage: main.py [-h] [-o OUTPUT] iprange

    positional arguments:
      iprange               The string of IP range, such as:
                            "192.168.1.0-192.168.1.255" : beginning-end
                            "192.168.1.0/24" : CIDR
                            "192.168.1.*" : wildcard

    optional arguments:
      -h, --help            show this help message and exit
      -o OUTPUT, --output OUTPUT
                            The output destination of result, default is stdout
## Database surrport
	Change main.py to fit your own database configuration.
```python
db_host = "localhost"
db_username = "root"
db_password = ""
db_name = "geoip"
db_table = "geoip"
```

![Image text](https://github.com/Ghostist/taobaoip/blob/master/screenshot/screenshot1.png)

![Image text](https://github.com/Ghostist/taobaoip/blob/master/screenshot/screenshot2.png)

# Note
The progressbar.py is included by package: progressbar2, which you can install through pip:
pip install progressbar2
I just put it here for convenience.
