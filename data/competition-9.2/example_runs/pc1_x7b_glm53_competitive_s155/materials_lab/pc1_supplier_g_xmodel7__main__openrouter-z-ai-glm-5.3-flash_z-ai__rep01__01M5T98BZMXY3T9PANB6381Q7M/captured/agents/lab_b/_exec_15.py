import pandas as pd
df = pd.read_csv('records.csv')
sub=df[(df.prototype_id=='p_FVCMZJEWBX')&(df.kind=='qualification')&(df.test=='seal hold temperature')]
print(sub[['record_id','value','measured_by']].to_string(), sub.value.mean())