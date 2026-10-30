import pandas as pd
df = pd.read_csv('records.csv')
m = df[df.prototype_id=='p_7ZJ7YBKK9E']
print(m[['record_id','kind','test','specimen','value','measured_by','requester']].to_string())