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

cancel = False

def initlog():
    logfilename = "{}.log".format(time.strftime("%Y%m%d-%H%M%S"))
    logfile = os.path.join(os.getcwd(), logfilename)
    logging.basicConfig(filename = logfilename, level = logging.DEBUG, filemode = 'w', 
                        format = '%(asctime)s - %(levelname)s: %(message)s')
    
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
    target = gettarget(output)
    signal.signal(signal.SIGINT, interrupt_handler)
    
    jobs = Queue.Queue()
    results = Queue.Queue()
    ratelimit = RateLimit(10, 1)     # ip.taobao.com limit the rate with 10qps
    concurrency = multiprocessing.cpu_count() * 2
    starttime = time.time()
    
    create_threads(ratelimit, jobs, results, target, concurrency)
    count = add_jobs(jobs, ip_range)
    wait(count, jobs, results)
    
    span = time.time() - starttime
    print >>sys.stderr, "Cost times: {0:.3f}s".format(span)
    target.flush()
    logging.shutdown()
    
def create_threads(ratelimit, jobs, results, target, concurrency):
    for _ in range(concurrency):
        thread = threading.Thread(target=worker, args=(ratelimit, jobs, results))
        thread.daemon = True
        thread.start()
    output_thread = threading.Thread(target=process, args=(target, results))
    output_thread.daemon = True
    output_thread.start()

def add_jobs(jobs, ip_range):
    for count, ip in enumerate(iprange.iprange(ip_range), start=1):
        jobs.put(ip)
    return count

def wait(count, jobs, results):
    global cancel
    print >>sys.stderr, "Processing {} ip(s)".format(count)
    try:
        jobs.join()
        results.join()
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
    result = []
    try:
        response = urllib.urlopen(url).read()
        jsondata = json.loads(response)
        if jsondata[u'code'] == 0:
            result.append(jsondata[u'data'][u'ip'].encode('utf-8'))            
            result.append(jsondata[u'data'][u'country'].encode('utf-8'))
            result.append(jsondata[u'data'][u'country_id'].encode('utf-8'))
            result.append(jsondata[u'data'][u'area'].encode('utf-8'))
            result.append(jsondata[u'data'][u'area_id'].encode('utf-8'))
            result.append(jsondata[u'data'][u'region'].encode('utf-8'))
            result.append(jsondata[u'data'][u'region_id'].encode('utf-8'))
            result.append(jsondata[u'data'][u'city'].encode('utf-8'))
            result.append(jsondata[u'data'][u'city_id'].encode('utf-8'))
            result.append(jsondata[u'data'][u'county'].encode('utf-8'))
            result.append(jsondata[u'data'][u'county_id'].encode('utf-8'))
            result.append(jsondata[u'data'][u'isp'].encode('utf-8'))
            result.append(jsondata[u'data'][u'isp_id'].encode('utf-8'))            
        else:
            return 0, result
    except:
        logging.exception("Url open failed:" + url)
        return 0, result
    return 1, result

def worker(ratelimit, jobs, results):
    global cancel
    while not cancel:
        try:
            ratelimit.ratecontrol()
            ip = jobs.get(timeout=2) # Wait 2 seconds
            ok, result = fetch(ip)
            if not ok:
                logging.error("Fetch information failed, ip:{}".format(ip))
            elif result is not None:
                results.put(" ".join(result))
            jobs.task_done()    # Notify one item
        except Queue.Empty:
            pass
        except:
            logging.exception("Unknown Error!")

def process(target, results):
    global cancel
    while not cancel:
        try:
            line = results.get(timeout=5)
        except Queue.Empty:
            pass
        else:
            print >>target, line
            results.task_done()

if __name__ == "__main__":
    main()
    