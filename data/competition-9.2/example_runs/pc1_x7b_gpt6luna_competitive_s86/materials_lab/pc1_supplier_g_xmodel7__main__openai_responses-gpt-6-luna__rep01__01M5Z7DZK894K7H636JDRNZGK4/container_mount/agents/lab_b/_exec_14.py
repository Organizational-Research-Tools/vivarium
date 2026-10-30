import pandas as pd
p=pd.read_csv('records.csv')
q=p[(p.project=='QP-9219') & (p.kind=='exploratory')]
print(q.groupby(['prototype_id','test']).size().unstack(fill_value=0).to_string())
print('ids',q.prototype_id.drop_duplicates().tolist())