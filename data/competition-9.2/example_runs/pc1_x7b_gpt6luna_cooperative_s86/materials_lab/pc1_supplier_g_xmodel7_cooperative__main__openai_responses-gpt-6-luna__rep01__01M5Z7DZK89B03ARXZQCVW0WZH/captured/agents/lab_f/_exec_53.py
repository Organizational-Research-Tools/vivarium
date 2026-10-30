import pandas as pd
x=pd.read_csv('records.csv'); d=x.groupby(['project','prototype_id','test']).value.mean().unstack();
for proj in ['QP-9259','QP-9980','QP-3617','QP-6879']:
 print('\n',proj)
 z=d.loc[proj] if proj in d.index.get_level_values(0) else None
 if z is not None:
  # only candidates at least 1 passing and 1 missing
  print(z.to_string())