import pandas as pd
x=pd.read_csv('records.csv')
print(x.columns.tolist())
y=x[x.prototype_id.eq('p_NBE0SSEEDQ')]
print(y[['record_id','test','specimen','value','measured_by','record_type']].to_string(index=False) if len(y) else y)
