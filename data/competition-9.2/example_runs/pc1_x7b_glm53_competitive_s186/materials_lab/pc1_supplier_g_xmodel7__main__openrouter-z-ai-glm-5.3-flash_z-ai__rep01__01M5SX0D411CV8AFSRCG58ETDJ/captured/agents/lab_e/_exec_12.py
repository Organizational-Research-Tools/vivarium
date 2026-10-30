import pandas as pd
df = pd.read_csv('records.csv')
print(df[(df.prototype_id=='p_MBHXZ56X8R')&(df.instrument=='water')][['record_id','value','measured_by','requester']])
