import pandas as pd
x=pd.read_csv('records.csv')
for p in ['p_FF5QPYJ1FJ','p_FF5QPYJ1FM','p_FF5QPYJ1FP']:
 d=x[x.prototype_id==p]
 print('\n',p, d[['test','measured_by','value']].groupby(['test','measured_by']).agg(['count','mean']).round(5).to_string())