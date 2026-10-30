import pandas as pd
df = pd.read_csv('records.csv')
# 27X prototypes on QP-1586/8864 with strength/water receipts >= thresholds
m = df[(df.kind=='qualification') & df.project.isin(['QP-8864','QP-1586'])]
g = m.groupby(['prototype_id','test']).value.agg(['size','mean'])
print(g.to_string())
print(df[df.binder_system=='27X'].prototype_id.unique())