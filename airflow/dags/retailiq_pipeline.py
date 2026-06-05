"""
RetailIQ Pipeline DAG
=====================
Runs every 6 hours:
  1. s3_to_snowflake  — Bronze → Silver → Gold
  2. anomaly_detector — detect price anomalies
"""

from airflow import DAG
from airflow.operators.bash import BashOperator
from datetime import datetime, timedelta

default_args = {
    "owner":            "retailiq",
    "retries":          2,
    "retry_delay":      timedelta(minutes=5),
    "email_on_failure": False,
}

with DAG(
    dag_id="retailiq_pipeline",
    default_args=default_args,
    description="ETL: S3 → Snowflake + Anomaly Detection",
    schedule_interval="0 */6 * * *",   # every 6 hours
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["retailiq", "etl", "ml"],
) as dag:

    etl = BashOperator(
        task_id="s3_to_snowflake",
        bash_command="cd /opt/airflow/project/storage && python s3_to_snowflake.py",
    )

    anomaly = BashOperator(
        task_id="anomaly_detector",
        bash_command="cd /opt/airflow/project/ml && python anomaly_detector.py",
    )

    alert = BashOperator(
        task_id="alert_engine",
        bash_command="cd /opt/airflow/project/alerting && python alert_engine.py",
    )

    etl >> anomaly >> alert
