import pandas as pd
df = pd.read_csv('records.csv')
q = df[(df.prototype_id=='p_GM7DHPGB5W')]
print(q.groupby(['test','measured_by']).value.agg(['size','mean']))