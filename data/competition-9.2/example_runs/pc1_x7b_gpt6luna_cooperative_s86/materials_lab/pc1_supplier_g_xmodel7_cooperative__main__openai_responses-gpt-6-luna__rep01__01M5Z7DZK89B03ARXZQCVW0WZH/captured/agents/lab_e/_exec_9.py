import pandas as pd
x=pd.read_csv('records.csv')
print(x.columns.tolist())
print(x[x.prototype_id.isin(['p_NQYNDKZ3CG','p_NQYNDKZ3CJ'])].tail(4).to_string(index=False))