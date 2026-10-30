import pandas as pd
x=pd.read_csv('records.csv'); print(x.columns.tolist()); print(x[x['prototype_id'].isin(['p_XB3KE57P1J','p_6RBMX00RYK'])].groupby(['prototype_id','property'])['value'].mean())