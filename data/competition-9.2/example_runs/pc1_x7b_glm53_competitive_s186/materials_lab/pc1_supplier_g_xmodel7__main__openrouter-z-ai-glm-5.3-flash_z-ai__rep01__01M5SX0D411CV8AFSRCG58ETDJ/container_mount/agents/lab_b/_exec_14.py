import pandas as pd
df = pd.read_csv('records.csv')
s = df[df.prototype_id=='p_S5C3TCY7F6']
print(s[['record_id','test','value','measured_by','kind']].to_string())
