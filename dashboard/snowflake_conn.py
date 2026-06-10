import snowflake.connector
import pandas as pd
import streamlit as st

SF_USER      = "MMAGDYY1"
SF_PASSWORD  = "YOUR_SNOWFLAKE_PASSWORD"
SF_ACCOUNT   = "kpvhttk-ir63402"
SF_DATABASE  = "RETAILQ"
SF_WAREHOUSE = "COMPUTE_WH"

@st.cache_resource
def get_connection():
    return snowflake.connector.connect(
        user=SF_USER,
        password=SF_PASSWORD,
        account=SF_ACCOUNT,
        warehouse=SF_WAREHOUSE,
        database=SF_DATABASE,
    )

@st.cache_data(ttl=300)
def query(sql):
    conn = get_connection()
    return pd.read_sql(sql, conn)
