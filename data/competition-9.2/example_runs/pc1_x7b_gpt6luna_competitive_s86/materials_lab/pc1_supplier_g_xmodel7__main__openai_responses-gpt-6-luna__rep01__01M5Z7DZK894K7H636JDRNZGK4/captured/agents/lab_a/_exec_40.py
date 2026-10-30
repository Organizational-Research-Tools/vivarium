import pandas as pd
x=pd.read_csv('records.csv')
for pid in ['p_T2SEB0BAET','p_CEYHT8P45J','p_H6M64FVH6V']:
 print('\n',pid)
 print(x[(x.prototype_id==pid)&(x.test=='seal hold temperature')][['record_id','value','measured_by','specimen','kind']].to_string(index=False))