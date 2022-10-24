# Import the driver.
import psycopg2
import psycopg2.errorcodes
import threading
from threading import Thread
import time
import datetime
import random
import numpy
import uuid
import math

usleep = lambda x: time.sleep(x/1000000.0)
msleep = lambda x: time.sleep(x/1000.0)

class dbstr:
  def __init__(self, database, user, host, port):
    self.database = database
    self.user = user
    # self.sslmode = sslmode
    self.host = host
    self.port = port

class ThreadWithReturnValue(Thread):
    def __init__(self, group=None, target=None, name=None,
                 args=(), kwargs={}, Verbose=None):
        Thread.__init__(self, group, target, name, args, kwargs)
        self._return = None
    def run(self):
        print(type(self._target))
        if self._target is not None:
            self._return = self._target(*self._args,
                                                **self._kwargs)
    def join(self, *args):
        Thread.join(self, *args)
        return self._return

def onestmt(conn, sql):
    with conn.cursor() as cur:
        cur.execute(sql)

def boolDistro(dval):
    if dval >= random.random():
        return True
    else:
        return False

def q0(val):
    return ("SELECT PG_SLEEP({})".format(val))

def q1(tablename):
    """create and insert data to events"""
    id1 = random.randint(1,100000)
    id2 = id1 + 1
    id3 = id2 + 1
    id4 = id3 + 1
    ## Keep some records regardless of TTL time 
    keep_record = 'True' if random.randint(1,10000) == 42 else 'False'

    qTemplate = """
    INSERT INTO {} (uuid1, uuid2, created_at, updated_at, j, keep_record) 
    VALUES ({})
    """
    eventvals = ""
    eventvals = eventvals + "'" + str(uuid.uuid4()) + "'" + "," 
    eventvals = eventvals + "'" + str(uuid.uuid4()) + "'" + "," 

    eventvals = eventvals + "'" + str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")) + "'" + ","
    eventvals = eventvals + "'" + str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")) + "'" + ","
 
    eventvals = eventvals + "'{"
    eventvals = eventvals + '"k1' + '":"' + str(id1) + '"' + ','
    eventvals = eventvals + '"k2' + '":"' + str(id2) + '"' + ','
    eventvals = eventvals + '"k3' + '":"' + str(id3) + '"' + ','
    eventvals = eventvals + '"k4' + '":"' + str(id4) + '"'
    eventvals = eventvals + "}'" + ","
    eventvals = eventvals + keep_record 

    # print("{}".format(qTemplate.format(eventvals)))
    return (qTemplate.format(tablename, eventvals))

def create_ddl(connStr):
    
    mycon = psycopg2.connect(connStr)
    mycon.set_session(autocommit=True)
    crbigfastddl1 = """
    CREATE TABLE IF NOT EXISTS events (
        uuid1 UUID NOT NULL,
        uuid2 UUID NOT NULL,
        created_at TIMESTAMPTZ NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL,
        j JSONB NOT NULL,
        keep_record bool DEFAULT false,
        id1 INT8 NULL AS ((j->>'k1':::STRING)::INT8) STORED,
        id2 INT8 NULL AS ((j->>'k2':::STRING)::INT8) STORED,
        id3 INT8 NULL AS ((j->>'k3':::STRING)::INT8) STORED,
        id4 INT8 NULL AS ((j->>'k4':::STRING)::INT8) STORED,
        PRIMARY KEY (uuid1, uuid2),
        INDEX idx_keep (created_at ASC) WHERE keep_record = true
    );
    """
    #     ) WITH (ttl = 'on', ttl_automatic_column = 'on', ttl_expire_after = '24:00:00':::INTERVAL, ttl_label_metrics='true');

    mycon = psycopg2.connect(connStr)
    mycon.set_session(autocommit=True)
    # onestmt(mycon, "set experimental_enable_hash_sharded_indexes=true;")
    onestmt(mycon, "DROP TABLE IF EXISTS events;")
    onestmt(mycon, crbigfastddl1)
    onestmt(mycon, "ALTER TABLE events SPLIT AT select gen_random_uuid() from generate_series(1,16);")   

def worker_steady(num, tpsPerThread, runtime, qFunc, tablename):
    """ingest worker:: Lookup valid session and then account"""
    print("Worker Steady State")

    mycon = psycopg2.connect(connStr)
    mycon.set_session(autocommit=True)

    # Configure Rate Limiter
    if tpsPerThread == 0:
        Limit=False
        arrivaleRateSec = 0
    else:
        Limit=True
        arrivaleRateSec = 1.0/tpsPerThread
    
    threadBeginTime = time.time()
    etime=threadBeginTime

    execute_count = 0
    resp = []

    with mycon:
        with mycon.cursor() as cur:
            while etime < (threadBeginTime + runtime):
                # begin time
                btime = time.time()

                # Run the query from qFunc
                cur.execute(qFunc(tablename))
                execute_count += 1

                etime = time.time()
                resp.append(etime-btime)

                sleepTime = arrivaleRateSec - (etime - btime)

                if Limit and sleepTime > 0:
                    time.sleep(sleepTime)

            # print("Worker_{}:  Queries={}, QPS={}, P90={}!!!".format(num, execute_count, (execute_count/(time.time()-threadBeginTime)), numpy.percentile(resp,90)))

    return (execute_count, resp)


## Main
##

# TODO make command-line options
#
# s = q1()
# print("{}".format(s))

connStr = "postgres://root@127.0.0.1:26257/defaultdb?sslmode=disable"
create_ddl(connStr)

# Runtime Per Table
runtime = 360000

QPS = 10000
numThreads = 128
qpsPerThread = QPS/numThreads

tables = []
tables.append("events")

results = []

for tab in tables:
    
    # Threads
    threads1 = []
    
    # Query Counters
    tq1 = 0
    tq1resp = []
 
    for i in range(numThreads):
        t1 = ThreadWithReturnValue(target=worker_steady, args=((i+1), qpsPerThread, runtime, q1, tab))
        threads1.append(t1)
        t1.start()

    # Wait for all of them to finish
    for x in threads1:
        qc, ra = x.join()
        tq1 = tq1 + qc
        tq1resp.extend(ra)


    print("{} Rows Inserted : {}".format(tab, tq1))
    print("{} QPS : {}".format(tab, tq1/runtime))
    print("{} respP99 : {}".format(tab, numpy.percentile(tq1resp,99)))
    
    ## Append Results summary
    lastrun = []
    lastrun.append(tab)
    lastrun.append(tq1/runtime)
    lastrun.append(numpy.percentile(tq1resp,99))

    results.append(lastrun)

    time.sleep(1)

print ("{:>30}  {:>10}  {:>10}".format('Table','QPS','respP99'))
print ("{}".format("-"*70))
for a in results:
    print("{:>30}  {:>10.1f}  {:>10.6f}".format(a[0], a[1], a[2]))

exit()

