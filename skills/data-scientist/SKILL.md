---
name: data-scientist
description: Use when analyzing a dataset end to end: sourcing, cleaning, exploring, visualizing, A/B testing, forecasting, predicting, or clustering, following the standard data science workflow.
---

# Data Scientist

Work through a data problem the way a data scientist would: four stages, in order, each with checks before moving on. Skip stages the task doesn't need, but never skip preparation or exploration before modeling.

```
1. Collection & Storage -> 2. Preparation -> 3. Exploration & Visualization -> 4. Experimentation & Prediction
```

Start every task by stating the question being answered in one sentence. If the question is vague, sharpen it before touching data.

---

## 1. Collection & Storage

**Identify the source**
- Company data: web events (event name, timestamp, user ID), surveys (interviews, questionnaires, focus groups, NPS), customer records, logistics, financial transactions.
- Open data: public APIs (e.g. Wikipedia, finance, maps) and public records (international bodies, national statistics offices, government agencies; data.gov, data.europa.eu).
- Note the source, collection date, and any access limits for every dataset used.

**Classify the data type** (it drives storage, cleaning, and chart choice)
- Quantitative: measurable numbers (height, count, price).
- Qualitative: observed descriptions (color, origin, smell).
- Specialized: image, text, geospatial, network/graph.

**Choose storage and retrieval**

| Data shape | Store in | Query with |
|---|---|---|
| Tabular (rows/columns) | Relational database | SQL |
| Unstructured (email, text, media, web pages, social) | Document database | NoSQL |

- Location: on-premises cluster or a cloud provider (AWS, Azure, Google Cloud); use parallel/distributed storage when data outgrows one machine.

**Pipelines (ETL)** when data arrives from several sources or repeatedly:
- Extract from each source at its own frequency (streaming, minutes, weekly).
- Transform only to organize: join sources, conform to the schema, drop irrelevant fields. Do not do analytical cleaning here.
- Load into the store; schedule or event-trigger the run, and add monitoring/alerts for failures.

---

## 2. Preparation (cleaning)

Messy data causes errors, wrong results, and biased models. Apply these in order and log every change:

1. **Tidy**: one row per observation, one column per variable. Transpose or reshape if needed.
2. **Remove duplicates**: check exact and near-duplicate rows; decide what counts as a duplicate.
3. **Unique ID**: add a stable identifier per row if none exists.
4. **Homogeneity**: one unit per column (e.g. convert feet to meters), one coding per category (e.g. ISO country codes, not a mix of "Belgium"/"BE").
5. **Data types**: numbers stored as numbers, dates as datetimes, categories as categories.
6. **Missing values**: first find the reason (data entry, error, or genuinely missing), then choose:
   - impute (mean/median/model; say which),
   - drop (only if few and random),
   - keep (when missingness is meaningful).

Check after cleaning: row counts before/after, no unexpected nulls, value ranges plausible.

---

## 3. Exploration & Visualization (EDA)

Goal: understand the data, form hypotheses, assess characteristics.

1. **Know your columns**: list each field and its type.
2. **Preview**: look at the first rows.
3. **Describe**: count, unique, top, frequency for categoricals; mean, std, min, quartiles, max for numerics. Compare counts across columns to spot missing data.
4. **Visualize anyway**: summary statistics can be identical for very different data (Anscombe's quartet). Always plot distributions and relationships.
5. **Ask follow-up questions**: break totals down by a second variable (e.g. by year and by site/outcome).
6. **Outliers**: use histograms/box plots; investigate before removing; never delete silently.

**Chart rules**
- Use color only when it encodes something; no rainbow bars for a single variable; no decoration.
- Use colorblind-safe palettes (avoid relying on red vs green).
- Sans-serif, readable fonts.
- Always label: title, x axis, y axis, legend (with units).
- Bar charts start at zero; axes must not exaggerate differences.
- Bar heights must match values; pie slices must sum to 100%.

**Dashboards** (many charts for ongoing monitoring): put headline KPIs on top, add filters, highlight the current period, use tooltips for detail. Tools: Tableau, Power BI, Looker, or Python/R/JavaScript.

---

## 4. Experimentation & Prediction

### Experiments / A/B tests
1. Form a question (e.g. does title A or B get more clicks?).
2. Form a null hypothesis (A and B perform the same).
3. Pick one metric (e.g. click-through rate) and get its baseline.
4. Calculate the sample size **before** running. Rates far from 50% (e.g. clicks under 3%) and smaller detectable differences both need larger samples.
5. Randomly split users (e.g. 50/50), run until the sample size is reached; don't peek and stop early.
6. Test significance with the right test (t-test, z-test, chi-square, ANOVA).
7. Interpret: pick the winner, or if not significant, conclude any difference is smaller than the threshold that matters; running longer won't fix that. Design a new experiment if needed.

### Time series forecasting
- Data points ordered in time (prices, rates, sensor readings).
- Plot first; look for trend and seasonality.
- Fit a model on history (statistical or ML) and forecast forward.
- Always report prediction intervals (e.g. 80% and 95%), not just a point line.

### Supervised machine learning (labels + features)
- Label = what to predict (e.g. churn vs stay); features = data that might predict it.
- Split historical data into training and test sets; train on one, evaluate on the other only.
- Don't trust accuracy alone on imbalanced data: a model predicting "no churn" for everyone can score 97% while catching 0% of churners. Report per-class performance (confusion matrix, precision, recall).

### Clustering (unsupervised, features only)
- Use for customer segmentation, image segmentation, anomaly detection.
- Select features, scale them, try several cluster counts, compare, and use domain knowledge to choose the final number.
- Describe each cluster in plain language and say how it answers the question.

---

## Deliverable checklist
- The question, the data sources, and their limits.
- Cleaning steps taken and rows affected.
- Key charts (labeled, honest axes) with one-sentence takeaways.
- Method, assumptions, and uncertainty (significance, intervals, per-class metrics).
- A plain-language recommendation and the next question worth asking.
