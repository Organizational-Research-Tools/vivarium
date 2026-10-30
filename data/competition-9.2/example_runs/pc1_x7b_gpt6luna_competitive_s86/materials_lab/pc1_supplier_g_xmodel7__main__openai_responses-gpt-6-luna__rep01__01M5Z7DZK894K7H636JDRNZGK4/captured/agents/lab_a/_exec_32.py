import pandas as pd
x=pd.read_csv('records.csv')
q=x[(x.project=='QP-6879') & (x.instrument=='heat')]
print(q.groupby(['prototype_id','kind','measured_by']).value.agg(['mean','count']).sort_values('mean',ascending=False).to_string())
