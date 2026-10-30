import pandas as pd
x=pd.read_csv('records.csv')
q=x[(x.kind=='qualification')].groupby(['project','prototype_id','test']).value.mean().unstack('test')
# print candidates with at least 2 tests and all possible threshold candidates
for proj in sorted(x.project.dropna().unique()):
 s=q.loc[proj] if proj in q.index.get_level_values(0) else None
 if s is not None:
  print('\n',proj)
  if any(s.columns): print(s.dropna(how='all').to_string())