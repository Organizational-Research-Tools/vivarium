import pandas as pd
x=pd.read_csv('records.csv');
for s in ['H6M64FVH6V','3TS98N4J3A','T2SEB0BAET','CEYHT8P45J','EGTGJGD3PY']:
 y=x[x.prototype_id.str.contains(s,na=False)]
 print('\n',s,len(y)); print(y.groupby(['kind','test','measured_by']).value.agg(['count','mean']).to_string())