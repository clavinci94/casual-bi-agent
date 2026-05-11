# Seed data

## Olist dataset

Source: <https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce>

Download `archive.zip`, unzip into this directory. You should get nine CSVs:

- `olist_customers_dataset.csv`
- `olist_geolocation_dataset.csv`
- `olist_order_items_dataset.csv`
- `olist_order_payments_dataset.csv`
- `olist_order_reviews_dataset.csv`
- `olist_orders_dataset.csv`
- `olist_products_dataset.csv`
- `olist_sellers_dataset.csv`
- `product_category_name_translation.csv`

These are gitignored — every dev fetches their own copy.

## Simulated extensions

After Olist is loaded, run `python data/seed/simulate.py` (TBD) to generate:

- **web_events** — clickstream synthesised from order timing
- **campaigns** — ~50 marketing campaigns, some with deliberately known causal effects (for ground-truth eval)
- **releases** — ~20 releases including the deliberate `mobile_checkout_v2` regression that drives the demo causal investigation
- **support_tickets** — ~5000 tickets linked to orders

Simulated data is reproducible from a seed (`SIMULATION_SEED=42` in `.env`).
