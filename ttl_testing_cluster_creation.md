# Create Environment for HASH index evaluation

This repository uses the roachprod tool to create a cluster and test machine to describe various use cases when evaluating the use of HASH indexes.

## Cluster Creation

```bash
roachprod create `whoami`-ttl --clouds aws --nodes 9 --aws-machine-type-ssd m6i.2xlarge --aws-zones us-east-1c --aws-enable-multiple-stores=true --aws-ebs-volume='{"VolumeType":"io2","VolumeSize":100,"Iops":500}' --aws-ebs-volume='{"VolumeType":"io2","VolumeSize":100,"Iops":500}' --aws-ebs-volume='{"VolumeType":"io2","VolumeSize":100,"Iops":500}' --aws-ebs-volume='{"VolumeType":"io2","VolumeSize":100,"Iops":500}' --lifetime 240h
roachprod stage `whoami`-ttl release v22.2.0
roachprod start `whoami`-ttl --store-count 4
roachprod pgurl `whoami`-ttl:1
roachprod adminurl `whoami`-ttl:1

echo "ALTER RANGE default CONFIGURE ZONE USING gc.ttlseconds = 7200;"|roachprod sql `whoami`-ttl:1
echo "ALTER DATABASE defaultdb CONFIGURE ZONE USING gc.ttlseconds = 7200;"| roachprod sql `whoami`-ttl:1
echo "SET CLUSTER SETTING rocksdb.min_wal_sync_interval='4ms';"| roachprod sql `whoami`-ttl:1

```

## Driver Machine

```bash
## -- configure driver machine
##
roachprod create `whoami`-drive --clouds aws --nodes 1 --aws-machine-type-ssd m6i.12xlarge --aws-ebs-volume='{"VolumeType":"io2","VolumeSize":200,"Iops":500}' --aws-zones us-east-1c --lifetime 240h
roachprod stage `whoami`-drive release v22.2.0

## Put Python Code on Driver
roachprod put `whoami`-drive:1 ingest_stress_plus.py 

## Login to Driver and finish configuration
roachprod ssh `whoami`-drive:1
sudo mv ./cockroach /usr/local/bin

sudo apt-get update -y
sudo apt-get install haproxy -y
cockroach gen haproxy --insecure   --host=10.11.38.43   --port=26257 
nohup haproxy -f haproxy.cfg &

## Install Python3
sudo apt-get update
sudo apt-get install libpq-dev python3-dev -y
sudo apt install python3-numpy python3-scipy python3-psycopg2 python3-dev -y
```

## Prometheus Install for Driver... rough notes

```bash
# Instructions: https://www.digitalocean.com/community/tutorials/how-to-install-prometheus-on-ubuntu-16-04
sudo useradd --no-create-home --shell /bin/false prometheus
sudo useradd --no-create-home --shell /bin/false node_exporter

sudo mkdir /etc/prometheus
sudo mkdir /var/lib/prometheus
sudo chown prometheus:prometheus /etc/prometheus
sudo chown prometheus:prometheus /var/lib/prometheus


# Download latest https://prometheus.io/download/
wget https://github.com/prometheus/prometheus/releases/download/v2.19.1/prometheus-2.19.1.linux-amd64.tar.gz

tar xvf prometheus-2.19.1.linux-amd64.tar.gz
sudo cp prometheus-2.19.1.linux-amd64/prometheus /usr/local/bin
sudo cp prometheus-2.19.1.linux-amd64/promtool /usr/local/bin
sudo chown prometheus:prometheus /usr/local/bin/prometheus
sudo chown prometheus:prometheus /usr/local/bin/promtool

sudo cp -r prometheus-2.19.1.linux-amd64/consoles /etc/prometheus
sudo cp -r prometheus-2.19.1.linux-amd64/console_libraries /etc/prometheus

sudo chown -R prometheus:prometheus /etc/prometheus/consoles
sudo chown -R prometheus:prometheus /etc/prometheus/console_libraries

rm -fr prometheus-2.19.1.linux-amd64 prometheus-2.19.1.linux-amd64.gz

## Configure Base YAML file
sudo echo \
"global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'prometheus'
    scrape_interval: 5s
    static_configs:
      - targets: ['localhost:9090']" > x
sudo mv x /etc/prometheus/prometheus.yml
sudo chown prometheus:prometheus /etc/prometheus/prometheus.yml

sudo -u prometheus /usr/local/bin/prometheus \
    --config.file /etc/prometheus/prometheus.yml \
    --storage.tsdb.path /var/lib/prometheus/ \
    --web.console.templates=/etc/prometheus/consoles \
    --web.console.libraries=/etc/prometheus/console_libraries
^C

sudo echo \
"[Unit]
Description=Prometheus
Wants=network-online.target
After=network-online.target

[Service]
User=prometheus
Group=prometheus
Type=simple
ExecStart=/usr/local/bin/prometheus \
    --config.file /etc/prometheus/prometheus.yml \
    --storage.tsdb.path /var/lib/prometheus/ \
    --web.console.templates=/etc/prometheus/consoles \
    --web.console.libraries=/etc/prometheus/console_libraries

[Install]
WantedBy=multi-user.target" > x
sudo mv x /etc/systemd/system/prometheus.service
sudo chown prometheus:prometheus /etc/systemd/system/prometheus.service

sudo systemctl daemon-reload
sudo systemctl start prometheus
sudo systemctl enable prometheus

sudo systemctl status prometheus

## Cockroach Prometheus Setup
##

sudo systemctl stop prometheus
sudo su - root
cd /etc/prometheus
mv prometheus.yml _prometheus.yml
mv rules/aggregation.rules.yml rules/_aggregation.rules.yml
mv rules/alerts.rules.yml rules/_alerts.rules.yml

wget https://raw.githubusercontent.com/cockroachdb/cockroach/master/monitoring/prometheus.yml -O prometheus.yml
wget -P rules https://raw.githubusercontent.com/cockroachdb/cockroach/master/monitoring/rules/aggregation.rules.yml
wget -P rules https://raw.githubusercontent.com/cockroachdb/cockroach/master/monitoring/rules/alerts.rules.yml

prometheus --config.file=prometheus.yml

## EDIT prometheus.yml
##
vi prometheus.yml
  ## put the SUT name and port for adminUI  glenn-prom-0001.roachprod.crdb.io:26258
    #   static_configs:
    # - targets: ['10.142.0.164:26258', '10.142.0.161:26258', '10.142.0.163:26258', '10.142.0.165:26258', '10.142.0.162:26258']

## START prometheus
sudo systemctl stop prometheus
sudo systemctl start prometheus
sudo systemctl enable prometheus
sudo systemctl status prometheus
```

## Prometheus should be HERE

http://`whoami`-drive.roachprod.crdb.io:9090/graph

## Grafana Install

[https://grafana.com/docs/grafana/latest/installation/debian/](https://grafana.com/docs/grafana/latest/installation/debian/)

```bash
## Reset Grafana Password... if needed
grafana-cli admin reset-admin-password --homepath "/usr/share/grafana" --config "/etc/grafana/grafana.ini" admin
```
## Running ingest_stress.py

This should take a few hours load...

```bash
roachprod put `whoami`-drive ./ingest_stress.py
roachprod ssh `whoami`-drive
python3 ./ingest_stress.py
```

## TTL Notes / Runlog

```sql
WITH (ttl_expire_after = '3 months')
```

`2022-05-12 UTC`  Restarted ingest at 2K RPS

`2022-05-13 16:48:17.984553+00` 
Observed hourly DELETE taking ~40min.  Increased default range concurrency to one per NODE.

```sql
set cluster setting sql.ttl.default_range_concurrency=9;
```

This lowered the DELETE duration from 40min to 10min...

![](TTL_increase_concurrency.png)

Changed batch size...

```sql
root@localhost:26257/defaultdb> select now();
               now
---------------------------------
  2022-05-16 15:52:04.654053+00


ALTER TABLE ingest_stress
WITH (ttl = 'on', ttl_automatic_column = 'on', ttl_expire_after = '06:00:00':::INTERVAL, ttl_job_cron = '@hourly', ttl_label_metrics = true, ttl_delete_batch_size = 1000);
```

### Grafana / Promentheus Settings

PromQL to display rows deleted by Table Name:
    `sum by(relation) (rate(jobs_row_level_ttl_rows_deleted[5m]))`


## V22.2 syntax

With CockroachDB v22.2 the TTL functionality has been improved to allow you to use your own expression to `DELETE` expired rows.  The row will be deleted if the current time is greater than `ttl_expiration_expression`.  This allows you to use an existing column to anchor the delete logic.

With v22.2, once the expiration activity is triggered, the `DELETE` activity is scheduled on each node where the data is scanned a _span_ at a time.

```sql

CREATE TABLE my_ttl_table (
    id INT8 NOT NULL,
    created_at TIMESTAMPTZ NULL DEFAULT now():::TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NULL DEFAULT now():::TIMESTAMPTZ,
    should_delete BOOL NULL,
    CONSTRAINT my_ttl_table_pkey PRIMARY KEY (id ASC)
);

ALTER TABLE my_ttl_table 
SET (ttl = 'on', 
     ttl_expiration_expression = '(updated_at AT TIME ZONE ''utc'' + INTERVAL ''2h'') AT TIME ZONE ''utc''',
     ttl_label_metrics = true);

ALTER TABLE my_ttl_table 
SET (ttl = 'on', 
     ttl_expiration_expression = "if(should_delete, updated_at, NULL)",
     ttl_label_metrics = true);

ALTER TABLE my_ttl_table 
SET (ttl = 'on', 
     ttl_expiration_expression = "if(should_delete, (updated_at AT TIME ZONE 'utc' + INTERVAL '10m') AT TIME ZONE 'utc', NULL)",
     ttl_label_metrics = true);

ALTER TABLE events 
SET (ttl = 'on', 
     ttl_expiration_expression = '(updated_at AT TIME ZONE ''utc'' + INTERVAL ''2h'') AT TIME ZONE ''utc''',
     ttl_label_metrics = true);

ALTER TABLE events 
SET (ttl = 'on', 
     ttl_expiration_expression = '(updated_at AT TIME ZONE ''utc'' + INTERVAL ''2h'') AT TIME ZONE ''utc''',
     ttl_label_metrics = true,
     ttl_range_concurrency = 2);

ALTER TABLE events 
SET (ttl = 'on', 
     ttl_expiration_expression = "if(not keep_record, (updated_at AT TIME ZONE 'utc' + INTERVAL '2h') AT TIME ZONE 'utc', NULL)",
     ttl_label_metrics = true,
     ttl_range_concurrency = 1);


ALTER RANGE default CONFIGURE ZONE USING gc.ttlseconds = 7200;
ALTER DATABASE defaultdb CONFIGURE ZONE USING gc.ttlseconds = 7200;

ALTER TABLE events configure zone using gc.ttlseconds = 7200;
ALTER INDEX events@idx_keep configure zone using gc.ttlseconds = 7200;

# Use to adjust the wait before commit... piggy back commits
###  2ms gives best response time, but 4ms is same as default p99 with 1/2 the IOPS!!!
###
SET CLUSTER SETTING rocksdb.min_wal_sync_interval='4ms';

ALTER TABLE events 
SET (ttl = 'on', 
     ttl_expiration_expression = "if(not keep_record, (updated_at AT TIME ZONE 'utc' + INTERVAL '2h') AT TIME ZONE 'utc', NULL)",
     ttl_label_metrics = true,
     ttl_range_concurrency = 1);


ALTER table events SET (ttl_pause=true);
```

1rg2NgL_oq7D4FMfVDFU2g
