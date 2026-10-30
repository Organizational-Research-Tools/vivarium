import pandas as pd
x=pd.read_csv('records.csv');
for pid in ['p_P76NJVZT8K','p_P76NJVZT8Q']:
 d=x[x.prototype_id==pid]
 print(pid);print(d.groupby(['instrument','test']).value.agg(['count','mean']))