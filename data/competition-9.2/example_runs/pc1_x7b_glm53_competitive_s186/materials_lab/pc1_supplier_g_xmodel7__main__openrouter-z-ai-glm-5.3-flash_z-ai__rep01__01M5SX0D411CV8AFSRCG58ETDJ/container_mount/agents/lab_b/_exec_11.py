import pandas as pd
df = pd.read_csv('records.csv')
for p in ['QP-8476','QP-4757','QP-3777','QP-4069']:
    s = df[(df.project==p)] if 'project' in df.columns else df[df.prototype_id.str.startswith('x')]
    print(p, s[['prototype_id','test','kind','value','measured_by']].groupby(['prototype_id','test'])['value'].agg(['count','mean']).to_string())
