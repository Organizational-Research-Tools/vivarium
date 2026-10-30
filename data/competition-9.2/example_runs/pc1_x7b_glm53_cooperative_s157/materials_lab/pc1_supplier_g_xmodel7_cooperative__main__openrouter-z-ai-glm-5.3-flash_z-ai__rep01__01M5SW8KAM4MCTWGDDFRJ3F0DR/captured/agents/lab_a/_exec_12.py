import pandas as pd
df = pd.read_csv('records.csv')
q = df[df.prototype_id=='p_GM7DHPGB5W']
print(q[['record_id','test','measured_by','value']].to_string())