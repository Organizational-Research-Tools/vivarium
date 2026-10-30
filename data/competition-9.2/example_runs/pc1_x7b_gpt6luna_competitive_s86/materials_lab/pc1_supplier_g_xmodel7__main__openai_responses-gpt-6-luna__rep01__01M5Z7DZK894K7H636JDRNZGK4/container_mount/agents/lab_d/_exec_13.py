import pandas as pd
x=pd.read_csv('records.csv'); y=x[x.prototype_id.eq('p_NBE0SSEEDQ')]
print(y[['record_id','kind','test','specimen','value','measured_by','requester']].to_string(index=False))