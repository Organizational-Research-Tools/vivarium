import pandas as pd
x=pd.read_csv('records.csv'); z=x[x.project.eq('QP-3617')].groupby(['prototype_id','test']).value.mean().unstack(); print(z.to_string())