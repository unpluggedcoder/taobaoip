import os
import sys
import time
import argparse
import threading
import signal
import multiprocessing
import logging
import Queue
import urllib
import json
import iprange
import MySQLdb
from progressbar import *

db_host = "localhost"
db_username = "root"
db_password = ""
db_name = "geoip"
db_table = "geoip"

TABLES = {}
TABLES[db_table] = (
    "CREATE TABLE IF NOT EXISTS `{}` ("
    "  `id` BIGINT NOT NULL AUTO_INCREMENT,"
    "  `ip` varchar(50) NOT NULL,"    
    "  `country` text,"
    "  `country_id` text,"
    "  `area` text,"
    "  `area_id` text,"
    "  `region` text,"
    "  `region_id` text,"
    "  `city` text,"
    "  `city_id` text,"
    "  `county` text,"
    "  `county_id` text,"
    "  `isp` text,"
    "  `isp_id` text,"
    "  `update` timestamp NOT NULL,"
    "  PRIMARY KEY (`id`,`ip`), UNIQUE KEY `ip` (`ip`)"
    ") DEFAULT CHARSET=UTF8".format(db_table))

insert_ip = (
    "REPLACE INTO {table} "
    "(ip, country, country_id, area, area_id, region, region_id, "
    " city, city_id, county, county_id, isp, isp_id) "
    " VALUES ('{ip}', '{country}', '{country_id}', '{area}', '{area_id}', '{region}', '{region_id}', "
    " '{city}', '{city_id}', '{county}', '{county_id}', '{isp}', '{isp_id}')")

output_format = (
    "{ip} {country} {country_id} {area} {area_id} {region} {region_id} "
    "{city} {city_id} {county} {county_id} {isp} {isp_id}")

cancel = False

def initlog():
    logfilename = "{}.log".format(time.strftime("%Y%m%d-%H%M%S"))
    logfile = os.path.join(os.getcwd(), logfilename)
    logging.basicConfig(filename = logfilename, level = logging.DEBUG, filemode = 'w', 
                        format = '%(asctime)s - %(levelname)s: %(message)s')
    
def initdb():
    try:
        db = MySQLdb.Connection(host=db_host, user=db_username, passwd=db_password, init_command="set names utf8")
        cursor = db.cursor()
        
        cursor.execute("CREATE DATABASE IF NOT EXISTS {} DEFAULT CHARACTER SET 'utf8'".format(db_name))
        cursor.execute("USE {}".format(db_name))
        #cursor.select_db(db_name)
        
        cursor.execute(TABLES[db_table])
        db.commit()
        return (1, db)
    except MySQLdb.Error as err:
        logging.exception("Initial database failed!");
        return (0, None)
        
    
def gettarget(output):
    try:
        if output:
            target = open(output, 'w')
            return target
    except IOError as err:
        logging.exception("Can not open output target!")
        print err.errno
        print err.message
    return sys.stdout

def handle_commandline():
    parser = argparse.ArgumentParser()
    parser.add_argument("iprange", help="""The string of IP range, such as:
    "192.168.1.0-192.168.1.255"   : beginning-end
    "192.168.1.0/24"              : CIDR
    "192.168.1.*"                 : wildcard""")
    parser.add_argument("-o", "--output", help="The output destination of result, default is stdout", default="")
    args = parser.parse_args()
    return args.iprange, args.output

def interrupt_handler(signal, frame):
    global cancel
    cancel = True

def main():
    ip_range, output = handle_commandline()
    initlog()
    ok , db = initdb()
    if not ok:
        exit(1)
    
    signal.signal(signal.SIGINT, interrupt_handler)
    target = gettarget(output)
    
    jobs = Queue.Queue()
    results = Queue.Queue()
    progress = Queue.Queue()
    
    ratelimit = RateLimit(10, 1)     # ip.taobao.com limit the rate with 10qps
    concurrency = multiprocessing.cpu_count() * 10
    
    create_threads(ratelimit, jobs, results, target, concurrency, progress, db)
    count = add_jobs(jobs, ip_range)
    
    pbar = create_progressbar(count, progress)
    wait(jobs, results, progress)
    pbar.finish()
    
    target.flush()
    if db is not None:
        db.commit()
        db.close()
    
    logging.shutdown()
    
def create_threads(ratelimit, jobs, results, target, concurrency, progress, db):
    for _ in range(concurrency):
        thread = threading.Thread(target=worker, args=(ratelimit, jobs, progress, results))
        thread.daemon = True
        thread.start()
    output_thread = threading.Thread(target=output, args=(target, progress, results, db))
    output_thread.daemon = True
    output_thread.start()

def add_jobs(jobs, ip_range):
    for count, ip in enumerate(iprange.iprange(ip_range), start=1):
        jobs.put(ip)
    return count

def create_progressbar(count, progress):
    widgets = ["Processing {} ip(s): ".format(count), Percentage(), ' ', Bar(marker=RotatingMarker()),
                               ' ', ETA()]
    pbar = ProgressBar(widgets=widgets, maxval=count).start()    
    prog_thread = threading.Thread(target=progproc, args=(pbar, count, progress))
    prog_thread.daemon = True
    prog_thread.start()
    return pbar

def wait(jobs, results, progress):
    global cancel
    try:
        jobs.join()
        results.join()
        progress.join()
    except KeyboardInterrupt:
        print "Canceling..."
        cancel = True
        logging.warning("Canceling...")
    except:
        logging.exception("Unknown Error!")
        
########################################################################
class RateLimit:
    """Rate limit for connections"""
    #----------------------------------------------------------------------
    def __init__(self, rate, interval):
        """
        Constructor
        @param rate Maximum number limit during interval time
        @param interval Time span for the rate
        """
        self.rate = rate
        self.interval = interval
        self.lastcheck = time.time()
        self.count = 0
        self.lock = threading.Condition()
        
    def ratecontrol(self):
        self.lock.acquire()
        while True:
            span = time.time() - self.lastcheck
            if span >= self.interval:   # interval time past, reset lastcheck time and count
                self.count = 1
                self.lastcheck = time.time()
                break
            elif self.count <= self.rate: # still under the rate control during interval
                self.count += 1
                break
            else:   # reached maximun rate in the interval time
                self.lock.wait(self.interval - span)
        self.lock.release()

########################################################################

def fetch(ip):
    url = 'http://ip.taobao.com/service/getIpInfo.php?ip=' + ip
    result = {}
    try:
        response = urllib.urlopen(url).read()
        jsondata = json.loads(response)
        if jsondata[u'code'] == 0:
            result['ip'] = jsondata[u'data'][u'ip'].encode('utf-8')          
            result['country'] = jsondata[u'data'][u'country'].encode('utf-8')
            result['country_id'] = jsondata[u'data'][u'country_id'].encode('utf-8')
            result['area'] = jsondata[u'data'][u'area'].encode('utf-8')
            result['area_id'] = jsondata[u'data'][u'area_id'].encode('utf-8')
            result['region'] = jsondata[u'data'][u'region'].encode('utf-8')
            result['region_id'] = jsondata[u'data'][u'region_id'].encode('utf-8')
            result['city'] = jsondata[u'data'][u'city'].encode('utf-8')
            result['city_id'] = jsondata[u'data'][u'city_id'].encode('utf-8')
            result['county'] = jsondata[u'data'][u'county'].encode('utf-8')
            result['county_id'] = jsondata[u'data'][u'county_id'].encode('utf-8')
            result['isp'] = jsondata[u'data'][u'isp'].encode('utf-8')
            result['isp_id'] = jsondata[u'data'][u'isp_id'].encode('utf-8')
        else:
            return 0, result
    except:
        logging.exception("Url open failed:" + url)
        return 0, result
    return 1, result

def worker(ratelimit, jobs, progress, results):
    global cancel
    while not cancel:
        try:
            ratelimit.ratecontrol()
            ip = jobs.get(timeout=2) # Wait 2 seconds
            ok, result = fetch(ip)
            
            if not ok:
                logging.error("Fetch information failed, ip:{}".format(ip))
                progress.put("") # Notify the progress even it failed
            else:
                results.put(result)
            
            jobs.task_done()    # Notify one job
        except Queue.Empty:
            pass
        except:
            logging.exception("Unknown Error!")
    
def output(target, progress, results, db):
    global cancel
    global output_format, insert_ip
    while not cancel:
        try:
            items = results.get(timeout=5)
            line = output_format.format(**items)
            print >>target, line
            if db is not None:
                items['table'] = db_table
                cursor = db.cursor()
                sql = insert_ip.format(**items)
                cursor.execute(sql)
                db.commit()            
            progress.put("")
            results.task_done()
        except Queue.Empty:
            pass
        except:
            logging.exception("Output item failed")
            

def progproc(progressbar, count, progress):
    """
    Since ProgressBar is not a thread-safe class, we use a Queue to do the counting job, like
    two other threads. Use this thread do the printing of progress bar. By the way, it will
    print to stderr, which does not conflict with the default result output(stdout).
    """
    idx = 1
    while True:
        try:
            progress.get(timeout=5)
            progressbar.update(idx)
            idx += 1
            progress.task_done()
        except Queue.Empty:
            pass
        except:
            logging.exception("Unknown Error!")

if __name__ == "__main__":
    main()
    