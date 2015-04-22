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
