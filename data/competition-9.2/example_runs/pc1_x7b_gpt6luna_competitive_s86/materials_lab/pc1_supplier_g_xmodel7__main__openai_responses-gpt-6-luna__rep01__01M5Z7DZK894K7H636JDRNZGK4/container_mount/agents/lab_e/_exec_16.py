import pandas as pd
x=pd.read_csv('records.csv')
print(x.columns.tolist())
print(x[x['prototype_id'].eq('p_4AQTFYGQBA')].drop_duplicates().to_string(index=False)[:4000])