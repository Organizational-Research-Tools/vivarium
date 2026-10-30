import pandas as pd
df=pd.read_csv('records.csv')
print(df.columns.tolist())
print(df['kind'].value_counts())
print(df[['record_id','kind','prototype_id','project_id','instrument','heat_mean' if 'heat_mean' in df.columns else 'value']].head() if True else '')
for c in df.columns: print(c)