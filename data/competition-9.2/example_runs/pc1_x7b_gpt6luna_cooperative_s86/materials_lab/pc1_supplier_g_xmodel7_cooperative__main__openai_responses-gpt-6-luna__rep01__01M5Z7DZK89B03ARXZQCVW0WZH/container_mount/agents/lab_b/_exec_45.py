import pandas as pd
x=pd.read_csv('records.csv')
for p in ['p_EZR46XFBAD','p_EZR46XFBAH','p_ZDYAYEX9AC']:
 d=x[(x.prototype_id==p)&(x.instrument=='strength')]
 print(p, d[['record_id','value','measured_by','requester']].to_string(index=False), '\nmean',d.value.mean())