import pandas as pd
x=pd.read_csv('records.csv')
print(x.columns.tolist())
for p in ['p_1R7D8ZYK1G','p_1R7D8ZYK1J','p_1R7D8ZYK1M']:
 y=x[(x.prototype_id==p)&(x.instrument=='water')]
 print(p, y.record_id.tolist())
print(x[x.prototype_id.str.contains('XDN',na=False)].tail(10).to_string(index=False))