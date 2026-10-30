import pandas as pd
x=pd.read_csv('records.csv')
print(x.columns.tolist())
print(x[x.prototype_id.str.contains('NQX11|RP6VC|M1K5|YJCA9|R')].tail(35).to_string(index=False))