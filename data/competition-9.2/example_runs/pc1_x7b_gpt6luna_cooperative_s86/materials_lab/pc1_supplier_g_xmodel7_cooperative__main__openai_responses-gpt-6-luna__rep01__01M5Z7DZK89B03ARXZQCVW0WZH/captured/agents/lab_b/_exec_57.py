import pandas as pd
x=pd.read_csv('records.csv')
print(x.columns.tolist())
print(x[x.prototype_id.isin(['p_CHA87BQ7J8','p_5B8A3997NZ'])].to_string(index=False))