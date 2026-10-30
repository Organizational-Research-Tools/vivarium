import pandas as pd
D=pd.read_csv('records.csv')
for p in ['p_2M4216T3YK','p_YP3K6XM4ZN','p_YZTF8EKPRY']:
 r=D[D.prototype_id==p].iloc[0]
 print(p, r['project'], [r[x] for x in D.columns[10:22]])