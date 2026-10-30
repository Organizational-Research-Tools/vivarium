import pandas as pd
df = pd.read_csv('records.csv')
m = df[(df.prototype_id=='p_CWRMK2CFRP') & (df.kind=='qualification')]
print(m[['record_id','test','specimen','value','measured_by','requester']].to_string())