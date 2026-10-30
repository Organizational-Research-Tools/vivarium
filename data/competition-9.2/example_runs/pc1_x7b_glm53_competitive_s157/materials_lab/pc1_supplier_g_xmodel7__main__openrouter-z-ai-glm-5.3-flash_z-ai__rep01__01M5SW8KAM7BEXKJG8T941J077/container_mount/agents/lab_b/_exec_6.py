import pandas as pd
df = pd.read_csv('records.csv')
qp5 = df[(df.project=='QP-5653')&(df.kind=='qualification')]
print(qp5.groupby(['prototype_id','test'])['value'].agg(['mean','count']).to_string())
# GQ screens
print(df[df.prototype_id.str.contains('QA38AA69GQ|9LQKQWB4')][['prototype_id','test','kind','value']].to_string())