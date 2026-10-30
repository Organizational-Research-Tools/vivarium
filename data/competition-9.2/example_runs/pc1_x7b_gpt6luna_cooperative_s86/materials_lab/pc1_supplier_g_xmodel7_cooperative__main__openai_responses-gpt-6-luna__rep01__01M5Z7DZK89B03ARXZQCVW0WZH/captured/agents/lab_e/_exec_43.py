import pandas as pd
x=pd.read_csv('records.csv')
z=x[x.kind=='qualification'].groupby(['project','prototype_id','test']).value.mean().unstack()
for pr in ['QP-9259','QP-3617','QP-9980','QP-9219','QP-9273','QP-6879','QP-5174','QP-7092']:
 print('\n',pr)
 print(z.loc[pr].to_string() if pr in z.index.get_level_values(0) else '')