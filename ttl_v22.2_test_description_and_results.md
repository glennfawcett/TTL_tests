# CockroachDB TTL tests with v22.2

Cockroach introduced the Time-To-Live functionality in v22.1.0 as a preview release to allow customers to begin to experiment with this functionality.  The inital release allowed customers to use the `WITH` syntax to With the release of v22.2, the TTL functionaly gets a   This introductary Cockroach v22.2 introduces some fantastics improvements to the TTL 

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

ALTER TABLE events 
SET (ttl = 'on', 
     ttl_expiration_expression = "if(not keep_record, (updated_at AT TIME ZONE 'utc' + INTERVAL '2h') AT TIME ZONE 'utc', NULL)",
     ttl_label_metrics = true,
     ttl_range_concurrency = 1,
     ttl_delete_rate_limit=11000);

ALTER TABLE events 
SET (ttl = 'on', 
     ttl_expiration_expression = "if(not keep_record, (updated_at AT TIME ZONE 'utc' + INTERVAL '2h') AT TIME ZONE 'utc', NULL)",
     ttl_label_metrics = true,
     ttl_range_concurrency = 1,
     ttl_delete_rate_limit=11000);

ALTER TABLE events 
SET (ttl_delete_rate_limit=11000);

ALTER TABLE events
SET (ttl_delete_rate_limit=2500);



```

## TTL Tests

Ran build up for ~2days with basically 500GB of replication size.  Setting the keep to a 2hr window and limiting the delete rate to ~30K rows per second which is 3x the 10k rps insert rate.



```sql
  
-- Enabled at "2022-10-27 02:22:00.302889+00"
--

ALTER TABLE events 
SET (ttl = 'on', 
     ttl_expiration_expression = "if(not keep_record, (updated_at AT TIME ZONE 'utc' + INTERVAL '2h') AT TIME ZONE 'utc', NULL)",
     ttl_label_metrics = true,
     ttl_range_concurrency = 1,
     ttl_delete_rate_limit=3334);

ALTER TABLE events 
RESET (ttl_delete_rate_limit);

ALTER TABLE events SET (ttl_delete_rate_limit=5555);

ALTER TABLE events SET (ttl_delete_rate_limit=2000);

```