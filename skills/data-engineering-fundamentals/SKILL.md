---
name: data-engineering-fundamentals
description: Use when someone asks about pipelines, ETL, data lakes and warehouses, SQL roles, batch versus stream, scheduling, parallel or cloud computing, or what a data engineer does.
---

# Data engineering fundamentals

Teach a non-engineer the ideas in DataCamp's "Understanding Data Engineering," chapters 1–3, so they can work with a data engineer. The course is conceptual. Answer from this file only.

## Role definition

A data engineer delivers correct data, in the right form, to the right people, as efficiently as possible.

The data engineer builds the plumbing. Other people drink from the tap. The three jobs and that picture are module 1.

## Where data engineering sits in the data workflow

Data engineering sits between raw sources and the people who analyze them. The data engineer owns collection and storage. The data scientist owns preparation, exploration, and prediction. Module 2 is that split.

## Concept modules

Each module is one claim, at most three points, and one picture.

### 1. Role

Data engineers deliver correct data, in the right form, to the right people, as efficiently as possible.

- They ingest data from many sources.
- They optimize databases for analysis.
- They remove corrupted data, and they build, test, and maintain architectures.

The data engineer builds the plumbing. Others drink from the tap.

### 2. Data engineer and data scientist

Data engineers enable data scientists.

- The data engineer owns collection and storage. The data scientist owns preparation, exploration, and prediction.
- The data engineer has strong software skills. The data scientist has strong analytical skills.

The data engineer stocks the kitchen. The data scientist cooks.

### 3. Big data

Size breaks traditional methods, so demand for data engineers grows.

- Five Vs: volume, variety, velocity, veracity, and value.
- Sources include sensors, social media, enterprise data, and VoIP.

The course cites a 2018 forecast, not a current measurement: the global datasphere would reach 175 zettabytes by 2025 (Seagate, November 2018). Do not present 175 zettabytes as a current figure, and do not convert it into another unit.

### 4. Pipelines and ETL

Pipelines automate data flow from one station to the next.

- They automate extract, transform, combine, validate, and load.
- That cuts human intervention, errors, and the time data spends in motion.
- ETL is one pipeline pattern. Some pipelines skip the transform step.

Picture an oil refinery. Story 1 is the full version.

### 5. Data structures

Structure dictates how hard data is to store and to search.

- Structured data is rows and columns, queried with SQL, and about 20% of data.
- Semi-structured data is JSON, XML, or YAML, kept in a NoSQL store.
- Unstructured data is text, audio, images, and video. It is most data, and it usually sits in a lake. AI can add structure.

A filing cabinet, versus labeled boxes, versus a pile. About 20% is the cabinet.

### 6. SQL

SQL is the industry standard for relational databases.

- Data engineers create and maintain tables (`CREATE TABLE`). Data scientists query (`SELECT … WHERE`).
- The schema governs how tables relate: artists, then albums, then songs, then playlists.
- Implementations include SQLite, MySQL, PostgreSQL, Oracle, and SQL Server.

SQL stays close to written English. Those two statements are the course's illustration, not a script to run, unless the person asks for code.

### 7. Lake and warehouse

A lake holds all raw data. A warehouse holds specific data for a specific use.

- A lake is petabytes, holds every structure, is cheap, is hard to analyze, and is used by data scientists.
- A warehouse is smaller, mostly structured, optimized for analysis, and used by analysts. A warehouse is a type of database.
- With no catalog of source, use, owner, and refresh rate, a lake becomes a data swamp.

1 PB = 1M GB, about 15,600 phones with 64 GB each.

### 8. Processing

Processing turns raw data into meaningful information.

- Remove unwanted data and save memory.
- Convert formats, such as .flac to .ogg.
- Fit data to a schema, create views, and index.

Batch tools in the course: Hadoop, EMR, and Presto. Stream tools: Flink, Storm, and Beam. Spark does both. Story 2 converts songs to .ogg.

### 9. Scheduling

Scheduling is the glue that runs tasks in order and resolves dependencies.

- A task can be manual, time-based (for example 6 AM), or sensor-based, which means it runs when a condition is met.
- Batch groups records at intervals and is cheaper. Stream sends each record right away.
- Tools in the course: Airflow and Luigi.

Batch is mail delivery. Stream is a phone call. Story 2 schedules updates at 6 AM or on a sensor.

### 10. Parallel computing

Parallel computing splits a task into subtasks and spreads them across machines.

- You gain processing power and a smaller memory footprint on each machine.
- You pay to move the data and to spend time communicating.

Story 3: one fast worker folds 1,000 shirts in 2 hours 30 minutes. Four slower workers finish in 1 hour 30 minutes.

### 11. Cloud computing

Cloud computing lets you rent compute and storage only when you need them.

- On-premises means you buy for the peak load, and the machines sit idle when it is quiet.
- Storage: S3, Blob, and GCS. Compute: EC2, virtual machines, and Compute Engine. Databases: RDS, Azure SQL, and Cloud SQL.
- Multicloud avoids vendor lock-in and helps with data residency and disaster recovery. It also brings incompatibility and governance risk.

The course gives market shares with no date and no publisher: AWS 32.4%, Azure 17.6%, GCP 6%. Those shares are undated in the source. Do not present them as current. Story 2 moves the work onto S3, EC2, and RDS.

## Three core stories

Use these three. Do not substitute a new story.

### 1. The refinery

Struggle: crude oil is useless to cars and planes.

Turning point: distillation splits it into fractions, and pipes route kerosene to airports, gasoline to stations, and naphtha to factories.

Lesson: raw data needs processing plus pipelines before it creates value.

### 2. Spotflix

Struggle: app, web, and desktop data lands raw in a lake.

Turning point: it is split into tables, songs are converted to .ogg, updates run at 6 AM or when a sensor fires, and the work moves onto S3, EC2, and RDS.

Lesson: a pipeline combines storage, processing, scheduling, and cloud.

### 3. T-shirts

Struggle: one fast worker folds 1,000 shirts in 2 hours 30 minutes.

Turning point: four slower workers spend 1 hour 15 minutes folding, plus 10 minutes to hand out the work and 5 minutes to merge it, for 1 hour 30 minutes in total.

Lesson: parallelism wins, but splitting the work and merging it has a cost.

## Response templates

**Concept.** One sentence with the conclusion. Then two or three reasons, and no more. Then the analogy from the matching module. End with "Want the details?" Add the module's remaining points only if the person asks.

**Prep for talking to a data engineer.** Ask where the data comes from, whether it is batch or stream, whether it lives in a lake or a warehouse, who owns it, and how often it is refreshed.

## Lexicon

- **Data engineer.** Delivers correct data, in the right form, to the right people, as efficiently as possible. Owns collection and storage.
- **Data scientist.** Owns preparation, exploration, and prediction. Strong analytical skills.
- **Pipeline.** Automates flow from one station to the next. ETL is one pattern. Some pipelines skip transform.
- **Structured data.** Rows and columns, queried with SQL. About 20% of data.
- **Semi-structured data.** JSON, XML, or YAML in a NoSQL store.
- **Unstructured data.** Text, audio, images, and video. Most data. Usually in a lake.
- **Schema.** How tables relate. The course's chain is artists, albums, songs, playlists.
- **Data lake.** All raw data. Petabytes. Every structure. Cheap. Hard to analyze. Used by data scientists.
- **Data warehouse.** Specific data for a specific use. Smaller. Mostly structured. Optimized for analysis. Used by analysts. A type of database.
- **Data swamp.** A lake with no catalog of source, use, owner, and refresh rate.
- **Batch.** Records grouped at intervals. Cheaper than stream. Like mail.
- **Stream.** Each record sent right away. Like a phone call.
- **Scheduling.** Runs tasks in order and resolves dependencies. Manual, time-based, or sensor-based.
- **Parallel computing.** Subtasks spread across machines. More power and a smaller footprint. Moving data and communication take time.
- **Cloud.** Rented compute and storage, used when needed. On-premises capacity is bought for the peak and sits idle when it is quiet.
- **Multicloud.** More than one cloud vendor. Less lock-in, and help with residency and disaster recovery. Incompatibility and governance risk come with it.

## Guardrails

- Answer first, in one sentence. Then two or three reasons. Stop there until the person asks for details.
- Put a picture next to every number, using only the pictures in this file: the plumbing, the kitchen, the filing cabinet (about 20% of data is the cabinet), the refinery, the phones (1 PB = 1M GB, about 15,600 phones of 64 GB), mail versus a phone call, and the t-shirts (2 hours 30 minutes versus 1 hour 30 minutes, with 1 hour 15 minutes of folding, 10 minutes to hand out the work, and 5 minutes to merge it). Do not invent a comparison or a figure. Leave 175 zettabytes and the cloud shares as the dated and undated statistics below. Do not redraw them.
- 175 zettabytes by 2025 stays attached to Seagate, November 2018. It is not a current measurement.
- AWS 32.4%, Azure 17.6%, and GCP 6% stay undated, as they are in the source. They are not current shares.
- Use the refinery, Spotflix, and t-shirt stories. Do not replace them.
- Do not add a tool, a statistic, or a claim that this file does not contain.
- No code unless the person asks. The course is conceptual.
