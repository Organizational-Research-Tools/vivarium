import pandas as pd
df = pd.read_csv('records.csv')
m = df.apply(lambda r: (r.get('conditioning_step')=='2JU') if isinstance(r.get('conditioning_step'),str) else False, axis=1)
sub = df[df.prototype_id.isin(['p_Y48JGKQMFK','p_5R1KRJFJ2F'])]
print(df[m][['prototype_id','test','kind','value','measured_by']].to_string())
print(sub[['prototype_id','test','kind','value','measured_by']].to_string())
