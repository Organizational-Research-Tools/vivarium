import pandas as pd
x=pd.read_csv('records.csv')
for id in ['p_9BPKMPQZJN','p_9BPKMPQZK5','p_2YHYS3GPHP','p_9BPKMPQZJV']:
 print('\n',id)
 y=x[(x.prototype_id==id)&(x.kind=='qualification')].groupby(['test','measured_by']).value.agg(['count','mean']).reset_index()
 print(y.to_string(index=False))
