import pandas as pd
x=pd.read_csv('records.csv')
for pid in ['p_H6M64FVH6S','p_H6M64FVH7B','p_3TS98N4J3A','p_6HZQR01SM9','p_6HZQR01SMH']:
 d=x[x.prototype_id==pid]
 print('\n',pid, len(d)); print(d[['record_id','kind','test','specimen','value','measured_by']].to_string(index=False) if len(d) else '')
