import pandas as pd
x=pd.read_csv('records.csv'); q=x[(x.project=='QP-3617')].copy()
mods=x.columns[11:]
print('mods',list(mods))
# unique recipes by prototype/test, aggregate
for test in ['heat','strength','water']:
 d=q[q.test==test].groupby(['prototype_id']+list(mods),dropna=False).value.mean().reset_index()
 if not d.empty:
  print('\n',test,len(d)); print(d[['prototype_id']+list(mods)+['value']].to_string(index=False))
