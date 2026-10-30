import pandas as pd
try:
    df=pd.read_csv('records.csv')
    print(df.shape); print(df.head())
except Exception as e: print(e)